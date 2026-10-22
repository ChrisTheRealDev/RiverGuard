from datetime import datetime, timezone
import pandas as pd
from tests.api_client import AuthenticatedClient as TestClient
import core
from api import app

def test_ingestion_and_missing_values(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'test.db')
    client=TestClient(app)
    payload={'device_id':'test','timestamp':datetime.now(timezone.utc).isoformat(),'ph':7.1}
    assert client.post('/api/v1/readings',json=payload).status_code==201
    row=core.history('esp32').iloc[0]
    assert row.ph==7.1 and pd.isna(row.turbidity) and pd.isna(row.anomaly)
    for update in [{'ph':15},{'ph':None},{'ph_unit':'volts'},{'timestamp':'2026-01-01T00:00:00'}]:
        assert client.post('/api/v1/readings',json=payload|update).status_code==422

def test_source_isolation_and_reset(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'test.db')
    model=core.train()
    for source in ['simulation','esp32']: core.save(core.sample('Normal river',0),source,'test',model=model)
    core.reset_simulation()
    assert core.history('simulation').empty
    assert len(core.history('esp32'))==1

def test_scenarios_and_evaluation():
    model=core.train()
    assert core.sample('Rising water level',40)['water_level']>core.sample('Rising water level',0)['water_level']
    assert core.assess(model,core.sample('Combined anomaly',20))[0]
    metrics, evidence=core.evaluate(model)
    assert len(evidence)==560
    assert metrics.accuracy.between(0,1).all()

def test_dashboard_smoke(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'dashboard.db')
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard.py',default_timeout=60).run()
    assert not app.exception
    assert len(app.metric)==4
    app.radio(key="source_choice").set_value('esp32').run()
    assert not app.exception
    assert any('Waiting' in item.value for item in app.info)
    app.radio(key="source_choice").set_value('simulation').run()
    app.selectbox(key='scenario_choice').select('Combined anomaly').run()
    assert not app.exception
    app.toggle(key='simulation_running').set_value(False).run()
    count=len(core.history('simulation'))
    app.run()
    assert len(core.history('simulation'))==count
    assert not app.exception
    app.number_input(key='flood_elevated').set_value(120.).run()
    assert app.number_input(key='flood_warning').value>=121
    app.number_input(key='flood_warning').set_value(130.).run()
    app.number_input(key='flood_rise').set_value(12.).run()
    assert app.number_input(key='flood_warning').value==130
    app.number_input(key='flood_elevated').set_value(80.).run()
    assert app.number_input(key='flood_warning').value==130
    next(b for b in app.button if b.label=='Reset & replay simulation').click().run()
    assert app.toggle(key='simulation_running').value
    assert not app.exception
    assert not app.exception
    app.button(key='rill_open').click().run()
    assert app.text_input(key='rill_draft_'+app.session_state['rill_active_simulation']).disabled is False
    assert app.button(key='rill_suggest_now').label=='Anything unusual?'


