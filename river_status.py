"""One deterministic signal policy for overview, historical alerts and reports."""
import json
from collections import deque
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REFERENCE_FIELDS = {'ph': ('Acidity', 6.5, 8.5), 'turbidity': ('Cloudiness', 0, 50),
                    'temperature': ('Temperature', 20, 32)}
FAULTS = {'missing', 'timeout', 'adc_limit', 'disabled', 'out_of_range', 'uncalibrated'}


def ordered(frame):
    result = frame.copy()
    if result.empty:
        return result
    result['timestamp'] = pd.to_datetime(result.timestamp, utc=True, format='mixed')
    return result.sort_values(['timestamp'] + (['id'] if 'id' in result else []), kind='stable')


def calibration_segments(frame):
    """Break at every chronological revision/datum transition, including rollbacks."""
    result = ordered(frame)
    if result.empty:
        result['segment'] = pd.Series(dtype='str')
        return result
    keys = result[['device_id']].copy()
    for name in ['config_revision', 'calibration_id']:
        keys[name] = result[name].fillna('').astype(str) if name in result else ''
    columns = ['config_revision', 'calibration_id']
    changed = keys[columns].ne(keys.groupby('device_id', sort=False)[columns].shift()).any(axis=1)
    changes = changed.groupby(result.device_id, sort=False).cumsum()
    result['segment'] = result.device_id.astype(str) + ':' + changes.astype(str)
    return result


def effective_row(row):
    result = row.copy()
    raw_health = result.get('sensor_health_json', '{}')
    try:
        health = json.loads(raw_health) if isinstance(raw_health, str) else {}
    except (ValueError, TypeError):
        health = {}
    if not isinstance(health, dict):
        health = {}
    for field in list(REFERENCE_FIELDS) + ['water_level']:
        if health.get(field) in FAULTS:
            result[field] = None
            result['calibrated'] = False
    return result


def observed_rise(frame):
    if frame.empty:
        return None
    levels = calibration_segments(frame)
    levels = levels[levels.device_id == levels.iloc[-1].device_id]
    levels = levels[levels.segment == levels.iloc[-1].segment].copy()
    if pd.isna(effective_row(levels.iloc[-1]).get('water_level')):
        return None
    levels['water_level'] = [effective_row(row).get('water_level') for _, row in levels.iterrows()]
    levels = levels.dropna(subset=['water_level'])
    levels = levels[levels.timestamp >= levels.timestamp.iloc[-1] - pd.Timedelta(seconds=30)]
    if len(levels) < 5:
        return None
    seconds = (levels.timestamp - levels.timestamp.iloc[0]).dt.total_seconds().to_numpy()
    if seconds[-1] < 8:
        return None
    return float(np.polyfit(seconds, levels.water_level.to_numpy(dtype=float), 1)[0] * 60)


def rise_rates(frame):
    """Linear-time rolling fits for complete historical signal evaluation."""
    frame = calibration_segments(frame)
    if not frame.empty and frame.device_id.nunique() > 1:
        rates = {}
        for _, group in frame.groupby('device_id', sort=False):
            rates.update(zip(group.index, rise_rates(group)))
        return [rates[index] for index in frame.index]
    rates = []
    previous = None
    samples = deque()
    sx = sy = sxx = sxy = 0.
    origin = 0.
    for row in frame.to_dict('records'):
        stamp = row['timestamp'].timestamp()
        if row['segment'] != previous:
            samples.clear()
            sx = sy = sxx = sxy = 0.
            origin = stamp
            previous = row['segment']
        x = stamp - origin
        while samples and x - samples[0][0] > 30:
            old_x, old_y = samples.popleft()
            sx -= old_x; sy -= old_y; sxx -= old_x * old_x; sxy -= old_x * old_y
        if x > 3600:
            # Rebase long histories so subtracting large squared timestamps does
            # not destroy the precision of a short-window slope.
            shift = samples[0][0] if samples else x
            samples = deque((old_x - shift, old_y) for old_x, old_y in samples)
            origin += shift
            x -= shift
            sx = sum(item[0] for item in samples); sy = sum(item[1] for item in samples)
            sxx = sum(item[0] ** 2 for item in samples); sxy = sum(item[0] * item[1] for item in samples)
        value = effective_row(row).get('water_level')
        if pd.notna(value):
            y = float(value)
            samples.append((x, y))
            sx += x; sy += y; sxx += x * x; sxy += x * y
        count = len(samples)
        denominator = count * sxx - sx * sx
        rate = None
        if pd.notna(value) and count >= 5 and x - samples[0][0] >= 8 and denominator > 1e-9:
            rate = float((count * sxy - sx * sy) / denominator * 60)
        rates.append(rate)
    return rates


def signal_evaluation(frame, elevated=70, warning=100, rise_limit=10, *, now=None, historical=False):
    """Use one policy; historical signals ignore wall-clock freshness only."""
    frame = ordered(frame)
    if frame.empty:
        return dict(tone='muted', title='Waiting for a reading', reason='No measurements received yet.',
                    action='Connect the station to begin.', flood='No reading', rate=None, age=None,
                    missing=[item[0] for item in REFERENCE_FIELDS.values()] + ['Water level'], fresh=False, signals=[])
    return evaluate_measurement(frame.iloc[-1], observed_rise(frame), elevated, warning, rise_limit,
                                now=now, historical=historical)


