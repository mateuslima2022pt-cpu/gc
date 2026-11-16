import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from gcadmin.agent import AgentServer, DEFAULT_CONFIG
from gcadmin.client import ClientServer, ClientState, protect
from gcadmin.core import Audit, Fault
from gcadmin.db import Database
from gcadmin.service import Service


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(DEFAULT_CONFIG, self.tmp.name, demo=True)

    def test_demo_is_explicit(self):
        s = self.service.status()
        self.assertEqual(s['mode'], 'demo')
        self.assertFalse(s['capabilities']['gm'])
        self.assertFalse(s['capabilities']['inventory_write'])

    def test_balance_sets_and_audits_before_after(self):
        result = self.service.balance(84267, dict(gp=10, cash=20))
        self.assertEqual(result['after'], dict(gp=10, cash=20))
        self.assertEqual(self.service.accounts('ikki2')[0]['cash'], 20)
        audit = self.service.audit.rows()[0]
        self.assertEqual(audit['status'], 'success')
        self.assertIn('before', audit['result'])

    def test_online_balance_blocked_and_audited(self):
        with self.assertRaises(Fault):
            self.service.balance(84269, dict(gp=10, cash=20))
        self.assertEqual(self.service.audit.rows()[0]['status'], 'error')

    def test_numeric_bounds_and_boolean_rejected(self):
        for gp, cash in [(3000000, 0), (-1, 0), (True, 10), (10, 2147483648), (10, 3.5)]:
            with self.subTest(gp=gp, cash=cash), self.assertRaises(Fault):
                self.service.balance(84267, dict(gp=gp, cash=cash))

    def test_create_only_three_starting_characters(self):
        result = self.service.create(dict(login='newtest', password='secret123', email='a@example.com'))
        d = self.service.detail(result['id'])
        self.assertEqual([(c['type'], c['level'], c['xp']) for c in d['characters']],
                         [(0, 1, 2020), (1, 1, 2020), (2, 1, 2020)])
        self.assertNotIn('secret123', json.dumps(self.service.audit.rows()))
        with self.assertRaises(Fault):
            self.service.create(dict(login='NEWTEST', password='secret123', email='a@example.com'))

    def test_unknown_process_rejected(self):
        with self.assertRaises(Fault):
            self.service.control('stop', '../../SQLServer')

    def test_stop_blocks_online_accounts(self):
        job = self.service.control('stop', 'all')
        for _ in range(100):
            result = self.service.jobs.get(job['id'])
            if result['state'] != 'running': break
            time.sleep(.01)
        self.assertEqual(result['state'], 'error')
        self.assertTrue(all(c['running'] for c in self.service.sample_components))

    def test_demo_stop_without_online_accounts(self):
        for a in self.service.sample_accounts: a['online'] = False
        job = self.service.control('stop', 'all')
        for _ in range(200):
            result = self.service.jobs.get(job['id'])
            if result['state'] != 'running': break
            time.sleep(.01)
        self.assertEqual(result['state'], 'success')
        self.assertFalse(any(c['running'] for c in self.service.sample_components))

    def test_inventory_is_readonly(self):
        inventory = self.service.detail(84267)['inventory']
        self.assertEqual(inventory[0]['item_id'], 74990)
        self.assertFalse(self.service.capabilities()['inventory_write'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.secret = 'test-token-that-is-long-enough-for-access'
        self.service = Service(DEFAULT_CONFIG, self.tmp.name, demo=True)
        self.server = AgentServer(('127.0.0.1', 0), self.service, self.secret)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, path, body=None, secret=None):
        headers = {'Content-Type': 'application/json'}
        if secret is not None: headers['Authorization'] = 'Bearer ' + secret
        request = Request(self.url + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=5) as r:
                return r.status, json.load(r)
        except HTTPError as r:
            return r.code, json.load(r)

    def test_agent_requires_auth_even_for_status(self):
        self.assertEqual(self.request('/v1/status')[0], 401)
        code, data = self.request('/v1/status', secret=self.secret)
        self.assertEqual(code, 200)
        self.assertEqual(data['data']['mode'], 'demo')

    def test_auth_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.request('/v1/status', secret='wrong')[0], 401)
        self.assertEqual(self.request('/v1/status', secret='wrong')[0], 429)

    def test_confirmation_required_for_process_control(self):
        self.assertEqual(self.request('/v1/processes', dict(action='stop', component='all'), self.secret)[0], 409)

    def test_unknown_capability_has_no_mutation_endpoint(self):
        self.assertEqual(self.request('/v1/accounts/84267/ban', {}, self.secret)[0], 404)

    def test_non_object_json_rejected(self):
        self.assertEqual(self.request('/v1/accounts', [], self.secret)[0], 400)

    def test_balance_via_api(self):
        code, data = self.request('/v1/accounts/84267/balance', dict(gp=500, cash=100), self.secret)
        self.assertEqual(code, 200)
        self.assertEqual(data['data']['after']['cash'], 100)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = ClientState(self.tmp.name)

    def test_public_http_is_rejected(self):
        for host in ['8.8.8.8', '0.0.0.0', 'example.com', '127.0.0.1/secret', 'x@127.0.0.1']:
            with self.subTest(host=host), self.assertRaises(Fault):
                self.state.validate_profile(dict(host=host, port=18740))

    def test_private_http_and_public_https_allowed(self):
        for data in [dict(host='100.100.100.100', https=False), dict(host='127.0.0.1'),
                     dict(host='localhost'), dict(host='admin.example.com', https=True)]:
            self.assertEqual(self.state.validate_profile(data)['host'], data['host'])

    def test_profiles_do_not_save_plaintext_password(self):
        data = dict(host='127.0.0.1', name='Local', password='not-saved', remember=False)
        self.state.save(data)
        self.assertNotIn('not-saved', self.state.profile_file.read_text())

    def test_authenticated_remote_gateway_uses_agent_contract(self):
        secret = 'remote-gateway-test-token-with-32-chars'
        agent = AgentServer(('127.0.0.1', 0), self.state.demo, secret)
        threading.Thread(target=agent.serve_forever, daemon=True).start()
        try:
            conn = dict(url=f'http://127.0.0.1:{agent.server_port}', password=secret)
            result = self.state.remote('GET', '/v1/accounts?q=ikki2', connection=conn)
            self.assertEqual(result[0]['login'], 'ikki2')
            result = self.state.remote('POST', '/v1/accounts/84267/balance',
                                       dict(gp=1200, cash=700), connection=conn)
            self.assertEqual(result['after'], dict(gp=1200, cash=700))
            conn['password'] = 'wrong'
            with self.assertRaises(Fault) as error:
                self.state.remote('GET', '/v1/status', connection=conn)
            self.assertEqual(error.exception.status, 401)
        finally:
            agent.shutdown()
            agent.server_close()

    def test_local_api_rejects_missing_nonce_and_cross_origin(self):
        server = ClientServer(('127.0.0.1', 0), self.state)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            with self.assertRaises(HTTPError) as error:
                urlopen(url + '/api/profiles')
            self.assertEqual(error.exception.code, 403)
            req = Request(url + '/api/profiles', headers={
                'X-GCAdmin-Session': self.state.session, 'Origin': 'https://attacker.example'})
            with self.assertRaises(HTTPError) as error:
                urlopen(req)
            self.assertEqual(error.exception.code, 403)
            with urlopen(url + '/') as page:
                html = page.read().decode()
                self.assertIn(self.state.session, html)
                self.assertNotIn('__SESSION__', html)
        finally:
            server.shutdown()
            server.server_close()


class DatabaseTests(unittest.TestCase):
    def test_sql_rolls_back_and_closes_on_fault(self):
        class Fake:
            rolled = closed = False
            def rollback(self): self.rolled = True
            def close(self): self.closed = True
        fake = Fake()
        db = Database({})
        with patch.object(db, 'connect', return_value=fake):
            with self.assertRaises(Fault):
                with db.session(): raise Fault('fail')
        self.assertTrue(fake.rolled)
        self.assertTrue(fake.closed)

    def test_missing_odbc_raises_without_leaking_credentials(self):
        db = Database({})
        # Boundary validation happens before an actual SQL connection.
        with self.assertRaises(Fault): db.balance(1, 5000000, 0)


if __name__ == '__main__':
    unittest.main()
