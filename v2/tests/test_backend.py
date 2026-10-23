import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.store import Store, Problem, DEFAULTS, calibration, hardware, iso, parse
from server.app import create_apps


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'v2.db')


def packet(device='river-01', sample='sample-1', seconds=0, revision=0):
    return {'device_id': device, 'mode': 'hardware', 'sample_id': sample,
            'timestamp': iso(time.time()*1000+seconds*1000), 'setup_protocol': 'remote-v1',
            'config_revision': revision, 'raw': {'ph_mv': 1700, 'ph_adc': 2200, 'temperature_c': 27.4, 'distance_cm': 30},
            'sensor_health': {'ph': 'ok', 'turbidity': 'missing', 'temperature': 'ok', 'water_level': 'ok'}}


def settings():
    return {'enabled': dict.fromkeys(DEFAULTS['enabled'], True), 'ph': [{'mv': 1500, 'value': 7}, {'mv': 2000, 'value': 4}],
            'turbidity': [{'mv': 1500, 'value': 100}, {'mv': 2000, 'value': 0}],
            'level': {'reference': 50, 'minimum': 25, 'maximum': 450}, 'temperature_offset': 0, 'verified': False}


def demo(seconds=0):
    return {'timestamp': iso(time.time()*1000+seconds*1000), 'ph': 7.1, 'turbidity': 12, 'temperature': 27.4, 'water_level': 35, 'scenario': 'Normal river'}


def test_database_reopens_and_rejects_foreign_database(tmp_path):
    path = tmp_path/'v2.db'; Store(path).set_state('hello', 'saved')
    assert Store(path).get_state('hello') == {'value': 'saved'}
    old = tmp_path/'old.db'
    with sqlite3.connect(old) as db: db.execute('CREATE TABLE personal_data(value TEXT)')
    before = old.read_bytes()
    with pytest.raises(RuntimeError, match='not a RiverGuard V2'): Store(old)
    assert old.read_bytes() == before


def test_credentials_are_hashed_rotatable_and_station_scoped(store):
    first = store.register('river-01')['token']
    with store.connect() as db:
        assert db.execute('SELECT token_hash FROM stations').fetchone()[0] != first
    assert store.authenticate('Bearer '+first) == 'river-01'
    with pytest.raises(Problem) as exc: store.ingest('river-01', packet('river-02'))
    assert exc.value.status == 403
    with pytest.raises(Problem): store.register('river-01')
    second = store.register('river-01', True)['token']
    assert first != second
    with pytest.raises(Problem): store.authenticate('Bearer '+first)


def test_delayed_packets_do_not_replace_current_and_duplicate_mutation_rejected(store):
    store.register('river-01')
    current = packet(); delayed = packet(sample='delayed', seconds=-90)
    store.ingest('river-01', current); store.ingest('river-01', delayed)
    result = store.readings('esp32', 'river-01')
    assert [row['payload']['sample_id'] for row in result['items']] == ['sample-1', 'delayed']
    assert store.stations()[0]['lastMeasured'] == result['items'][0]['timestamp']
    assert store.ingest('river-01', current)['duplicate']
    current['raw']['temperature_c'] = 33
    with pytest.raises(Problem) as exc: store.ingest('river-01', current)
    assert exc.value.status == 409


def test_future_missing_zone_bad_health_and_nonfinite_rejected():
    for value in (packet(seconds=6), packet() | {'timestamp': '2026-10-22T12:00:00'},
                  packet() | {'sensor_health': {'ph': 'great'}}, packet() | {'raw': {'ph_mv': float('nan')}},
                  packet() | {'config_revision': True}):
        with pytest.raises(Problem): hardware(value)
    for value in ('{"a":1,"a":2}', '{"v":NaN}', '{"v":'+('['*40)+'0'+(']'*40)+'}'):
        with pytest.raises(Problem): parse(value)


