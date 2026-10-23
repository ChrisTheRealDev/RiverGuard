"""Offline synthetic scenarios, independent AI evaluation, and durable storage."""
import os
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import accuracy_score, confusion_matrix

DB = Path(os.environ.get('RIVERGUARD_DB', str(Path(__file__).parent / 'data' / 'riverguard.db')))
FEATURES = ['ph', 'turbidity', 'temperature']
FEATURE_NAMES = {'ph': 'Acidity', 'turbidity': 'Cloudiness', 'temperature': 'Temperature'}
SCENARIOS = ['Normal river', 'Sudden change', 'Increasing turbidity', 'Abnormal pH', 'Temperature change', 'Rising water level', 'Combined anomaly']
SCHEMA_VERSION = 3
_migration_lock = threading.RLock()


class ClosingConnection(sqlite3.Connection):
    """Keep sqlite transaction semantics, and always release the file handle."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def measured_millis(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Measurement timestamp must include a timezone.')
    return int(stamp.timestamp() * 1000)


def _migrate(con):
    version = con.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError('This database was created by a newer RiverGuard version. Open it with that version; do not downgrade it.')
    if version == SCHEMA_VERSION:
        return
    with _migration_lock:
        con.execute('BEGIN IMMEDIATE')
        try:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('This database uses a newer RiverGuard schema. Do not downgrade it.')
            if version == SCHEMA_VERSION:
                con.commit()
                return
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if tables:
                # A second read connection takes an online SQLite snapshot, including
                # committed WAL contents, while our write lock excludes schema changes.
                folder = DB.parent / 'backups'
                folder.mkdir(parents=True, exist_ok=True)
                backup = folder / f'{DB.stem}.pre-v{SCHEMA_VERSION}.{uuid.uuid4().hex}.sqlite3'
                source = sqlite3.connect(DB, timeout=15)
                destination = sqlite3.connect(backup)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
                    source.close()
            con.execute('''CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY, timestamp TEXT, received_at TEXT, device_id TEXT,
                source TEXT, ph REAL, turbidity REAL, temperature REAL, water_level REAL,
                calibrated INTEGER, anomaly INTEGER, explanation TEXT)''')
            columns = {r[1] for r in con.execute('PRAGMA table_info(readings)')}
            for column, kind in [('sample_id','TEXT'), ('raw_json','TEXT'), ('sensor_health_json','TEXT'),
                                 ('calibration_id','TEXT'), ('config_revision','INTEGER'),
                                 ('setup_protocol','TEXT'), ('measured_ms','INTEGER')]:
                if column not in columns:
                    con.execute(f'ALTER TABLE readings ADD COLUMN {column} {kind}')
            for identity, stamp in con.execute('SELECT id,timestamp FROM readings WHERE measured_ms IS NULL').fetchall():
                try:
                    millis = measured_millis(stamp)
                except (ValueError, TypeError, OverflowError):
                    continue  # Keep malformed historical evidence intact; never invent time.
                con.execute('UPDATE readings SET measured_ms=? WHERE id=?', (millis, identity))
            con.execute('CREATE UNIQUE INDEX IF NOT EXISTS sensor_sample ON readings(source,device_id,sample_id) WHERE sample_id IS NOT NULL')
            con.execute('CREATE INDEX IF NOT EXISTS readings_station_time ON readings(source,device_id,measured_ms,id)')
            con.execute('CREATE INDEX IF NOT EXISTS readings_source_time ON readings(source,measured_ms,id)')
            con.execute('''CREATE TABLE IF NOT EXISTS station_thresholds (
                source TEXT, device_id TEXT, revision INTEGER, settings TEXT, saved_at TEXT,
                PRIMARY KEY(source,device_id,revision))''')
            con.execute('''CREATE TABLE IF NOT EXISTS station_settings (
                device_id TEXT, revision INTEGER, settings TEXT, saved_at TEXT,
                PRIMARY KEY(device_id,revision))''')
            con.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            con.execute('INSERT OR IGNORE INTO schema_migrations VALUES (?,?)', (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()))
            con.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            con.commit()
        except BaseException:
            con.rollback()
            raise

def connect(*, check_same_thread=True):
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=15, factory=ClosingConnection, check_same_thread=check_same_thread)
    try:
        con.execute('PRAGMA journal_mode=WAL')
        _migrate(con)
        return con
    except BaseException:
        con.close()
        raise

def sample(scenario, step, seed=42):
    rng = np.random.default_rng(seed + step)
    values = dict(ph=float(rng.normal(7.1, .12)), turbidity=float(max(0, rng.normal(12, 2))),
                  temperature=float(rng.normal(27, .4)), water_level=float(rng.normal(35, .3)))
    active = step >= 10
    if active:
        if scenario in ['Sudden change', 'Combined anomaly']: values['turbidity'] += 100
        if scenario == 'Increasing turbidity': values['turbidity'] += min((step-9)*6, 180)
        if scenario in ['Abnormal pH', 'Combined anomaly']: values['ph'] -= 2.2
        if scenario in ['Temperature change', 'Combined anomaly']: values['temperature'] += 7
        if scenario == 'Rising water level': values['water_level'] += min((step-9)*3, 160)
    return values

def baseline(v):
    return any(v.get(k) is not None and not lo <= v[k] <= hi
               for k, lo, hi in [('ph', 6.5, 8.5), ('turbidity', 0, 50), ('temperature', 20, 32)])

def train():
    rng = np.random.default_rng(821)
    x = np.column_stack([rng.normal(7.1,.12,1500), rng.normal(12,2,1500), rng.normal(27,.4,1500)])
    return IsolationForest(n_estimators=150, contamination=.02, random_state=17).fit(x)

def assess(model, v):
    if any(v.get(k) is None for k in FEATURES): return None, 'AI unavailable: incomplete sensor measurements.'
    flag = bool(model.predict([[v[k] for k in FEATURES]])[0] == -1)
    deviations = [(abs((v[k]-mean)/sd), k) for k,mean,sd in zip(FEATURES,[7.1,12,27],[.12,2,.4])]
    contributors = [FEATURE_NAMES[k] for z,k in sorted(deviations, reverse=True)[:2]]
    return flag, ('Unusual combination; largest deviations from synthetic baseline: ' + ', '.join(contributors) + '. Not confirmed pollution.') if flag else 'Within learned synthetic baseline.'

def save(v, source, device_id, timestamp=None, calibrated=False, model=None, sample_id=None):
    v = sanitize_legacy(v)
    calibrated = bool(calibrated) and not any(v.get('sensor_health', {}).get(k) in SENSOR_FAULTS for k in FEATURES + ['water_level'])
    flag, explanation = assess(model if model is not None else train(), v)
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        cursor=con.execute('INSERT OR IGNORE INTO readings (timestamp,received_at,device_id,source,ph,turbidity,temperature,water_level,calibrated,anomaly,explanation,sample_id,raw_json,sensor_health_json,calibration_id,config_revision,setup_protocol,measured_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (timestamp or now, now, device_id, source, *[v.get(k) for k in FEATURES+['water_level']], int(calibrated), None if flag is None else int(flag), explanation,sample_id,
                     json.dumps(v.get('raw',{}),allow_nan=False),json.dumps(v.get('sensor_health',{})),v.get('calibration_id'),v.get('config_revision'),v.get('setup_protocol'),measured_millis(timestamp or now)))
        if cursor.rowcount==0 and sample_id is not None:
            stored=con.execute('SELECT anomaly FROM readings WHERE source=? AND device_id=? AND sample_id=?',(source,device_id,sample_id)).fetchone()
            flag=None if stored[0] is None else bool(stored[0])
    return flag

SENSOR_FAULTS = {'missing', 'timeout', 'adc_limit', 'disabled', 'out_of_range', 'uncalibrated'}


def sanitize_legacy(payload):
    """Retain reported legacy values as evidence, never as valid faulted readings."""
    if payload.get('setup_protocol') == 'remote-v1':
        return payload
    result = dict(payload)
    raw = dict(result.get('raw') or {})
    reported = dict(raw.get('reported_values') or {})
    for field in FEATURES + ['water_level']:
        if result.get('sensor_health', {}).get(field) in SENSOR_FAULTS and result.get(field) is not None:
            reported[field] = result[field]
            result[field] = None
    if reported:
        raw['reported_values'] = reported
    result['raw'] = raw
    return result


def history(source, device_id=None, since=None, until=None, limit=None):
    clauses=['source=?']; params=[source]
    if device_id is not None:
        clauses.append('device_id=?'); params.append(device_id)
    for value, operator in [(since, '>='), (until, '<=')]:
        if value is not None:
            clauses.append(f'measured_ms {operator} ?'); params.append(measured_millis(value))
    query='SELECT * FROM readings WHERE '+' AND '.join(clauses)
    if limit is not None:
        query='SELECT * FROM ('+query+' ORDER BY measured_ms DESC,id DESC LIMIT ?) ORDER BY measured_ms,id'
        params.append(int(limit))
    else:
        query+=' ORDER BY measured_ms,id'
    with connect() as con:
        return pd.read_sql_query(query, con, params=params)

def reset_simulation():
    with connect() as con: con.execute("DELETE FROM readings WHERE source='simulation'")

def evaluate(model):
    rows=[]
    # Evaluation seeds and scenarios are independent of normal-only training data.
    for s in SCENARIOS:
        for i in range(80):
            v=sample(s,i,seed=99100)
            expected = s not in ['Normal river','Rising water level'] and i >= 10
            rows.append(dict(scenario=s,step=i,expected=expected,rules=baseline(v),**v))
    df=pd.DataFrame(rows)
    df['ai']=model.predict(df[FEATURES].to_numpy()) == -1
    metrics=[]
    for method in ['ai','rules']:
        tn,fp,fn,tp=confusion_matrix(df.expected,df[method],labels=[False,True]).ravel()
        delays=[]
        missed_scenarios=0
        for s in SCENARIOS:
            events=df[(df.scenario==s)&df.expected]
            hits=events[events[method]]
            if not hits.empty: delays.append(int(hits.step.min()-events.step.min()))
            elif not events.empty: missed_scenarios+=1
        metrics.append(dict(method=method,accuracy=accuracy_score(df.expected,df[method]),
                            false_positive_rate=fp/(fp+tn),missed_anomalies=int(fn),
                            missed_scenarios=missed_scenarios,
                            mean_detection_delay_steps=float(np.mean(delays))))
    return pd.DataFrame(metrics),df
