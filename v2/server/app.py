"""Same interface contract for the V2 laptop backend and Android native bridge."""
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import socket
import time
from urllib.parse import urlencode
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .store import Store, Problem, parse, keys, boolean, number, text
from .security import Access

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT/'v2'


class BodyLimit:
    def __init__(self, app, maximum=131072): self.app, self.maximum = app, maximum
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PATCH', 'PUT'):
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            data.extend(message.get('body', b''))
            if len(data) > self.maximum:
                return await JSONResponse({'detail': 'Request too large. Send one sample or settings change.'}, 413)(scope, receive, send)
            if not message.get('more_body'): break
        pending = True
        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


def addresses():
    result = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            address = item[4][0]
            if ':' not in address and not address.startswith('127.'): result.add(address)
    except OSError: pass
    return sorted(result)


def create_apps(database, web_port=8510, sensor_port=8010, extra_hosts=()):
    store = Store(database); access = Access(store)
    monitoring = {'error': None}
    async def monitor():
        while True:
            try:
                if store.get_state('receiver.enabled')['value'] is True:
                    for entry in store.stations():
                        await asyncio.to_thread(store.evaluate_alerts, entry['deviceId'])
                monitoring['error'] = None
            except Exception:
                monitoring['error'] = 'Monitoring could not read or store sensor data. Check the V2 service; do not clear its data.'
            await asyncio.sleep(3)
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(monitor())
        app.state.monitor_task = task
        try: yield
        finally:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    web, sensor = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan), FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @web.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    hostnames = ['localhost', '127.0.0.1', '[::1]', socket.gethostname(), *addresses(), *extra_hosts]
    for app in (web, sensor):
        app.state.store = store; app.state.access = access
        app.add_middleware(BodyLimit)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hostnames)
        @app.exception_handler(Problem)
        async def problem(_request, exc):
            return JSONResponse({'detail': exc.message}, exc.status, headers={'Retry-After': '60'} if exc.status == 429 else {})
        @app.get('/health')
        async def health():
            with store.connect() as db: db.execute('SELECT 1').fetchone()
            if monitoring['error']: return JSONResponse({'ok': False, 'product': 'RiverGuard V2', 'detail': monitoring['error']}, 503)
            return {'ok': True, 'product': 'RiverGuard V2', 'database': 'ready', 'time': time.time()}

    async def body(request, maximum=131072):
        data = await request.body()
        if len(data) > maximum: raise Problem(413, 'Request is too large.')
        return parse(data)

    def receiver():
        enabled = store.get_state('receiver.enabled')['value'] is True
        return {'running': enabled and monitoring['error'] is None, 'enabled': enabled, 'port': sensor_port, 'addresses': addresses(), **({'error': monitoring['error']} if monitoring['error'] else {})}

    @web.get('/api/v2/session')
    async def session(request: Request):
        result = access.session(request)
        return {'authenticated': bool(result), **({'csrf': result['csrf'], 'sessionId': result['id']} if result else {})}

    @web.post('/api/v2/bootstrap')
    async def bootstrap(request: Request):
        value = await body(request); keys(value, ('token',), ('token',))
        token, session = access.bootstrap(request, value['token'])
        response = JSONResponse({'authenticated': True, 'csrf': session['csrf']})
        access.cookie(response, token)
        return response

    @web.post('/api/v2/pair')
    async def pair(request: Request):
        value = await body(request); keys(value, ('code',), ('code',))
        token, session = access.pair(request, value['code'])
        response = JSONResponse({'authenticated': True, 'csrf': session['csrf']})
        access.cookie(response, token)
        return response

    @web.post('/api/v2/phone/{method}')
    async def operation(method: str, request: Request):
        session = access.require(request); value = await body(request)
        if method == 'getState':
            keys(value, ('key',), ('key',)); return store.get_state(value['key'])
        if method == 'setState':
            keys(value, ('key', 'value'), ('key', 'value')); return store.set_state(value['key'], value['value'])
        if method == 'registerStation':
            keys(value, ('deviceId', 'rotate'), ('deviceId',)); return store.register(value['deviceId'], value.get('rotate', False))
        if method == 'listStations':
            keys(value, ()); return {'items': store.stations(), 'receiver': receiver()}
        if method == 'getSettings':
            keys(value, ('deviceId',), ('deviceId',)); return store.settings(value['deviceId'])
        if method == 'saveSettings':
            keys(value, ('deviceId', 'expectedRevision', 'settings'), ('deviceId', 'expectedRevision', 'settings'))
            return store.save_settings(value['deviceId'], value['expectedRevision'], value['settings'])
        if method == 'listReadings':
            keys(value, ('source', 'deviceId', 'limit', 'cursor'), ('source', 'deviceId'))
            return store.readings(value['source'], value['deviceId'], value.get('limit', 120), value.get('cursor'))
        if method == 'appendDemo':
            keys(value, ('payload',), ('payload',)); return store.append_demo(value['payload'])
        if method == 'setReceiver':
            keys(value, ('enabled',), ('enabled',)); store.set_state('receiver.enabled', boolean(value['enabled'])); return receiver()
        if method == 'getMonitoring':
            keys(value, ()); return {**receiver(), 'notificationsAllowed': False, 'note': 'Laptop monitoring requires the V2 service to remain running. Native Android notifications are available in the APK.'}
        if method == 'exportData':
            keys(value, ('source', 'deviceId'), ('source', 'deviceId')); store.scope(value['source'], value['deviceId'])
            return {'url': '/api/v2/export?'+urlencode(value), 'name': 'RiverGuard-V2-'+value['deviceId']+'.csv', 'mime': 'text/csv'}
        if method == 'saveText':
            keys(value, ('name', 'mime', 'content'), ('name', 'mime', 'content'))
            text(value['name'], 1, 100); text(value['mime'], 1, 100); text(value['content'], 0, 65536)
            if any(c in value['name'] for c in '/\\\r\n'): raise Problem(422, 'Use a plain filename.')
            return value
        if method == 'saveGuide':
            keys(value, ()); return {'url': '/api/v2/guide', 'name': 'RiverGuard-Hardware-Guide.pdf', 'mime': 'application/pdf'}
        if method == 'createPairCode':
            keys(value, ()); return access.pair_code()
        if method == 'signOut':
            keys(value, ()); access.revoke(session['id']); response = JSONResponse({'signedOut': True}); response.delete_cookie('riverguard_v2_session'); return response
        raise Problem(404, 'This operation is not available.')

    @web.get('/api/v2/export')
    async def export(request: Request, source: str, deviceId: str):
        access.require(request)
        output = store.export(source, deviceId)
        return StreamingResponse(output, media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="RiverGuard-V2-{deviceId}.csv"', 'Cache-Control': 'no-store'})

    @web.get('/api/v2/guide')
    async def guide(request: Request):
        access.require(request)
        path = ROOT/'output/pdf/RiverGuard-Friend-Setup.pdf'
        if not path.is_file(): path = ROOT/'mobile/offline/public/guides/RiverGuard-Friend-Setup.pdf'
        if not path.is_file(): raise Problem(404, 'Hardware guide is not installed.')
        return FileResponse(path, media_type='application/pdf', filename='RiverGuard-Hardware-Guide.pdf')

    @sensor.get('/api/v1/device-config')
    async def device_config(request: Request, device_id: str):
        owner = store.authenticate(request.headers.get('authorization'))
        if owner != device_id: raise Problem(403, 'Station credential belongs to another station.')
        return store.configuration(owner)

    @sensor.post('/api/v1/readings')
    async def ingest(request: Request):
        owner = store.authenticate(request.headers.get('authorization'))
        if not receiver()['enabled']: raise Problem(503, 'The station receiver is disabled. Enable monitoring in RiverGuard V2.')
        return store.ingest(owner, await body(request, 32768))

    @web.get('/{asset_path:path}')
    async def assets(asset_path: str):
        if asset_path.startswith(('api/', 'health')): raise Problem(404, 'Not found.')
        base = (V2/'mobile/web').resolve(); path = (base/asset_path).resolve()
        if not path.is_relative_to(base): raise Problem(404, 'Not found.')
        if not path.is_file(): path = base/'index.html'
        if not path.is_file(): return JSONResponse({'detail': 'Build the V2 frontend first: cd v2/frontend, npm ci, npm run build.'}, 503)
        return FileResponse(path, headers={'Cache-Control': 'no-store' if path.name == 'index.html' else 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})

    return web, sensor
