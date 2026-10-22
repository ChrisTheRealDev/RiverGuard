from datetime import datetime, timezone
from pathlib import Path
import base64
import pandas as pd
import plotly.graph_objects as go
from charting import summarize, group_alerts
from html import escape
import streamlit as st
from core import SCENARIOS, FEATURES, train, sample, save, history, reset_simulation, evaluate
from river_status import overview
from reading_visuals import reading_guide
from sensor_support import sensor_health, decode, observation_report

st.set_page_config(page_title='RiverGuard AI',page_icon='🌊',layout='wide')
st.markdown('<style>'+ (Path(__file__).parent/'assets'/'ui.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
with st.sidebar:
    st.markdown('<div class="station-brand">≈ RiverGuard<span style="color:#6550c8">.</span></div>',unsafe_allow_html=True)
    page=st.radio('Workspace',['River overview','Sensor setup'],key='workspace_page',label_visibility='collapsed')
if page=='Sensor setup':
    from setup_ui import render
    render()
    st.stop()
@st.cache_resource
def get_model(): return train()
model=get_model()
@st.cache_data
def evaluation_results(): return evaluate(get_model())
mascot_uri='data:image/png;base64,'+base64.b64encode((Path(__file__).parent/'assets'/'rill-otter.png').read_bytes()).decode()
st.markdown(f'''<style>.st-key-rill_companion button::before{{content:"";display:inline-block;width:48px;height:42px;background:url("{mascot_uri}") center/contain no-repeat;transition:transform .25s ease;}}.st-key-rill_companion button:hover::before{{transform:rotate(-8deg);}}</style>''',unsafe_allow_html=True)
st.markdown(f'''<div class="hero"><div><div class="eyebrow">RiverGuard AI / River intelligence</div>
<h1>River overview</h1>
<p>Your station, at a glance.</p></div>
<img class="mascot" src="{mascot_uri}" alt="Rill, our river otter, floating on a ripple with a leaf" title="Meet Rill, your river companion"></div>''',unsafe_allow_html=True)
def notify_change(key, message):
    value=st.session_state[key]
    previous=st.session_state.get('_previous_'+key,value)
    if previous!=value: st.toast(message(value))
    st.session_state['_previous_'+key]=value

def replay():
    reset_simulation()
    st.session_state.step=0
    st.session_state.simulation_running=True
    st.toast('Synthetic history cleared. Replay starts from the baseline.')

with st.sidebar:
    st.subheader('Station controls')
    source=st.radio('Data source',['simulation','esp32'],format_func=lambda x:'Synthetic demonstration' if x=='simulation' else 'ESP32 measurements',key='source_choice')
    notify_change('source_choice',lambda v:'Simulation selected' if v=='simulation' else 'Listening for ESP32 measurements')
    selected_station=None
    if source=='esp32':
        stations=history('esp32')
        station_ids=stations.device_id.drop_duplicates().tolist() if not stations.empty else []
        if station_ids:
            selected_station=st.selectbox('Connected station',station_ids,key='hardware_station')
        st.button('Refresh station list',help='Discover a station that has just sent its first reading.')
    with st.expander('Connect a real station',expanded=source=='esp32'):
        st.caption('1 · Start RiverGuard.cmd starts the receiver on port 8000. Keep this laptop and the ESP32 on the same private Wi-Fi.')
        st.code('http://YOUR_LAPTOP_IP:8000/docs',language=None)
        st.caption('2 · Open that address from another device to check network access. Use ipconfig on the laptop to find its Wi-Fi IPv4 address.')
        st.caption('3 · Upload remote-v1 firmware once with Wi-Fi and that address, then use Sensor setup to enable and calibrate each probe without reflashing.')
        st.caption('4 · Select ESP32 measurements. Readings appear automatically; a sample over 30 seconds old is marked delayed. Calibrate before interpreting it.')
        if source=='esp32':
            station_rows=history('esp32')
            if not station_rows.empty:
                latest=station_rows.iloc[-1]
                st.caption(f"Last received · {latest.device_id} · {latest.received_at}")
        st.caption('pH, cloudiness and temperature use prototype reference ranges. The scales explain measurements; they do not certify water safety.')
    scenario=st.selectbox('Demonstration scenario',SCENARIOS,disabled=source!='simulation',key='scenario_choice')
    running=st.toggle('Run simulation',value=True,disabled=source!='simulation',key='simulation_running')
    notify_change('simulation_running',lambda v:'Simulation resumed' if v else 'Simulation paused — your readings are saved')
    st.button('Reset & replay simulation',disabled=source!='simulation',on_click=replay,help='Clears synthetic history and restarts this scenario. ESP32 readings are kept.')
    if st.session_state.get('scenario')!=scenario:
        if 'scenario' in st.session_state: st.toast(f'{scenario} selected. Starting with ten baseline samples.')
        st.session_state.step=0; st.session_state.scenario=scenario
    period=st.selectbox('History window',['Last hour','Last 24 hours','All stored'])
    with st.expander('Water-level thresholds'):
        elevated=st.number_input('Elevated level (cm)',value=70.,min_value=0.,key='flood_elevated')
        if st.session_state.get('flood_warning',100.)<=elevated:
            st.session_state.flood_warning=elevated+1
        warning=st.number_input('Warning level (cm)',value=100.,min_value=0.,key='flood_warning')
        rise_limit=st.number_input('Warning rise rate (cm/min)',min_value=.1,value=10.,key='flood_rise')
        st.caption('Demonstration settings, not validated flood predictions.')
        st.caption(f'Applied settings · watch {elevated:g} cm · warning {warning:g} cm · rise {rise_limit:g} cm/min')
        st.caption('The warning level is kept above the watch level automatically.')
def station_history():
    frame=history(source)
    if source=='esp32' and not frame.empty:
        return frame[frame.device_id==(selected_station or frame.iloc[-1].device_id)]
    return frame

@st.fragment(run_every='2s')
def live():
    if source=='simulation' and running:
        step=st.session_state.get('step',0)
        save(sample(scenario,step),'simulation','demo-station',model=model)
        st.session_state.step=step+1
    df=station_history()
    if df.empty:
        st.markdown(f'<div class="connection"><img src="{mascot_uri}" alt="Rill the river otter waiting for the station" width="110"><h3>Rill is ready. Your station is next.</h3><p>Connect the ESP32 to the same network and send its first measurement.<br>Want to explore first? Choose Synthetic demonstration in Station controls.</p></div>',unsafe_allow_html=True)
        st.info('Waiting for the first reading. The dashboard remains available while the device is disconnected.')
        return
    df['timestamp']=pd.to_datetime(df.timestamp,utc=True,format='mixed')
    df['received_at']=pd.to_datetime(df.received_at,utc=True,format='mixed')
    last=df.iloc[-1]
    age=(datetime.now(timezone.utc)-last.timestamp.to_pydatetime()).total_seconds()
    local_time=last.timestamp.tz_convert('Asia/Kuala_Lumpur')
    status=overview(df,elevated,warning,rise_limit)
    if source=='simulation' and not running:
        status.update(tone='muted',title='Simulation paused',reason='These readings are frozen at the last sample.',action='Turn on Run simulation to continue, or replay the scenario.')
    badge='SYNTHETIC DEMO' if source=='simulation' else 'ESP32 STATION'
    flow='Paused' if source=='simulation' and not running else 'Delayed' if status['age']>30 else 'Live'
    st.markdown(f'''<section class="river-status {status['tone']}"><div class="status-meta"><span>{badge}</span><span>{flow} · {local_time:%I:%M:%S %p} MYT</span></div>
    <div class="status-body"><div><div class="eyebrow">River signals</div><h2>{status['title']}</h2><p>{status['reason']}<span class="inline-next"> {status['action']}</span></p></div><div class="water-watch"><span>WATER-LEVEL WATCH</span><strong>{status['flood']}</strong></div></div>
    <div class="next-step"><strong>Next step</strong> {status['action']}</div></section>''',unsafe_allow_html=True)
    st.caption(('Simulated readings' if source=='simulation' else 'Provisional sensor readings')+' · signal checks do not establish water safety or predict floods.')
    with st.container(key='sensor_grid'):
        cols=st.columns(4)
        for col,key,label,unit in zip(cols,FEATURES+['water_level'],['Acidity · pH','Cloudiness · NTU','Temperature · °C','Water level · cm'],['pH','NTU','°C','cm']):
            value=last[key]
            device_rows=df[df.device_id==last.device_id]
            previous=device_rows.iloc[-2][key] if len(device_rows)>1 else None
            delta=f'{round(float(value-previous),2)+0.:+.2f} {unit}' if pd.notna(value) and previous is not None and pd.notna(previous) else None
            limits={'ph':(6.5,8.5),'turbidity':(0,50),'temperature':(20,32),'water_level':(0,elevated)}
            lo,hi=limits[key]
            missing_text={'uncalibrated':'Needs calibration','out_of_range':'Outside sensor range','disabled':'Sensor not enabled','missing':'No response','timeout':'No echo','adc_limit':'Check analog input'}.get(decode(last.get('sensor_health_json')).get(key),'Waiting for this sensor')
            with col.container(key='reading_card_'+key):
                st.metric(label,'Unavailable' if pd.isna(value) else f'{value:.2f}' if key=='ph' else f'{value:.1f}',delta,delta_color='normal',help={'ph':'How acidic or alkaline the water is. Demo reference: 6.5–8.5 pH.','turbidity':'How cloudy the water is. Demo reference: up to 50 NTU.','temperature':'Water temperature. Demo reference: 20–32 °C.','water_level':f'Height above the station datum. Watch: {elevated:g} cm; warning: {warning:g} cm.'}[key]+' Arrows show change since the previous sample, not safety.')
                st.markdown(reading_guide(key,value,elevated,warning,missing_text),unsafe_allow_html=True)

@st.fragment(run_every='30s')
def details():
    df=station_history()
    if df.empty: return
    df['timestamp']=pd.to_datetime(df.timestamp,utc=True,format='mixed')
    if period!='All stored':
        hours=1 if period=='Last hour' else 24
        df=df[df.timestamp>=pd.Timestamp.now(tz='UTC')-pd.Timedelta(hours=hours)]
    if df.empty:
        st.info('No readings in this time window. Choose a longer History window in Station controls.')
        return
    with st.container(key='observation_workspace'):
        chart_column,alerts_column=st.columns([1.8,1],gap='large')
        with chart_column:
            trend_title,trend_controls=st.columns([.9,2.4],gap='medium',vertical_alignment='center')
            trend_title.markdown('### River trends')
            st.session_state.setdefault('reading_choice','ph')
            names={'ph':'pH','turbidity':'Cloudiness','temperature':'Temperature','water_level':'Water level'}
            def choose_reading(value): st.session_state.reading_choice=value
            with trend_controls.container(key='reading_picker'):
                options=st.columns(4)
                for col,key in zip(options,FEATURES+['water_level']):
                    col.button(names[key],key='chart_'+key,type='primary' if st.session_state.reading_choice==key else 'secondary',use_container_width=True,on_click=choose_reading,args=(key,))
            field=st.session_state.reading_choice
            window=st.session_state.get('chart_window') or '10 minutes'
            chart_data=df.sort_values('timestamp').copy()
            if window!='Full history':
                minutes=10 if window=='10 minutes' else 60
                chart_data=chart_data[chart_data.timestamp>=chart_data.timestamp.max()-pd.Timedelta(minutes=minutes)]
            chart_label={'ph':'Acidity (pH)','turbidity':'Cloudiness (NTU)','temperature':'Temperature (°C)','water_level':'Water level (cm)'}[field]
            palette={'ph':('#bdb1ff','rgba(189,177,255,.09)'),'turbidity':('#d6be7e','rgba(214,190,126,.09)'),'temperature':('#eeaa91','rgba(238,170,145,.09)'),'water_level':('#79cbb5','rgba(121,203,181,.09)')}
            accent,fill=palette[field]
            unit={'ph':'pH','turbidity':'NTU','temperature':'°C','water_level':'cm'}[field]
            valid=chart_data[field].dropna()
            def display_number(value): return f'{value:.2f}' if field=='ph' else f'{value:.1f}'
            last_value=chart_data.iloc[-1][field]
            plotted='Missing' if pd.isna(last_value) else display_number(last_value)+' '+unit
            observed='No readings' if valid.empty else display_number(valid.min())+' – '+display_number(valid.max())+' '+unit
            st.markdown(f'<div class="chart-summary" style="--reading-accent:{accent}"><div><span>Last plotted</span><strong>{plotted}</strong></div><div><span>Range · {escape(window)}</span><strong>{observed}</strong></div><div><span>Valid samples</span><strong>{len(valid):,}</strong></div></div>',unsafe_allow_html=True)
            show_limits=st.session_state.get('chart_reference_limits',False)
            summary,seconds=summarize(chart_data,field)
            fig=go.Figure()
            for (device,group),color in zip(summary.groupby('device_id'),[accent,'#8db8df','#e6b2c7','#c5ce99']*20):
                # Separate polygons prevent a fill from bridging missing-data intervals.
                segments=group.assign(segment=group['mean'].isna().cumsum()).dropna(subset=['mean'])
                for _,segment in segments.groupby('segment'):
                    fig.add_trace(go.Scatter(x=list(segment.local_time)+list(segment.local_time.iloc[::-1]),y=list(segment['max'])+list(segment['min'].iloc[::-1]),mode='lines',line=dict(width=0),fill='toself',fillcolor=fill,showlegend=False,hoverinfo='skip'))
                fig.add_trace(go.Scatter(x=group.local_time,y=group['mean'],name=str(device),mode='lines+markers',marker=dict(size=3),line=dict(color=color,width=2.5),customdata=group[['min','max','count']],connectgaps=False,hovertemplate='<b>%{x|%d %b · %H:%M:%S} MYT</b><br>Average: %{y:.2f}<br>Range: %{customdata[0]:.2f} – %{customdata[1]:.2f}<extra>%{fullData.name}</extra>'))
            if show_limits:
                guides={'ph':[(6.5,'Lower reference'),(8.5,'Upper reference')],'turbidity':[(50,'Demo reference')],'temperature':[(20,'Lower reference'),(32,'Upper reference')],'water_level':[(elevated,'Watch setting'),(warning,'Warning setting')]}[field]
                for limit,label in guides:
                    fig.add_hline(y=limit,line_dash='dash',line_color='#b7c4ca77',line_width=1,annotation_text=f'{label} · {limit:g} {unit}',annotation_position='top left',annotation_font_color='#c5d2d4',annotation_font_size=11)
            fig.update_layout(template='plotly_dark',height=290,margin=dict(l=10,r=16,t=45 if summary.device_id.nunique()>1 else 16,b=16),yaxis_title=chart_label,xaxis_title=None,paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#b5c9cb',size=13),hovermode='closest',hoverlabel=dict(bgcolor='#19333e',bordercolor='#819b9d',font_size=13),legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='left',x=0),showlegend=summary.device_id.nunique()>1,uirevision=f'{source}-{field}-{window}',transition_duration=0)
            fig.update_xaxes(gridcolor='rgba(180,210,210,.08)',zeroline=False,nticks=5,tickformat='%H:%M')
            fig.update_yaxes(gridcolor='rgba(180,210,210,.12)',zeroline=False,nticks=6)

            st.plotly_chart(fig,width='stretch',height='stretch',key='history_chart',config={'displaylogo':False,'scrollZoom':False,'modeBarButtonsToRemove':['lasso2d','select2d']})
            with st.expander('Chart options'):
                if st.button('Refresh chart and alerts',key='refresh_observation'):
                    st.toast('Chart and alerts updated')
                st.caption('Charts refresh every 30 seconds. Live readings update every 2 seconds.')
                st.segmented_control('Chart window',['10 minutes','1 hour','Full history'],default='10 minutes',key='chart_window')
                st.toggle('Show demo reference limits',value=False,key='chart_reference_limits')
                st.caption(f'{seconds}-second averages · shaded band shows min–max · times in MYT. Dashed lines are demo settings, not verified safety limits.')
            with st.expander('Recent readings table'):
                st.caption('Latest 12 individual measurements in the plotted window · newest first · times in MYT')
                recent=chart_data.tail(12).iloc[::-1].copy()
                recent['Time (MYT)']=recent.timestamp.dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%d %b %H:%M:%S')
                columns=['Time (MYT)','ph','turbidity','temperature','water_level']
                if recent.device_id.nunique()>1: columns.insert(1,'device_id')
                table=recent[columns].rename(columns={'device_id':'Station','ph':'pH','turbidity':'Cloudiness (NTU)','temperature':'Temperature (°C)','water_level':'Level (cm)'})
                st.dataframe(table,hide_index=True,width='stretch',column_config={'pH':st.column_config.NumberColumn(format='%.2f'),'Cloudiness (NTU)':st.column_config.NumberColumn(format='%.1f'),'Temperature (°C)':st.column_config.NumberColumn(format='%.1f'),'Level (cm)':st.column_config.NumberColumn(format='%.1f')})
        with alerts_column:
            st.subheader('Recent alerts')
            st.markdown(f'<p class="section-note"><span class="alerts-count-wide">Latest 3 signals</span><span class="alerts-count-short">Latest 2 signals</span> · {escape(period.lower())}</p>',unsafe_allow_html=True)
            events=[]
            for _, row in df.iterrows():
                if row.anomaly==1:
                    events.append(dict(timestamp=row.timestamp,severity='Review',explanation=row.explanation,device_id=row.device_id,kind='pattern',pattern=','.join(sorted(str(row.explanation).split(':')[-1].replace('. Not confirmed pollution.','').strip(' .').split(', ')))))
                if pd.notna(row.water_level) and row.water_level>=elevated:
                    events.append(dict(timestamp=row.timestamp,severity='Warning' if row.water_level>=warning else 'Elevated',explanation=f'Water level {row.water_level:.1f} cm exceeds a demonstration threshold.',device_id=row.device_id,kind='level',pattern='level'))
            if events:
                rows=[]
                for event in group_alerts(events)[-3:][::-1]:
                    measured=pd.to_datetime(event['timestamp'],utc=True).tz_convert('Asia/Kuala_Lumpur')
                    tone='warning' if event['severity']=='Warning' else 'review'
                    first=pd.to_datetime(event['start_timestamp'],utc=True).tz_convert('Asia/Kuala_Lumpur')
                    explanation=event['explanation'].replace('Unusual combination; largest deviations from synthetic baseline:','Unusual pattern · baseline differences:').replace('. Not confirmed pollution.','').replace('turbidity','cloudiness').replace('ph','pH')
                    explanation=explanation.replace('Unusual pattern · baseline differences: combined measurements','Unusual combination of readings').replace('Unusual pattern · baseline differences:','Changed from demo baseline:')
                    context=f"{event['count']} flagged reading"+('s' if event['count']!=1 else '')+f' · {measured:%d %b}'
                    if event['count']>1: context+=f" · {first:%H:%M}–{measured:%H:%M}"
                    if df.device_id.nunique()>1: context+=' · '+str(event['device_id'])
                    rows.append(f'<tr><td class="alert-time"><span class="alert-label {tone}">{escape(event["severity"])}</span><strong title="{measured:%d %b %Y %H:%M:%S} MYT">{measured:%H:%M:%S}</strong></td><td>{escape(explanation)}<small>{escape(context)}</small></td></tr>')
                st.markdown('<div class="alerts-ledger"><table><thead><tr><th scope="col">Signal / time</th><th scope="col">What changed</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>',unsafe_allow_html=True)
                with st.expander('All recent flagged samples'):
                    event_table=pd.DataFrame(events).tail(30)[['timestamp','device_id','severity','explanation']]
                    event_table['timestamp']=pd.to_datetime(event_table.timestamp,utc=True).dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%d %b %H:%M:%S MYT')
                    st.dataframe(event_table.rename(columns={'timestamp':'Time','severity':'Status','explanation':'Explanation'}),hide_index=True)
            else:
                st.success('No alerts in this time window.')
                st.caption('We’re watching for unusual combinations and water-level threshold crossings. This does not establish water safety.')
    reports,ai=st.tabs(['Reports','AI evidence'])
    with reports:
        last=df.iloc[-1]
        status=overview(df,elevated,warning,rise_limit)
        if source=='esp32':
            with st.expander('Sensor health & raw signals'):
                received=pd.to_datetime(last.received_at,utc=True)
                receipt_age=max(0,(datetime.now(timezone.utc)-received.to_pydatetime()).total_seconds())
                st.caption(f'Station {last.device_id} · last transmission {receipt_age:.0f}s ago · calibration record: {last.get("calibration_id") or "not provided"}')
                health_rows=''.join(f'<div><strong>{escape(row["Sensor"])}</strong><span>{escape(row["State"])}</span></div>' for row in sensor_health(last))
                st.markdown('<div class="sensor-health">'+health_rows+'</div>',unsafe_allow_html=True)
                raw=decode(last.get('raw_json'))
                if raw:
                    st.caption('Raw ADC counts / ADC-pin millivolts / echo distance. These are not pH, NTU or water height.')
                    st.json(raw,expanded=False)
                else: st.caption('This firmware did not include raw sensor signals.')
        with st.expander('Station details & how this status is calculated'):
            st.write(f'Station: {last.device_id}')
            st.write(f'Measured (UTC): {last.timestamp} · Received (UTC): {last.received_at}')
            st.write('Rise rate: unavailable' if status['rate'] is None else f"Observed rise rate: {status['rate']:+.1f} cm/min")
            st.write(last.explanation)
            st.caption('Status combines freshness, missing readings, calibration, demo thresholds and experimental AI detection. It is not an official Malaysian WQI. Green/red arrows indicate increase/decrease, not safety.')
            if source=='simulation':
                count=st.session_state.get('step',0)
                st.caption(f"{scenario} · {count} samples · {'Collecting baseline' if count<=10 else 'Scenario running'}")
        st.subheader('Take the evidence with you')
        st.write(f'{len(df):,} readings · {"Synthetic demonstration" if source=="simulation" else "ESP32 measurements"} · {period.lower()}')
        st.download_button('Download readings CSV',df.to_csv(index=False),'riverguard-readings.csv','text/csv',on_click=lambda:st.toast('CSV prepared — check your browser downloads.'),type='primary')
        st.caption('Units: pH, NTU, °C, cm. Source and calibration state are included in every record.')
        st.download_button('Download observation report',observation_report(df,elevated,warning,rise_limit),'riverguard-observation.txt','text/plain')
    with ai:
        metrics,details=evaluation_results()
        st.subheader('How well did the detectors do?')
        st.caption('Tested on 560 labelled synthetic samples, separate from training. These are demonstration results.')
        left,right=st.columns(2)
        for column,(_,result),name in zip([left,right],metrics.iterrows(),['AI detector','Simple thresholds']):
            with column:
                st.markdown(f'<div class="evaluation-card"><span>{name}</span><strong>{result.accuracy:.1%}</strong><p>samples classified correctly</p><small>{int(result.missed_anomalies)} missed abnormal samples · {result.false_positive_rate:.1%} false-positive rate</small></div>',unsafe_allow_html=True)
        st.info('Simple thresholds performed better on this test set. The AI is experimental, not a proven upgrade.')
        with st.expander('Full evaluation details'):
            st.dataframe(metrics.rename(columns={'method':'Detector','accuracy':'Accuracy','false_positive_rate':'False-positive rate','missed_anomalies':'Missed samples','missed_scenarios':'Missed scenarios','mean_detection_delay_steps':'Average delay (steps)'}),hide_index=True)
            st.caption('Training: 1,500 normal synthetic samples. Delay uses nominal 2-second steps and excludes missed scenarios. Water level alone is not labelled a pollution anomaly. Explanations rank baseline deviations, not causal model contributions.')
        st.download_button('Download evaluation evidence',details.to_csv(index=False),'synthetic-evaluation.csv','text/csv')
live()
details()

def rill_chat():
    from rill_jobs import ReplyJob
    from rill_ai import provider
    import rill_store
    conversation_key='rill_chat_'+source
    failure_key='rill_failure_'+source
    loaded_key='rill_loaded_'+source
    active_key='rill_active_'+source
    manage_key='rill_manage_'+source
    if not st.session_state.get(loaded_key):
        if conversation_key in st.session_state:
            rill_store.save(source,st.session_state[conversation_key],st.session_state.get(failure_key))
        else:
            saved=rill_store.load(source)
            st.session_state[conversation_key]=saved['messages'] if saved else []
            if saved and saved['failure']: st.session_state[failure_key]=saved['failure']
        st.session_state[loaded_key]=True
    if not st.session_state.get(active_key):
        st.session_state[active_key]=rill_store.active(source) or rill_store.new_conversation(source)
    chat_id=st.session_state[active_key]
    job_key='rill_job_'+source+'_'+chat_id
    messages=st.session_state[conversation_key]
    def open_conversation(selected):
        rill_store.activate(source,selected)
        saved=rill_store.load(source,selected)
        st.session_state.pop(manage_key,None)
        st.session_state[active_key]=selected
        st.session_state[conversation_key]=saved['messages']
        st.session_state.pop(failure_key,None)
        selected_job_key='rill_job_'+source+'_'+selected
        selected_job=st.session_state.get(selected_job_key)
        if selected_job and selected_job.poll()['done']:
            st.session_state.pop(selected_job_key,None)
            selected_job=None
        if saved['failure'] and not selected_job: st.session_state[failure_key]=saved['failure']
    def start_reply(question,past):
        attempt=rill_store.begin(source,question,past,st.session_state[conversation_key],chat_id=chat_id)
        return ReplyJob(question,past,station_history(),elevated,warning,rise_limit,persist=(source,attempt))
    job=st.session_state.get(job_key)
    state=job.poll() if job else None
    if state and state['done']:
        if not state['error'] and not job.stop.is_set():
            messages.append({'role':'assistant','content':state['text']})
            st.session_state.pop(failure_key,None)
        elif state['error']:
            st.session_state[failure_key]=dict(error=state['error'],question=job.question,messages=job.messages,retry_at=state['retry_at'],partial=state['text'])
        st.session_state.pop(job_key,None)
        job=None; state=None
    busy=job is not None
    source_label='Synthetic demo readings' if source=='simulation' else 'Connected to ESP32 readings'
    def close_rill():
        st.session_state.rill_ui_open=False
    with st.container(key='rill_header'):
        identity,close=st.columns([6,1],vertical_alignment='center')
        identity.markdown(f'<div class="rill-profile"><img src="{mascot_uri}" alt="Rill the river otter"><div><strong>Your river, explained.</strong><p>{source_label}</p></div></div>',unsafe_allow_html=True)
        if close.button('×',key='rill_close',help='Close chat'):
            close_rill()
            st.rerun()
    with st.container(key='rill_history'):
        if st.button('New conversation',key='rill_clear',use_container_width=True):
            open_conversation(rill_store.new_conversation(source))
            st.rerun()
        chats=rill_store.conversations(source)
        with st.expander(f'Chat history ({len(chats)})'):
            st.caption('Open a saved chat to continue or manage it.')
            with st.container(height=180,border=False):
                for chat in chats:
                    date=pd.to_datetime(chat['updated'],unit='s',utc=True).tz_convert('Asia/Kuala_Lumpur')
                    label=chat['title']+(' · Current' if chat['id']==chat_id else '')
                    if st.button(label,key='rill_history_'+chat['id'],use_container_width=True,disabled=chat['id']==chat_id):
                        open_conversation(chat['id'])
                        st.rerun()
                    st.caption(f"{date:%d %b · %I:%M %p} MYT"+(' · Reply needs retry' if chat['needs_retry'] else ''))
        selected_chat=next((chat for chat in chats if chat['id']==chat_id),None)
        if selected_chat:
            with st.expander('Manage this conversation'):
                st.caption(selected_chat['title'])
                rename_button,delete_button=st.columns(2)
                if rename_button.button('Rename',key='rill_rename_'+chat_id,use_container_width=True):
                    st.session_state[manage_key]=dict(action='rename',id=chat_id)
                    st.rerun()
                if delete_button.button('Delete',key='rill_delete_'+chat_id,use_container_width=True):
                    st.session_state[manage_key]=dict(action='delete',id=chat_id)
                    st.rerun()
        manage=st.session_state.get(manage_key)
        target=next((chat for chat in chats if manage and chat['id']==manage['id']),None)
        if target:
            with st.container(key='rill_manage_panel'):
                if manage['action']=='rename':
                    with st.form('rill_rename_form_'+target['id']):
                        name=st.text_input('Conversation name',value=target['title'],max_chars=64,key='rill_name_'+target['id'])
                        save_name,cancel_name=st.columns(2)
                        submit=save_name.form_submit_button('Save name',use_container_width=True,type='primary')
                        cancel=cancel_name.form_submit_button('Cancel',use_container_width=True)
                    if submit:
                        try:
                            rill_store.rename(source,target['id'],name)
                            st.session_state.pop(manage_key,None)
                            st.toast('Conversation renamed')
                            st.rerun()
                        except ValueError as exc: st.error(str(exc))
                    if cancel:
                        st.session_state.pop(manage_key,None)
                        st.rerun()
                else:
                    st.markdown('**Delete this conversation?**')
                    st.write(target['title'])
                    st.caption('This permanently deletes this chat, its messages and any saved retry. You cannot undo it.')
                    confirm,keep=st.columns(2)
                    if confirm.button('Delete chat',key='rill_confirm_delete',type='primary',use_container_width=True):
                        deleted_job=st.session_state.pop('rill_job_'+source+'_'+target['id'],None)
                        if deleted_job: deleted_job.cancel()
                        selected=rill_store.delete(source,target['id'])
                        st.session_state.pop(manage_key,None)
                        if target['id']==chat_id: open_conversation(selected)
                        st.toast('Conversation deleted')
                        st.rerun()
                    if keep.button('Keep chat',key='rill_cancel_delete',use_container_width=True):
                        st.session_state.pop(manage_key,None)
                        st.rerun()
        current_title=next((chat['title'] for chat in chats if chat['id']==chat_id),'New conversation')
        st.caption(current_title)
        if target:
            st.caption('Your messages stay saved while you manage this chat.')
            return
    question=None
    if not messages:
        st.caption('Ask a question, or start here.')
        a,b=st.columns(2)
        if a.button('Anything unusual?',key='rill_suggest_now',use_container_width=True,disabled=busy):
            question='Is anything unusual in the latest readings? Explain it simply.'
        if b.button('Why cloudy water?',key='rill_suggest_cloudy',use_container_width=True,disabled=busy):
            question='Why might river water look cloudy, and what does our turbidity reading tell us?'
    transcript=st.container(height=90 if busy else 140 if st.session_state.get(failure_key) else 230,border=False,key='rill_transcript') if messages else st.container(key='rill_transcript')
    with transcript:
        if len(messages)>12:
            with st.expander(f'Earlier messages ({len(messages)-12})'):
                for message in messages[:-12]:
                    with st.chat_message(message['role'],avatar=str(Path(__file__).parent/'assets'/'rill-otter.png') if message['role']=='assistant' else '🙂'):
                        st.markdown(message['content'])
        for message in messages[-12:]:
            with st.chat_message(message['role'],avatar=str(Path(__file__).parent/'assets'/'rill-otter.png') if message['role']=='assistant' else '🙂'):
                st.markdown(message['content'])
        failed=st.session_state.get(failure_key)
        if failed and failed.get('partial'):
            with st.chat_message('assistant',avatar=str(Path(__file__).parent/'assets'/'rill-otter.png')):
                st.markdown(failed['partial'])
                st.caption('Reply interrupted · retry for a complete answer')
    if state:
        @st.fragment(run_every='1s')
        def reply_progress():
            current=job.poll()
            if current['done']: st.rerun()
            with st.container(height=140,border=False):
                with st.chat_message('assistant',avatar=str(Path(__file__).parent/'assets'/'rill-otter.png')):
                    if current['text']: st.markdown(current['text']+' ▌')
                    else: st.markdown('<div class="rill-thinking"><span></span><span></span><span></span></div>',unsafe_allow_html=True)
            stage={'Queued':'Waiting to start','Thinking':'Thinking through your readings','Writing':'Putting the answer into words'}[current['stage']]
            st.caption(f"{stage} · {current['elapsed']}s")
            if current['sample']:
                sample_time=pd.to_datetime(current['sample'],utc=True).tz_convert('Asia/Kuala_Lumpur')
                st.caption(f"Using the sample captured at {sample_time:%I:%M:%S %p} MYT. Live monitoring continues.")
            if st.button('Stop reply',key='rill_stop'):
                job.cancel();st.session_state.pop(job_key,None)
                rill_store.save(source,messages,chat_id=chat_id)
                st.session_state.pop(failure_key,None)
                st.rerun()
        reply_progress()
    failure=st.session_state.get(failure_key)
    if failure and not busy:
        from time import monotonic
        cloud_wait_applies=not (provider()=='ollama' and 'cloud' in failure['error'].lower())
        needs_countdown=cloud_wait_applies and failure['retry_at']>monotonic()
        @st.fragment(run_every='1s' if needs_countdown else None)
        def recovery():
            from time import monotonic
            from math import ceil
            previous_cloud_failure=provider()=='ollama' and 'cloud' in failure['error'].lower()
            remaining=0 if previous_cloud_failure else max(0,ceil(failure['retry_at']-monotonic()))
            with st.container(key='rill_recovery'):
                if previous_cloud_failure:
                    st.info('That earlier cloud reply did not finish. You can retry with local AI now.')
                else:
                    st.warning(failure['error'])
                if st.button('Retry reply',key='rill_retry',type='primary',disabled=remaining>0):
                    st.session_state[job_key]=start_reply(failure['question'],failure['messages'])
                    st.session_state.pop(failure_key,None)
                    st.rerun()
                st.caption('Your question is still in the chat. Retry uses a fresh reading snapshot.')
                if remaining: st.caption(f'You can retry in {remaining}s. Rill will not resend automatically.')
        recovery()
    with st.form('rill_composer_'+chat_id,clear_on_submit=True):
        entry,send=st.columns([5,1],vertical_alignment='center')
        typed=entry.text_input('Ask Rill',placeholder='Ask about your river…',max_chars=1500,key='rill_draft_'+chat_id,disabled=busy,label_visibility='collapsed')
        submitted=send.form_submit_button('Send',type='primary',disabled=busy,use_container_width=True)
    question=(typed.strip() if submitted and typed else None) or question
    st.caption('Saved on this device · AI can make mistakes')
    if provider()=='gemini': st.caption('Cloud AI · your question and selected readings are sent to Google')
    else: st.caption('Local AI · questions and readings stay on this computer')
    if question and not busy:
        past=list(messages)
        messages.append({'role':'user','content':question})
        st.session_state[conversation_key]=messages
        st.session_state.pop(failure_key,None)
        st.session_state[job_key]=start_reply(question,past)
        st.rerun()

def rill_launcher():
    with st.container(key='rill_companion'):
        if st.button('Ask Rill',key='rill_open',help='Chat about your river readings'):
            st.session_state.rill_ui_open=True
    if st.session_state.get('rill_ui_open',False):
        with st.container(key='rill_panel'):
            rill_chat()
rill_launcher()
