import asyncio
import socket
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import core
import security
import api
from ui_api import create_app
from serve import check_ports
from ui_api import authenticated_events


@pytest.fixture
def web(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'web.db')
    with TestClient(create_app(),base_url='http://localhost',client=('127.0.0.1',4444)) as client:
        yield client


def owner(client):
    response = client.post('/api/ui/bootstrap',json={'token':security.bootstrap_token()},headers={'Origin':'http://localhost'})
    assert response.status_code==200,response.text
    client.headers.update({'Origin':'http://localhost','X-CSRF-Token':response.json()['csrf']})
    return response.json()


def test_bootstrap_pairing_csrf_and_revocation(web):
    assert web.get('/api/ui/session').json()=={'authenticated':False}
    assert web.get('/api/ui/stations').status_code==401
    owner(web)
    cookie = web.cookies.get(security.COOKIE)
    assert cookie
    assert web.post('/api/ui/pair-code',headers={'X-CSRF-Token':'bad'}).status_code==403
    assert web.post('/api/ui/pair-code',headers={'Origin':'http://evil.example'}).status_code==403
    code=web.post('/api/ui/pair-code').json()['code']
    # A separate browser shares the server, not its startup/shutdown lifecycle.
    phone=TestClient(web.app,base_url='http://localhost',client=('192.168.1.5',5555))
    result=phone.post('/api/ui/pair',json={'code':code},headers={'Origin':'http://localhost'})
    assert result.status_code==200,result.text
    assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']
    assert phone.post('/api/ui/pair',json={'code':code},headers={'Origin':'http://localhost'}).status_code==401
    current=phone.get('/api/ui/session').json()
    phone_id=current['session_id']
    phone.close()
    assert web.delete('/api/ui/sessions/'+phone_id).status_code==200
    with core.connect() as con:
        assert not con.execute('SELECT 1 FROM browser_sessions WHERE id=?',(phone_id,)).fetchone()


def test_new_and_existing_browser_sessions_have_readable_labels(web):
    web.headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36 Edg/131.0'
    owner(web)
    assert web.get('/api/ui/sessions').json()['sessions'][0]['label']=='Edge · Windows'
    code=web.post('/api/ui/pair-code').json()['code']
    phone=TestClient(web.app,base_url='http://localhost',client=('192.168.1.5',5555))
    try:
        response=phone.post('/api/ui/pair',json={'code':code},headers={'Origin':'http://localhost','User-Agent':'Mozilla/5.0 (iPhone) Version/18.0 Safari/605.1'})
        assert response.status_code==200
        assert {row['label'] for row in web.get('/api/ui/sessions').json()['sessions']}=={'Edge · Windows','Safari · iOS'}
        with core.connect() as con:
            security.new_session(con,'Laptop · Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36')
        assert 'Browser · Windows' in {row['label'] for row in web.get('/api/ui/sessions').json()['sessions']}
    finally:
        phone.close()


def test_pair_code_expiry_attempt_limit_and_remote_bootstrap(web):
    owner(web)
    code=web.post('/api/ui/pair-code').json()['code']
    with core.connect() as con:
        con.execute('UPDATE browser_pair_codes SET expires=?',(time.time()-1,))
    # Different remote client cannot exchange the loopback bootstrap token.
    remote=TestClient(web.app,base_url='http://localhost',client=('192.168.1.9',9000))
    assert remote.post('/api/ui/bootstrap',json={'token':security.bootstrap_token()},headers={'Origin':'http://localhost'}).status_code==403
    for _ in range(5):
        assert remote.post('/api/ui/pair',json={'code':code},headers={'Origin':'http://localhost'}).status_code==401
    assert remote.post('/api/ui/pair',json={'code':code},headers={'Origin':'http://localhost'}).status_code==429
    remote.close()


