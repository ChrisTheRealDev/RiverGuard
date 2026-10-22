"""Readable temporal summaries that retain sample extremes and missing bins."""
import math
import pandas as pd
from river_status import calibration_segments, effective_row

def group_alerts(events,gap_seconds=10):
    """Collapse repeated signal bursts, without mixing stations or severities."""
    groups=[];active={}
    for event in sorted(events,key=lambda e:pd.Timestamp(e['timestamp'])):
        key=(event.get('device_id'),event.get('segment'),event.get('kind'),event['severity'],event.get('pattern',event['explanation']))
        measured=pd.Timestamp(event['timestamp'])
        current=active.get(key)
        if current is None or (measured-pd.Timestamp(current['timestamp'])).total_seconds()>gap_seconds:
            current=dict(event,start_timestamp=event['timestamp'],count=0)
            groups.append(current);active[key]=current
        current.update(timestamp=event['timestamp'],explanation=event['explanation'],count=current['count']+1)
    return sorted(groups,key=lambda e:pd.Timestamp(e['timestamp']))

def summarize(frame,field,points=80):
    if frame.empty:
        return pd.DataFrame(columns=['timestamp','mean','min','max','count','device_id','segment','local_time']),1
    frame=calibration_segments(frame)
    frame[field]=[effective_row(row).get(field) for row in frame.to_dict('records')]
    span=(frame.timestamp.max()-frame.timestamp.min()).total_seconds()
    seconds=max(1,math.ceil(span/points))
    cadence=frame.groupby('device_id').timestamp.diff().dt.total_seconds()
    positive=cadence[cadence>0]
    if not positive.empty:
        seconds=max(seconds,math.ceil(float(positive.median())))
    if seconds>1: seconds=math.ceil(seconds/5)*5
    parts=[]
    for (device,segment),group in frame.groupby(['device_id','segment'],sort=False):
        values=group.set_index('timestamp')[field].resample(f'{seconds}s').agg(['mean','min','max','count'])
        values['device_id']=device
        # Missing bins get their own boundaries so neither line nor min/max
        # envelope can span a real acquisition or sensor-health gap.
        gaps=values['count'].eq(0).cumsum()
        values['segment']=segment+':gap'+gaps.astype(str)
        parts.append(values.reset_index())
    result=pd.concat(parts,ignore_index=True)
    result['local_time']=result.timestamp.dt.tz_convert('Asia/Kuala_Lumpur')
    return result,seconds
