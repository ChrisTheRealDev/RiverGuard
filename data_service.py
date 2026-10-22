"""Station-scoped data contracts shared by the API, UI and exports."""
import base64
import csv
import io
import json
import math
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import core
from charting import summarize, group_alerts
from river_status import signal_evaluation, calibration_segments, ordered, effective_row, evaluate_measurement, rise_rates

UNITS = {'ph': 'pH', 'turbidity': 'NTU', 'temperature': '°C', 'water_level': 'cm'}
DEFAULT_THRESHOLDS = {'elevated': 70., 'warning': 100., 'rise_limit': 10.}


def _scope(source, device_id=None):
    if source not in ('simulation', 'esp32'):
        raise ValueError('Unknown data source.')
    if device_id is not None and (not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 80):
        raise ValueError('Choose a valid station ID.')


def _json(value):
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if value is None:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _reading(row):
    result = _json(effective_row(pd.Series(dict(row))).to_dict())
    for column, name in [('raw_json', 'raw'), ('sensor_health_json', 'sensor_health')]:
        try:
            result[name] = json.loads(result.get(column) or '{}')
            if not isinstance(result[name], dict):
                result[name] = {}
        except (ValueError, TypeError):
            result[name] = {}
    result['calibrated'] = bool(result.get('calibrated'))
    return result


def _thresholds(con, source, device_id):
    row = con.execute('SELECT revision,settings FROM station_thresholds WHERE source=? AND device_id=? ORDER BY revision DESC LIMIT 1', (source, device_id)).fetchone()
    return (json.loads(row[1]) | {'revision': row[0]}) if row else DEFAULT_THRESHOLDS | {'revision': 0}


def stations(source):
    _scope(source)
    with core.connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('''SELECT * FROM (
            SELECT *,MAX(received_at) OVER (PARTITION BY device_id) AS last_transmission,
                ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY measured_ms DESC,id DESC) AS position
            FROM readings WHERE source=?) WHERE position=1 ORDER BY device_id''', (source,)).fetchall()
    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        item = _reading(row)
        age = (now - datetime.fromisoformat(item['timestamp'])).total_seconds()
        received_age = (now - datetime.fromisoformat(item['last_transmission'])).total_seconds()
        result.append(dict(device_id=item['device_id'], source=source, last_measured=item['timestamp'],
                           last_received=item['last_transmission'], fresh=-5 <= age <= 30, connected=-5 <= received_age <= 30,
                           calibrated=item['calibrated'], calibration_id=item.get('calibration_id'),
                           config_revision=item.get('config_revision'), sensor_health=item['sensor_health'],
                           available_sensors=[key for key in UNITS if item.get(key) is not None]))
    return result


def thresholds(source, device_id):
    _scope(source, device_id)
    with core.connect() as con:
        return _thresholds(con, source, device_id)


def save_thresholds(source, device_id, settings, expected_revision):
    _scope(source, device_id)
    if not isinstance(settings, dict) or set(settings) - set(DEFAULT_THRESHOLDS) - {'revision'}:
        raise ValueError('Specify watch, warning and rise-rate settings.')
    try:
        values = {key: float(settings[key]) for key in DEFAULT_THRESHOLDS}
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError('All three threshold values are required.') from error
    if not all(math.isfinite(v) for v in values.values()) or not 0 <= values['elevated'] < values['warning'] or values['rise_limit'] <= 0:
        raise ValueError('Warning must be above the non-negative watch level, and rise rate must be positive.')
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise ValueError('Invalid threshold revision.')
    with core.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current = con.execute('SELECT MAX(revision) FROM station_thresholds WHERE source=? AND device_id=?', (source, device_id)).fetchone()[0] or 0
        if current != expected_revision:
            raise ValueError('Threshold settings changed in another window. Refresh before saving again.')
        con.execute('INSERT INTO station_thresholds VALUES (?,?,?,?,?)',
                    (source, device_id, current + 1, json.dumps(values), datetime.now(timezone.utc).isoformat()))
    return values | {'revision': current + 1}


