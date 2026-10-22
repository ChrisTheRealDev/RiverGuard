"""Isolated storage, calibration, signal and export integration regressions."""
import csv
import io
import json
import sqlite3
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest
import core
import data_service as data
import station_setup
from river_status import overview, signal_evaluation, observed_rise
from charting import summarize
from concurrent.futures import ThreadPoolExecutor


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DB', tmp_path / 'test.db')
    return core.DB


def rows(values, *, revision=1, start=None, device='one', ph=7.1):
    start = start or datetime.now(timezone.utc) - timedelta(seconds=(len(values)-1)*5)
    return pd.DataFrame([dict(id=i+1, timestamp=(start+timedelta(seconds=i*5)).isoformat(),
                             received_at=datetime.now(timezone.utc).isoformat(), source='esp32', device_id=device,
                             ph=ph, turbidity=12., temperature=27., water_level=value, calibrated=1, anomaly=0,
                             explanation='Within learned synthetic baseline.', config_revision=revision, calibration_id=f'app-r{revision}')
                         for i, value in enumerate(values)])


def insert(frame):
    columns = list(frame.columns)
    with core.connect() as con:
        for record in frame.to_dict('records'):
            record['measured_ms'] = core.measured_millis(record['timestamp'])
            names = columns + ['measured_ms']
            con.execute('INSERT INTO readings ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')', [record[name] for name in names])


def test_migration_online_backup_preserves_existing_evidence_and_closes(db):
    old = sqlite3.connect(db)
    old.execute('CREATE TABLE readings (id INTEGER PRIMARY KEY,timestamp TEXT,received_at TEXT,device_id TEXT,source TEXT,ph REAL,turbidity REAL,temperature REAL,water_level REAL,calibrated INTEGER,anomaly INTEGER,explanation TEXT)')
    stamp='2026-10-20T08:00:00+08:00'
    old.execute('INSERT INTO readings VALUES(1,?,?,?,?,?,?,?,?,?,?,?)',(stamp,stamp,'legacy','esp32',7.1,12,27,35,1,0,'original'))
    old.execute('CREATE TABLE chat_preservation (content TEXT)')
    old.execute("INSERT INTO chat_preservation VALUES ('keep me')")
    old.commit(); old.close()
    with core.connect() as con:
        assert con.execute('SELECT measured_ms FROM readings').fetchone()[0] == 1792454400000
        assert con.execute('PRAGMA user_version').fetchone()[0] == core.SCHEMA_VERSION
        assert con.execute('SELECT content FROM chat_preservation').fetchone()[0] == 'keep me'
    with pytest.raises(sqlite3.ProgrammingError):
        con.execute('SELECT 1')
    backups = list((db.parent/'backups').glob('*.sqlite3'))
    assert len(backups)==1
    backup = sqlite3.connect(backups[0])
    try:
        assert backup.execute('SELECT explanation FROM readings').fetchone()[0] == 'original'
        assert backup.execute('SELECT content FROM chat_preservation').fetchone()[0] == 'keep me'
        assert 'measured_ms' not in [col[1] for col in backup.execute('PRAGMA table_info(readings)')]
    finally:
        backup.close()
    with core.connect():
        pass
    assert len(list((db.parent/'backups').glob('*.sqlite3'))) == 1


def test_newer_database_version_is_never_downgraded(db):
    con=sqlite3.connect(db)
    con.execute('PRAGMA user_version=999')
    con.execute('CREATE TABLE future_evidence (content TEXT)')
    con.execute("INSERT INTO future_evidence VALUES ('preserved')")
    con.commit();con.close()
    with pytest.raises(RuntimeError,match='newer'):
        core.connect()
    con=sqlite3.connect(db)
    try:
        assert con.execute('PRAGMA user_version').fetchone()[0]==999
        assert con.execute('SELECT content FROM future_evidence').fetchone()[0]=='preserved'
    finally:
        con.close()


