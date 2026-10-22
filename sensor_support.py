"""Sensor diagnostics and deterministic, auditable observation reports."""
import json
from datetime import datetime, timezone
import pandas as pd
from river_status import overview, ordered, effective_row

NAMES={'ph':'Acidity','turbidity':'Cloudiness','temperature':'Temperature','water_level':'Water level'}
HEALTH={'ok':'Reading received','missing':'No sensor response','uncalibrated':'Calibration needed','out_of_range':'Outside calibrated / distance range','disabled':'Not enabled in firmware','timeout':'No echo received','adc_limit':'Check analog input / voltage divider'}

def decode(value):
    if not isinstance(value,str): return {}
    try:
        result=json.loads(value)
        return result if isinstance(result,dict) else {}
    except ValueError: return {}

def sensor_health(row):
    health=decode(row.get('sensor_health_json'))
    return [{'Sensor':label,'State':HEALTH.get(health.get(key),'No reading' if pd.isna(row.get(key)) else 'Received · verification unknown'),
             'Value available':'Yes' if pd.notna(row.get(key)) else 'No'} for key,label in NAMES.items()]

def observation_report(frame,elevated=70,warning=100,rise_limit=10):
    if frame.empty: return 'No observations available.'
    frame=ordered(frame)
    frame=pd.DataFrame([effective_row(row) for row in frame.to_dict('records')])
    last=frame.iloc[-1]
    state=overview(frame,elevated,warning,rise_limit)
    lines=['RiverGuard observation report',f'Generated UTC: {datetime.now(timezone.utc).isoformat()}',
           f'Station: {last.device_id}',f'Source: {last.source}',f'Samples in selected window: {len(frame)}',
           f'Latest measurement: {last.timestamp}',f'Calibration verified: {bool(last.calibrated)}',
           f'Current status: {state["title"]}',state['reason'],f'Next step: {state["action"]}','',
           'Observed measurements (missing values excluded from ranges):']
    for key,unit in [('ph','pH'),('turbidity','NTU'),('temperature','°C'),('water_level','cm')]:
        values=frame[key].dropna()
        lines.append(f'{NAMES[key]}: no calibrated readings' if values.empty else f'{NAMES[key]}: range {values.min():.2f}–{values.max():.2f} {unit}; {len(values)} available, {len(frame)-len(values)} missing')
    lines+=['',f'Water-level watch / warning settings: {elevated:g} / {warning:g} cm; rise {rise_limit:g} cm/min',
            'Historical signals are evaluated using the current station threshold settings; changing settings changes that interpretation.',
            'Sensor health:']+[f'{r["Sensor"]}: {r["State"]}' for r in sensor_health(last)]
    lines+=['','Reference ranges and anomaly detection are experimental. No water-safety, pollution-cause, official WQI or flood prediction is established. Raw values are separate from calibrated readings in the CSV export.']
    return '\n'.join(lines)
