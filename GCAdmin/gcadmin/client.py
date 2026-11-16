from __future__ import annotations

import argparse
import base64
import ctypes
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, ProxyHandler, HTTPRedirectHandler
import webbrowser
from .agent import DEFAULT_CONFIG
from .core import Fault, atomic_json, state_dir, token
from .service import Service

WEB = Path(__file__).resolve().parent.parent / 'web'


def protect(value, decrypt=False):
    """Windows DPAPI, scoped to the current Windows user; never a plaintext fallback."""
    if os.name != 'nt':
        if decrypt:
            return ''
        raise Fault('Guardar senha só está disponível com proteção DPAPI no Windows. Usa conexão sem guardar.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode('utf-8')
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise Fault('Não foi possível proteger/ler a senha com DPAPI.')
    try:
        result = ctypes.string_at(output.data, output.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the bearer token to a redirected destination.


class ClientState:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.demo = Service(DEFAULT_CONFIG, directory, demo=True)
        self.session = token()
        self.lock = threading.RLock()
        self.profile_file = self.directory / 'profiles.json'
        self.connection = None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def profiles(self):
        with self.lock:
            if not self.profile_file.exists():
                return []
            return json.loads(self.profile_file.read_text(encoding='utf-8'))

    @staticmethod
    def validate_profile(data):
        host = str(data.get('host', '')).strip()
        parsed = urlparse('//' + host)
        if not host or parsed.hostname != host or parsed.username or '/' in host or ':' in host:
            raise Fault('Indica apenas IPv4 ou hostname, sem protocolo, porta ou caminho.')
        try:
            port = int(data.get('port', 18740))
        except (TypeError, ValueError):
            raise Fault('Porta inválida.')
        if not 1 <= port <= 65535:
            raise Fault('Porta inválida.')
        https = bool(data.get('https', False))
        if not https:
            try:
                address = ipaddress.ip_address(host)
                vpn = address.version == 4 and address in ipaddress.ip_network('100.64.0.0/10')
                if not (address.is_private or address.is_loopback or vpn) or address.is_unspecified:
                    raise ValueError()
            except ValueError:
                if host != 'localhost':
                    raise Fault('HTTP só é permitido para IP privado/VPN ou localhost. Para host público usa HTTPS.')
        return dict(name=str(data.get('name') or 'Grand Chase Season 2')[:80], host=host,
                    port=port, https=https)

    def save(self, data):
        profile = self.validate_profile(data)
        key = str(data.get('id') or token()[:12])
        with self.lock:
            rows = self.profiles()
            old = next((p for p in rows if p['id'] == key), {})
            profile['id'] = key
            if data.get('remember'):
                secret = data.get('password', '')
                if secret:
                    profile['secret'] = protect(secret)
                elif old.get('secret'):
                    profile['secret'] = old['secret']
            rows = [p for p in rows if p['id'] != key] + [profile]
            atomic_json(self.profile_file, rows)
        return {'id': key}

    def public_profiles(self):
        return [{k: v for k, v in p.items() if k != 'secret'} | {'remember': bool(p.get('secret'))}
                for p in self.profiles()]

    def remote(self, method, path, data=None, connection=None):
        with self.lock:
            conn = connection or self.connection
        if not conn:
            raise Fault('Conecta primeiro a um agente ou abre a demonstração.', 409)
        if conn.get('demo'):
            return self.demo_route(method, path, data or {})
        raw = json.dumps(data).encode('utf-8') if data is not None else None
        req = Request(conn['url'] + path, data=raw, method=method,
                      headers={'Authorization': 'Bearer ' + conn['password'], 'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=25) as response:
                result = json.loads(response.read(2_000_000))
        except HTTPError as exc:
            try:
                message = json.loads(exc.read(16000)).get('error', 'Pedido recusado.')
            except ValueError:
                message = f'Erro HTTP {exc.code} no agente.'
            raise Fault(message, exc.code)
        except (URLError, TimeoutError, OSError):
            raise Fault('Agente indisponível. Verifica IP, porta, VPN e firewall.', 503)
        if not result.get('ok'):
            raise Fault(result.get('error', 'Erro no agente.'), 502)
        return result['data']

    def demo_route(self, method, path, data):
        from urllib.parse import parse_qs
        parsed = urlparse(path)
        route = parsed.path
        service = self.demo
        if method == 'GET':
            if route == '/v1/status': return service.status()
            if route == '/v1/accounts': return service.accounts(parse_qs(parsed.query).get('q', [''])[0])
            if route.startswith('/v1/accounts/'): return service.detail(int(route.rsplit('/', 1)[1]))
            if route == '/v1/audit': return service.audit.rows()
            if route.startswith('/v1/jobs/'): return service.jobs.get(route.rsplit('/', 1)[1])
            if route == '/v1/logs': return service.logs(parse_qs(parsed.query).get('component', ['GameServer'])[0])
        if method == 'POST':
            if route == '/v1/accounts': return service.create(data)
            if route.endswith('/balance'): return service.balance(int(route.split('/')[-2]), data)
            if route in ('/v1/processes', '/v1/backups'):
                if data.get('confirm') != 'CONFIRMAR':
                    raise Fault('Confirma a operação.', 409)
                return service.backup() if route.endswith('backups') else service.control(data.get('action'), data.get('component', 'all'))
        raise Fault('Rota desconhecida.', 404)


class ClientServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, state):
        self.state = state
        super().__init__(address, ClientHandler)


class ClientHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, raw, mime='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def api(self, method):
        try:
            # Host + Origin + per-launch nonce prevent drive-by web pages using the local proxy.
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected:
                raise Fault('Host inválido.', 403)
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected:
                raise Fault('Origem inválida.', 403)
            if not hmac.compare_digest(self.headers.get('X-GCAdmin-Session', ''), self.server.state.session):
                raise Fault('Sessão local inválida. Reabre o aplicativo.', 403)
            data = {}
            if method == 'POST':
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise Fault('Content-Type inválido.', 415)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 16384:
                        raise Fault('Pedido demasiado grande ou vazio.', 413)
                    data = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError):
                    raise Fault('Pedido inválido.')
                if not isinstance(data, dict):
                    raise Fault('Pedido inválido.')
            state = self.server.state
            path = self.path.removeprefix('/api')
            if method == 'GET' and path == '/profiles':
                result = state.public_profiles()
            elif method == 'POST' and path == '/profiles':
                result = state.save(data)
            elif method == 'POST' and path == '/profiles/delete':
                with state.lock:
                    atomic_json(state.profile_file, [p for p in state.profiles() if p['id'] != data.get('id')])
                result = {}
            elif method == 'POST' and path == '/disconnect':
                with state.lock:
                    state.connection = None
                result = {}
            elif method == 'POST' and path == '/connect':
                if data.get('demo'):
                    conn = dict(demo=True)
                else:
                    profile = state.validate_profile(data)
                    password = data.get('password', '')
                    if not password and data.get('id'):
                        old = next((p for p in state.profiles() if p['id'] == data['id']), {})
                        if old.get('secret'):
                            password = protect(old['secret'], decrypt=True)
                    if not isinstance(password, str) or len(password) < 24:
                        raise Fault('A senha do agente deve ter pelo menos 24 caracteres.')
                    conn = dict(url=f'{"https" if profile["https"] else "http"}://{profile["host"]}:{profile["port"]}',
                                password=password)
                result = state.remote('GET', '/v1/status', connection=conn)
                with state.lock:
                    state.connection = conn
            else:
                result = state.remote(method, path, data if method == 'POST' else None)
            self.respond(200, json.dumps(dict(ok=True, data=result), ensure_ascii=False).encode('utf-8'))
        except Fault as exc:
            self.respond(exc.status, json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False).encode('utf-8'))
        except Exception:
            self.respond(500, json.dumps(dict(ok=False, error='Erro local. Reabre o aplicativo e verifica a configuração.')).encode())

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self.api('GET')
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            return self.respond(403, b'Forbidden', 'text/plain')
        path = self.path.split('?', 1)[0]
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in files:
            return self.respond(404, b'Not found', 'text/plain')
        name, mime = files[path]
        raw = (WEB / name).read_bytes()
        if name == 'index.html':
            raw = raw.replace(b'__SESSION__', self.server.state.session.encode())
        self.respond(200, raw, mime)

    def do_POST(self):
        if not self.path.startswith('/api/'):
            return self.respond(404, b'Not found', 'text/plain')
        self.api('POST')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    server = ClientServer(('127.0.0.1', args.port), ClientState(state_dir()))
    url = f'http://127.0.0.1:{server.server_port}/'
    print('GCAdmin local:', url)
    if args.no_open:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return
    if not args.browser:
        try:
            import webview
        except ImportError:
            print('pywebview indisponível; a abrir no navegador.')
        else:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            webview.create_window('GCAdmin • Grand Chase Season 2', url, width=1440, height=940,
                                  min_size=(1050, 720), background_color='#111318')
            try:
                webview.start()
            finally:
                server.shutdown()
                server.server_close()
            return
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
