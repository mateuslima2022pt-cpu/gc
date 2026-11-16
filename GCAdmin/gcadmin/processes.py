from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from .core import Fault

COMPONENTS = [
    ('CenterServer', 'CenterServer/CenterServer.exe', 9500, 'Coordenação e login'),
    ('CashServer', 'CashServer/CashServer.exe', 19560, 'Saldo e compras por cash'),
    ('UDPRelay', 'UDPRelay/RelayServer.exe', 9600, 'Relay UDP'),
    ('TCPRelay', 'TCPRelay/TCPRelay.exe', 9700, 'Relay TCP'),
    ('MsgRouter', 'MsgRouter/MsgRouter.exe', 9200, 'Encaminhamento de mensagens'),
    ('MsgServer', 'MsgServer/MsgServer.exe', 9300, 'Mensagens e amigos'),
    ('GameServer', 'GameServer/GameServer.exe', 9400, 'Mundo de jogo · Season 2'),
]
STOP_ORDER = ['GameServer', 'MsgServer', 'MsgRouter', 'CenterServer', 'TCPRelay', 'UDPRelay', 'CashServer']


class Processes:
    def __init__(self, cfg):
        self.root = Path(cfg['server_root']).resolve()
        self.cfg = cfg
        self.cpu_cache = {}

    def path(self, name):
        for key, rel, _, _ in COMPONENTS:
            if key == name:
                p = (self.root / rel).resolve()
                if not p.is_relative_to(self.root):
                    raise Fault('Caminho de componente inválido.')
                return p
        raise Fault('Componente desconhecido.', 404)

    def matches(self, name):
        import psutil
        wanted = os.path.normcase(str(self.path(name)))
        found = []
        for p in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if (p.info['name'] or '').lower() == self.path(name).name.lower() and not p.info['exe']:
                    raise Fault(f'Sem acesso ao caminho de {name}. Inicia o agente com permissões adequadas.', 409)
                if p.info['exe'] and os.path.normcase(str(Path(p.info['exe']).resolve())) == wanted:
                    found.append(p)
            except (psutil.Error, OSError):
                continue
        return found

    def status(self):
        import psutil
        result = []
        for name, rel, port, description in COMPONENTS:
            processes = self.matches(name)
            mem, cpu = 0, 0
            for p in processes:
                try:
                    key = (p.pid, p.create_time())
                    tracked = self.cpu_cache.setdefault(key, p)
                    mem += tracked.memory_info().rss
                    cpu += tracked.cpu_percent() / max(1, psutil.cpu_count() or 1)
                except psutil.Error:
                    pass
            result.append(dict(name=name, description=description, path=rel, port=port,
                               running=bool(processes), pids=[p.pid for p in processes],
                               cpu=round(cpu, 1), memory_mb=round(mem / 1048576, 1),
                               exists=self.path(name).is_file()))
        living = set()
        for p in psutil.process_iter():
            try:
                if p.is_running():
                    living.add((p.pid, p.create_time()))
            except psutil.Error:
                continue
        self.cpu_cache = {k: v for k, v in self.cpu_cache.items() if k in living}
        return result

    def start(self, name, log):
        if os.name != 'nt':
            raise Fault('Os executáveis do jogo exigem agente Windows.', 409)
        path = self.path(name)
        if self.matches(name):
            log(f'{name}: já está em execução.')
            return
        if not path.is_file():
            raise Fault(f'Executável não encontrado: {path}', 409)
        if name == 'GameServer':
            for dependency in ('CenterServer', 'CashServer'):
                if not self.matches(dependency):
                    raise Fault(f'Inicia {dependency} antes do GameServer.', 409)
        child = subprocess.Popen([str(path)], cwd=str(path.parent),
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
        time.sleep(self.cfg.get('start_delay_seconds', 3))
        if child.poll() is not None:
            raise Fault(f'{name} terminou durante o arranque; consulta os logs.', 409)
        log(f'{name}: iniciado (PID {child.pid}). Presença do processo não confirma estado Ready.')

    def stop(self, name, log):
        if os.name != 'nt':
            raise Fault('Encerramento de consola exige agente Windows.', 409)
        targets = self.matches(name)
        if not targets:
            log(f'{name}: já está parado.')
            return
        if name != 'GameServer' and self.matches('GameServer'):
            raise Fault('Encerra o GameServer antes dos componentes de suporte.', 409)
        import psutil
        for p in targets:
            log(f'{name}: a enviar Ctrl+Z e Enter ao PID {p.pid}.')
            # Child helper isolates AttachConsole/FreeConsole from the HTTP agent.
            command = ([sys.executable, '--console-stop', str(p.pid)] if getattr(sys, 'frozen', False)
                       else [sys.executable, '-m', 'gcadmin.console_stop', '--pid', str(p.pid)])
            result = subprocess.run(command,
                                    cwd=str(Path(__file__).resolve().parent.parent), timeout=15,
                                    capture_output=True)
            if result.returncode:
                raise Fault(f'Não foi possível enviar Ctrl+Z a {name}. Nenhum processo foi forçado.', 409)
            try:
                code = p.wait(timeout=self.cfg.get('stop_timeout_seconds', 120))
            except psutil.TimeoutExpired:
                raise Fault(f'{name} não terminou no prazo. Sequência interrompida, sem forçar.', 409)
            if code not in (None, 0):
                raise Fault(f'{name} terminou com código {code}. Sequência interrompida.', 409)
            log(f'{name}: terminou; código {code if code is not None else "indisponível"}.')

    def action(self, action, component, log):
        names = [x[0] for x in COMPONENTS] if component == 'all' else [component]
        for name in names:
            self.path(name)
        if action in ('stop', 'restart'):
            for name in STOP_ORDER:
                if name in names:
                    self.stop(name, log)
        if action in ('start', 'restart'):
            for name in names:
                self.start(name, log)
        return dict(message='Sequência concluída. SQL Server mantido em funcionamento.')

    def logs(self, component):
        folder = self.path(component).parent
        candidates = []
        if folder.is_dir():
            for p in folder.rglob('*'):
                if not p.is_file() or not p.resolve().is_relative_to(folder.resolve()):
                    continue
                if p.suffix.lower() in ('.log', '.txt') and p.stat().st_size:
                    candidates.append(p)
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for p in candidates[:4]:
            with p.open('rb') as stream:
                stream.seek(max(0, p.stat().st_size - 24000))
                raw = stream.read(24000)
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('cp1252', errors='replace')
            result.append(dict(file=str(p.relative_to(folder)), text='\n'.join(text.splitlines()[-120:])))
        return result