def test_sensor_credentials_scope_and_rotation(web):
    owner(web)
    result=web.post('/api/ui/register-station',json={'device_id':'river-01'})
    assert result.status_code==200
    key=result.json()['token']
    payload={'device_id':'river-01','timestamp':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'ph':7.1}
    sensor=TestClient(api.app,base_url='http://localhost')
    assert sensor.post('/api/v1/readings',json=payload).status_code==401
    headers={'Authorization':'Bearer '+key}
    assert sensor.post('/api/v1/readings',json=payload,headers=headers).status_code==201
    assert sensor.post('/api/v1/readings',json=payload|{'device_id':'other'},headers=headers).status_code==403
    assert sensor.get('/api/v1/device-config',params={'device_id':'other'},headers=headers).status_code==403
    assert sensor.put('/api/v1/stations/river-01/configuration',json={'expected_revision':0,'settings':{}},headers=headers).status_code==401
    assert web.post('/api/ui/register-station',json={'device_id':'river-01'}).status_code==409
    assert web.post('/api/ui/register-station',json={'device_id':'river-01','rotate':True}).status_code==200
    assert sensor.post('/api/v1/readings',json=payload,headers=headers).status_code==401
    with core.connect() as con:
        assert con.execute('SELECT token_hash FROM device_credentials').fetchone()[0]!=key
    sensor.close()


