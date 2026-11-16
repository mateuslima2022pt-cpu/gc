from __future__ import annotations

import datetime as dt
import json
import logging
import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path


class Fault(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def state_dir():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    path = base / 'GCAdmin'
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


class Audit:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions '
                       '(id TEXT PRIMARY KEY, time TEXT, action TEXT, target TEXT, '
                       'details TEXT, status TEXT, result TEXT)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def begin(self, action, target, details=None):
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?)',
                       (key, now(), action, str(target), json.dumps(details or {}, ensure_ascii=False),
                        'pending', ''))
        return key

    def end(self, key, success, result):
        with self.connect() as db:
            db.execute('UPDATE actions SET status=?, result=? WHERE id=?',
                       ('success' if success else 'error', str(result)[:2000], key))

    def rows(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM actions ORDER BY time DESC, rowid DESC LIMIT 150')]


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}

    def start(self, name, fn):
        with self.lock:
            if any(j['state'] == 'running' for j in self.jobs.values()):
                raise Fault('Outra operação está em curso. Aguarda a conclusão.', 409)
            key = uuid.uuid4().hex
            job = dict(id=key, name=name, state='running', started=now(), messages=[])
            if len(self.jobs) >= 100:
                self.jobs.pop(next(iter(self.jobs)))
            self.jobs[key] = job

        def log(message):
            with self.lock:
                job['messages'].append(str(message))

        def run():
            try:
                result = fn(log)
                with self.lock:
                    job.update(state='success', result=result, ended=now())
            except Exception as exc:
                if not isinstance(exc, Fault):
                    logging.exception('Falha interna numa operação assíncrona')
                with self.lock:
                    job.update(state='error', error=str(exc) if isinstance(exc, Fault)
                               else 'Falha interna no agente. Consulta os registos locais.', ended=now())
        threading.Thread(target=run, daemon=True).start()
        return self.get(key)

    def get(self, key):
        with self.lock:
            if key not in self.jobs:
                raise Fault('Operação não encontrada.', 404)
            return json.loads(json.dumps(self.jobs[key]))


def token():
    return secrets.token_urlsafe(36)