def test_station_time_filter_before_paging_no_10000_cap_and_complete_export(db):
    now=datetime.now(timezone.utc)
    sparse=rows([35], start=now-timedelta(days=2), device='quiet')
    insert(sparse)
    with core.connect() as con:
        con.executemany('INSERT INTO readings(timestamp,received_at,device_id,source,ph,turbidity,temperature,water_level,calibrated,anomaly,measured_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        [((now+timedelta(seconds=i)).isoformat(),now.isoformat(),'busy','esp32',7.1,12,27,35,1,0,core.measured_millis((now+timedelta(seconds=i)).isoformat())) for i in range(10001)])
    assert len(core.history('esp32')) == 10002
    assert station_setup.latest('quiet').device_id == 'quiet'
    assert {item['device_id'] for item in data.stations('esp32')} == {'busy','quiet'}
    page=data.reading_page('esp32','quiet',limit=1)
    assert page['total']==1 and page['items'][0]['device_id']=='quiet'
    first=data.reading_page('esp32','busy',limit=2, since=(now+timedelta(seconds=9998)).isoformat())
    assert first['total']==3 and len(first['items'])==2 and first['next_cursor']
    second=data.reading_page('esp32','busy',cursor=first['next_cursor'],limit=2,since=(now+timedelta(seconds=9998)).isoformat())
    assert len(second['items'])==1 and not second['next_cursor']
    output=list(csv.DictReader(io.StringIO(''.join(data.export_csv('esp32','busy')))))
    assert len(output)==10001


def test_measurement_order_pagination_snapshot_and_scope(db):
    now=datetime.now(timezone.utc)
    frame=rows([35,36,37], start=now-timedelta(seconds=10))
    insert(frame.iloc[[2,0,1]])
    assert core.history('esp32','one').iloc[-1].water_level==37
    assert station_setup.latest('one').water_level==37
    first=data.reading_page('esp32','one',limit=1)
    late=rows([30],start=now-timedelta(seconds=6));late['id']=4
    insert(late)
    second=data.reading_page('esp32','one',cursor=first['next_cursor'],limit=2)
    assert [item['water_level'] for item in second['items']]==[36,35]
    assert second['total']==3
    with pytest.raises(ValueError):
        data.reading_page('esp32','another',cursor=first['next_cursor'])


def test_faulted_legacy_values_preserved_but_not_interpreted(db):
    value=dict(ph=7.1,turbidity=12.,temperature=27.,water_level=35.,sensor_health={'ph':'missing'})
    class Normal:
        def predict(self, values): return [1]
    core.save(value,'esp32','one',calibrated=True,model=Normal())
    frame=core.history('esp32','one')
    assert pd.isna(frame.iloc[-1].ph) and not frame.iloc[-1].calibrated
    assert json.loads(frame.iloc[-1].raw_json)['reported_values']['ph']==7.1
    assert overview(frame)['title'] != 'No unusual signals'


def test_clock_and_available_water_warning_priority(db):
    now=datetime.now(timezone.utc)
    assert not signal_evaluation(rows([35],start=now+timedelta(seconds=6)),now=now)['fresh']
    assert signal_evaluation(rows([35],start=now+timedelta(seconds=5)),now=now)['fresh']
    frame=rows([110],ph=None)
    assert overview(frame)['title']=='Water level needs attention'
    assert overview(frame)['missing']==['Acidity']


def test_calibration_jump_never_becomes_rise_or_continuous_graph(db):
    frame=rows([15]*5+[45]*2)
    frame['config_revision']=[1]*5+[2]*2
    frame['calibration_id']=['app-r1']*5+['app-r2']*2
    assert observed_rise(frame) is None
    assert overview(frame)['flood']=='Below watch level'
    summary,_=summarize(frame,'water_level')
    assert summary.segment.nunique()==2
    assert set(summary['mean'].dropna())=={15,45}


def test_rule_and_rise_signals_match_overview_and_persisted_thresholds(db):
    frame=rows([35,37,39,41,43,45,47])
    insert(frame)
    result=data.overview_data('esp32','one','water_level')
    assert result['status']['flood']=='Warning'
    assert any(item['kind']=='rise' for item in result['alerts']['items'])
    page=data.alert_page('esp32','one')
    assert any(item['kind']=='rise' for item in page['items'])
    saved=data.save_thresholds('esp32','one',{'elevated':70,'warning':100,'rise_limit':100},0)
    assert saved['revision']==1
    with pytest.raises(ValueError):
        data.save_thresholds('esp32','one',{'elevated':70,'warning':100,'rise_limit':10},0)
    assert data.overview_data('esp32','one','water_level')['status']['flood']=='Below watch level'
    assert not data.alert_page('esp32','one')['items']
    changed=frame.iloc[[-1]].copy();changed['id']=8;changed['ph']=9.;changed['timestamp']=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    insert(changed)
    assert any(signal['kind']=='threshold' for signal in data.overview_data('esp32','one')['status']['signals'])
    assert any(item['kind']=='threshold' for item in data.alert_page('esp32','one')['items'])
    json.dumps(data.overview_data('esp32','one'),allow_nan=False)


def test_csv_formula_text_escaped_but_negative_numeric_unchanged(db):
    frame=rows([35],device='=HYPERLINK("bad")')
    frame['temperature']=-2.5
    frame['explanation']='  +SUM(1,2)'
    insert(frame)
    data.save_thresholds('esp32',frame.iloc[0].device_id,{'elevated':60,'warning':95,'rise_limit':12},0)
    output=list(csv.DictReader(io.StringIO(''.join(data.export_csv('esp32',frame.iloc[0].device_id)))))
    assert output[0]['device_id'].startswith("'=")
    assert output[0]['explanation'].startswith("'  +")
    assert output[0]['temperature']=='-2.5'
    assert output[0]['applied_watch_cm']=='60.0'
    assert output[0]['applied_warning_cm']=='95.0'
    assert output[0]['applied_rise_cm_per_min']=='12.0'
    assert output[0]['threshold_revision']=='1'
    assert 'current station threshold' in output[0]['threshold_interpretation']


def test_threshold_revision_conflict_is_atomic_and_export_snapshot_is_consistent(db):
    insert(rows([35]))
    def change(rise):
        try:
            return data.save_thresholds('esp32','one',{'elevated':70,'warning':100,'rise_limit':rise},0)
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(change,[11,12]))
    assert sum(result=='conflict' for result in results)==1
    settings=data.thresholds('esp32','one')
    stream=data.export_csv('esp32','one')
    header=next(stream)  # Read snapshot also captures the threshold revision.
    data.save_thresholds('esp32','one',{'elevated':80,'warning':120,'rise_limit':20},settings['revision'])
    exported=list(csv.DictReader(io.StringIO(header+''.join(stream))))
    assert exported[0]['threshold_revision']=='1'
    assert exported[0]['applied_watch_cm']=='70.0'
    assert data.thresholds('esp32','one')['revision']==2