def test_rill_retry_preserves_conversation_and_refreshes_readings(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    from threading import Event
    from time import monotonic
    import rill_jobs
    monkeypatch.setenv('RILL_PROVIDER','gemini')
    monkeypatch.setattr(core,'DB',tmp_path/'retry.db')
    requests=[]
    class CompletedReply:
        def __init__(self,question,messages,frame,*thresholds,**kwargs):
            requests.append((question,list(messages),frame.copy()))
            self.question=question; self.messages=messages; self.stop=Event()
        def poll(self):
            return dict(done=True,error=None,text='Here is the updated answer.',retry_at=0)
    monkeypatch.setattr(rill_jobs,'ReplyJob',CompletedReply)
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard.py',default_timeout=60).run()
    chat=[{'role':'user','content':'Earlier question'},{'role':'assistant','content':'Earlier answer'},{'role':'user','content':'What changed?'}]
    app.session_state['rill_chat_simulation']=chat.copy()
    failure=dict(error='Cloud limit reached',question='What changed?',messages=chat[:-1],retry_at=monotonic()+60,partial='An interrupted answer')
    app.session_state['rill_failure_simulation']=failure
    app.session_state['rill_ui_open']=True
    app.run()
    assert app.button(key='rill_retry').disabled is True
    assert requests==[]
    monkeypatch.setenv('RILL_PROVIDER','ollama')
    app.run()
    assert app.button(key='rill_retry').disabled is False
    monkeypatch.setenv('RILL_PROVIDER','gemini')
    app.session_state['rill_failure_simulation']={**failure,'retry_at':0}
    app.run()
    assert app.button(key='rill_retry').disabled is False
    app.button(key='rill_retry').click().run()
    app.run()
    assert not app.exception
    assert requests[0][0]=='What changed?'
    assert requests[0][1]==chat[:-1]
    assert not requests[0][2].empty
    saved=app.session_state['rill_chat_simulation']
    assert saved[:3]==chat
    assert saved[-1]['content']=='Here is the updated answer.'
    assert sum(m['content']=='What changed?' for m in saved)==1
    assert 'rill_failure_simulation' not in app.session_state


def test_rill_composer_sends_once_and_keeps_question(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    from threading import Event
    import rill_jobs
    monkeypatch.setattr(core,'DB',tmp_path/'composer.db')
    calls=[]
    class Reply:
        def __init__(self,question,messages,frame,*args,**kwargs):
            calls.append(question);self.stop=Event()
        def poll(self): return dict(done=True,error=None,text='A clear reply.',retry_at=0)
    monkeypatch.setattr(rill_jobs,'ReplyJob',Reply)
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard.py',default_timeout=60).run()
    app.button(key='rill_open').click().run()
    draft='rill_draft_'+app.session_state['rill_active_simulation']
    app.text_input(key=draft).set_value('  What changed?  ')
    next(b for b in app.button if b.label=='Send').click().run()
    app.run()
    assert not app.exception
    assert calls==['What changed?']
    messages=app.session_state['rill_chat_simulation']
    assert [m['content'] for m in messages]==['What changed?','A clear reply.']

def test_sensor_retry_and_station_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'sensor.db')
    client=TestClient(app)
    data={'device_id':'station-01','sample_id':'boot-1:sample-2','timestamp':datetime.now(timezone.utc).isoformat(),'ph':7.2,'temperature':26.5}
    for _ in range(2): assert client.post('/api/v1/readings',json=data).status_code==201
    assert len(core.history('esp32'))==1
    data['device_id']='station-02'
    assert client.post('/api/v1/readings',json=data).status_code==201
    # A device credential may only inspect its own station. Aggregated station
    # discovery is now an authenticated browser operation.
    stations=client.get('/api/v1/stations',params={'device_id':'station-01'}).json()['stations']
    stations+=client.get('/api/v1/stations',params={'device_id':'station-02'}).json()['stations']
    assert len(stations)==2
    assert all(s['connected'] and s['fresh'] and not s['calibrated'] for s in stations)
    assert stations[0]['available_sensors']==['ph','temperature']
    assert client.get('/api/v1/station-setup').json()['units']['turbidity']=='NTU'
    assert client.post('/api/v1/readings',json=data|{'device_id':'  '}).status_code==422


def test_reading_visuals_explain_missing_and_extremes():
    from reading_visuals import reading_guide
    assert 'Waiting' in reading_guide('ph',float('nan'))
    assert 'Near neutral' in reading_guide('ph',7)
    assert 'Acidic side' in reading_guide('ph',4)
    assert 'not germs' in reading_guide('turbidity',900)
    assert 'left:100.0%' in reading_guide('turbidity',900)
    assert '30.0 cm below watch' in reading_guide('water_level',40,70,100)
    assert 'At warning' in reading_guide('water_level',100,70,100)

def test_hardware_raw_contract_and_missing_sensor_ui(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(core,'DB',tmp_path/'raw.db')
    client=TestClient(app)
    payload={'device_id':'raw-station','sample_id':'boot:1','mode':'hardware',
             'timestamp':datetime.now(timezone.utc).isoformat(),'temperature_c':27.4,
             'turbidity_raw':2150,'distance_cm':15.0,'ph':None,'water_level_cm':None,
             'raw':{'ph_adc':1800,'ph_mv':1495},'tds_ppm':None,
             'sensor_health':{'ph':'uncalibrated','turbidity':'uncalibrated','temperature':'ok','water_level':'out_of_range'}}
    assert client.post('/api/v1/readings',json=payload).status_code==201
    row=core.history('esp32').iloc[0]
    raw=json.loads(row.raw_json)
    assert raw['turbidity_adc']==2150 and raw['distance_cm']==15
    assert pd.isna(row.turbidity) and pd.isna(row.water_level) and pd.isna(row.ph)
    assert row.temperature==27.4 and not row.calibrated
    for bad in [{'raw':'oops'},{'tds_ppm':123},{'turbidity_raw':5000},{'mode':'simulation'},{'unknown':1}]:
        assert client.post('/api/v1/readings',json=payload|bad).status_code==422
    ui=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard.py',default_timeout=60).run()
    ui.radio(key='source_choice').set_value('esp32').run()
    assert not ui.exception
    assert ui.selectbox(key='hardware_station').value=='raw-station'
    assert len(ui.metric)==4
    from sensor_support import observation_report
    report=observation_report(core.history('esp32'))
    assert 'no calibrated readings' in report and 'Calibration needed' in report
    assert '27.40' in report


def test_sensor_health_heartbeat_and_stale_status(tmp_path,monkeypatch):
    from datetime import timedelta
    from river_status import overview
    monkeypatch.setattr(core,'DB',tmp_path/'health.db')
    payload={'device_id':'offline-probe','timestamp':(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat(),
             'sensor_health':{'ph':'disabled','turbidity':'disabled','temperature':'missing','water_level':'timeout'}}
    client=TestClient(app)
    assert client.post('/api/v1/readings',json=payload).status_code==201
    status=client.get('/api/v1/stations',params={'device_id':'offline-probe'}).json()['stations'][0]
    assert status['connected'] and not status['fresh'] and not status['available_sensors']
    assert status['sensor_health']['water_level']=='timeout'
    assert 'fresh' in overview(core.history('esp32'))['title']
