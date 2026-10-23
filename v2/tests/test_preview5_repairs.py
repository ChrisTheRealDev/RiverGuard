import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from test_backend import settings,packet
from server.store import Store,Problem
from server.app import create_apps
from server import demo

def test_verification_requires_fresh_complete_evidence(tmp_path):
 s=Store(tmp_path/'check.db');s.register('river-01');cfg=settings();s.save_settings('river-01',0,cfg)
 s.save_watch('esp32','river-01',0,{'elevated':10,'warning':20,'rise_limit':10});cfg['verified']=True
 for i,age in enumerate([-3600,0]):
  p=packet(sample='bad-'+str(i),seconds=age,revision=1);s.ingest('river-01',p)
  with pytest.raises(Problem,match='fresh usable'):s.save_settings('river-01',1,cfg)
 p=packet(sample='complete',revision=1);p['raw']['turbidity_mv']=1800;p['sensor_health']['turbidity']='ok';s.ingest('river-01',p)
 assert s.save_settings('river-01',1,cfg)['settings']['verified']

def test_local_host_changes_keep_host_protection(tmp_path):
 with patch('server.app.addresses',return_value=['192.168.1.20']):web,_=create_apps(tmp_path/'hosts.db')
 with patch('server.app.addresses',return_value=['192.168.1.21']),TestClient(web,base_url='http://192.168.1.21') as client:
  assert client.get('/health').status_code==200
  assert client.get('/health',headers={'Host':'evil.example'}).status_code==400

def test_demo_independent_variation_and_scenario_meaning():
 now=1792728000000
 for scenario in demo.SCENARIOS:
  samples=[demo.sample(scenario,i,now+i*2000) for i in range(120)]
  assert all(0<=s['turbidity']<=250 and 0<=s['water_level']<=150 for s in samples)
  assert len({round(s['temperature'],3) for s in samples})>30
  assert len({round(s['ph'],3) for s in samples[10:]})>30
  if scenario=='Cloudier water':assert all(s['turbidity']>50 for s in samples[10:])
  if scenario=='Sudden change':assert all(s['ph']<6.5 for s in samples[10:])
  if scenario=='Rising water level':assert samples[80]['water_level']>samples[20]['water_level']+30
 assert demo.sample('Normal river',0,now)['ph']!=demo.sample('Normal river',0,now+240000)['ph']
