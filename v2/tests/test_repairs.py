"""Regression evidence for the October V2 audit repair, using isolated databases."""
import asyncio
import csv
import io
import json
import sqlite3
import threading
import time
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.store import Store, Problem, iso, hardware
from server.app import create_apps
from server import demo
from test_backend import settings, packet, login


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path/'repair.db')
    result.register('river-01')
    cfg = settings(); cfg['level']['reference'] = 200
    result.save_settings('river-01', 0, cfg)
    result.save_watch('esp32', 'river-01', 0, {'elevated':70,'warning':100,'rise_limit':10})
    return result


def reading(store, sample, height, when=None, fault=None):
    p = packet(sample=sample, revision=1)
    p['timestamp'] = iso(when if when is not None else time.time()*1000)
    p['raw']['distance_cm'] = None if height is None else 200-height
    if fault: p['sensor_health']['water_level'] = fault
    store.ingest('river-01', p)
    return p


def test_missing_or_faulted_readings_never_recover_water_warning(store):
    reading(store, 'high', 150); store.evaluate_alerts('river-01')
    for i in range(4):
        reading(store, 'missing-'+str(i), None, fault='timeout')
        assert not any(e['phase']=='recovered' and e['kind']=='water_warning' for e in store.evaluate_alerts('river-01'))
    assert store.get_state('alert-status:river-01')['value']['conditions']['water_warning']['active']


def test_short_excursion_and_restart_processing_are_durable(store):
    now = time.time()*1000
    reading(store, 'normal', 20, now-4000)
    reading(store, 'brief-high', 150, now-2000)
    reading(store, 'normal-again', 20, now)
    reopened = Store(store.path)
    events = reopened.evaluate_alerts('river-01')
    assert any(e['sample']=='brief-high' and e['kind']=='water_warning' for e in events)
    assert reopened.evaluate_alerts('river-01') == []
    warning = next(e for e in events if e['kind']=='water_warning')
    assert warning['watchRevision']==1 and warning['watchSettings']['warning']==100
    assert warning['measuredAt'] and warning['evaluatedAt'] and warning['calibrationRevision']==1


def test_delayed_packet_does_not_regress_current_or_count_as_recovery(store):
    now = time.time()*1000
    reading(store,'current-high',150,now);store.evaluate_alerts('river-01')
    for i in range(3): reading(store,'delayed-'+str(i),20,now-20000-i*1000)
    assert store.evaluate_alerts('river-01') == []
    state = store.get_state('alert-status:river-01')['value']
    assert state['sample']=='current-high' and state['conditions']['water_warning']['clearCount']==0


def test_export_captures_policy_and_ceilings_in_one_snapshot(store, monkeypatch):
    reading(store, 'before-export', 20)
    original = store._watch
    changed = False
    def concurrent_policy_write(db, source, device, *args):
        nonlocal changed
        if not changed:
            changed = True
            other = Store(store.path)
            other.save_watch(source, device, 1, {'elevated':80,'warning':110,'rise_limit':12})
            reading(other, 'during-export', 150)
        return original(db, source, device, *args)
    monkeypatch.setattr(store, '_watch', concurrent_policy_write)
    exported = list(csv.DictReader(io.StringIO(''.join(store.export('esp32','river-01')))))
    assert [row['sample_id'] for row in exported] == ['before-export']
    assert json.loads(exported[0]['export_watch_settings_json'])['revision'] == 1
    assert Store(store.path).get_watch('esp32','river-01')['revision'] == 2


def test_policy_change_is_not_river_recovery(store):
    reading(store,'high',150);store.evaluate_alerts('river-01')
    store.save_watch('esp32','river-01',1,{'elevated':155,'warning':170,'rise_limit':10})
    events=store.evaluate_alerts('river-01')
    assert any(e['phase']=='settings_changed' for e in events)
    assert not any(e['phase']=='recovered' for e in events)


def test_recheck_resolves_without_poisoning_future_recovery():
    from server.signals import apply
    def evaluation(sample, active=False, revision=1):
        return {'sample':sample,'fresh':True,'calibrationRevision':1,'watchRevision':revision,'evidence':{'water_warning':'active' if active else 'clear'},'signals':[{'kind':'water_warning','level':3,'title':'High water','detail':'Check water'}] if active else []}
    state,_=apply(None,evaluation('high',True),1000)
    phases=[]
    for i in range(3):state,events=apply(state,evaluation('new-policy-'+str(i),revision=2),2000+i);phases.extend(e['phase'] for e in events)
    assert 'rechecked' in phases and 'recovered' not in phases
    state,_=apply(state,evaluation('new-high',True,2),3000)
    phases=[]
    for i in range(3):state,events=apply(state,evaluation('clear-'+str(i),revision=2),4000+i);phases.extend(e['phase'] for e in events)
    assert 'recovered' in phases and 'rechecked' not in phases