def test_clock_policy_and_host_guard(web):
    owner(web)
    key=web.post('/api/ui/register-station',json={'device_id':'clock'}) .json()['token']
    from datetime import datetime,timezone,timedelta
    sensor=TestClient(api.app)
    payload={'device_id':'clock','timestamp':(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat(),'ph':7.1}
    assert sensor.post('/api/v1/readings',json=payload,headers={'Authorization':'Bearer '+key}).status_code==422
    assert web.get('/api/ui/session',headers={'Host':'rebind.attacker.example'}).status_code==400
    sensor.close()


def test_json_body_size_is_bounded_before_parsing(web):
    oversized=b'"'+b'x'*(128*1024)+b'"'
    assert web.post('/api/ui/pair',content=oversized,headers={'Content-Type':'application/json'}).status_code==413
    sensor=TestClient(api.app)
    assert sensor.post('/api/v1/readings',content=oversized,headers={'Content-Type':'application/json'}).status_code==413
    sensor.close()


def test_streamed_body_limit_rejects_before_json_and_replays_small_body():
    async def exercise(chunks,maximum):
        received=[];sent=[]
        pending=iter([{'type':'http.request','body':chunk,'more_body':index<len(chunks)-1}
                      for index,chunk in enumerate(chunks)])
        async def receive(): return next(pending)
        async def send(message): sent.append(message)
        async def downstream(scope,receive,send):
            received.append(await receive())
        middleware=security.RequestBodyLimit(downstream,maximum)
        await middleware({'type':'http','method':'POST','headers':[]},receive,send)
        return received,sent
    received,sent=asyncio.run(exercise([b'123',b'456'],5))
    assert received==[] and sent[0]['status']==413
    received,sent=asyncio.run(exercise([b'12',b'34'],5))
    assert received==[{'type':'http.request','body':b'1234','more_body':False}]
    assert sent==[]


def test_legacy_owner_calibration_edit_invalidates_verification(web):
    import station_setup
    owner(web)
    settings={'enabled':dict.fromkeys(station_setup.FIELDS,True),
              'ph':[{'mv':1500,'value':7},{'mv':2100,'value':4}],
              'turbidity':[{'mv':1200,'value':100},{'mv':2400,'value':0}],
              'level':{'reference':180,'minimum':20,'maximum':600},
              'temperature_offset':0,'verified':True}
    station_setup.store('verified-station',settings,0)
    receiver=TestClient(api.app,base_url='http://localhost',cookies=web.cookies,headers=dict(web.headers))
    result=receiver.put('/api/v1/stations/verified-station/configuration',json={
        'settings':settings|{'temperature_offset':1},'expected_revision':1})
    assert result.status_code==200,result.text
    assert station_setup.load('verified-station')['settings']['verified'] is False
    receiver.close()


def test_data_setup_and_chat_api_flow(web):
    owner(web)
    # Pause the single backend simulation before assertions and exports.
    assert web.post('/api/ui/simulation',json={'running':False}).status_code==200
    snapshot=web.get('/api/ui/overview').json()
    assert 'status' in snapshot and 'chart' in snapshot and 'alerts' in snapshot
    assert web.get('/api/ui/history').status_code==200
    assert web.get('/api/ui/exports').status_code==200
    assert web.get('/api/ui/guides').json()['pdf_url'].endswith('.pdf')
    chat=web.post('/api/ui/conversations',json={'source':'simulation','device_id':'demo-station'}).json()
    renamed=web.patch('/api/ui/conversations/'+chat['id'],json={'title':'Saved river chat','expected_revision':chat['revision']})
    assert renamed.status_code==200
    assert web.delete('/api/ui/conversations/'+chat['id'],params={'expected_revision':chat['revision']}).status_code==409
    assert web.delete('/api/ui/conversations/'+chat['id'],params={'expected_revision':renamed.json()['revision']}).status_code==200


def test_setup_with_real_raw_sample_serializes_acknowledgement(web):
    owner(web)
    key=web.post('/api/ui/register-station',json={'device_id':'raw-station'}).json()['token']
    from datetime import datetime,timezone
    payload={'device_id':'raw-station','timestamp':datetime.now(timezone.utc).isoformat(),
             'setup_protocol':'remote-v1','config_revision':0,'raw':{'ph_mv':1600,'ph_adc':2100}}
    sensor=TestClient(api.app)
    response=sensor.post('/api/v1/readings',json=payload,headers={'Authorization':'Bearer '+key})
    assert response.status_code==201,response.text
    snapshot=web.get('/api/ui/setup',params={'device_id':'raw-station'})
    assert snapshot.status_code==200,snapshot.text
    assert snapshot.json()['connection']['acknowledged'] is True
    assert snapshot.json()['signals']['ph_mv']==1600
    sensor.close()


def test_occupied_port_reports_actual_conflict():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        listener.listen()
        with pytest.raises(RuntimeError,match='already in use'):
            check_ports([listener.getsockname()[1]])


def test_existing_stream_stops_after_session_revocation(monkeypatch):
    class Request:
        async def is_disconnected(self): return False
    current=[{'id':'paired'},None]
    monkeypatch.setattr(security,'find_session',lambda request:current.pop(0))
    async def events():
        yield 'first snapshot'
        yield 'must not leak after revocation'
    async def collect():
        return [event async for event in authenticated_events(Request(),events())]
    assert asyncio.run(collect())==['first snapshot']


def test_provider_destination_does_not_expose_url_credentials(web,monkeypatch):
    import rill_ai
    owner(web)
    monkeypatch.setattr(rill_ai,'HOST','http://private-user:private-pass@192.168.1.4:11434/path?key=private-key')
    result=web.get('/api/ui/session')
    assert result.json()['provider']['host']=='http://192.168.1.4:11434'
    assert not any(secret in result.text for secret in ['private-user','private-pass','private-key'])


@pytest.mark.parametrize('pinned,selected,expected',[('station-A','station-B','station-A'),(None,'station-B','station-B')])
def test_saved_chat_uses_pinned_station_before_dashboard_selection(web,monkeypatch,pinned,selected,expected):
    import pandas as pd
    import data_service
    owner(web)
    chat=web.post('/api/ui/conversations',json={'source':'esp32','device_id':pinned}).json()
    captured={}
    def history(source,device_id=None,**kwargs):
        captured['history_scope']=(source,device_id)
        return pd.DataFrame([{'device_id':device_id,'ph':7.1}])
    def thresholds(source,device_id):
        captured['threshold_scope']=(source,device_id)
        return {'elevated':70.,'warning':100.,'rise_limit':10.}
    async def submit(chat_id,question,revision,request_id,frame,settings,**kwargs):
        captured['frame_devices']=frame.device_id.tolist()
        return {'id':'mock-job','state':'queued'}
    monkeypatch.setattr(core,'history',history)
    monkeypatch.setattr(data_service,'thresholds',thresholds)
    monkeypatch.setattr(web.app.state.chat,'submit',submit)
    response=web.post('/api/ui/conversations/'+chat['id']+'/messages',json={
        'question':'How is this station?','expected_revision':chat['revision'],
        'request_id':'pinned-scope','device_id':selected})
    assert response.status_code==200,response.text
    assert captured['history_scope']==('esp32',expected)
    assert captured['threshold_scope']==('esp32',expected)
    assert captured['frame_devices']==[expected]
