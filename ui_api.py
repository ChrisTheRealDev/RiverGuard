"""Authenticated local web application. Sensor credentials have no UI privileges."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import core
import security
import station_setup

ROOT = Path(__file__).resolve().parent


async def authenticated_events(request, events):
    """Revocation ends an observer, never the durable generation itself."""
    try:
        async for event in events:
            if await request.is_disconnected() or security.find_session(request) is None:
                return
            yield event
    except Exception as exc:
        from chat_service import ChatError
        if isinstance(exc,ChatError) and exc.status==404:
            return
        raise


class Simulation:
    def __init__(self):
        self.state = dict(scenario='Normal river', running=True, step=0, scenarios=core.SCENARIOS)
        self.task = None
        self.lock = asyncio.Lock()

    async def start(self):
        with core.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS runtime_state (name TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            row = con.execute("SELECT payload FROM runtime_state WHERE name='simulation'").fetchone()
            if row:
                self.state.update(json.loads(row[0]))
        self.task = asyncio.create_task(self.run())

    def persist(self):
        with core.connect() as con:
            con.execute("INSERT INTO runtime_state VALUES ('simulation',?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload", (json.dumps(self.state),))

    async def run(self):
        from api import model
        while True:
            async with self.lock:
                if self.state['running']:
                    await asyncio.to_thread(core.save, core.sample(self.state['scenario'], self.state['step']), 'simulation', 'demo-station', model=model)
                    self.state['step'] += 1
                    self.persist()
            await asyncio.sleep(2)

    async def change(self, values):
        async with self.lock:
            if values.get('reset'):
                await asyncio.to_thread(core.reset_simulation)
                self.state['step'] = 0
            if values.get('scenario') is not None and values['scenario'] != self.state['scenario']:
                if values['scenario'] not in core.SCENARIOS:
                    raise HTTPException(422, 'Choose one of the listed demonstration scenarios.')
                self.state.update(scenario=values['scenario'], step=0)
            if values.get('running') is not None:
                self.state['running'] = values['running']
            self.persist()
        return self.state

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


class Bootstrap(BaseModel):
    token: str = Field(max_length=200)


class Pair(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class Register(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    rotate: bool = False


class SimulationChange(BaseModel):
    scenario: str | None = None
    running: bool | None = None
    reset: bool = False


class ThresholdChange(BaseModel):
    source: Literal['simulation','esp32']
    device_id: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    elevated: float = Field(gt=0, le=10000, allow_inf_nan=False)
    warning: float = Field(gt=0, le=10000, allow_inf_nan=False)
    rise_limit: float = Field(gt=0, le=1000, allow_inf_nan=False)


class SetupChange(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    settings: station_setup.Settings


class Capture(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    field: Literal['ph_mv','turbidity_mv','temperature_c','distance_cm']


class ConversationCreate(BaseModel):
    source: Literal['simulation','esp32']
    device_id: str | None = Field(default=None, max_length=80)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)


class ModelChange(BaseModel):
    model: str = Field(min_length=1,max_length=128)
    expected_revision: int = Field(ge=0)


class Message(BaseModel):
    question: str = Field(default='', max_length=1500)
    expected_revision: int = Field(ge=0)
    request_id: str = Field(min_length=1, max_length=100)
    device_id: str | None = Field(default=None, max_length=80)
    mode: Literal['question','retry','continue'] = 'question'
    job_id: str | None = Field(default=None, max_length=100)


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        from chat_service import ChatService
        security.initialize()
        app.state.chat = ChatService()
        await app.state.chat.startup()
        app.state.simulation = Simulation()
        await app.state.simulation.start()
        yield
        await app.state.simulation.stop()
        await app.state.chat.shutdown()

    app = FastAPI(title='RiverGuard local application', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(security.RequestBodyLimit)

    @app.middleware('http')
    async def host_guard(request, call_next):
        if (request.url.hostname or '').lower() not in security.allowed_hosts():
            return JSONResponse({'detail':'Use the laptop address shown by RiverGuard.'}, status_code=400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail':str(exc)}, status_code=409 if 'changed' in str(exc).lower() else 422)

    from chat_service import ChatError
    @app.exception_handler(ChatError)
    async def chat_error(request, exc):
        return JSONResponse({'detail':exc.detail}, status_code=exc.status)

    @app.get('/health')
    def health():
        return {'status':'ok','service':'riverguard-web','instance':os.environ.get('RIVERGUARD_INSTANCE','')}

    @app.get('/api/ui/session')
    def session_info(request: Request):
        import rill_ai
        session = security.find_session(request)
        if not session:
            return {'authenticated':False}
        endpoint = urlsplit('https://generativelanguage.googleapis.com' if rill_ai.provider()=='gemini' else rill_ai.HOST)
        host = endpoint.hostname or ''
        if ':' in host:
            host = '['+host+']'
        try:
            destination = f'{endpoint.scheme}://{host}'+(f':{endpoint.port}' if endpoint.port else '')
        except ValueError:
            destination = 'Invalid configured endpoint'
        provider = request.app.state.chat.ai_settings()['provider'] | {'kind':rill_ai.provider(),'host':destination}
        return {'authenticated':True,'csrf':session['csrf'],'session_id':session['id'], 'provider':provider,
                'lan_urls':security.lan_urls(int(os.environ.get('RIVERGUARD_WEB_PORT','8501')))}

    @app.post('/api/ui/bootstrap')
    def bootstrap(data: Bootstrap, request: Request, response: Response):
        token, session = security.bootstrap(request, data.token)
        security.set_cookie(response, token)
        return {'authenticated':True,'csrf':session['csrf']}

    @app.get('/api/ui/ai/models')
    async def ai_models(request: Request, session=Depends(security.require_session)):
        import rill_models
        import rill_ai
        try:
            models=await rill_models.catalog()
        except rill_ai.RillError as exc:
            raise HTTPException(503,str(exc)) from exc
        return request.app.state.chat.ai_settings() | models

    @app.put('/api/ui/ai/model')
    async def ai_model(values: ModelChange, request: Request, session=Depends(security.require_session)):
        import rill_models
        import rill_ai
        try:
            models=await rill_models.catalog()
        except rill_ai.RillError as exc:
            raise HTTPException(503,str(exc)) from exc
        if values.model not in {model['name'] for model in models['models']}:
            raise HTTPException(422,'Choose an installed local chat model. Install it with Ollama first, then refresh the list.')
        return request.app.state.chat.select_model(values.model,values.expected_revision) | models

    @app.post('/api/ui/ai/warmup')
    async def ai_warmup(request: Request, session=Depends(security.require_session)):
        import rill_models
        import rill_ai
        settings=request.app.state.chat.ai_settings()
        if settings['warming'] or settings['active_jobs']:
            return settings
        try:
            models=await rill_models.catalog()
        except rill_ai.RillError as exc:
            raise HTTPException(503,str(exc)) from exc
        current=request.app.state.chat.ai_settings()
        if current['selected_model']!=settings['selected_model']:
            raise HTTPException(409,'The AI model changed. Refresh the model list before preparing it.')
        if settings['selected_model'] not in {model['name'] for model in models['models']}:
            raise HTTPException(422,'The selected local model is not installed or cannot be used locally. Refresh models in Settings.')
        # An empty preload can discard a useful existing prompt/KV cache. Leave
        # an already-loaded model at the intended context size alone.
        if any(model['name']==settings['selected_model'] and model.get('context_length')==4096
               for model in models['loaded']):
            return current
        return request.app.state.chat.prepare_model(settings['selected_model'])

    @app.post('/api/ui/pair')
    def pair(data: Pair, request: Request, response: Response):
        token, session = security.pair(request, data.code)
        security.set_cookie(response, token)
        return {'authenticated':True,'csrf':session['csrf']}

    @app.post('/api/ui/pair-code')
    def code(session=Depends(security.require_session)):
        return security.pair_code()

    @app.get('/api/ui/sessions')
    def sessions(session=Depends(security.require_session)):
        return {'sessions':security.sessions(session['id'])}

    @app.delete('/api/ui/sessions/{session_id}')
    def revoke(session_id: str, response: Response, session=Depends(security.require_session)):
        security.revoke(session_id)
        if session_id==session['id']:
            response.delete_cookie(security.COOKIE, path='/')
        return {'revoked':True}

    @app.get('/api/ui/stations')
    def stations(request: Request, source: Literal['simulation','esp32']='simulation', session=Depends(security.require_session)):
        import data_service as data
        return {'stations':data.stations(source),'registered':security.registered_devices(), 'simulation':request.app.state.simulation.state}

    @app.post('/api/ui/register-station')
    def register(data: Register, session=Depends(security.require_session)):
        return security.register_device(data.device_id, data.rotate)

    @app.get('/api/ui/overview')
    def overview(request: Request, source: Literal['simulation','esp32']='simulation', device_id: str='demo-station',
                 field: Literal['ph','turbidity','temperature','water_level']='ph', window: Literal['10','60','all']='10', session=Depends(security.require_session)):
        import data_service as data
        return data.overview_data(source,device_id,field,window) | {'simulation':request.app.state.simulation.state}

    @app.get('/api/ui/history')
    def history(source: Literal['simulation','esp32']='simulation', device_id: str='demo-station', cursor: str | None=None,
                limit: int=50, since: str | None=None, until: str | None=None, session=Depends(security.require_session)):
        import data_service as data
        return data.reading_page(source,device_id,cursor, min(200,max(1,limit)),since=since,until=until)

    @app.get('/api/ui/alerts')
    def alerts(source: Literal['simulation','esp32']='simulation', device_id: str='demo-station', cursor: str | None=None,
               limit: int=50, grouped: bool=True, session=Depends(security.require_session)):
        import data_service as data
        return data.alert_page(source,device_id,cursor,min(200,max(1,limit)),grouped=grouped)

    @app.put('/api/ui/thresholds')
    def thresholds(values: ThresholdChange, session=Depends(security.require_session)):
        import data_service as data
        if values.warning <= values.elevated:
            raise HTTPException(422,'Warning level must be higher than the watch level.')
        return data.save_thresholds(values.source,values.device_id,values.model_dump(include={'elevated','warning','rise_limit'}),values.expected_revision)

    @app.post('/api/ui/simulation')
    async def simulation(values: SimulationChange, request: Request, session=Depends(security.require_session)):
        return await request.app.state.simulation.change(values.model_dump())

    @app.get('/api/ui/setup')
    def setup(device_id: str, session=Depends(security.require_session)):
        from sensor_support import decode
        row = station_setup.latest(device_id)
        record = station_setup.load(device_id)
        raw = decode(row.get('raw_json')) if row is not None else {}
        with core.connect() as con:
            receipt = con.execute("SELECT MAX(received_at) FROM readings WHERE source='esp32' AND device_id=?",(device_id,)).fetchone()[0]
        age = (time.time()-datetime.fromisoformat(receipt).timestamp()) if receipt else None
        measured = (time.time()-datetime.fromisoformat(row.timestamp).timestamp()) if row is not None else None
        latest = json.loads(row.to_json()) if row is not None else None
        return {'record':record,'latest':latest,'signals':raw,'connection':{
            'connected':age is not None and age<=30, 'age':age,'measured_age':measured,
            'acknowledged':bool(row is not None and row.get('setup_protocol')=='remote-v1' and row.get('config_revision')==record['revision'])}}

    @app.put('/api/ui/setup')
    def save_setup(values: SetupChange, session=Depends(security.require_session)):
        previous = station_setup.load(values.device_id)
        settings = values.settings.model_dump()
        # A changed calibration or enabled set always invalidates old verification.
        before = previous['settings'] | {'verified':False}
        if before != settings | {'verified':False}:
            settings['verified'] = False
        station_setup.store(values.device_id,settings,values.expected_revision)
        return station_setup.load(values.device_id)

    @app.post('/api/ui/capture')
    def capture(values: Capture, session=Depends(security.require_session)):
        return {'value':station_setup.capture(values.device_id,values.field)}

    @app.get('/api/ui/guides')
    def guides(session=Depends(security.require_session)):
        return {'tank_markdown':(ROOT/'hardware/Tank-Assembly.md').read_text(encoding='utf-8'),
                'wiring_image':'/guides/RiverGuard-Wiring.png','tank_image':'/guides/Tank-Layout.png',
                'pdf_url':'/guides/RiverGuard-Friend-Setup.pdf'}

    @app.get('/guides/{name}')
    def guide(name: str):
        allowed = {'RiverGuard-Wiring.png':ROOT/'hardware/RiverGuard-Wiring.png', 'Tank-Layout.png':ROOT/'hardware/Tank-Layout.png',
                   'RiverGuard-Friend-Setup.pdf':ROOT/'output/pdf/RiverGuard-Friend-Setup.pdf'}
        if name not in allowed:
            raise HTTPException(404)
        return FileResponse(allowed[name])

    @app.get('/api/ui/evaluation')
    def evaluation(session=Depends(security.require_session)):
        from api import model
        metrics, evidence = core.evaluate(model)
        return {'metrics':json.loads(metrics.to_json(orient='records')),'samples':len(evidence)}

    @app.get('/api/ui/exports')
    def export(kind: Literal['csv','report','evaluation']='csv', source: Literal['simulation','esp32']='simulation', device_id: str='demo-station', session=Depends(security.require_session)):
        import data_service as data
        from sensor_support import observation_report
        filename = {'csv':'riverguard-readings.csv','report':'riverguard-observation.txt','evaluation':'synthetic-evaluation.csv'}[kind]
        if kind=='csv':
            content = data.export_csv(source,device_id)
        elif kind=='report':
            settings = data.thresholds(source,device_id)
            content = iter([observation_report(core.history(source,device_id),settings['elevated'],settings['warning'],settings['rise_limit'])])
        else:
            from api import model
            content = iter([core.evaluate(model)[1].to_csv(index=False)])
        if isinstance(content, str):
            content = iter([content])
        return StreamingResponse(content,media_type='text/plain; charset=utf-8' if kind=='report' else 'text/csv; charset=utf-8',
                                 headers={'Content-Disposition':f'attachment; filename="{filename}"'})

    @app.get('/api/ui/conversations')
    def conversations(request: Request, source: Literal['simulation','esp32']='simulation', session=Depends(security.require_session)):
        return {'items':request.app.state.chat.list_conversations(source)}

    @app.post('/api/ui/conversations')
    def create_conversation(values: ConversationCreate, request: Request, session=Depends(security.require_session)):
        return request.app.state.chat.create_conversation(values.source,values.device_id)

    @app.get('/api/ui/conversations/{chat_id}')
    def conversation(chat_id: str, request: Request, session=Depends(security.require_session)):
        return request.app.state.chat.get_conversation(chat_id)

    @app.patch('/api/ui/conversations/{chat_id}')
    def rename(chat_id: str, values: Rename, request: Request, session=Depends(security.require_session)):
        return request.app.state.chat.rename(chat_id,values.title,values.expected_revision)

    @app.delete('/api/ui/conversations/{chat_id}')
    async def delete(chat_id: str, request: Request, expected_revision: int, session=Depends(security.require_session)):
        # The service atomically checks the confirmed revision, deletes, then
        # cancels its worker. Never refresh the revision after a concurrent edit.
        request.app.state.chat.delete(chat_id,expected_revision)
        return {'deleted':True}

    @app.post('/api/ui/conversations/{chat_id}/messages')
    async def message(chat_id: str, values: Message, request: Request, session=Depends(security.require_session)):
        import data_service as data
        chat = request.app.state.chat.get_conversation(chat_id)
        # Saved station chats keep their own measurement scope when the user
        # switches the dashboard station before reopening them. Older unbound
        # conversations can still use the dashboard's selected station.
        device = chat.get('device_id') or values.device_id or ('demo-station' if chat['source']=='simulation' else '')
        frame = core.history(chat['source'],device,limit=100)
        return await request.app.state.chat.submit(chat_id,values.question,values.expected_revision,values.request_id,frame,
                                                   data.thresholds(chat['source'],device),mode=values.mode,job_id=values.job_id)

    @app.get('/api/ui/jobs/{job_id}')
    def job(job_id: str, request: Request, session=Depends(security.require_session)):
        return request.app.state.chat.get_job(job_id)

    @app.post('/api/ui/jobs/{job_id}/cancel')
    async def cancel(job_id: str, request: Request, session=Depends(security.require_session)):
        return await request.app.state.chat.cancel(job_id)

    @app.get('/api/ui/jobs/{job_id}/events')
    async def events(job_id: str, request: Request, after: int=0, session=Depends(security.require_session)):
        request.app.state.chat.get_job(job_id)
        try:
            after = max(after,int(request.headers.get('last-event-id','0')))
        except ValueError:
            raise HTTPException(422,'Invalid stream cursor.')
        return StreamingResponse(authenticated_events(request,request.app.state.chat.events(job_id,after)),media_type='text/event-stream',
                                 headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})

    # Separate public mascot from built JS assets; every runtime asset is local.
    @app.get('/assets/rill-otter.png')
    def mascot():
        return FileResponse(ROOT/'assets/rill-otter.png')

    frontend = ROOT/'frontend/dist'
    app.mount('/assets',StaticFiles(directory=frontend/'assets',check_dir=False),name='frontend-assets')

    @app.get('/{path:path}')
    def index(path: str):
        if path.startswith(('api/','guides/','assets/')):
            raise HTTPException(404)
        file = frontend/'index.html'
        if not file.exists():
            return JSONResponse({'detail':'Frontend has not been built. Run npm ci and npm run build in frontend.'},status_code=503)
        return FileResponse(file,headers={'Cache-Control':'no-cache'})

    return app


app = create_app()