def test_watch_cas_scope_and_geometry(store):
    with pytest.raises(Problem) as conflict: store.save_watch('esp32','river-01',0,{'elevated':10,'warning':20,'rise_limit':5})
    assert conflict.value.status==409
    cfg=settings();store.save_settings('river-01',1,cfg)
    assert not store.get_watch('esp32','river-01')['valid']
    assert store.get_watch('esp32','river-01')['settings']['warning']==100
    assert store.get_watch('simulation','demo-station')['valid']
    with pytest.raises(Problem):store.register('demo-station')
    cfg['verified']=True
    with pytest.raises(Problem):store.save_settings('river-01',2,cfg)


def test_null_geometry_stays_null_until_explicitly_saved(tmp_path):
    store=Store(tmp_path/'new.db');store.register('new')
    cfg=store.settings('new')['settings'];cfg['temperature_offset']=.25
    assert store.save_settings('new',0,cfg)['settings']['level'] is None
    assert not store.get_watch('esp32','new')['valid']


def test_hardware_csv_uses_captured_calibration_not_current(store):
    reading(store,'captured',20)
    cfg=settings();cfg['level']['reference']=100
    store.save_settings('river-01',1,cfg)
    row=next(csv.DictReader(io.StringIO(''.join(store.export('esp32','river-01')))))
    assert float(row['water_level'])==20 and float(row['temperature'])==27.4
    assert row['turbidity']=='' and json.loads(row['settings_json'])['level']['reference']==200


def test_public_state_cannot_access_internal_ledgers(store):
    for key in ['alert-status:river-01','runtime:demo','watch:river-01','receiver.enabled','session:123']:
        for write in [True,False]:
            with pytest.raises(Problem):store.public_state(key,{'conditions':'broken'},write)
    store.public_state('draft:esp32:river-01',{'revision':1,'settings':settings()},True)
    assert store.public_state('draft:esp32:river-01')['value']['revision']==1


def test_huge_numeric_input_is_validation_error():
    p=packet();p['raw']['ph_mv']=10**1000
    with pytest.raises(Problem) as exc:hardware(p)
    assert exc.value.status==422


def test_corrupt_ledger_quarantined_without_losing_samples(store):
    reading(store,'high',150);store.evaluate_alerts('river-01')
    with store.connect() as db:db.execute("UPDATE alert_progress SET ledger=?", ('{"conditions":"broken"}',))
    events=store.evaluate_alerts('river-01')
    assert any(e['kind']=='monitoring' for e in events)
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM quarantine').fetchone()[0]==1
    assert store.readings('esp32','river-01')['total']==1


def test_demo_shared_pause_cas_and_long_running_bounds(store):
    for scenario in demo.SCENARIOS:
        for step in [0,10,249,4978,2**31,10**12]:
            p=demo.sample(scenario,step,time.time()*1000)
            assert 0<=p['water_level']<=150 and 0<=p['turbidity']<=250
    state=demo.control(store,0,'Rising water level',True)
    demo.tick(store,time.time()*1000)
    other=Store(store.path)
    demo.control(other,state['revision'],'Cloudier water',False)
    count=store.readings('simulation','demo-station')['total']
    demo.tick(store,time.time()*1000+5000)
    assert store.readings('simulation','demo-station')['total']==count
    with pytest.raises(Problem):demo.control(store,0,'Normal river',True)


def test_migration_backup_preserves_old_events_and_sessions(tmp_path):
    path=tmp_path/'old.db';store=Store(path)
    with store.connect() as db:
        db.execute('PRAGMA user_version=1')
        db.execute("INSERT INTO state VALUES ('watch:demo-station',?)", ('{"elevated":70,"warning":100,"rise_limit":10}',))
        db.execute("INSERT INTO state VALUES ('draft:river-01',?)", ('{"revision":1,"settings":{}}',))
        db.execute("INSERT INTO alert_events(device_id,event_json) VALUES ('river-01',?)", ('{"title":"original evidence"}',))
    upgraded=Store(path)
    backups=list(tmp_path.glob('*.backup'));assert len(backups)==1
    with sqlite3.connect(backups[0]) as db:assert db.execute('PRAGMA user_version').fetchone()[0]==1
    assert upgraded.get_watch('simulation','demo-station')['needsReview']
    assert upgraded.get_watch('esp32','demo-station')['needsReview']
    assert upgraded.get_state('alerts:river-01')['value'][0]['title']=='original evidence'
    assert upgraded.get_state('draft:esp32:river-01')['value']['revision']==1
    Store(path);assert len(list(tmp_path.glob('*.backup')))==1


