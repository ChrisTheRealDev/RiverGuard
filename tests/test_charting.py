from datetime import datetime, timezone, timedelta
import pandas as pd
from charting import summarize

def test_aggregation_keeps_spikes_and_missing_values():
    now=datetime.now(timezone.utc)
    data=pd.DataFrame([{'timestamp':now+timedelta(seconds=i),'device_id':'demo','ph':14 if i==40 else 7} for i in range(600)])
    result,seconds=summarize(data,'ph')
    assert seconds>=4
    assert len(result)<=122
    assert result['max'].max()==14
    assert result['count'].sum()==600
    data['ph']=None
    result,_=summarize(data,'ph')
    assert result['mean'].isna().all()


def test_alert_bursts_keep_stations_severities_and_gaps_separate():
    from charting import group_alerts
    now=datetime.now(timezone.utc)
    def event(seconds,station='a',severity='Review'):
        return dict(timestamp=now+timedelta(seconds=seconds),device_id=station,kind='pattern',severity=severity,pattern='ph',explanation='Reading needs review')
    groups=group_alerts([event(0),event(2),event(4,'b'),event(5,severity='Warning'),event(25)])
    assert len(groups)==4
    assert groups[0]['count']==2
    assert groups[0]['start_timestamp']==now
    assert groups[-1]['timestamp']==now+timedelta(seconds=25)
    assert sum(g['count'] for g in groups)==5