def test_csv_stream_survives_worker_thread_handoffs(db):
    insert(rows([35]))
    stream=data.export_csv('esp32','one')
    with ThreadPoolExecutor(max_workers=1) as first, ThreadPoolExecutor(max_workers=1) as second:
        header=first.submit(next,stream).result()
        chunk=second.submit(next,stream).result()
    assert len(list(csv.DictReader(io.StringIO(header+chunk))))==1
    assert list(stream)==[]


def test_graph_has_real_gap_boundaries_without_artificial_cadence_gaps(db):
    frame=rows([35,36,37])
    normal,_=summarize(frame,'water_level')
    assert normal[normal['count']>0].segment.nunique()==1
    frame.loc[1,'water_level']=None
    missing,_=summarize(frame,'water_level')
    assert missing[missing['count']>0].segment.nunique()==2


def test_receipt_heartbeat_does_not_roll_measurement_back(db):
    now=datetime.now(timezone.utc)
    frame=rows([35,110],start=now-timedelta(minutes=2))
    frame.loc[0,'received_at']=(now-timedelta(minutes=2)).isoformat()
    frame.loc[1,'timestamp']=(now-timedelta(minutes=4)).isoformat()
    frame.loc[1,'received_at']=now.isoformat()
    insert(frame)
    [station]=data.stations('esp32')
    assert station['connected'] and not station['fresh']
    assert station['last_received']==now.isoformat()
    assert station['last_measured']==frame.iloc[0].timestamp
    assert data.overview_data('esp32','one')['latest']['water_level']==35


def test_overview_cards_and_status_use_one_read_snapshot(db,monkeypatch):
    insert(rows([35]))
    original=data._thresholds
    def arriving_packet(con,source,device):
        result=original(con,source,device)
        frame=rows([110],start=datetime.now(timezone.utc)+timedelta(seconds=1))
        frame['id']=2
        insert(frame)
        return result
    monkeypatch.setattr(data,'_thresholds',arriving_packet)
    overview=data.overview_data('esp32','one')
    assert overview['latest']['water_level']==35
    assert overview['status']['flood']=='Below watch level'
    assert core.history('esp32','one').iloc[-1].water_level==110


def test_stale_warning_is_explicitly_last_known(db):
    frame=rows([110],start=datetime.now(timezone.utc)-timedelta(minutes=2))
    status=overview(frame)
    assert status['title']=='Last-known water-level warning'
    assert status['flood']=='Warning' and not status['fresh']
    assert 'Current conditions are unknown' in status['reason']
    assert status['signals']==[]


def test_flagged_samples_include_every_rule_without_double_counting(db):
    frame=rows([110,111,112])
    frame['ph']=9.
    frame['anomaly']=1
    insert(frame)
    episodes=data.alert_page('esp32','one')
    samples=data.alert_page('esp32','one',grouped=False,limit=2)
    assert samples['total']==3 and len(samples['items'])==2
    assert all(item['count']==1 and len(item['signals'])>=3 for item in samples['items'])
    assert all(item['severity']=='Warning' for item in samples['items'])
    remaining=data.alert_page('esp32','one',cursor=samples['next_cursor'],grouped=False,limit=2)
    assert len(remaining['items'])==1 and remaining['next_cursor'] is None
    assert len({item['reading_id'] for item in samples['items']+remaining['items']})==3
    with pytest.raises(ValueError):
        data.alert_page('esp32','one',cursor=samples['next_cursor'],grouped=True)
    assert episodes['grouped'] is True and any(item['count']==3 for item in episodes['items'])


def test_station_settings_schema_is_initialized_once(db,monkeypatch):
    with core.connect() as con:
        assert con.execute("SELECT name FROM sqlite_master WHERE name='station_settings'").fetchone()
    statements=[]
    original=core.connect
    def traced(**kwargs):
        con=original(**kwargs)
        con.set_trace_callback(statements.append)
        return con
    monkeypatch.setattr(core,'connect',traced)
    station_setup.load('one')
    station_setup.load('one')
    assert not any('CREATE TABLE' in command.upper() for command in statements)