def test_cookie_names_isolate_installations_and_peer_revocation(tmp_path):
    a,_=create_apps(tmp_path/'a.db',extra_hosts=('testserver',))
    b,_=create_apps(tmp_path/'b.db',extra_hosts=('testserver',))
    assert a.state.access.cookie_name!=b.state.access.cookie_name
    with TestClient(a, client=('127.0.0.1', 51000)) as client:
        headers=login(client,a)
        with a.state.store.connect() as db:token,peer=a.state.access.new_session(db)
        result=client.post('/api/v2/phone/listSessions',json={},headers=headers)
        assert len(result.json()['items'])==2
        assert client.post('/api/v2/phone/revokeSession',json={'sessionId':peer['id']},headers=headers).status_code==200
        assert client.get('/api/v2/session').json()['authenticated']
        client.cookies.set(a.state.access.cookie_name,token)
        assert not client.get('/api/v2/session').json()['authenticated']


@pytest.mark.parametrize('condition', [
    {'active':True,'clearCount':0},
    {'active':True,'clearCount':0,'level':'3'},
    {'active':True,'clearCount':0,'level':True},
    {'active':True,'clearCount':-1,'level':3},
])
def test_invalid_ledger_conditions_are_quarantined(store, condition):
    reading(store,'high',150);store.evaluate_alerts('river-01')
    with store.connect() as db:db.execute('UPDATE alert_progress SET ledger=?',(json.dumps({'conditions':{'water_warning':condition}}),))
    store.evaluate_alerts('river-01')
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM quarantine').fetchone()[0]==1


def test_last_known_warning_and_event_export_survive_fault(store):
    reading(store,'high',150);store.evaluate_alerts('river-01')
    reading(store,'missing',None);store.evaluate_alerts('river-01')
    water=next(c for c in store.alert_state('esp32','river-01')['conditions'] if c['kind']=='water_warning')
    assert water['lastKnown'] and water['level']==3 and water['measuredAt']
    exported=list(csv.DictReader(io.StringIO(''.join(store.export('esp32','river-01')))))
    high=next(r for r in exported if r['sample_id']=='high')
    event=next(e for e in json.loads(high['alert_events_json']) if e['kind']=='water_warning')
    assert event['watchSettings']['warning']==100 and event['measuredAt']


def test_write_lock_does_not_block_async_http_loop(tmp_path):
    import httpx
    web,_=create_apps(tmp_path/'lock.db',extra_hosts=('testserver',))
    token=web.state.access.bootstrap_token()
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web,client=('127.0.0.1',50000)),base_url='http://testserver') as client:
            login_result=await client.post('/api/v2/bootstrap',json={'token':token},headers={'Origin':'http://testserver'})
            headers={'Origin':'http://testserver','X-CSRF-Token':login_result.json()['csrf']}
            held=threading.Event()
            def hold():
                with web.state.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE');held.set();time.sleep(.6)
            thread=threading.Thread(target=hold);thread.start();held.wait()
            request=asyncio.create_task(client.post('/api/v2/phone/setReceiver',json={'enabled':True},headers=headers))
            start=time.monotonic();await asyncio.sleep(.05)
            assert time.monotonic()-start<.25
            assert (await request).status_code==200
            thread.join()
    asyncio.run(scenario())


def test_failed_monitor_is_not_reported_healthy(tmp_path):
    web,_=create_apps(tmp_path/'health.db',extra_hosts=('testserver',))
    with TestClient(web,client=('127.0.0.1',50000)) as client:
        headers=login(client,web)
        client.post('/api/v2/phone/setReceiver',json={'enabled':True},headers=headers)
        client.portal.call(lambda:web.state.monitor_task.cancel())
        result=client.get('/health')
        assert result.status_code==503
        status=client.post('/api/v2/phone/getMonitoring',json={},headers=headers).json()
        assert not status['running'] and status['error']
