"""Background laptop counterpart of the shared visible/native reference rules."""
from .store import FIELDS, iso, timestamp


def derive(row, now):
    packet, settings = row['payload'], row['settings']
    values = dict.fromkeys(FIELDS)
    measured = timestamp(row['timestamp'], now+10**15)
    received = timestamp(row['receivedAt'], now+10**15)
    fresh = -5000 <= now-measured <= 30000 and -5000 <= now-received <= 30000
    revision = packet.get('config_revision')
    if settings is not None and isinstance(revision, (int, float)) and not isinstance(revision, bool) and int(revision) == revision:
        raw = packet.get('raw', {}); health = packet.get('sensor_health', {})
        for field in FIELDS:
            if not settings['enabled'].get(field) or health.get(field, '') not in ('', 'ok', 'uncalibrated', 'unknown'): continue
            if field in ('ph', 'turbidity'):
                mv, adc, points = raw.get(field+'_mv'), raw.get(field+'_adc'), settings.get(field)
                if mv is None or not 150 <= mv <= 3050 or (adc is not None and not 5 < adc < 4090) or not points: continue
                for a, b in zip(points, points[1:]):
                    if a['mv'] <= mv <= b['mv']:
                        values[field] = a['value']+(mv-a['mv'])*(b['value']-a['value'])/(b['mv']-a['mv']); break
            elif field == 'temperature':
                value = raw.get('temperature_c')
                if value is not None and -55 <= value+settings['temperature_offset'] <= 125: values[field] = value+settings['temperature_offset']
            else:
                distance, level = raw.get('distance_cm'), settings.get('level')
                if distance is not None and level and level['minimum'] <= distance <= min(level['maximum'], level['reference']): values[field] = level['reference']-distance
    return {'values': values, 'fresh': fresh, 'time': measured, 'revision': packet.get('config_revision'), 'station': row['deviceId'], 'sample': packet.get('sample_id', str(row['id']))}


def evaluate(rows, watch, now):
    if not rows: return {'signals': [], 'fresh': False, 'sample': '', 'rate': None}
    records = [derive(row, now) for row in rows]
    current = records[0]; values = current['values']; signals = []
    settings = {'elevated': 70, 'warning': 100, 'rise_limit': 10} | (watch or {})
    def add(kind, level, title, detail): signals.append(dict(kind=kind, level=level, title=title, detail=detail))
    rate = None
    tail = records[:5]
    if len(tail) == 5 and current['fresh'] and all(row['values']['water_level'] is not None and row['revision'] == current['revision'] and row['station'] == current['station'] for row in tail) and all(a['time']-b['time'] <= 30000 for a, b in zip(tail, tail[1:])) and tail[0]['time']-tail[4]['time'] >= 8000:
        xs = [(row['time']-tail[4]['time'])/1000 for row in tail]; ys = [row['values']['water_level'] for row in tail]
        denominator = 5*sum(x*x for x in xs)-sum(xs)**2
        if denominator > 0: rate = round((5*sum(x*y for x, y in zip(xs, ys))-sum(xs)*sum(ys))/denominator*60, 2)
    if current['fresh']:
        height = values['water_level']
        if height is not None and height >= settings['warning']: add('water_warning', 3, 'Water height needs attention', f'{height:.1f} cm is at or above your warning setting. Check the physical water height now.')
        if rate is not None and rate >= settings['rise_limit']: add('water_rise', 3, 'Water is rising quickly', f'{rate:.1f} cm/min across five same-calibration readings. Check the station and water height.')
        if height is not None and settings['elevated'] <= height < settings['warning']: add('water_watch', 2, 'Watch the water height', f'{height:.1f} cm is at or above your watch setting.')
        for field, low, high, name in [('ph', 6.5, 8.5, 'Acidity'), ('turbidity', 0, 50, 'Cloudiness'), ('temperature', 20, 32, 'Temperature')]:
            if values[field] is not None and not low <= values[field] <= high: add(field+'_reference', 1, name+' has changed', name+' is outside the prototype reference. Inspect the sensor and water conditions; this does not identify pollution.')
        missing = sum(value is None for value in values.values())
        if missing: add('sensor_health', 1, 'Some sensors need checking', f'{missing} readings are unavailable. Check connections and calibration. Any known water-height warning still matters.')
    else: add('connection', 1, 'Fresh river readings are missing', 'Check that the station and laptop share Wi-Fi and monitoring is active. Saved readings cannot describe current conditions.')
    evidence = {kind: 'unknown' for kind in ('water_warning', 'water_watch', 'water_rise', 'ph_reference', 'turbidity_reference', 'temperature_reference', 'sensor_health', 'connection')}
    if current['fresh']:
        evidence['connection'] = 'clear'
        evidence['sensor_health'] = 'clear'
        if values['water_level'] is not None:
            evidence['water_warning'] = evidence['water_watch'] = 'clear'
            if values['water_level'] >= settings['warning']: evidence['water_watch'] = 'unknown'
        if rate is not None: evidence['water_rise'] = 'clear'
        for field in ('ph', 'turbidity', 'temperature'):
            if values[field] is not None: evidence[field+'_reference'] = 'clear'
    for signal in signals: evidence[signal['kind']] = 'active'
    return {'signals': signals, 'evidence': evidence, 'fresh': current['fresh'], 'sample': current['sample'], 'rate': rate,
            'measuredAt': iso(current['time']), 'calibrationRevision': current['revision']}


