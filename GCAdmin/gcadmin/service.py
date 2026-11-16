from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import socket
import threading
import time
from .core import Audit, Fault, Jobs, now
from .db import Database
from .processes import COMPONENTS, Processes


class Service:
    def __init__(self, config, data_dir, demo=False):
        self.config = config
        self.demo = demo
        self.audit = Audit(Path(data_dir) / ('demo-audit.sqlite' if demo else 'audit.sqlite'))
        self.jobs = Jobs()
        self.db = Database(config.get('sql', {}))
        self.processes = Processes(config)
        self.lock = threading.RLock()
        self.sample_accounts = [
            dict(id=84267, login='ikki2', email='ikki2@example.com', online=False,
                 lastLogin='2026-11-16T16:48:00', gp=1999000, cash=997050),
            dict(id=84268, login='teste03', email='teste@example.com', online=False,
                 lastLogin='2026-11-16T15:22:00', gp=2000000, cash=1000000),
            dict(id=84269, login='lire', email='lire@example.com', online=True,
                 lastLogin='2026-11-16T17:03:00', gp=12500, cash=0),
        ]
        self.sample_components = [dict(name=name, path=rel, port=port, description=desc,
                                       running=True, pids=[14000 + i * 117], cpu=round(0.4 + i * .31, 1),
                                       memory_mb=round(28 + i * 37.4, 1), exists=True)
                                  for i, (name, rel, port, desc) in enumerate(COMPONENTS)]
        self.demo_start = time.monotonic()

    def capabilities(self):
        return dict(monitoring=True, accounts=True, balances=True, create_account=True,
                    inventory_read=True, process_control=True, sql_backup=True,
                    gm=False, ban=False, kick=False, inventory_write=False,
                    warehouse=False, delete=False, broadcast=False, events=False,
                    gpu=False, filesystem_backup=False)

    def status(self):
        if self.demo:
            with self.lock:
                return dict(mode='demo', name='Grand Chase • Season 2', host='Demonstração local',
                            os='Windows Server 2022 · exemplo', time=now(),
                            uptime=int(time.monotonic() - self.demo_start),
                            metrics=dict(cpu=12.4, memory_used_gb=3.8, memory_total_gb=16,
                                         disk_used_gb=42.7, disk_total_gb=160),
                            database=dict(connected=True, accounts=len(self.sample_accounts),
                                          online=sum(bool(a['online']) for a in self.sample_accounts),
                                          online_source='Dados simulados; não representa a VPS.'),
                            components=copy.deepcopy(self.sample_components), capabilities=self.capabilities())
        import psutil
        mem = psutil.virtual_memory()
        disk = shutil.disk_usage(self.processes.root if self.processes.root.exists() else Path.cwd())
        try:
            database = dict(connected=True, **self.db.summary())
        except Fault as exc:
            database = dict(connected=False, accounts=None, online=None, error=str(exc))
        except Exception:
            database = dict(connected=False, accounts=None, online=None,
                            error='Falha na ligação SQL. Confere instância, permissões e driver no agente.')
        return dict(mode='real', name=self.config.get('name', 'Grand Chase Season 2'), host=socket.gethostname(),
                    os='Windows' if os.name == 'nt' else os.name, time=now(),
                    uptime=int(time.time() - psutil.boot_time()),
                    metrics=dict(cpu=psutil.cpu_percent(), memory_used_gb=round(mem.used / 2**30, 2),
                                 memory_total_gb=round(mem.total / 2**30, 2),
                                 disk_used_gb=round(disk.used / 2**30, 2), disk_total_gb=round(disk.total / 2**30, 2)),
                    database=database, components=self.processes.status(), capabilities=self.capabilities())

    def accounts(self, query):
        if not self.demo:
            return self.db.accounts(query)
        with self.lock:
            return [copy.deepcopy(a) for a in self.sample_accounts
                    if query.lower() in (str(a['id']) + a['login'] + a['email']).lower()]

    def detail(self, account_id):
        if not self.demo:
            return self.db.detail(account_id)
        with self.lock:
            a = next((a for a in self.sample_accounts if a['id'] == account_id), None)
            if not a:
                raise Fault('Conta não encontrada.', 404)
            return dict(login=a['login'], characters=[
                dict(type=i, name=a['login'], character=n, promotion=0, level=1,
                     xp=2020, wins=0, losses=0) for i, n in enumerate(['Elesis', 'Lire', 'Arme'])],
                inventory=[dict(uid=1021, item_id=74990, name='Teste do Ronan', quantity=1),
                           dict(uid=1022, item_id=59780, name='Mochila (+10)', quantity=1)],
                inventory_scope='Inventário de demonstração; consulta de itens de quantidade.')

    def mutation(self, action, target, details, fn):
        key = self.audit.begin(action, target, details)
        try:
            result = fn()
            self.audit.end(key, True, result)
            return result
        except Fault as exc:
            self.audit.end(key, False, str(exc))
            raise
        except Exception:
            self.audit.end(key, False, 'Falha interna. Operação requer verificação no agente.')
            raise

    def balance(self, account_id, data):
        gp, cash = data.get('gp'), data.get('cash')
        if type(gp) is not int or not 0 <= gp <= 2999999 or type(cash) is not int or not 0 <= cash <= 2147483647:
            raise Fault('Saldos inválidos: GP até 2.999.999; cash até 2.147.483.647.')
        def apply():
            if not self.demo:
                return self.db.balance(account_id, gp, cash)
            with self.lock:
                a = next((a for a in self.sample_accounts if a['id'] == account_id), None)
                if not a:
                    raise Fault('Conta não encontrada.', 404)
                if a['online']:
                    raise Fault('Sai da conta antes de alterar os saldos.', 409)
                before = dict(gp=a['gp'], cash=a['cash'])
                a.update(gp=gp, cash=cash)
                return dict(login=a['login'], before=before, after=dict(gp=gp, cash=cash))
        return self.mutation('Definir GP/cash', account_id, dict(gp=gp, cash=cash), apply)

    def create(self, data):
        login, password, email = data.get('login'), data.get('password'), data.get('email')
        def apply():
            if not self.demo:
                return self.db.create(login, password, email)
            import re
            if not isinstance(login, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,20}', login):
                raise Fault('Login: 3 a 20 letras, números ou sublinhado.')
            if not isinstance(password, str) or not re.fullmatch(r'[A-Za-z0-9]{8,20}', password):
                raise Fault('Senha de jogo: 8 a 20 letras/números.')
            if not isinstance(email, str) or '@' not in email or len(email) > 100:
                raise Fault('E-mail inválido.')
            with self.lock:
                if any(a['login'].lower() == login.lower() for a in self.sample_accounts):
                    raise Fault('Login já existe.', 409)
                key = max(a['id'] for a in self.sample_accounts) + 1
                self.sample_accounts.append(dict(id=key, login=login, email=email, online=False,
                                                gp=500, cash=0, lastLogin=now()))
                return dict(id=key, login=login)
        # Password never enters audit details.
        return self.mutation('Criar conta', login or '', dict(email=email), apply)

    def control(self, action, component):
        if action not in ('start', 'stop', 'restart'):
            raise Fault('Ação inválida.')
        if component not in ['all'] + [x[0] for x in COMPONENTS]:
            raise Fault('Componente desconhecido.', 404)
        def work(log):
            def apply():
                if action in ('stop', 'restart') and component in ('all', 'GameServer'):
                    if self.demo:
                        online = sum(bool(a['online']) for a in self.sample_accounts)
                    else:
                        online = self.db.summary()['online']
                    if online:
                        raise Fault(f'Existem {online} contas marcadas online. Encerramento bloqueado até saírem do jogo.', 409)
                if self.demo:
                    for c in self.sample_components:
                        if component in ('all', c['name']):
                            log(f"[DEMO] {action}: {c['name']}")
                            with self.lock:
                                c['running'] = action != 'stop'
                                c['pids'] = [14000] if c['running'] else []
                            time.sleep(.12)
                    return dict(message='Simulação concluída; nenhum processo real foi alterado.')
                return self.processes.action(action, component, log)
            return self.mutation(f'Processos: {action}', component, {}, apply)
        return self.jobs.start(f'{action}: {component}', work)

    def backup(self):
        def work(log):
            def apply():
                if self.demo:
                    log('[DEMO] Simulação de backup COPY_ONLY; nenhum arquivo .bak foi criado.')
                    return dict(files=[], note='Simulação. Não representa uma cópia recuperável.')
                return self.db.backup(self.config['backup_dir'], self.config.get('databases', ['gc', 'Stat', 'msg', 'Web']), log)
            return self.mutation('Backup SQL', 'databases', {}, apply)
        return self.jobs.start('Backup SQL', work)

    def logs(self, component):
        if component not in [x[0] for x in COMPONENTS]:
            raise Fault('Componente desconhecido.', 404)
        if self.demo:
            return [dict(file='DEMONSTRACAO.log', text=f'{now()} [DEMO] {component}: componente disponível.\n'
                         '[DEMO] Estes registos não vêm do servidor de jogo.\n'
                         '[DEMO] Conecta ao agente para consultar os ficheiros reais.')]
        return self.processes.logs(component)
