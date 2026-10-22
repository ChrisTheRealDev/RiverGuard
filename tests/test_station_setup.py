from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json
import pytest
from tests.api_client import AuthenticatedClient as TestClient
from pydantic import ValidationError
import core
import station_setup as setup
from api import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DB',tmp_path/'station.db')
    return TestClient(app)

def settings():
    return {'enabled':dict.fromkeys(setup.FIELDS,True),'ph':[{'mv':1500,'value':7},{'mv':2100,'value':4}],
            'turbidity':[{'mv':1200,'value':100},{'mv':2400,'value':0}],
            'level':{'reference':60,'minimum':20,'maximum':600},'temperature_offset':.5,'verified':True}

def packet(revision=1,sample='sample-1'):
    return {'device_id':'station-01','sample_id':sample,'setup_protocol':'remote-v1','config_revision':revision,
            'timestamp':datetime.now(timezone.utc).isoformat(),
            'raw':{'ph_mv':1800,'ph_adc':2200,'turbidity_mv':1800,'turbidity_adc':2300,'temperature_c':27,'distance_cm':45},
            'sensor_health':dict.fromkeys(setup.FIELDS,'uncalibrated')}

def test_settings_revision_ack_and_raw_preservation(client):
    assert client.get('/api/v1/device-config',params={'device_id':'station-01'}).json()['enabled']['ph'] is False
    result=client.put('/api/v1/stations/station-01/configuration',json={'expected_revision':0,'settings':settings()})
    assert result.status_code==200 and result.json()['revision']==1
    assert client.get('/api/v1/device-config',params={'device_id':'station-01'}).json()['revision']==1
    assert client.post('/api/v1/readings',json=packet()).status_code==201
    row=core.history('esp32').iloc[-1]
    assert row.ph==5.5 and row.turbidity==50 and row.temperature==27.5 and row.water_level==15
    assert row.calibrated and row.calibration_id=='app-r1' and row.config_revision==1
    assert json.loads(row.raw_json)['temperature_c']==27
    assert setup.capture('station-01','ph_mv')==1800

def test_old_packets_keep_their_revision_and_duplicate_is_idempotent(client):
    setup.store('station-01',settings(),0)
    newer=settings();newer['temperature_offset']=1
    setup.store('station-01',newer,1)
    assert client.post('/api/v1/readings',json=packet(1)).status_code==201
    assert core.history('esp32').iloc[-1].temperature==27.5
    assert client.post('/api/v1/readings',json=packet(2)).status_code==201
    assert len(core.history('esp32'))==1
    assert core.history('esp32').iloc[-1].calibration_id=='app-r1'
    assert client.post('/api/v1/readings',json=packet(2,'sample-2')).status_code==201
    assert core.history('esp32').iloc[-1].temperature==28
    assert client.post('/api/v1/readings',json=packet(99,'unknown')).status_code==409
    assert setup.load('other-station')['revision']==0

def test_configuration_conflicts_and_validation(client):
    setup.store('station-01',settings(),0)
    assert client.put('/api/v1/stations/station-01/configuration',json={'expected_revision':0,'settings':settings()}).status_code==409
    for patch in [{'ph':[{'mv':1500,'value':7},{'mv':1500,'value':4}]},
                  {'ph':[{'mv':1500,'value':15},{'mv':2100,'value':4}]},
                  {'level':{'reference':10,'minimum':20,'maximum':600}},
                  {'turbidity':[{'mv':1200,'value':0},{'mv':2400,'value':0}]},
                  {'temperature_offset':6},{'enabled':{'ph':True}}]:
        assert client.put('/api/v1/stations/station-01/configuration',json={'expected_revision':1,'settings':settings()|patch}).status_code==422
    assert setup.load('station-01')['revision']==1

def test_faults_missing_and_blind_zone_are_not_zero(client):
    setup.store('station-01',settings(),0)
    bad=packet();bad['raw'].update(ph_mv=100,turbidity_mv=3000,distance_cm=15)
    bad['sensor_health']['temperature']='missing'
    assert client.post('/api/v1/readings',json=bad).status_code==201
    row=core.history('esp32').iloc[-1]
    assert all(__import__('pandas').isna(row[k]) for k in setup.FIELDS)
    assert not row.calibrated
    health=json.loads(row.sensor_health_json)
    assert health['ph']=='adc_limit' and health['water_level']=='out_of_range'
    with pytest.raises(ValueError): setup.capture('station-01','ph_mv')

def test_capture_rejects_stale_and_disabled(client):
    setup.store('station-01',settings(),0)
    data=packet();data['timestamp']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    assert client.post('/api/v1/readings',json=data).status_code==201
    with pytest.raises(ValueError): setup.capture('station-01','ph_mv')
    zero=packet(0,'zero');assert client.post('/api/v1/readings',json=zero).status_code==201
    with pytest.raises(ValueError): setup.capture('station-01','ph_mv')

def test_setup_ui_save_capture_and_navigation(client):
    from streamlit.testing.v1 import AppTest
    setup.store('station-01',settings(),0)
    assert client.post('/api/v1/readings',json=packet()).status_code==201
    ui=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard.py',default_timeout=60).run()
    ui.radio(key='workspace_page').set_value('Sensor setup').run()
    assert not ui.exception
    assert any('Settings acknowledged' in m.value for m in ui.markdown)
    prefix='setup_station-01_1_'
    ui.checkbox(key=prefix+'ph_settled').check().run()
    ui.button(key=prefix+'ph_capture_0').click().run()
    assert ui.number_input(key=prefix+'ph_mv_0').value==1800
    assert not ui.checkbox(key=prefix+'ph_settled').value
    ui.number_input(key=prefix+'ph_value_0').set_value(6.).run()
    assert ui.number_input(key=prefix+'ph_mv_0').value==1800
    ui.button(key=prefix+'ph_save').click().run()
    assert not ui.exception
    assert setup.load('station-01')['revision']==2
    assert not setup.load('station-01')['settings']['verified']
    assert core.history('esp32').iloc[-1].calibration_id=='app-r1'
    ui.radio(key='workspace_page').set_value('River overview').run()
    assert not ui.exception and len(ui.metric)==4