def apply(previous, evaluation, now):
    state = previous or {'conditions': {}}
    conditions = state.setdefault('conditions', {}); events = []
    sample = evaluation['sample']; new_sample = sample != state.get('sample', '')
    segment = [evaluation.get('calibrationRevision'), evaluation.get('watchRevision')]
    changed_segment = state.get('segment') != segment
    if changed_segment:
        if any(c.get('active') for c in conditions.values()):
            events.append({'kind': 'settings', 'phase': 'settings_changed', 'level': 1, 'title': 'Settings changed — recheck needed', 'detail': 'A calibration or watch setting changed. This is not evidence of river recovery.', 'timestamp': iso(now), 'sample': sample})
        for kind, old in conditions.items():
            if kind not in ('connection', 'sensor_health'):
                old['clearCount'] = 0
                if old['active']: old['recheck'] = True
        state['segment'] = segment
    active = set()
    for signal in evaluation['signals']:
        kind = signal['kind']; active.add(kind); old = conditions.get(kind)
        if not old or not old['active'] or old['level'] < signal['level'] or (changed_segment and kind not in ('connection', 'sensor_health')):
            events.append(signal | {'phase': 'active', 'timestamp': iso(now), 'sample': sample})
        conditions[kind] = {'active': True, 'level': signal['level'], 'clearCount': 0, 'title': signal['title'], 'detail': signal['detail'], 'measuredAt': evaluation.get('measuredAt'), 'lastKnown': False, 'recheck': old.get('recheck', False) if old and old['active'] else False}
    for kind, old in conditions.items():
        if old['active'] and kind not in active:
            old['lastKnown'] = True
    if new_sample and evaluation['fresh']:
        for kind, old in conditions.items():
            if kind in active or not old['active']: continue
            evidence = evaluation.get('evidence', {}).get(kind)
            if kind == 'monitoring': evidence = evaluation.get('evidence', {}).get('sensor_health')
            if evidence != 'clear':
                old['clearCount'] = 0
                continue
            old['clearCount'] += 1
            if old['clearCount'] >= 3:
                old['active'] = False
                recheck = old.get('recheck', False)
                old['recheck'] = False
                events.append({'kind': kind, 'phase': 'rechecked' if recheck else 'recovered', 'level': 0, 'title': 'Fresh readings checked against updated settings' if recheck else 'Reading check returned within its reference', 'detail': 'Three fresh readings do not trigger this condition under the current settings. '+('Settings changed; this does not show an environmental improvement. ' if recheck else '')+'This does not establish water safety.', 'timestamp': iso(now), 'sample': sample})
    state['sample'] = sample
    for event in events:
        event.update({key: evaluation.get(key) for key in ('measuredAt', 'calibrationRevision', 'watchRevision', 'watchSettings')})
        event['evaluatedAt'] = iso(now)
        event['provenance'] = 'captured'
    return state, events
