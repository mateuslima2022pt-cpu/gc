from __future__ import annotations

import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path
from .core import Fault

CHARACTERS = ['Elesis', 'Lire', 'Arme', 'Lass', 'Ryan', 'Ronan', 'Amy', 'Jin', 'Sieghart']


class Database:
    def __init__(self, cfg):
        self.cfg = cfg

    def connect(self, autocommit=False):
        try:
            import pyodbc
        except ImportError:
            raise Fault('Instala pyodbc e Microsoft ODBC Driver 18 no agente.', 503)
        # ODBC brace quoting prevents semicolons in credentials becoming connection options.
        def q(value):
            return '{' + str(value).replace('}', '}}') + '}'
        cfg = self.cfg
        cs = ('DRIVER=' + q(cfg.get('driver', 'ODBC Driver 18 for SQL Server')) +
              ';SERVER=' + q(cfg.get('server', 'localhost')) + ';DATABASE=gc;Encrypt=yes;' +
              'TrustServerCertificate=' + ('yes' if cfg.get('trust_certificate', True) else 'no') + ';')
        if cfg.get('windows_auth', True):
            cs += 'Trusted_Connection=yes;'
        else:
            password = os.environ.get('GCADMIN_SQL_PASSWORD')
            if not password:
                raise Fault('GCADMIN_SQL_PASSWORD não está definido no agente.', 503)
            cs += 'UID=' + q(cfg.get('user', 'gcadmin')) + ';PWD=' + q(password) + ';'
        return pyodbc.connect(cs, timeout=8, autocommit=autocommit)

    @contextmanager
    def session(self, autocommit=False):
        conn = self.connect(autocommit)
        try:
            yield conn
        except Exception:
            if not autocommit:
                conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def rows(cursor):
        cols = [c[0] for c in cursor.description]
        return [{k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in zip(cols, row)}
                for row in cursor.fetchall()]

    def summary(self):
        with self.session() as con:
            row = con.cursor().execute('SELECT COUNT_BIG(*), '
                                      'COALESCE(SUM(CASE WHEN Connecting=1 THEN 1 ELSE 0 END),0) '
                                      'FROM dbo.users').fetchone()
            return dict(accounts=int(row[0]), online=int(row[1]),
                        online_source='Indicador Connecting da base; pode conter sessões antigas.')

    def accounts(self, query=''):
        query = str(query)[:100]
        pattern = '%' + query.replace('~', '~~').replace('%', '~%').replace('_', '~_').replace('[', '~[') + '%'
        with self.session() as con:
            cur = con.cursor().execute(
                'SELECT TOP (100) u.LoginUID AS id, u.Login AS login, u.email, '
                'u.Connecting AS online, u.lastLogin, u.gamePoint AS gp, '
                'COALESCE(c.Cash,0) AS cash FROM dbo.users u '
                'LEFT JOIN dbo.CashUsers c ON c.Login=u.Login '
                "WHERE u.Login LIKE ? ESCAPE '~' OR u.email LIKE ? ESCAPE '~' "
                'OR CONVERT(varchar(20),u.LoginUID)=? ORDER BY u.LoginUID DESC',
                pattern, pattern, query)
            return self.rows(cur)

    @staticmethod
    def login_for(con, account_id, offline=False):
        hint = ' WITH (UPDLOCK,HOLDLOCK)' if offline else ''
        row = con.cursor().execute('SELECT Login, Connecting FROM dbo.users' + hint +
                                   ' WHERE LoginUID=?', account_id).fetchone()
        if not row:
            raise Fault('Conta não encontrada.', 404)
        if offline and row[1]:
            raise Fault('A conta está marcada online. Sai do jogo antes de alterar o saldo.', 409)
        return row[0]

    def detail(self, account_id):
        with self.session() as con:
            login = self.login_for(con, account_id)
            chars = self.rows(con.cursor().execute(
                'SELECT CharType AS type, CharName AS name, Promotion AS promotion, '
                'Level AS level, Exp AS xp, Win AS wins, Lose AS losses '
                'FROM dbo.Characters WHERE Login=? ORDER BY CharType', login))
            for c in chars:
                c['character'] = CHARACTERS[c['type']] if c['type'] < len(CHARACTERS) else str(c['type'])
            inventory = self.rows(con.cursor().execute(
                'SELECT TOP (150) d.DurationItemUID AS uid, d.GoodsID AS item_id, '
                'g.GoodsName AS name, d.Duration AS quantity FROM dbo.DurationItemObjectList d '
                'LEFT JOIN dbo.GoodsInfoList g ON g.GoodsID=d.GoodsID '
                'WHERE d.OwnerLogin=? ORDER BY d.DurationItemUID DESC', login))
            return dict(login=login, characters=chars, inventory=inventory,
                        inventory_scope='Itens de quantidade; limite de 150. Equipamentos/armazém ainda não integrados.')

    def balance(self, account_id, gp, cash):
        if type(gp) is not int or not 0 <= gp <= 2999999:
            raise Fault('GP deve estar entre 0 e 2.999.999.')
        if type(cash) is not int or not 0 <= cash <= 2147483647:
            raise Fault('Cash deve estar entre 0 e 2.147.483.647.')
        with self.session() as con:
            login = self.login_for(con, account_id, offline=True)
            cur = con.cursor()
            before = cur.execute('SELECT u.gamePoint, COALESCE(c.Cash,0) FROM dbo.users u '
                                 'LEFT JOIN dbo.CashUsers c WITH (UPDLOCK,HOLDLOCK) ON c.Login=u.Login '
                                 'WHERE u.LoginUID=?', account_id).fetchone()
            cur.execute('UPDATE dbo.users SET gamePoint=? WHERE LoginUID=?', gp, account_id)
            cur.execute('IF EXISTS (SELECT 1 FROM dbo.CashUsers WITH (UPDLOCK,HOLDLOCK) WHERE Login=?) '
                        'UPDATE dbo.CashUsers SET Cash=? WHERE Login=? '
                        'ELSE INSERT dbo.CashUsers(Login,Cash) VALUES (?,?)', login, cash, login, login, cash)
            con.commit()
            return dict(login=login, before=dict(gp=before[0], cash=before[1]), after=dict(gp=gp, cash=cash))

    def create(self, login, password, email):
        if not isinstance(login, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,20}', login):
            raise Fault('Login: 3 a 20 letras, números ou sublinhado.')
        if not isinstance(password, str) or not re.fullmatch(r'[A-Za-z0-9]{8,20}', password):
            raise Fault('Senha de jogo: 8 a 20 letras/números, para compatibilidade com o cliente antigo.')
        if not isinstance(email, str) or len(email) > 100 or '@' not in email:
            raise Fault('Indica um e-mail válido de até 100 caracteres.')
        digest = hashlib.md5(password.encode('ascii')).hexdigest()  # Legacy game protocol only.
        with self.session() as con:
            cur = con.cursor()
            if cur.execute('SELECT 1 FROM dbo.users WITH (UPDLOCK,HOLDLOCK) WHERE Login=?', login).fetchone():
                raise Fault('Este login já existe.', 409)
            cur.execute('INSERT dbo.users(Login,passwd,sex,firstLogin,lastConnect,lastLogin,playTime,'
                        'gamePoint,IPAddress,Connecting,email) VALUES (?,?,0,GETDATE(),GETDATE(),GETDATE(),'
                        "0,500,'0.0.0.0',0,?)", login, digest, email)
            row = cur.execute('SELECT LoginUID FROM dbo.users WHERE Login=?', login).fetchone()
            # Require the configured Season 2 trigger; do not silently invent character creation rules.
            chars = list(cur.execute('SELECT CharType,Level,Exp FROM dbo.Characters WHERE Login=? ORDER BY CharType', login))
            if [tuple(c) for c in chars] != [(0, 1, 2020), (1, 1, 2020), (2, 1, 2020)]:
                raise Fault('Criação cancelada: o trigger não produziu apenas Elesis, Lire e Arme com nível 1 e 2020 XP.', 409)
            con.commit()
            return dict(id=row[0], login=login)

    def backup(self, folder, databases, log):
        from .core import now
        allowed = {'gc', 'Stat', 'msg', 'Web'}
        if not databases or any(x not in allowed for x in databases):
            raise Fault('Bases permitidas: gc, Stat, msg e Web.')
        folder = Path(folder)
        if not folder.is_absolute():
            raise Fault('A pasta de backup deve ser absoluta.')
        folder.mkdir(parents=True, exist_ok=True)
        stamp = now().replace(':', '').replace('+', '_')
        files = []
        with self.session(autocommit=True) as con:
            con.timeout = 300
            for name in databases:
                path = str(folder / f'{name}_{stamp}.bak')
                log(f'Backup COPY_ONLY de {name}...')
                cur = con.cursor().execute(f'BACKUP DATABASE [{name}] TO DISK=? WITH COPY_ONLY, CHECKSUM', path)
                while cur.nextset():
                    pass
                cur = con.cursor().execute('RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM', path)
                while cur.nextset():
                    pass
                files.append(path)
                log(f'{name}: backup verificado.')
        return dict(files=files, note='Backups locais à VPS; copia-os também para outro destino.')
