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
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum or not math.isfinite(value) or (integer and int(value) != value):
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


def validate_draft(value):
    """Allow unfinished numbers, but never malformed structures in restored forms."""
    if value is None: return
    keys(value, ('revision', 'settings'), ('revision', 'settings'))
    number(value['revision'], 0, 2147483647, True)
    settings = value['settings']
    keys(settings, DEFAULTS, DEFAULTS)
    keys(settings['enabled'], FIELDS, FIELDS)
    for flag in settings['enabled'].values(): boolean(flag)
    boolean(settings['verified'])
    def incomplete(n):
        if n is not None: number(n, -1e12, 1e12)
    incomplete(settings['temperature_offset'])
    if settings['level'] is not None:
        keys(settings['level'], ('reference', 'minimum', 'maximum'), ('reference', 'minimum', 'maximum'))
        for n in settings['level'].values(): incomplete(n)
    for field in ('ph', 'turbidity'):
        points = settings[field]
        if points is not None:
            if not isinstance(points, list) or len(points) > 5: raise Problem(422, 'Invalid calibration draft points.')
            for point in points:
                keys(point, ('mv', 'value'), ('mv', 'value'))
                incomplete(point['mv']); incomplete(point['value'])


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
            from .migrations import migrate
            migrate(db, self.path)

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

    def public_state(self, key, value=None, write=False):
        """Only user preferences/drafts are reachable through the generic bridge."""
        self.state_key(key)
        if key.startswith('alerts:') and not write:
            return self.get_state(key)
        if key == 'v2-preferences':
            if write:
                keys(value, ('source', 'deviceId', 'scenario', 'running'), ('source', 'deviceId'))
                self.scope(value['source'], value['deviceId'])
                if 'running' in value: boolean(value['running'])
                if 'scenario' in value: text(value['scenario'], 1, 80)
        elif key.startswith('draft:esp32:'):
            station(key[len('draft:esp32:'):])
            if write: validate_draft(value)
        else:
            raise Problem(403, 'This state is private to the monitoring service.')
        return self.set_state(key, value) if write else self.get_state(key)

    @staticmethod
    def validate_watch(settings):
        keys(settings, ('elevated', 'warning', 'rise_limit'), ('elevated', 'warning', 'rise_limit'))
        number(settings['elevated'], 0, 1000); number(settings['warning'], 0, 1000)
        number(settings['rise_limit'], .000001, 10000)
        if settings['elevated'] >= settings['warning']: raise Problem(422, 'Warning height must exceed watch height.')
        return settings

    def _watch(self, db, source, device, calibration_settings=None):
        row = db.execute('SELECT * FROM watch WHERE source=? AND device_id=?', (source, device)).fetchone()
        settings = json.loads(row['settings']) if row else {'elevated': 70, 'warning': 100, 'rise_limit': 10}
        valid = True
        try: self.validate_watch(settings)
        except Problem: valid = False
        if source == 'esp32':
            cfg = calibration_settings if calibration_settings is not None else self._settings(db, device)['settings']
            level = cfg.get('level')
            valid = valid and bool(level) and settings['warning'] <= level['reference'] - level['minimum']
        review = bool(row['needs_review']) if row else False
        return {'revision': row['revision'] if row else 0, 'settings': settings, 'valid': bool(valid and not review), 'needsReview': review}

    def get_watch(self, source, device):
        self.scope(source, device)
        with self.connect() as db: return self._watch(db, source, device)

    def alert_state(self, source, device):
        self.scope(source, device)
        if source == 'simulation': return {'conditions': []}
        with self.connect() as db:
            row = db.execute('SELECT ledger FROM alert_progress WHERE device_id=?', (device,)).fetchone()
        try:
            conditions = json.loads(row[0]).get('conditions', {}) if row else {}
            return {'conditions': [dict(kind=k, level=v['level'], title=v.get('title', 'Last known '+k.replace('_',' ')), detail=v.get('detail','Check fresh readings before assuming this condition has cleared.'), measuredAt=v.get('measuredAt'), lastKnown=v.get('lastKnown',True)) for k,v in conditions.items() if v['active']]}
        except (ValueError, TypeError, AttributeError, KeyError):
            raise Problem(503, 'Monitoring state needs rechecking. Saved evidence is preserved.')

    def save_watch(self, source, device, expected, settings):
        self.scope(source, device); number(expected, 0, 2147483646, True); self.validate_watch(settings)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self._watch(db, source, device)
            if expected != old['revision']: raise Problem(409, 'Watch settings changed elsewhere. Reload them before saving; your edits are preserved.')
            if source == 'esp32':
                if not db.execute('SELECT 1 FROM stations WHERE device_id=?', (device,)).fetchone(): raise Problem(404, 'Register this station first.')
                level = self._settings(db, device)['settings']['level']
                if not level or settings['warning'] > level['reference']-level['minimum']:
                    raise Problem(422, 'Calibrate water distance first and choose watch levels within its measurable height.')
            db.execute('INSERT INTO watch VALUES (?,?,?,?,0) ON CONFLICT(source,device_id) DO UPDATE SET revision=excluded.revision,settings=excluded.settings,needs_review=0', (source, device, expected+1, encode(settings)))
            return self._watch(db, source, device)

    def register(self, device, rotate=False):
        station(device); boolean(rotate)
        token = secrets.token_hex(32)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            exists = db.execute('SELECT 1 FROM stations WHERE device_id=?', (device,)).fetchone()
            if device == 'demo-station' and not exists: raise Problem(422, 'This station ID is reserved for Demo. Choose a different ID.')
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
            if normalized['verified']:
                watch = self._watch(db, 'esp32', device, normalized)
                ack = db.execute('SELECT ack_revision FROM stations WHERE device_id=?', (device,)).fetchone()[0]
                if not watch['valid'] or ack != expected:
                    raise Problem(422, 'Save compatible watch levels and wait for the station to acknowledge calibration before verification.')
                from .signals import derive
                latest = db.execute("SELECT * FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 1", (device,)).fetchone()
                evidence = derive(self.row(latest), time.time()*1000) if latest else None
                if not evidence or not evidence['fresh'] or evidence['revision'] != expected or any(v is None for v in evidence['values'].values()):
                    raise Problem(422, 'Verification needs fresh usable readings from all four probes at the saved calibration revision. Check signals and try again.')
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
            # Paired browsers share this installation's demo. They can tick a
            # few milliseconds apart and even hold different scenario drafts.
            # The first accepted sample in each measurement-time slot wins;
            # another browser neither duplicates nor replaces that evidence.
            sample = 'demo-slot-'+str(measured//2000)
            if db.execute("SELECT 1 FROM readings WHERE source='simulation' AND device_id='demo-station' AND sample_id=?", (sample,)).fetchone():
                return {'stored': True, 'duplicate': True}
            return self._append(db, 'simulation', 'demo-station', payload, None, measured, sample)

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
            db.execute('BEGIN')
            ceiling = db.execute('SELECT COALESCE(MAX(id),0) FROM readings WHERE source=? AND device_id=?', (source, device)).fetchone()[0]
            policy = self._watch(db, source, device)
            event_ceiling = db.execute('SELECT COALESCE(MAX(id),0) FROM alert_events WHERE device_id=?', (device,)).fetchone()[0]
        def rows():
            yield ['id', 'source', 'device_id', 'timestamp', 'received_at', 'sample_id', 'config_revision', 'ph', 'turbidity', 'temperature', 'water_level', 'raw_json', 'settings_json', 'payload_json', 'export_watch_settings_json', 'alert_events_json']
            previous = 0
            while True:
                with self.connect() as db:
                    batch = db.execute('SELECT * FROM readings WHERE source=? AND device_id=? AND id>? AND id<=? ORDER BY id LIMIT 500', (source, device, previous, ceiling)).fetchall()
                    event_map = {}
                    if source == 'esp32':
                        for row in batch:
                            found = db.execute("SELECT event_json FROM alert_events WHERE device_id=? AND id<=? AND json_extract(event_json,'$.sample')=? ORDER BY id", (device, event_ceiling, row['sample_id'])).fetchall()
                            event_map[row['id']] = [json.loads(e[0]) for e in found]
                if not batch: return
                for row in batch:
                    packet = json.loads(row['payload']); demo = row['source'] == 'simulation'
                    from .signals import derive
                    values = packet if demo else derive(self.row(row), row['measured_ms'])['values']
                    yield [row['id'], row['source'], row['device_id'], row['timestamp'], row['received_at'], row['sample_id'], packet.get('config_revision'), *[values.get(field) for field in FIELDS], encode(packet.get('raw', {})), row['settings_json'], row['payload'], encode(policy), encode(event_map.get(row['id'], []))]
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
        station(device)
        events = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO alert_progress(device_id) VALUES (?)', (device,))
            progress = db.execute('SELECT * FROM alert_progress WHERE device_id=?', (device,)).fetchone()
            try:
                state = json.loads(progress['ledger'])
                if not isinstance(state, dict) or not isinstance(state.get('conditions', {}), dict): raise ValueError('ledger')
                if any(not isinstance(v, dict) or not isinstance(v.get('active'), bool) or type(v.get('clearCount', 0)) is not int or not 0 <= v.get('clearCount', 0) <= 3 or type(v.get('level')) is not int or not 0 <= v['level'] <= 3 for v in state.get('conditions', {}).values()): raise ValueError('conditions')
            except (ValueError, TypeError):
                db.execute('INSERT INTO quarantine(key,value,created) VALUES (?,?,?)', ('alert-progress:'+device, progress['ledger'], time.time()))
                state = {'conditions': {'monitoring': {'active': True, 'level': 2, 'clearCount': 0, 'lastKnown': True, 'title': 'Monitoring state needs rechecking', 'detail': 'Earlier warning state was unreadable. Three complete fresh readings are needed to recheck monitoring.', 'measuredAt': None}}}
                events.append({'kind':'monitoring', 'phase':'active', 'level':1, 'title':'Monitoring state needs rechecking', 'detail':'Unreadable internal state was preserved for inspection. Earlier warnings cannot be assumed recovered.', 'timestamp':iso(now), 'provenance':'unavailable'})
            last_id, current_ms, current_id = progress['last_id'], progress['current_ms'], progress['current_id']
            watch = self._watch(db, 'esp32', device)
            pending = db.execute("SELECT * FROM readings WHERE source='esp32' AND device_id=? AND id>? ORDER BY id LIMIT 500", (device, last_id)).fetchall()
            for row in pending:
                last_id = row['id']
                if (row['measured_ms'], row['id']) <= (current_ms, current_id): continue
                context = db.execute("SELECT * FROM readings WHERE source='esp32' AND device_id=? AND id<=? AND (measured_ms<? OR (measured_ms=? AND id<=?)) ORDER BY measured_ms DESC,id DESC LIMIT 5", (device, row['id'], row['measured_ms'], row['measured_ms'], row['id'])).fetchall()
                # Evaluate freshness as received, not after a busy worker catches up.
                evaluation = evaluate([self.row(r) for r in context], watch['settings'], timestamp(row['received_at'], now+10**15))
                evaluation.update(watchRevision=watch['revision'], watchSettings=watch['settings'])
                if not watch['valid']:
                    for kind in ('water_watch', 'water_warning', 'water_rise'):
                        if evaluation['evidence'][kind] == 'clear': evaluation['evidence'][kind] = 'unknown'
                state, additions = apply(state, evaluation, now)
                events.extend(additions)
                current_ms, current_id = row['measured_ms'], row['id']
            # Clock-driven connectivity is separate from per-packet processing.
            if current_id and (not pending or len(pending) < 500):
                latest = db.execute("SELECT * FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 5", (device,)).fetchall()
                evaluation = evaluate([self.row(r) for r in latest], watch['settings'], now)
                evaluation.update(watchRevision=watch['revision'], watchSettings=watch['settings'])
                if not watch['valid']:
                    for kind in ('water_watch', 'water_warning', 'water_rise'):
                        if evaluation['evidence'][kind] == 'clear': evaluation['evidence'][kind] = 'unknown'
                state, additions = apply(state, evaluation, now)
                events.extend(additions)
            db.execute('UPDATE alert_progress SET last_id=?,current_ms=?,current_id=?,ledger=? WHERE device_id=?', (last_id, current_ms, current_id, encode(state), device))
            # Retain a read-only internal diagnostic key for migration/debugging.
            db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('alert-status:'+device, encode(state)))
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