def test_settings_cas_snapshot_and_verification_reset(store):
    store.register('river-01')
    cfg = settings(); first = store.save_settings('river-01', 0, cfg)
    assert first['revision'] == 1
    store.save_watch('esp32', 'river-01', 0, {'elevated': 10, 'warning': 20, 'rise_limit': 10})
    ack=packet(sample='ack-1',revision=1);ack['raw']['turbidity_mv']=1800;ack['sensor_health']['turbidity']='ok';store.ingest('river-01',ack)
    cfg['verified'] = True
    assert store.save_settings('river-01', 1, cfg)['settings']['verified'] is True
    store.ingest('river-01', packet(revision=2))
    cfg['temperature_offset'] = 1
    changed = store.save_settings('river-01', 2, cfg)
    assert changed['settings']['verified'] is False
    assert store.readings('esp32', 'river-01')['items'][0]['settings']['temperature_offset'] == 0
    with pytest.raises(Problem) as exc: store.save_settings('river-01', 2, cfg)
    assert exc.value.status == 409
    with pytest.raises(Problem): store.ingest('river-01', packet(sample='unknown', revision=100))


def test_concurrent_settings_only_one_expected_revision_wins(store):
    store.register('river-01'); result = []
    def save():
        try: result.append(store.save_settings('river-01', 0, settings())['revision'])
        except Problem as exc: result.append(exc.status)
    threads = [threading.Thread(target=save) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(result) == [1, 409]


def test_calibration_monotonic_and_strict_types():
    cfg = settings(); cfg['turbidity'] = [{'mv': 1500, 'value': 0}, {'mv': 2000, 'value': 100}, {'mv': 2500, 'value': 50}]
    with pytest.raises(Problem): calibration(cfg)
    cfg = settings(); cfg['enabled']['ph'] = 1
    with pytest.raises(Problem): calibration(cfg)


def test_complete_history_over_ten_thousand_scoped_paginated_and_snapshot_export(store):
    stamp = int(time.time()*1000)-11000000
    with store.connect() as db:
        rows = []
        for i in range(10017):
            p = demo(); p['timestamp'] = iso(stamp+i*1000)
            rows.append(('simulation', 'demo-station', p['timestamp'], stamp+i*1000, p['timestamp'], json.dumps(p), 'seed-'+str(i)))
        db.executemany('INSERT INTO readings(source,device_id,timestamp,measured_ms,received_at,payload,sample_id) VALUES (?,?,?,?,?,?,?)', rows)
        db.execute('INSERT INTO readings(source,device_id,timestamp,measured_ms,received_at,payload,sample_id) VALUES (?,?,?,?,?,?,?)', ('simulation', 'other-station', iso(stamp), stamp, iso(stamp), json.dumps(demo()), 'other'))
    first = store.readings('simulation', 'demo-station', 500)
    assert first['total'] == 10017
    export = store.export('simulation', 'demo-station')
    store.append_demo(demo())
    ids = [row['id'] for row in first['items']]; cursor = first['nextCursor']
    while cursor:
        page = store.readings('simulation', 'demo-station', 500, cursor)
        assert page['total'] == 10017
        ids.extend(row['id'] for row in page['items']); cursor = page['nextCursor']
    assert len(ids) == len(set(ids)) == 10017
    exported = list(csv.reader(io.StringIO(''.join(export))))
    assert len(exported) == 10018
    with pytest.raises(Problem): store.readings('simulation', 'other-station', 10, first['nextCursor'])


def test_demo_idempotent_watch_and_preferences(store):
    p = demo(); assert not store.append_demo(p)['duplicate']; assert store.append_demo(p)['duplicate']
    assert store.readings('simulation', 'demo-station')['total'] == 1
    with pytest.raises(Problem): store.set_state('watch:river-01', {'elevated': 100, 'warning': 70, 'rise_limit': 10})
    with pytest.raises(Problem): store.set_state('../path', 'value')
    store.set_state('draft:river-01', {'temperature_offset': None})
    assert store.get_state('draft:river-01')['value']['temperature_offset'] is None


def test_overlapping_demo_browsers_keep_first_sample_in_two_second_slot(store):
    slot = int(time.time()//2)*2000
    first = demo(); first['timestamp'] = iso(slot+100)
    second = demo(); second['timestamp'] = iso(slot+1800); second['ph'] = 7.8
    barrier = threading.Barrier(2); results = []
    def append(payload):
        barrier.wait()
        results.append(store.append_demo(payload))
    threads = [threading.Thread(target=append, args=(payload,)) for payload in (first, second)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert len(results) == 2 and all(result['stored'] for result in results)
    assert sorted(result['duplicate'] for result in results) == [False, True]
    rows = store.readings('simulation', 'demo-station')
    assert rows['total'] == 1
    saved = rows['items'][0]['payload']
    assert (saved['timestamp'], saved['ph']) in {(first['timestamp'], first['ph']), (second['timestamp'], second['ph'])}
    # Replaying the losing request cannot replace the first accepted evidence.
    store.append_demo(first); store.append_demo(second)
    assert store.readings('simulation', 'demo-station')['items'][0]['payload'] == saved
    following = demo(); following['timestamp'] = iso(slot+2100)
    assert not store.append_demo(following)['duplicate']
    assert store.readings('simulation', 'demo-station')['total'] == 2


@pytest.fixture
def clients(tmp_path):
    web, sensor = create_apps(tmp_path/'api.db', extra_hosts=('testserver',))
    with TestClient(web, client=('127.0.0.1', 51000)) as browser, TestClient(sensor) as device:
        yield browser, device, web


def login(browser, web):
    token = web.state.access.bootstrap_token()
    result = browser.post('/api/v2/bootstrap', json={'token': token}, headers={'Origin': 'http://testserver'})
    assert result.status_code == 200
    return {'Origin': 'http://testserver', 'X-CSRF-Token': result.json()['csrf']}


def test_authentication_csrf_origin_device_boundary_and_complete_export(clients):
    browser, device, web = clients
    path = '/api/v2/phone/'
    assert browser.post(path+'listStations', json={}).status_code == 401
    headers = login(browser, web)
    assert browser.post(path+'registerStation', json={'deviceId': 'river-01'}).status_code == 403
    wrong = headers | {'Origin': 'http://evil.example'}
    assert browser.post(path+'registerStation', json={'deviceId': 'river-01'}, headers=wrong).status_code == 403
    registered = browser.post(path+'registerStation', json={'deviceId': 'river-01'}, headers=headers).json()
    bearer = {'Authorization': 'Bearer '+registered['token']}
    assert device.post('/api/v1/readings', json=packet()).status_code == 401
    assert device.post('/api/v1/readings', json=packet(), headers=bearer).status_code == 503
    assert browser.post(path+'setReceiver', json={'enabled': True}, headers=headers).status_code == 200
    assert device.get('/api/v1/device-config?device_id=river-02', headers=bearer).status_code == 403
    assert device.get('/api/v1/device-config?device_id=river-01', headers=bearer).json()['revision'] == 0
    assert device.post('/api/v1/readings', json=packet(), headers=bearer).status_code == 200
    assert device.post('/api/v2/phone/saveSettings', json={}, headers=bearer).status_code == 404
    result = browser.post(path+'exportData', json={'source': 'esp32', 'deviceId': 'river-01'}, headers=headers).json()
    export = browser.get(result['url'])
    assert export.status_code == 200 and 'settings_json' in export.text and 'sample-1' in export.text
    assert browser.get('/api/v2/session').json()['authenticated'] is True


def test_pairing_single_use_expiry_attempt_limit_and_session_revocation(clients):
    browser, _, web = clients
    headers = login(browser, web)
    code = browser.post('/api/v2/phone/createPairCode', json={}, headers=headers).json()['code']
    with TestClient(web, client=('192.168.1.10', 51000)) as paired:
        assert paired.post('/api/v2/bootstrap', json={'token': web.state.access.bootstrap_token()}, headers={'Origin': 'http://testserver'}).status_code == 403
        assert paired.post('/api/v2/pair', json={'code': code}, headers={'Origin': 'http://testserver'}).status_code == 200
        assert paired.post('/api/v2/pair', json={'code': code}, headers={'Origin': 'http://testserver'}).status_code == 401
        for _ in range(4): assert paired.post('/api/v2/pair', json={'code': 'bad'}, headers={'Origin': 'http://testserver'}).status_code == 401
        assert paired.post('/api/v2/pair', json={'code': 'bad'}, headers={'Origin': 'http://testserver'}).status_code == 429
    code = web.state.access.pair_code()['code']
    with web.state.store.connect() as db: db.execute('UPDATE pairing SET expires=0')
    assert browser.post('/api/v2/pair', json={'code': code}, headers={'Origin': 'http://testserver'}).status_code == 401
    assert browser.post('/api/v2/phone/signOut', json={}, headers=headers).status_code == 200
    assert browser.get('/api/v2/session').json()['authenticated'] is False


def test_request_bounds_duplicate_json_and_host_guard(clients):
    browser, _, web = clients; headers = login(browser, web)
    assert browser.post('/api/v2/phone/getState', content='{"key":"a","key":"b"}', headers=headers).status_code == 422
    assert browser.post('/api/v2/phone/getState', content=' '*131073, headers=headers).status_code == 413
    assert browser.get('/health', headers={'Host': 'evil.example'}).status_code == 400
    assert browser.get('/health').json()['database'] == 'ready'


def test_background_alerts_preserve_water_warning_missing_sensor_and_deduplicate(store):
    store.register('river-01'); cfg = settings(); cfg['level']['reference'] = 200
    store.save_settings('river-01', 0, cfg)
    p = packet(revision=1); p['raw']['distance_cm'] = 50
    p['raw']['ph_mv'] = 1500
    store.ingest('river-01', p)
    first = store.evaluate_alerts('river-01')
    assert {event['kind'] for event in first} >= {'water_warning', 'sensor_health'}
    assert store.evaluate_alerts('river-01') == []
    events = store.get_state('alerts:river-01')['value']
    assert len(events) == 2 and all(event['phase'] == 'active' for event in events)
    assert {event['kind'] for event in store.evaluate_alerts('river-01', time.time()*1000+40000)} == {'connection'}
    assert store.evaluate_alerts('river-01', time.time()*1000+50000) == []
    # A stale sample never clears the previous high-water condition.
    assert store.get_state('alert-status:river-01')['value']['conditions']['water_warning']['active']


def test_alert_recovery_requires_three_distinct_fresh_samples(store):
    store.register('river-01'); cfg = settings(); cfg['level']['reference'] = 200
    store.save_settings('river-01', 0, cfg)
    p = packet(revision=1); p['raw']['distance_cm'] = 50
    store.ingest('river-01', p); store.evaluate_alerts('river-01')
    now = time.time()*1000
    for i in range(3):
        p = packet(sample='clear-'+str(i), revision=1)
        p['timestamp'] = iso(now+i*1000); p['raw']['distance_cm'] = 180
        store.ingest('river-01', p)
        events = store.evaluate_alerts('river-01', now+i*1000)
        assert store.evaluate_alerts('river-01', now+i*1000) == []
        recovered = [event for event in events if event['kind'] == 'water_warning' and event['phase'] == 'recovered']
        assert bool(recovered) is (i == 2)


def test_backend_rules_match_shared_js_for_fresh_and_calibration_boundaries(store, tmp_path):
    import subprocess
    store.register('river-01'); cfg = settings(); cfg['level']['reference'] = 200
    store.save_settings('river-01', 0, cfg)
    now = round(time.time()*1000)
    for i in range(5):
        p = packet(sample='rise-'+str(i), revision=1)
        p['timestamp'] = iso(now-8000+i*2000); p['raw']['distance_cm'] = 120-i*10
        store.ingest('river-01', p)
    rows = store.readings('esp32', 'river-01')['items']
    from server.signals import evaluate
    own = evaluate(rows, None, now)
    fixture = tmp_path/'fixture.json'; fixture.write_text(json.dumps({'rows': rows, 'now': now}), encoding='utf-8')
    domain = Path(__file__).resolve().parents[2]/'mobile/offline/domain.js'
    script = "const d=require(process.argv[1]),fs=require('fs'),v=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const e=d.evaluate(v.rows,null,v.now);process.stdout.write(JSON.stringify({kinds:e.signals.map(s=>s.kind).sort(),rate:e.rate}));"
    result = subprocess.run(['node', '-e', script, str(domain), str(fixture)], check=True, capture_output=True, text=True)
    shared = json.loads(result.stdout)
    assert sorted(signal['kind'] for signal in own['signals']) == shared['kinds']
    assert own['rate'] == shared['rate']
