"""Versioned station settings and raw-signal calibration, shared by API and UI."""
import json
import re
from datetime import datetime, timezone
from math import isfinite
from pydantic import BaseModel, Field, ConfigDict, model_validator
import core

FIELDS=['ph','turbidity','temperature','water_level']

class Point(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    mv: float = Field(ge=150,le=3050)
    value: float = Field(ge=0,le=10000)

class Level(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    reference: float = Field(gt=0,le=1000)
    minimum: float = Field(gt=0,le=1000)
    maximum: float = Field(gt=0,le=1000)
    @model_validator(mode='after')
    def bounds(self):
        if not self.minimum<self.reference<=self.maximum: raise ValueError('Reference must be above the minimum distance and at or below the maximum.')
        return self

class Settings(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    enabled: dict[str,bool] = Field(default_factory=lambda:dict.fromkeys(FIELDS,False))
    ph: list[Point] | None = Field(default=None,min_length=2,max_length=2)
    turbidity: list[Point] | None = Field(default=None,min_length=2,max_length=5)
    level: Level | None = None
    temperature_offset: float = Field(default=0,ge=-5,le=5)
    verified: bool = False
    @model_validator(mode='after')
    def validate_points(self):
        if set(self.enabled)!=set(FIELDS): raise ValueError('Specify all four sensor enabled states.')
        for name in ['ph','turbidity']:
            points=getattr(self,name)
            if points:
                points.sort(key=lambda p:p.mv)
                if any(b.mv-a.mv<1 for a,b in zip(points,points[1:])): raise ValueError('Calibration signals must be at least 1 mV apart.')
                if name=='ph' and (any(p.value>14 for p in points) or abs(points[0].value-points[1].value)<.1): raise ValueError('Use two different pH buffers between 0 and 14.')
                if name=='turbidity' and len({p.value for p in points})!=len(points): raise ValueError('Each NTU standard must have a different known value.')
        if self.verified and not (self.ph and self.turbidity and self.level and all(self.enabled.values())):
            raise ValueError('Verify only after enabling and calibrating all four sensors.')
        return self

def db():
    return core.connect()

def load(device_id,revision=None):
    with db() as con:
        if revision is None: row=con.execute('SELECT revision,settings,saved_at FROM station_settings WHERE device_id=? ORDER BY revision DESC LIMIT 1',(device_id,)).fetchone()
        else: row=con.execute('SELECT revision,settings,saved_at FROM station_settings WHERE device_id=? AND revision=?',(device_id,revision)).fetchone()
    return {'revision':row[0],'settings':json.loads(row[1]),'saved_at':row[2]} if row else {'revision':0,'settings':Settings().model_dump(),'saved_at':None}

def store(device_id,settings,expected_revision):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',device_id): raise ValueError('Use 1-80 letters, digits, hyphens or underscores for the station ID.')
    settings=Settings.model_validate(settings).model_dump()
    with db() as con:
        con.execute('BEGIN IMMEDIATE')
        current=con.execute('SELECT MAX(revision) FROM station_settings WHERE device_id=?',(device_id,)).fetchone()[0] or 0
        if current!=expected_revision: raise ValueError('Settings changed in another window. Refresh before saving again.')
        con.execute('INSERT INTO station_settings VALUES (?,?,?,?)',(device_id,current+1,json.dumps(settings,allow_nan=False),datetime.now(timezone.utc).isoformat()))
    return current+1

def interpolate(value,points):
    if value is None or not points: return None
    for a,b in zip(points,points[1:]):
        if a['mv']<=value<=b['mv']:
            return a['value']+(value-a['mv'])*(b['value']-a['value'])/(b['mv']-a['mv'])
    return None

def calibrate(payload):
    """Use the sample's acknowledged revision, never today's settings on old packets."""
    if payload.get('setup_protocol')!='remote-v1': return core.sanitize_legacy(payload)
    revision=payload.get('config_revision')
    record=load(payload['device_id'],revision) if revision is not None else load(payload['device_id'],0)
    if record['revision']!=(revision or 0): raise ValueError('Unknown station configuration revision; resync the station.')
    cfg=record['settings']; raw=payload.get('raw',{}); health={}; values={}
    faults=payload.get('sensor_health',{})
    for field in FIELDS:
        value=None
        if not cfg['enabled'][field]: state='disabled'
        elif faults.get(field) in ['missing','timeout','adc_limit','disabled','out_of_range']:
            state=faults[field]
        elif field in ['ph','turbidity']:
            mv=raw.get(field+'_mv'); adc=raw.get(field+'_adc')
            if mv is None: state='missing'
            elif not 150<=mv<=3050 or (adc is not None and not 5<adc<4090): state='adc_limit'
            else:
                value=interpolate(mv,cfg[field]); state='ok' if value is not None else 'uncalibrated' if not cfg[field] else 'out_of_range'
        elif field=='temperature':
            raw_temp=raw.get('temperature_c')
            value=None if raw_temp is None else raw_temp+cfg['temperature_offset']
            if value is not None and not -55<=value<=125: value=None
            state='ok' if value is not None else 'missing'
        else:
            distance=raw.get('distance_cm'); level=cfg['level']
            if distance is None: state='timeout'
            elif not level: state='uncalibrated'
            elif not level['minimum']<=distance<=level['maximum'] or distance>level['reference']: state='out_of_range'
            else: value=level['reference']-distance; state='ok'
        health[field]=state;values[field]=value
    return payload|values|{'sensor_health':health,'calibrated':cfg['verified'] and all(v is not None for v in values.values()),'calibration_id':f'app-r{record["revision"]}'}

def latest(device_id):
    rows=core.history('esp32',device_id=device_id,limit=1)
    return None if rows.empty else rows.iloc[-1]

def capture(device_id,field):
    from sensor_support import decode
    row=latest(device_id)
    if row is None: raise ValueError('Waiting for the first real station packet.')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(row.timestamp)).total_seconds()
    receipt_age=(datetime.now(timezone.utc)-datetime.fromisoformat(row.received_at)).total_seconds()
    if not -5<=age<=30 or not -5<=receipt_age<=30: raise ValueError('Signal is not fresh. Reconnect the station and check its clock before capturing.')
    value=decode(row.raw_json).get(field)
    if value is None or not isfinite(value): raise ValueError('No raw signal for this sensor yet. Enable it and check its connection.')
    health=decode(row.sensor_health_json)
    key='ph' if field.startswith('ph') else 'turbidity' if field.startswith('turbidity') else 'temperature' if field=='temperature_c' else 'water_level'
    if health.get(key) in ['adc_limit','missing','timeout','disabled']: raise ValueError('Sensor is not ready to capture. Check its connection and enabled state.')
    return float(value)
