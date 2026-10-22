"""Append-only V2 evidence, with no dependency on the shipped app's database."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import base64
import csv
import hashlib
import io
import json
import math
import re
import secrets
import sqlite3
import time

FIELDS = ('ph', 'turbidity', 'temperature', 'water_level')
STATES = {'ok', 'missing', 'uncalibrated', 'out_of_range', 'disabled', 'timeout', 'adc_limit'}
DEFAULTS = {'enabled': dict.fromkeys(FIELDS, False), 'ph': None, 'turbidity': None,
            'level': None, 'temperature_offset': 0, 'verified': False}


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def encode(value):
    try:
        return json.dumps(value, allow_nan=False, separators=(',', ':'), sort_keys=True)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Problem(422, 'Use valid finite JSON values.') from exc


def parse(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        def depth(item, level=0):
            if level > 32:
                raise ValueError('deep JSON')
            if isinstance(item, dict):
                for child in item.values(): depth(child, level+1)
            elif isinstance(item, list):
                for child in item: depth(child, level+1)
        depth(value)
        if not isinstance(value, dict): raise ValueError('object required')
        return value
    except (ValueError, TypeError, RecursionError, UnicodeDecodeError) as exc:
        raise Problem(422, 'Send one valid JSON object with unique keys and nesting at most 32 levels.') from exc


def keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value)-set(allowed) or set(required)-set(value):
        raise Problem(422, 'Unexpected or missing field in this configuration or reading.')


def text(value, minimum=1, maximum=128):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise Problem(422, 'Enter a valid text value.')
    return value


def station(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise Problem(422, 'Use 1–80 letters, digits, hyphens or underscores for the station ID.')
    return value


def number(value, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum or (integer and int(value) != value):
        raise Problem(422, 'A number is missing or outside its supported range.')
    return value


def boolean(value):
    if type(value) is not bool: raise Problem(422, 'Use true or false.')
    return value


def timestamp(value, now=None):
    try:
        stamp = datetime.fromisoformat(text(value, 20, 64).replace('Z', '+00:00'))
        if stamp.tzinfo is None: raise ValueError('offset required')
        milliseconds = round(stamp.timestamp()*1000)
        if milliseconds < 946684800000 or milliseconds > (now if now is not None else time.time()*1000)+5000:
            raise ValueError('clock range')
        return milliseconds
    except (ValueError, OverflowError, OSError) as exc:
        raise Problem(422, 'Use an ISO measurement time with timezone, from 2000 onward and no more than five seconds ahead.') from exc


def iso(milliseconds=None):
    return datetime.fromtimestamp((milliseconds if milliseconds is not None else time.time()*1000)/1000, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def calibration(value):
    keys(value, DEFAULTS, DEFAULTS)
    normalized = json.loads(encode(value))
    keys(normalized['enabled'], FIELDS, FIELDS)
    for flag in normalized['enabled'].values(): boolean(flag)
    for field in ('ph', 'turbidity'):
        points = normalized[field]
        if points is None: continue
        if not isinstance(points, list) or not 2 <= len(points) <= (2 if field == 'ph' else 5):
            raise Problem(422, 'Use two pH buffers or two to five NTU standards.')
        for point in points:
            keys(point, ('mv', 'value'), ('mv', 'value'))
            number(point['mv'], 150, 3050)
            number(point['value'], 0, 14 if field == 'ph' else 10000)
        points.sort(key=lambda p: p['mv'])
        direction = None
        for a, b in zip(points, points[1:]):
            delta = b['value']-a['value']
            if b['mv']-a['mv'] < 1 or abs(delta) < (.1 if field == 'ph' else 1e-12):
                raise Problem(422, 'Use different reference values and signals at least 1 mV apart.')
            sign = delta > 0
            if direction is not None and direction != sign:
                raise Problem(422, 'Calibration standards reverse direction; check the settled signals.')
            direction = sign
    level = normalized['level']
    if level is not None:
        keys(level, ('reference', 'minimum', 'maximum'), ('reference', 'minimum', 'maximum'))
        for value in level.values(): number(value, .001, 1000)
        if not level['minimum'] < level['reference'] <= level['maximum']:
            raise Problem(422, 'Zero-level distance must be above the minimum and within the maximum.')
    number(normalized['temperature_offset'], -5, 5)
    boolean(normalized['verified'])
    if normalized['verified'] and not (all(normalized['enabled'].values()) and normalized['ph'] and normalized['turbidity'] and level):
        raise Problem(422, 'Enable and calibrate all four channels before verification.')
    return normalized


def hardware(packet, now=None):
    keys(packet, ('device_id', 'mode', 'sample_id', 'timestamp', 'setup_protocol', 'config_revision', 'raw', 'sensor_health', 'calibrated', 'calibration_id', 'tds_ppm', 'ph', 'turbidity', 'temperature', 'temperature_c', 'water_level', 'water_level_cm', 'ph_unit', 'turbidity_unit', 'temperature_unit', 'water_level_unit'), ('device_id', 'sample_id', 'timestamp', 'setup_protocol', 'config_revision', 'raw', 'sensor_health'))
    station(packet['device_id'])
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', text(packet['sample_id'], 1, 100)):
        raise Problem(422, 'Invalid sample identifier.')
    if packet['setup_protocol'] != 'remote-v1' or packet.get('mode', 'hardware') != 'hardware':
        raise Problem(422, 'Upload the remote-v1 hardware firmware.')
    number(packet['config_revision'], 0, 2147483647, True)
    if 'calibrated' in packet: boolean(packet['calibrated'])
    if packet.get('calibration_id') is not None: text(packet['calibration_id'], 1, 80)
    if packet.get('tds_ppm') is not None: raise Problem(422, 'TDS is unsupported until the sensor is confirmed.')
    raw = packet['raw']
    bounds = {'ph_mv': (0, 3300), 'turbidity_mv': (0, 3300), 'ph_adc': (0, 4095), 'turbidity_adc': (0, 4095), 'temperature_c': (-55, 125), 'distance_cm': (0, 1000)}
    keys(raw, bounds)
    for key, value in raw.items():
        if value is not None: number(value, *bounds[key], integer=key.endswith('_adc'))
    keys(packet['sensor_health'], FIELDS)
    if any(not isinstance(value, str) or value not in STATES for value in packet['sensor_health'].values()):
        raise Problem(422, 'Unknown sensor-health state.')
    for key, expected in {'ph_unit': 'pH', 'turbidity_unit': 'NTU', 'temperature_unit': 'C', 'water_level_unit': 'cm'}.items():
        if key in packet and packet[key] != expected: raise Problem(422, 'Unsupported measurement unit.')
    for key in ('ph', 'turbidity', 'temperature', 'temperature_c', 'water_level', 'water_level_cm'):
        if packet.get(key) is not None:
            number(packet[key], -55 if key.startswith('temperature') else 0, 14 if key == 'ph' else 10000 if key == 'turbidity' else 125 if key.startswith('temperature') else 1000)
    return timestamp(packet['timestamp'], now)


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            application = db.execute('PRAGMA application_id').fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if (tables and application != 0x52475632) or application not in (0, 0x52475632):
                raise RuntimeError('This is not a RiverGuard V2 database. Choose a separate V2 file; the existing database was not changed.')
            if version not in (0, 1): raise RuntimeError('Unsupported V2 database version; preserve the data folder.')
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stations(device_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,last_received TEXT,last_measured TEXT,ack_revision INTEGER);
            CREATE TABLE IF NOT EXISTS configurations(device_id TEXT,revision INTEGER,settings TEXT,created_at TEXT,PRIMARY KEY(device_id,revision),FOREIGN KEY(device_id) REFERENCES stations(device_id));
            CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,device_id TEXT NOT NULL,timestamp TEXT NOT NULL,measured_ms INTEGER NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL,settings_json TEXT,sample_id TEXT,UNIQUE(source,device_id,sample_id));
            CREATE INDEX IF NOT EXISTS station_measurement ON readings(source,device_id,measured_ms DESC,id DESC);
            CREATE TABLE IF NOT EXISTS alert_events(id INTEGER PRIMARY KEY AUTOINCREMENT,device_id TEXT NOT NULL,event_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS station_alert_events ON alert_events(device_id,id DESC);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,hash TEXT UNIQUE NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS bootstrap(hash TEXT PRIMARY KEY,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pairing(hash TEXT PRIMARY KEY,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(address TEXT,attempted REAL);
            PRAGMA user_version=1;
            PRAGMA application_id=1380406834;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get_state(self, key):
        self.state_key(key)
        with self.connect() as db:
            if key.startswith('alerts:'):
                device = station(key[7:])
                return {'value': [json.loads(row[0]) for row in db.execute('SELECT event_json FROM alert_events WHERE device_id=? ORDER BY id DESC LIMIT 100', (device,))]}
            row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return {'value': json.loads(row[0]) if row else None}

    @staticmethod
    def state_key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key): raise Problem(422, 'Invalid preference key.')

    def set_state(self, key, value):
        self.state_key(key)
        encoded = encode(value)
        if len(encoded.encode()) > 65536: raise Problem(413, 'This preference is too large.')
        if key.startswith('watch:'):
            station(key[6:]); keys(value, ('elevated', 'warning', 'rise_limit'), ('elevated', 'warning', 'rise_limit'))
            number(value['elevated'], 0, 1000); number(value['warning'], 0, 1000); number(value['rise_limit'], .000001, 10000)
            if value['elevated'] >= value['warning']: raise Problem(422, 'Warning height must exceed watch height.')
        with self.connect() as db:
            db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encoded))
        return {'saved': True}

    def register(self, device, rotate=False):
        station(device); boolean(rotate)
        token = secrets.token_hex(32)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            exists = db.execute('SELECT 1 FROM stations WHERE device_id=?', (device,)).fetchone()
            if exists and not rotate: raise Problem(409, 'Station already registered. Replace its credential only if you can update the private firmware configuration.')
            db.execute('INSERT INTO stations(device_id,token_hash) VALUES (?,?) ON CONFLICT(device_id) DO UPDATE SET token_hash=excluded.token_hash', (device, digest(token)))
        return {'deviceId': device, 'token': token}

    def authenticate(self, header):
        if not isinstance(header, str) or not re.fullmatch(r'Bearer [A-Za-z0-9_-]{32,200}', header): raise Problem(401, 'Station credential required.')
        with self.connect() as db:
            row = db.execute('SELECT device_id FROM stations WHERE token_hash=?', (digest(header[7:]),)).fetchone()
        if not row: raise Problem(401, 'Station credential is invalid or revoked.')
        return row[0]

    @staticmethod
    def _settings(db, device, revision=None):
        row = db.execute('SELECT revision,settings FROM configurations WHERE device_id=?'+(' ORDER BY revision DESC LIMIT 1' if revision is None else ' AND revision=?'), (device,) if revision is None else (device, revision)).fetchone()
        if row: return {'revision': row[0], 'settings': json.loads(row[1])}
        if revision not in (0, None): raise Problem(409, 'Unknown calibration revision. Resync the station configuration.')
        return {'revision': 0, 'settings': json.loads(encode(DEFAULTS))}

    def settings(self, device):
        station(device)
        with self.connect() as db: return self._settings(db, device)

    def save_settings(self, device, expected, incoming):
        station(device); number(expected, 0, 2147483646, True)
        normalized = calibration(incoming)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM stations WHERE device_id=?', (device,)).fetchone(): raise Problem(404, 'Register this station first.')
            old = self._settings(db, device)
            if old['revision'] != expected: raise Problem(409, 'Settings changed. Reload the saved configuration before saving again.')
            if (old['settings'] | {'verified': False}) != (normalized | {'verified': False}): normalized['verified'] = False
            db.execute('INSERT INTO configurations VALUES (?,?,?,?)', (device, expected+1, encode(normalized), iso()))
        return {'revision': expected+1, 'settings': normalized}

    def configuration(self, device):
        cfg = self.settings(device)
        return {'device_id': device, 'protocol': 'remote-v1', 'revision': cfg['revision'], 'enabled': cfg['settings']['enabled'], 'server_time': iso(), 'server_epoch_seconds': int(time.time())}

    def ingest(self, authenticated, packet):
        measured = hardware(packet)
        if packet['device_id'] != authenticated: raise Problem(403, 'A station can submit only its own readings.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            settings = self._settings(db, authenticated, packet['config_revision'])['settings']
            return self._append(db, 'esp32', authenticated, packet, settings, measured, packet['sample_id'])

    def _append(self, db, source, device, payload, settings, measured, sample):
        encoded = encode(payload); received = iso()
        existing = db.execute('SELECT payload FROM readings WHERE source=? AND device_id=? AND sample_id=?', (source, device, sample)).fetchone()
        if existing:
            if json.loads(existing[0]) != payload: raise Problem(409, 'This sample ID was already used for different readings. Keep retries unchanged.')
        else:
            db.execute('INSERT INTO readings(source,device_id,timestamp,measured_ms,received_at,payload,settings_json,sample_id) VALUES (?,?,?,?,?,?,?,?)', (source, device, iso(measured), measured, received, encoded, encode(settings) if settings else None, sample))
        if source == 'esp32':
            latest = db.execute("SELECT timestamp,payload FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 1", (device,)).fetchone()
            db.execute('UPDATE stations SET last_received=?,last_measured=?,ack_revision=? WHERE device_id=?', (received, latest[0], json.loads(latest[1])['config_revision'], device))
        return {'stored': True, 'duplicate': bool(existing)}

    def append_demo(self, payload):
        keys(payload, ('timestamp', 'ph', 'turbidity', 'temperature', 'water_level', 'scenario'), ('ph', 'turbidity', 'temperature', 'water_level'))
        for key, low, high in [('ph', 0, 14), ('turbidity', 0, 10000), ('temperature', -55, 125), ('water_level', 0, 1000)]: number(payload[key], low, high)
        payload = dict(payload)
        payload.setdefault('timestamp', iso())
        measured = timestamp(payload['timestamp'])
        if 'scenario' in payload: text(payload['scenario'], 1, 80)
        payload.update(device_id='demo-station', mode='simulation')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._append(db, 'simulation', 'demo-station', payload, None, measured, 'demo-'+str(measured))

    def stations(self):
        with self.connect() as db:
            return [dict(deviceId=r['device_id'], revision=r['revision'] or 0, acknowledgedRevision=r['ack_revision'], lastReceived=r['last_received'], lastMeasured=r['last_measured']) for r in db.execute('SELECT *, (SELECT MAX(revision) FROM configurations c WHERE c.device_id=s.device_id) revision FROM stations s ORDER BY device_id')]

    @staticmethod
    def scope(source, device):
        if source not in ('simulation', 'esp32'): raise Problem(422, 'Choose demonstration or sensor readings.')
        station(device)

    @staticmethod
    def row(row):
        return dict(id=row['id'], source=row['source'], deviceId=row['device_id'], timestamp=row['timestamp'], receivedAt=row['received_at'], payload=json.loads(row['payload']), settings=json.loads(row['settings_json']) if row['settings_json'] else None)

    def readings(self, source, device, limit=120, cursor=None):
        self.scope(source, device); number(limit, 1, 500, True)
        with self.connect() as db:
            ceiling = db.execute('SELECT COALESCE(MAX(id),0) FROM readings WHERE source=? AND device_id=?', (source, device)).fetchone()[0]
            boundary = None
            if cursor:
                try:
                    token = parse(base64.urlsafe_b64decode(text(cursor, 1, 2048)+'='*((-len(cursor)) % 4)))
                    if token['source'] != source or token['deviceId'] != device: raise ValueError('scope')
                    ceiling = number(token['ceiling'], 0, 2**63-1, True)
                    boundary = (number(token['ms'], 0, 2**63-1, True), number(token['id'], 1, 2**63-1, True))
                except (ValueError, KeyError, TypeError) as exc: raise Problem(422, 'Invalid history cursor for this station.') from exc
            where = 'source=? AND device_id=? AND id<=?'; args = [source, device, ceiling]
            total = db.execute('SELECT COUNT(*) FROM readings WHERE '+where, args).fetchone()[0]
            if boundary:
                where += ' AND (measured_ms<? OR (measured_ms=? AND id<?))'; args += [boundary[0], boundary[0], boundary[1]]
            rows = db.execute('SELECT * FROM readings WHERE '+where+' ORDER BY measured_ms DESC,id DESC LIMIT ?', args+[int(limit)+1]).fetchall()
        next_cursor = None
        if len(rows) > limit:
            last = rows[int(limit)-1]
            next_cursor = base64.urlsafe_b64encode(encode(dict(source=source, deviceId=device, ceiling=ceiling, ms=last['measured_ms'], id=last['id'])).encode()).decode().rstrip('=')
        return {'items': [self.row(row) for row in rows[:int(limit)]], 'nextCursor': next_cursor, 'total': total}

    def export(self, source, device):
        self.scope(source, device)
        # A ceiling cursor makes one immutable snapshot without retaining a
        # database lock while a slow browser downloads.
        with self.connect() as db:
            ceiling = db.execute('SELECT COALESCE(MAX(id),0) FROM readings WHERE source=? AND device_id=?', (source, device)).fetchone()[0]
        def rows():
            yield ['id', 'source', 'device_id', 'timestamp', 'received_at', 'sample_id', 'config_revision', 'ph', 'turbidity', 'temperature', 'water_level', 'raw_json', 'settings_json', 'payload_json']
            previous = 0
            while True:
                with self.connect() as db:
                    batch = db.execute('SELECT * FROM readings WHERE source=? AND device_id=? AND id>? AND id<=? ORDER BY id LIMIT 500', (source, device, previous, ceiling)).fetchall()
                if not batch: return
                for row in batch:
                    packet = json.loads(row['payload']); demo = row['source'] == 'simulation'
                    yield [row['id'], row['source'], row['device_id'], row['timestamp'], row['received_at'], row['sample_id'], packet.get('config_revision'), *[packet.get(field) if demo else None for field in FIELDS], encode(packet.get('raw', {})), row['settings_json'], row['payload']]
                previous = batch[-1]['id']
        def generate():
            for row in rows():
                out = io.StringIO(newline=''); writer = csv.writer(out)
                writer.writerow([formula_safe(value) for value in row])
                yield out.getvalue()
        return generate()

    def evaluate_alerts(self, device, now=None):
        from .signals import evaluate, apply
        now = time.time()*1000 if now is None else now
        rows = self.readings('esp32', device, 120)['items']
        if not rows: return []
        watch = self.get_state('watch:'+device)['value']
        evaluation = evaluate(rows, watch, now)
        key = 'alert-status:'+device
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
            state, events = apply(json.loads(previous[0]) if previous else None, evaluation, now)
            encoded = encode(state)
            if not previous or previous[0] != encoded:
                db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encoded))
            for event in events:
                event['deviceId'] = device
                db.execute('INSERT INTO alert_events(device_id,event_json) VALUES (?,?)', (device, encode(event)))
        return events


def formula_safe(value):
    if value is None: return ''
    if isinstance(value, str) and (value[:1] in ('\t', '\r', '\n') or value.lstrip(' \t\r\n')[:1] in ('=', '+', '-', '@')):
        return "'"+value
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
