"""Private-network browser pairing and least-privilege sensor credentials."""
import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
import re
from fastapi import HTTPException, Request
import core

COOKIE = 'riverguard_session'
SESSION_SECONDS = 30 * 86400


class RequestBodyLimit:
    """Bound JSON parsing memory on both private-network HTTP services."""
    def __init__(self, app, maximum=128*1024):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        from starlette.responses import JSONResponse
        body = bytearray()
        headers = dict(scope.get('headers',[]))
        try:
            oversized = int(headers.get(b'content-length',b'0')) > self.maximum
        except ValueError:
            return await JSONResponse({'detail':'Invalid content length.'},400)(scope,receive,send)
        while not oversized:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body',b'')
            oversized = len(body)+len(chunk) > self.maximum
            if not oversized:
                body.extend(chunk)
            if not message.get('more_body',False):
                break
        if oversized:
            return await JSONResponse({'detail':'Request is too large. Send one reading or question at a time.'},413)(scope,receive,send)
        pending = True
        async def bounded_receive():
            nonlocal pending
            if pending:
                pending = False
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def tables(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS browser_sessions (
      id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, csrf TEXT NOT NULL,
      label TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS browser_bootstrap (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS browser_pair_codes (code_hash TEXT PRIMARY KEY, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS pairing_attempts (address TEXT, attempted REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS device_credentials (device_id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created REAL NOT NULL);
    ''')


def initialize():
    with core.connect() as con:
        tables(con)


def allowed_hosts():
    hosts = {'localhost', '127.0.0.1', '::1'}
    try:
        hosts.add(socket.gethostname().lower())
        hosts.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None))
    except OSError:
        pass
    return hosts


def lan_urls(port=8501):
    return [f'http://{host}:{port}' for host in sorted(allowed_hosts())
            if host not in {'localhost', '127.0.0.1', '::1'} and ':' not in host and host[0].isdigit()]


def loopback(request):
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def validate_origin(request):
    origin = request.headers.get('origin')
    expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
    if origin != expected:
        raise HTTPException(403, 'Open RiverGuard directly from this device before changing anything.')


def find_session(request):
    token = request.cookies.get(COOKIE, '')
    if not token:
        return None
    with core.connect() as con:
        row = con.execute('SELECT id,csrf,label,created,expires FROM browser_sessions WHERE token_hash=? AND expires>?',
                          (digest(token), time.time())).fetchone()
    if not row:
        return None
    return dict(zip(['id', 'csrf', 'label', 'created', 'expires'], row))


def require_session(request: Request):
    session = find_session(request)
    if not session:
        raise HTTPException(401, 'Pair this browser with your laptop to continue.')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        validate_origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
            raise HTTPException(403, 'Your session changed. Refresh RiverGuard and try again.')
    return session


def set_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite='strict', path='/')


def new_session(con, label):
    token = secrets.token_urlsafe(32)
    now = time.time()
    session = dict(id=secrets.token_hex(12), csrf=secrets.token_urlsafe(24), label=label[:100], created=now, expires=now+SESSION_SECONDS)
    con.execute('INSERT INTO browser_sessions VALUES (?,?,?,?,?,?)',
                (session['id'], digest(token), session['csrf'], session['label'], now, session['expires']))
    return token, session


def browser_label(user_agent):
    ua = (user_agent or '').lower()
    browser = next((name for markers, name in [
        (('edg/', 'edga/', 'edgios/'), 'Edge'), (('opr/', 'opios/'), 'Opera'),
        (('samsungbrowser/',), 'Samsung Internet'), (('firefox/', 'fxios/'), 'Firefox'),
        (('chrome/', 'crios/', 'chromium/'), 'Chrome'), (('safari/',), 'Safari')]
        if any(marker in ua for marker in markers)), 'Browser')
    system = next((name for markers, name in [
        (('iphone', 'ipad', 'ipod'), 'iOS'), (('android',), 'Android'),
        (('windows',), 'Windows'), (('cros',), 'ChromeOS'),
        (('macintosh', 'mac os x'), 'macOS'), (('linux',), 'Linux')]
        if any(marker in ua for marker in markers)), None)
    return browser + (' · ' + system if system else '')


def bootstrap_token():
    token = secrets.token_urlsafe(32)
    with core.connect() as con:
        con.execute('DELETE FROM browser_bootstrap WHERE expires<?', (time.time(),))
        con.execute('INSERT INTO browser_bootstrap VALUES (?,?)', (digest(token), time.time()+120))
    return token


def bootstrap(request, token):
    validate_origin(request)
    if not loopback(request):
        raise HTTPException(403, 'Laptop setup must be opened on the laptop itself.')
    with core.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT expires FROM browser_bootstrap WHERE token_hash=?', (digest(token),)).fetchone()
        if not row or row[0] <= time.time():
            raise HTTPException(401, 'This setup link expired. Open Start RiverGuard again for a new link.')
        con.execute('DELETE FROM browser_bootstrap WHERE token_hash=?', (digest(token),))
        return new_session(con, browser_label(request.headers.get('user-agent')))


def pair_code():
    code = f'{secrets.randbelow(100000000):08d}'
    expires = time.time()+300
    with core.connect() as con:
        con.execute('DELETE FROM browser_pair_codes')
        con.execute('INSERT INTO browser_pair_codes VALUES (?,?,0)', (digest(code), expires))
    return {'code': code, 'expires_at': expires}


def pair(request, code):
    validate_origin(request)
    now = time.time()
    address = request.client.host
    error = None
    result = None
    with core.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('DELETE FROM pairing_attempts WHERE attempted<?', (now-300,))
        recent = con.execute('SELECT COUNT(*) FROM pairing_attempts WHERE address=? AND attempted>?', (address, now-60)).fetchone()[0]
        global_recent = con.execute('SELECT COUNT(*) FROM pairing_attempts').fetchone()[0]
        if recent >= 5 or global_recent >= 30:
            error = (429, 'Too many pairing attempts. Wait a minute and request a new code.')
        else:
            row = con.execute('SELECT expires,used FROM browser_pair_codes WHERE code_hash=?', (digest(code.strip()),)).fetchone()
            if not row or row[0] <= now or row[1]:
                con.execute('INSERT INTO pairing_attempts VALUES (?,?)', (address, now))
                error = (401, 'That code is invalid, expired or already used. Get a new code from a paired device.')
            else:
                con.execute('UPDATE browser_pair_codes SET used=1 WHERE code_hash=?', (digest(code.strip()),))
                result = new_session(con, browser_label(request.headers.get('user-agent')))
    # Raise after committing failed-attempt counters.
    if error:
        raise HTTPException(*error, headers={'Retry-After':'60'} if error[0]==429 else None)
    return result


def sessions(current_id):
    with core.connect() as con:
        rows = con.execute('SELECT id,label,created FROM browser_sessions WHERE expires>? ORDER BY created DESC', (time.time(),)).fetchall()
    return [dict(id=r[0], label=browser_label(r[1]) if 'mozilla/' in r[1].lower() else r[1], created=r[2], current=r[0]==current_id) for r in rows]


def revoke(session_id):
    with core.connect() as con:
        con.execute('DELETE FROM browser_sessions WHERE id=?', (session_id,))


def register_device(device_id, rotate=False):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', device_id):
        raise HTTPException(422, 'Use 1–80 letters, digits, hyphens or underscores for the station ID.')
    token = secrets.token_urlsafe(32)
    with core.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT 1 FROM device_credentials WHERE device_id=?', (device_id,)).fetchone() and not rotate:
            raise HTTPException(409, 'This station is already registered. Keep its existing private firmware configuration.')
        con.execute('INSERT INTO device_credentials VALUES (?,?,?) ON CONFLICT(device_id) DO UPDATE SET token_hash=excluded.token_hash,created=excluded.created', (device_id, digest(token), time.time()))
    return {'device_id':device_id, 'token':token}


def registered_devices():
    with core.connect() as con:
        return [dict(device_id=r[0], created=r[1]) for r in con.execute('SELECT device_id,created FROM device_credentials ORDER BY device_id')]


def require_device(request: Request):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer '):
        raise HTTPException(401, 'Register this station and upload its private configuration first.', headers={'WWW-Authenticate':'Bearer'})
    with core.connect() as con:
        row = con.execute('SELECT device_id FROM device_credentials WHERE token_hash=?', (digest(header[7:]),)).fetchone()
    if not row:
        raise HTTPException(401, 'Station credential is invalid or revoked.', headers={'WWW-Authenticate':'Bearer'})
    return row[0]