def _encode_cursor(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')


def _decode_cursor(cursor):
    try:
        if not isinstance(cursor, str) or len(cursor) > 4096:
            raise ValueError()
        result = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError('Invalid page cursor. Refresh the list.') from error


def reading_page(source, device_id, cursor=None, limit=50, *, since=None, until=None):
    _scope(source, device_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError('Page size must be between 1 and 200.')
    time_filter = {'since': core.measured_millis(since) if since is not None else None,
                   'until': core.measured_millis(until) if until is not None else None}
    if time_filter['since'] is not None and time_filter['until'] is not None and time_filter['since'] > time_filter['until']:
        raise ValueError('Start time must be before end time.')
    clauses = ['source=?', 'device_id=?']; args = [source, device_id]
    for key, operator in [('since', '>='), ('until', '<=')]:
        if time_filter[key] is not None:
            clauses.append(f'measured_ms{operator}?'); args.append(time_filter[key])
    where = ' AND '.join(clauses)
    with core.connect() as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        if cursor:
            page = _decode_cursor(cursor)
            if page.get('source') != source or page.get('device_id') != device_id or page.get('times') != time_filter:
                raise ValueError('Page cursor belongs to a different station or time range.')
            if not {'anchor','last_id','last_ms'}.issubset(page) or not all(type(page.get(key)) is int for key in ['anchor', 'last_id']) or not (page.get('last_ms') is None or type(page['last_ms']) is int):
                raise ValueError('Invalid page cursor.')
            anchor = page['anchor']
        else:
            page = None
            anchor = con.execute('SELECT COALESCE(MAX(id),0) FROM readings WHERE ' + where, args).fetchone()[0]
        base = where + ' AND id<=?'; base_args = args + [anchor]
        total = con.execute('SELECT COUNT(*) FROM readings WHERE ' + base, base_args).fetchone()[0]
        if page:
            if page['last_ms'] is None:
                base += ' AND measured_ms IS NULL AND id<?'
                base_args += [page['last_id']]
            else:
                base += ' AND (measured_ms<? OR (measured_ms=? AND id<?) OR measured_ms IS NULL)'
                base_args += [page['last_ms'], page['last_ms'], page['last_id']]
        rows = con.execute('SELECT * FROM readings WHERE ' + base + ' ORDER BY measured_ms DESC,id DESC LIMIT ?', base_args + [limit + 1]).fetchall()
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit and visible:
        last = visible[-1]
        next_cursor = _encode_cursor(dict(source=source, device_id=device_id, times=time_filter, anchor=anchor,
                                          last_ms=last['measured_ms'], last_id=last['id']))
    return {'items': [_reading(row) for row in visible], 'total': total, 'next_cursor': next_cursor}


def _events(frame, settings, grouped=True):
    if frame.empty:
        return []
    frame = calibration_segments(frame)
    events = []
    for row, rate in zip(frame.to_dict('records'), rise_rates(frame)):
        evaluated = evaluate_measurement(row, rate, **{key: settings[key] for key in DEFAULT_THRESHOLDS}, historical=True)
        if not grouped and evaluated['signals']:
            signals = evaluated['signals']
            severity = max((signal['severity'] for signal in signals), key={'Review':0,'Elevated':1,'Warning':2}.get)
            events.append(dict(id=f'sample:{int(row["id"])}', reading_id=int(row['id']), timestamp=row['timestamp'].isoformat(),
                               device_id=row['device_id'], segment=row['segment'], count=1,
                               severity=severity, kind=signals[0]['kind'] if len(signals)==1 else 'multiple',
                               title=signals[0]['title'] if len(signals)==1 else f'{len(signals)} signals in this sample',
                               explanation=' '.join(signal['explanation'] for signal in signals), signals=signals,
                               settings_revision=settings['revision'], interpretation='Evaluated using current station threshold settings.'))
            continue
        for signal in evaluated['signals']:
            events.append(signal | dict(id=f'{int(row["id"])}:{signal["kind"]}:{signal.get("field") or "all"}',
                                        reading_id=int(row['id']), timestamp=row['timestamp'].isoformat(), device_id=row['device_id'],
                                        segment=row['segment'], count=1, settings_revision=settings['revision'],
                                        interpretation='Evaluated using current station threshold settings.'))
    return group_alerts(events) if grouped else events


def alert_page(source, device_id, cursor=None, limit=50, *, grouped=True):
    _scope(source, device_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError('Page size must be between 1 and 200.')
    if not isinstance(grouped, bool):
        raise ValueError('Choose grouped episodes or individual flagged samples.')
    frame = core.history(source, device_id=device_id)
    settings = thresholds(source, device_id)
    anchor = int(frame.id.max()) if not frame.empty else 0
    before = None
    if cursor:
        page = _decode_cursor(cursor)
        if page.get('source') != source or page.get('device_id') != device_id or page.get('revision') != settings['revision'] or page.get('grouped',True) != grouped:
            raise ValueError('Alert settings or station changed. Refresh the list.')
        if type(page.get('anchor')) is not int or type(page.get('offset')) is not int or page['offset'] < 0:
            raise ValueError('Invalid alert page cursor.')
        anchor = page['anchor']; before = page['offset']
        frame = frame[frame.id <= anchor]
    items = list(reversed(_events(frame, settings, grouped=grouped)))
    offset = before or 0
    visible = items[offset:offset + limit]
    next_cursor = _encode_cursor(dict(source=source, device_id=device_id, revision=settings['revision'], anchor=anchor,
                                      offset=offset + limit, grouped=grouped)) if offset + limit < len(items) else None
    return {'items': _json(visible), 'total': len(items), 'next_cursor': next_cursor,
            'settings_revision': settings['revision'], 'grouped':grouped,
            'interpretation': 'Evaluated using current station threshold settings.'}


def overview_data(source, device_id, field='ph', window='10'):
    _scope(source, device_id)
    if field not in UNITS:
        raise ValueError('Choose one of the four sensor measurements.')
    minutes = {'10': 10, '30': 30, '60': 60, '1h': 60, '24h': 1440, '1440': 1440, 'all': None}.get(str(window), 'invalid')
    if minutes == 'invalid':
        raise ValueError('Unknown chart window.')
    with core.connect() as con:
        # Status, cards, chart and settings describe one consistent SQLite
        # snapshot even when a new sensor sample arrives during this request.
        con.execute('BEGIN')
        settings = _thresholds(con, source, device_id)
        recent = pd.read_sql_query('SELECT * FROM (SELECT * FROM readings WHERE source=? AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 2) ORDER BY measured_ms,id', con, params=(source, device_id))
        latest = _reading(recent.iloc[-1]) if not recent.empty else None
        previous = _reading(recent.iloc[-2]) if len(recent) > 1 else None
        cutoff = int(recent.iloc[-1].measured_ms) - minutes * 60000 if minutes is not None and not recent.empty else None
        query = 'SELECT * FROM readings WHERE source=? AND device_id=?'
        params = [source, device_id]
        if cutoff is not None:
            query += ' AND measured_ms>=?'; params.append(cutoff)
        frame = pd.read_sql_query(query+' ORDER BY measured_ms,id', con, params=params)
    summary, seconds = summarize(frame, field)
    points = [{key: row[key] for key in ['timestamp', 'mean', 'min', 'max', 'count', 'segment']} for _, row in summary.iterrows()]
    status_frame = frame[frame.measured_ms >= int(recent.iloc[-1].measured_ms) - 30000] if latest else frame
    status = signal_evaluation(status_frame, **{key: settings[key] for key in DEFAULT_THRESHOLDS})
    events = list(reversed(_events(frame, settings)))
    return _json(dict(status=status, latest=latest, previous=previous,
                      chart=dict(points=points, seconds=seconds, field=field, unit=UNITS[field]),
                      alerts=dict(items=events[:3], total=len(events), settings_revision=settings['revision'],
                                  interpretation='Evaluated using current station threshold settings.'),
                      settings=settings, station=dict(source=source, device_id=device_id), updated_at=datetime.now(timezone.utc).isoformat()))


def _csv_cell(value):
    if isinstance(value, str) and (value.startswith(('\t', '\r', '\n')) or value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def export_csv(source, device_id):
    """Stream every station row in one read snapshot; never cap or coerce numbers."""
    _scope(source, device_id)
    # Starlette advances a synchronous streaming iterator in its worker pool;
    # successive (serial) next() calls need not run on the same OS thread.
    with core.connect(check_same_thread=False) as con:
        con.execute('BEGIN')
        stored = con.execute('SELECT revision,settings FROM station_thresholds WHERE source=? AND device_id=? ORDER BY revision DESC LIMIT 1', (source, device_id)).fetchone()
        settings = json.loads(stored[1]) if stored else DEFAULT_THRESHOLDS
        metadata = [settings['elevated'], settings['warning'], settings['rise_limit'], stored[0] if stored else 0,
                    'Historical interpretation uses current station threshold settings at export.']
        cursor = con.execute('SELECT * FROM readings WHERE source=? AND device_id=? ORDER BY measured_ms,id', (source, device_id))
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([column[0] for column in cursor.description] + ['applied_watch_cm', 'applied_warning_cm',
                         'applied_rise_cm_per_min', 'threshold_revision', 'threshold_interpretation'])
        yield output.getvalue(); output.seek(0); output.truncate(0)
        while rows := cursor.fetchmany(500):
            writer.writerows([_csv_cell(value) for value in list(row) + metadata] for row in rows)
            yield output.getvalue(); output.seek(0); output.truncate(0)
