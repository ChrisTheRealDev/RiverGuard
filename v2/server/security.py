"""Installation-local browser sessions and pairing, separate from V1 cookies."""
import hmac
import ipaddress
import secrets
import time
from .store import Problem, digest, text

COOKIE = 'riverguard_v2_session'
SESSION_SECONDS = 30*86400


class Access:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def origin(request):
        expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
        if request.headers.get('origin') != expected:
            raise Problem(403, 'Open RiverGuard directly on this device before changing anything.')

    def session(self, request):
        token = request.cookies.get(COOKIE, '')
        if not token: return None
        with self.store.connect() as db:
            row = db.execute('SELECT id,csrf,expires FROM sessions WHERE hash=? AND expires>?', (digest(token), time.time())).fetchone()
        return dict(row) if row else None

    def require(self, request):
        session = self.session(request)
        if not session: raise Problem(401, 'Open the laptop launcher or pair this browser to continue.')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            self.origin(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
                raise Problem(403, 'Your session changed. Refresh RiverGuard before trying again.')
        return session

    @staticmethod
    def new_session(db):
        token = secrets.token_urlsafe(32)
        session = {'id': secrets.token_hex(12), 'csrf': secrets.token_urlsafe(24), 'expires': time.time()+SESSION_SECONDS}
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (session['id'], digest(token), session['csrf'], session['expires']))
        return token, session

    @staticmethod
    def cookie(response, token):
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite='strict', path='/')

    def bootstrap_token(self):
        token = secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute('DELETE FROM bootstrap WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO bootstrap VALUES (?,?)', (digest(token), time.time()+120))
        return token

    def bootstrap(self, request, token):
        self.origin(request)
        try: local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError): local = False
        if not local: raise Problem(403, 'The initial owner link must be opened on the laptop.')
        text(token, 16, 200)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT expires FROM bootstrap WHERE hash=?', (digest(token),)).fetchone()
            if not row or row[0] <= time.time(): raise Problem(401, 'This owner link expired. Restart the V2 launcher for a new link.')
            db.execute('DELETE FROM bootstrap WHERE hash=?', (digest(token),))
            return self.new_session(db)

    def pair_code(self):
        code = f'{secrets.randbelow(100000000):08d}'
        expires = time.time()+300
        with self.store.connect() as db:
            db.execute('DELETE FROM pairing')
            db.execute('INSERT INTO pairing VALUES (?,?)', (digest(code), expires))
        return {'code': code, 'expires_at': expires}

    def pair(self, request, code):
        self.origin(request)
        text(code, 1, 20)
        now = time.time(); address = request.client.host
        result = None; error = None
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE attempted<?', (now-300,))
            recent = db.execute('SELECT COUNT(*) FROM attempts WHERE address=? AND attempted>?', (address, now-60)).fetchone()[0]
            total = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
            if recent >= 5 or total >= 30:
                error = Problem(429, 'Too many pairing attempts. Wait a minute, then request a new code.')
            else:
                row = db.execute('SELECT expires FROM pairing WHERE hash=?', (digest(code.strip()),)).fetchone()
                if not row or row[0] <= now:
                    db.execute('INSERT INTO attempts VALUES (?,?)', (address, now))
                    error = Problem(401, 'That code is invalid, expired or already used.')
                else:
                    db.execute('DELETE FROM pairing WHERE hash=?', (digest(code.strip()),))
                    result = self.new_session(db)
        if error: raise error
        return result

    def revoke(self, session_id):
        text(session_id, 1, 100)
        with self.store.connect() as db: db.execute('DELETE FROM sessions WHERE id=?', (session_id,))
