from datetime import datetime, timezone, timedelta
import pandas as pd
from river_status import overview, observed_rise

def readings(**overrides):
    row=dict(timestamp=datetime.now(timezone.utc).isoformat(),device_id='demo',source='simulation',ph=7.1,turbidity=12,temperature=27,water_level=35,anomaly=0,calibrated=0)
    return pd.DataFrame([row|overrides])

def test_status_summarizes_changes_without_safety_claim():
    assert overview(readings())['tone']=='calm'
    assert overview(readings(ph=4.2))['title']=='Unusual signals detected'
    assert overview(readings(water_level=110))['flood']=='Warning'
    assert overview(readings(water_level=80))['tone']=='watch'

def test_missing_stale_and_uncalibrated_take_priority():
    assert overview(readings(ph=None))['tone']=='muted'
    old=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    assert overview(readings(timestamp=old,ph=4.2))['title']=='Waiting for a fresh reading'
    assert overview(readings(source='esp32'))['title']=='Calibrate the station first'

def test_rise_uses_trend_instead_of_single_noise_jump():
    now=datetime.now(timezone.utc)
    rows=[]
    for i,value in enumerate([35,35.3,34.7,35.2,34.8,35,35.4]):
        rows.append(readings(timestamp=(now-timedelta(seconds=12-2*i)).isoformat(),water_level=value).iloc[0])
    df=pd.DataFrame(rows)
    assert abs(observed_rise(df))<10
    assert overview(df)['flood']=='Below watch level'
    df['water_level']=[35+2*i for i in range(7)]
    assert observed_rise(df)>50
    assert overview(df)['flood']=='Warning'
