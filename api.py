import logging
import json
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException, Depends, Request
from contextlib import asynccontextmanager
import security
import station_setup
from pydantic import BaseModel, Field, model_validator, AliasChoices, ConfigDict
from core import save, train, connect

logging.basicConfig(filename=str(__import__('pathlib').Path(__file__).parent / 'events.log'),level=logging.INFO)
@asynccontextmanager
async def lifespan(app):
    security.initialize()
    yield

app=FastAPI(title='RiverGuard AI sensor receiver', lifespan=lifespan)
app.add_middleware(security.RequestBodyLimit)
model=train()

class RawSensors(BaseModel):
    model_config=ConfigDict(extra='forbid')
    ph_adc: int | None = Field(default=None,ge=0,le=4095)
    ph_mv: float | None = Field(default=None,ge=0,le=3300,allow_inf_nan=False)
    turbidity_adc: int | None = Field(default=None,ge=0,le=4095)
    turbidity_mv: float | None = Field(default=None,ge=0,le=3300,allow_inf_nan=False)
    distance_cm: float | None = Field(default=None,ge=0,le=1000,allow_inf_nan=False)
    temperature_c: float | None = Field(default=None,ge=-55,le=125,allow_inf_nan=False)

class Reading(BaseModel):
    model_config=ConfigDict(extra='forbid')
    device_id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    sample_id: str | None = Field(default=None,min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9_.:-]+$')
    timestamp: datetime
    mode: Literal['hardware']='hardware'
    ph: float | None = Field(default=None,ge=0,le=14,allow_inf_nan=False)
    turbidity: float | None = Field(default=None,ge=0,le=10000,allow_inf_nan=False)
    temperature: float | None = Field(default=None,ge=-55,le=125,allow_inf_nan=False,validation_alias=AliasChoices('temperature','temperature_c'))
    water_level: float | None = Field(default=None,ge=0,le=10000,allow_inf_nan=False,validation_alias=AliasChoices('water_level','water_level_cm'))
    raw: RawSensors = Field(default_factory=RawSensors)
    sensor_health: dict[Literal['ph','turbidity','temperature','water_level'],Literal['ok','missing','uncalibrated','out_of_range','disabled','timeout','adc_limit']] = Field(default_factory=dict)
    calibration_id: str | None = Field(default=None,max_length=80)
    setup_protocol: Literal['remote-v1'] | None = None
    config_revision: int | None = Field(default=None,ge=0)
    tds_ppm: None = None  # Reserved; no unconfirmed TDS driver or conversions.
    ph_unit: Literal['pH']='pH'
    turbidity_unit: Literal['NTU']='NTU'
    temperature_unit: Literal['C']='C'
    water_level_unit: Literal['cm']='cm'
    calibrated: bool=False

    @model_validator(mode='before')
    @classmethod
    def raw_aliases(cls,data):
        if isinstance(data,dict):
            data=dict(data)
            if data.get('raw') is not None and not isinstance(data['raw'],dict): raise ValueError('Raw readings must be an object')
            raw=dict(data.get('raw') or {})
            for alias,key in [('turbidity_raw','turbidity_adc'),('distance_cm','distance_cm')]:
                if alias in data:
                    if key in raw and raw[key]!=data[alias]: raise ValueError('Conflicting raw readings')
                    raw[key]=data.pop(alias)
            data['raw']=raw
        return data

    @model_validator(mode='after')
    def validate_reading(self):
        if self.timestamp.tzinfo is None: raise ValueError('Timestamp must include timezone')
        self.device_id=self.device_id.strip()
        if not self.device_id: raise ValueError('Device ID cannot be blank')
        if (self.timestamp-datetime.now(timezone.utc)).total_seconds()>5: raise ValueError('Station clock is more than five seconds ahead. Resync NTP before sending readings.')
        if all(getattr(self,k) is None for k in ['ph','turbidity','temperature','water_level']) and all(v is None for v in self.raw.model_dump().values()) and not self.sensor_health:
            raise ValueError('At least one raw or calibrated measurement is required')
        return self

@app.get('/health')
def health(): return {'status':'ok','service':'riverguard-receiver','instance':__import__('os').environ.get('RIVERGUARD_INSTANCE','')}

@app.get('/api/v1/station-setup')
def station_setup_info(device_id=Depends(security.require_device)):
    return {'server_time':datetime.now(timezone.utc).isoformat(),'post_path':'/api/v1/readings',
            'recommended_interval_seconds':5,'stale_after_seconds':30,
            'units':{'ph':'pH','turbidity':'NTU','temperature':'C','water_level':'cm'},
            'missing_values':'Send null or omit disconnected sensors. Never send a made-up zero.',
            'sample_id':'Unique per sample, unchanged on retries (e.g. boot UUID plus counter).'}

@app.get('/api/v1/stations')
def stations(device_id=Depends(security.require_device)):
    with connect() as con:
        con.row_factory=__import__('sqlite3').Row
        rows=con.execute("SELECT *, (SELECT MAX(received_at) FROM readings WHERE source='esp32' AND device_id=?) AS last_transmission FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 1", (device_id,device_id)).fetchall()
    now=datetime.now(timezone.utc)
    return {'stations':[{'device_id':r['device_id'],'last_received':r['last_transmission'],
        'last_measured':r['timestamp'],'connected':-5<=(now-datetime.fromisoformat(r['last_transmission'])).total_seconds()<=30,
        'fresh':-5<=(now-datetime.fromisoformat(r['timestamp'])).total_seconds()<=30,
        'calibrated':bool(r['calibrated']),
        'calibration_id':r['calibration_id'],'sensor_health':json.loads(r['sensor_health_json'] or '{}'),
        'available_sensors':[k for k in ['ph','turbidity','temperature','water_level'] if r[k] is not None]} for r in rows]}

@app.post('/api/v1/readings',status_code=201)
def ingest(reading: Reading, device_id=Depends(security.require_device)):
    if reading.device_id!=device_id: raise HTTPException(403,'A station can only submit its own readings.')
    try:
        try: payload=station_setup.calibrate(reading.model_dump())
        except ValueError as error: raise HTTPException(409,str(error)) from error
        flag=save(payload, 'esp32', reading.device_id, reading.timestamp.isoformat(),payload['calibrated'],model,sample_id=reading.sample_id)
        logging.info('Reading accepted from %s',reading.device_id)
        return {'stored':True,'anomaly':flag}
    except Exception:
        logging.exception('Ingestion failed')
        raise

@app.get('/api/v1/device-config')
def device_config(device_id: str, authenticated_device=Depends(security.require_device)):
    if device_id!=authenticated_device: raise HTTPException(403,'A station can only retrieve its own settings.')
    record=station_setup.load(device_id)
    return {'device_id':device_id,'protocol':'remote-v1','revision':record['revision'],'enabled':record['settings']['enabled']}

class ConfigurationUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    settings: station_setup.Settings

@app.put('/api/v1/stations/{device_id}/configuration')
def configure_station(device_id: str, update: ConfigurationUpdate, session=Depends(security.require_session)):
    settings=update.settings.model_dump()
    record=station_setup.load(device_id)
    previous=record['settings']
    # Preserve the legacy owner's initial complete calibration declaration.
    # Editing an existing calibration requires a separate verification step.
    if record['revision']>0 and previous | {'verified':False} != settings | {'verified':False}:
        settings['verified']=False
    try: revision=station_setup.store(device_id,settings,update.expected_revision)
    except ValueError as error: raise HTTPException(409,str(error)) from error
    return {'saved':True,'revision':revision,'state':'waiting_for_station_acknowledgement'}
