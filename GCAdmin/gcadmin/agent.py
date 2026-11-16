from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import logging
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlparse
from .core import Fault, atomic_json, state_dir, token
from .service import Service

DEFAULT_CONFIG = dict(name='Grand Chase • Season 2', bind='127.0.0.1', port=18740,
                      server_root=r'C:\GrandChaseS2\02_Codigo_Servidor',
                      backup_dir=r'C:\GCAdmin-Backups', databases=['gc', 'Stat', 'msg', 'Web'],
                      start_delay_seconds=3, stop_timeout_seconds=120,
                      sql=dict(server='localhost', driver='ODBC Driver 18 for SQL Server',
                               windows_auth=True, trust_certificate=True))


class AgentServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service, secret):
        self.service = service
        self.secret = secret
        self.failures = {}
        self.auth_lock = threading.Lock()
        super().__init__(address, AgentHandler)


class AgentHandler(BaseHTTPRequestHandler):
    server_version = 'GCAdmin-Agent/0.1'

    def log_message(self, *args):
        pass  # Never log request bodies, tokens or account passwords.

    def json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def auth(self):
        ip = self.client_address[0]
        with self.server.auth_lock:
            clock = time.monotonic()
            if len(self.server.failures) > 1000:
                self.server.failures = {k: v for k, v in self.server.failures.items() if clock-v[0] < 60}
            start, count = self.server.failures.get(ip, (clock, 0))
            if clock-start > 60:
                start, count = clock, 0
            if count >= 10:
                raise Fault('Muitas tentativas. Aguarda um minuto.', 429)
            expected = 'Bearer ' + self.server.secret
            if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                self.server.failures[ip] = (start, count + 1)
                raise Fault('Senha de acesso ao agente inválida.', 401)
            self.server.failures.pop(ip, None)

    def handle_api(self, method):
        try:
            self.connection.settimeout(20)
            self.auth()
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/')
            query = parse_qs(parsed.query)
            data = {}
            if method == 'POST':
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise Fault('Content-Type deve ser application/json.', 415)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise Fault('Tamanho de pedido inválido.')
                if not 0 < size <= 16384:
                    raise Fault('Pedido vazio ou demasiado grande.', 413)
                try:
                    data = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError):
                    raise Fault('JSON inválido.')
                if not isinstance(data, dict):
                    raise Fault('O pedido deve ser um objeto JSON.')
            service = self.server.service
            if method == 'GET' and path == '/v1/status':
                result = service.status()
            elif method == 'GET' and path == '/v1/accounts':
                result = service.accounts(query.get('q', [''])[0])
            elif method == 'GET' and path.startswith('/v1/accounts/'):
                tail = path.removeprefix('/v1/accounts/')
                if not tail.isdigit():
                    raise Fault('ID de conta inválido.')
                result = service.detail(int(tail))
            elif method == 'GET' and path == '/v1/audit':
                result = service.audit.rows()
            elif method == 'GET' and path == '/v1/logs':
                result = service.logs(query.get('component', ['GameServer'])[0])
            elif method == 'GET' and path.startswith('/v1/jobs/'):
                result = service.jobs.get(path.rsplit('/', 1)[1])
            elif method == 'POST' and path == '/v1/accounts':
                result = service.create(data)
            elif method == 'POST' and path.startswith('/v1/accounts/') and path.endswith('/balance'):
                target = path.split('/')[-2]
                if not target.isdigit():
                    raise Fault('ID inválido.')
                result = service.balance(int(target), data)
            elif method == 'POST' and path == '/v1/processes':
                if data.get('confirm') != 'CONFIRMAR':
                    raise Fault('Confirma a operação.', 409)
                result = service.control(data.get('action'), data.get('component', 'all'))
            elif method == 'POST' and path == '/v1/backups':
                if data.get('confirm') != 'CONFIRMAR':
                    raise Fault('Confirma o backup.', 409)
                result = service.backup()
            else:
                raise Fault('Função ainda não implementada ou rota desconhecida.', 404)
            self.json(200, dict(ok=True, data=result))
        except Fault as exc:
            self.json(exc.status, dict(ok=False, error=str(exc)))
        except Exception:
            logging.exception('Falha interna no agente')
            self.json(500, dict(ok=False, error='Falha no agente. Consulta agent-errors.log no servidor.'))

    def do_GET(self):
        self.handle_api('GET')

    def do_POST(self):
        self.handle_api('POST')


def main():
    parser = argparse.ArgumentParser(description='GCAdmin Windows agent')
    parser.add_argument('--config', default=str(state_dir() / 'agent.json'))
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--generate-token', action='store_true')
    args = parser.parse_args()
    if args.generate_token:
        print(token())
        return
    path = Path(args.config)
    if args.init:
        if path.exists():
            raise SystemExit('Configuração já existe; não foi substituída.')
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, DEFAULT_CONFIG)
        print(f'Configuração criada em {path}. Define GCADMIN_AGENT_TOKEN antes de iniciar.')
        return
    if not path.exists():
        raise SystemExit('Executa primeiro: python -m gcadmin.agent --init')
    config = json.loads(path.read_text(encoding='utf-8'))
    secret = os.environ.get('GCADMIN_AGENT_TOKEN', '')
    if len(secret) < 24:
        raise SystemExit('Define GCADMIN_AGENT_TOKEN com pelo menos 24 caracteres; usa --generate-token.')
    bind = config.get('bind', '127.0.0.1')
    # HTTP is intended only for loopback or a private VPN, never a public listener.
    try:
        addr = ipaddress.ip_address(bind)
        vpn = addr.version == 4 and addr in ipaddress.ip_network('100.64.0.0/10')
        if not (addr.is_loopback or addr.is_private or vpn) or addr.is_unspecified:
            raise ValueError()
    except ValueError:
        raise SystemExit('bind deve ser loopback ou IP privado específico da VPN; não uses 0.0.0.0/IP público.')
    directory = path.parent
    logging.basicConfig(filename=directory / 'agent-errors.log', level=logging.ERROR)
    service = Service(config, directory)
    server = AgentServer((bind, int(config.get('port', 18740))), service, secret)
    print(f'GCAdmin Agent em {bind}:{server.server_port}. Mantém esta sessão Windows aberta.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Agente encerrado; os processos do jogo não foram terminados.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