def evaluate_measurement(row, rate, elevated=70, warning=100, rise_limit=10, *, now=None, historical=False):
    """The shared per-measurement policy; rate comes from the same segmented fit."""
    row = effective_row(row)
    missing = [label for field, (label, _, _) in REFERENCE_FIELDS.items() if pd.isna(row.get(field))]
    if pd.isna(row.get('water_level')):
        missing.append('Water level')
    changed = [(field, label) for field, (label, low, high) in REFERENCE_FIELDS.items()
               if pd.notna(row.get(field)) and not low <= row[field] <= high]
    age = ((now or datetime.now(timezone.utc)) - pd.Timestamp(row['timestamp']).to_pydatetime()).total_seconds()
    fresh = -5 <= age <= 30
    level = row.get('water_level')
    flood = ('No reading' if pd.isna(level) else 'Warning' if level >= warning or (rate is not None and rate >= rise_limit)
             else 'Elevated' if level >= elevated else 'Below watch level')
    signals = []
    if historical or fresh:
        if pd.notna(level) and level >= elevated:
            severity = 'Warning' if level >= warning else 'Elevated'
            signals.append(dict(kind='level', severity=severity, title='Water level above warning' if severity == 'Warning' else 'Water level above watch',
                                explanation=f'Water level {level:.1f} cm crossed the current demonstration {severity.lower()} setting.',
                                field='water_level', pattern='absolute-level'))
        if rate is not None and rate >= rise_limit:
            signals.append(dict(kind='rise', severity='Warning', title='Water is rising quickly',
                                explanation=f'Observed rise {rate:.1f} cm/min crossed the current {rise_limit:g} cm/min demonstration setting.',
                                field='water_level', pattern='rise-rate'))
        for field, label in changed:
            signals.append(dict(kind='threshold', severity='Review', title=f'{label} outside the reference',
                                explanation=f'{label} crossed a demonstration reference range. This is not confirmed pollution.',
                                field=field, pattern=field))
        ai = pd.notna(row.get('anomaly')) and bool(row.get('anomaly'))
        if ai and all(pd.notna(row.get(field)) for field in REFERENCE_FIELDS):
            signals.append(dict(kind='pattern', severity='Review', title='Unusual combination of readings',
                                explanation=str(row.get('explanation') or 'The experimental AI flagged this sample. Not confirmed pollution.'),
                                field=None, pattern='synthetic-baseline'))
    provisional = row.get('source') == 'esp32' and not bool(row.get('calibrated', False))
    if not historical and age < -5:
        state = ('muted', 'Check the station clock', 'The measurement time is ahead of this laptop.', 'Synchronize the station clock before interpreting conditions.')
    elif not historical and age > 30:
        if flood == 'Warning':
            state = ('watch', 'Last-known water-level warning',
                     'The last sample crossed a water-level warning setting, but is over 30 seconds old. Current conditions are unknown.',
                     'Reconnect the station and verify a fresh water-level measurement.')
        else:
            state = ('muted', 'Waiting for a fresh reading', 'The last sample is over 30 seconds old.', 'Check the station connection before interpreting conditions.')
    elif flood == 'Warning':
        reason = 'The level or its rise rate crossed a demonstration warning threshold.'
        if missing:
            reason += ' Other sensor readings are missing.'
        if provisional:
            reason += ' This reading is provisional.'
        state = ('alert', 'Water level needs attention', reason, 'Review the water-level trend and verify the measurement.')
    elif missing:
        state = ('muted', 'Part of the picture is missing', ', '.join(missing) + ' readings are unavailable.', 'Check the missing sensors; available readings are shown below.')
    elif provisional:
        state = ('watch', 'Calibrate the station first', 'These sensor readings are still provisional.', 'Verify sensor calibration before interpreting river conditions.')
    elif changed or any(item['kind'] == 'pattern' for item in signals):
        reason = 'Changes in ' + ', '.join(label.lower() for _, label in changed) + '.' if changed else 'The AI found an unusual combination of readings.'
        state = ('alert', 'Unusual signals detected', reason, 'Compare the recent trend and check the sensors. This is not confirmed pollution.')
    elif flood == 'Elevated':
        state = ('watch', 'Keep an eye on the water', 'The level crossed the elevated demonstration threshold.', 'Watch the water-level trend for further changes.')
    else:
        state = ('calm', 'No unusual signals', 'Readings are within the prototype’s reference conditions.', 'Keep monitoring. No demonstration thresholds are currently crossed.')
    return dict(zip(['tone', 'title', 'reason', 'action'], state)) | dict(flood=flood, rate=rate, age=age,
                                                                         missing=missing, fresh=fresh, signals=signals)


def overview(frame, elevated=70, warning=100, rise_limit=10):
    return signal_evaluation(frame, elevated, warning, rise_limit)
