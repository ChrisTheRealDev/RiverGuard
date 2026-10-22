"""Stable setup forms with a separately refreshing connection monitor."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from html import escape
import streamlit as st
import core
import station_setup as setup
from sensor_support import decode, sensor_health

def render():
    st.title('Sensor setup')
    st.caption('Connect once. Check the signals. Calibrate here whenever you need to.')
    with st.expander('First-time setup & wiring'):
        st.info('Upload the new remote-v1 firmware once with your Wi-Fi, laptop URL and station ID. After that, enable sensors and calibrate here without another upload. Pins and Wi-Fi changes still require firmware configuration.')
        image=Path(__file__).parent/'hardware'/'RiverGuard-Wiring.png'
        if image.exists(): st.image(str(image),caption='Verify board labels, voltage dividers and your JSN revision before enabling sensors.')
        guide=Path(__file__).parent/'output'/'pdf'/'RiverGuard-Friend-Setup.pdf'
        if guide.exists(): st.download_button('Download wiring & first-upload guide',guide.read_bytes(),'RiverGuard-Friend-Setup.pdf','application/pdf')
    with st.expander('Build the tank, pole & sensor mounts'):
        layout=Path(__file__).parent/'hardware'/'Tank-Layout.png'
        if layout.exists(): st.image(str(layout),caption='Illustrative side view. Measure your tank and verified sensor range before sizing the stand.')
        assembly=Path(__file__).parent/'hardware'/'Tank-Assembly.md'
        if assembly.exists():
            st.markdown(assembly.read_text(encoding='utf-8'))
            st.download_button('Download tank assembly instructions',assembly.read_text(encoding='utf-8'),'RiverGuard-Tank-Assembly.md','text/markdown')
    frame=core.history('esp32')
    ids=frame.device_id.drop_duplicates().tolist() if not frame.empty else []
    chosen=st.selectbox('Station to set up',ids+['Add a station…'],key='setup_station')
    device=st.text_input('Station ID (same as firmware)',value='riverguard-01',key='setup_device') if chosen=='Add a station…' else chosen
    if not device: st.info('Enter your station ID to begin.');return
    record=setup.load(device); cfg=record['settings']; revision=record['revision']
    prefix=f'setup_{device}_{revision}_'
    st.button('Refresh saved settings',help='Reload settings if another browser changed them.')
    @st.fragment(run_every='2s')
    def monitor():
        row=setup.latest(device)
        current=setup.load(device)
        if row is None:
            st.info('Waiting for this station. You can prepare settings now; they stay pending until it connects.')
            return
        age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(row.received_at)).total_seconds())
        measured=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(row.timestamp)).total_seconds())
        remote=row.get('setup_protocol')=='remote-v1'
        applied=remote and row.get('config_revision')==current['revision']
        state='Connected' if age<=30 else 'Station offline'
        note='Settings acknowledged' if applied else 'Waiting for settings acknowledgement' if remote else 'One-time firmware upgrade needed'
        st.markdown(f'<div class="setup-status"><strong>{state}</strong><span>Last transmission {age:.0f}s ago · measured {measured:.0f}s ago</span><small>{note} · saved revision {current["revision"]}</small></div>',unsafe_allow_html=True)
        if applied and age>30: st.caption('That acknowledgement is from an older packet. Reconnect before capturing a signal.')
        rows=''.join(f'<div><strong>{escape(r["Sensor"])}</strong><span>{escape(r["State"])}</span></div>' for r in sensor_health(row))
        st.markdown('<div class="sensor-health">'+rows+'</div>',unsafe_allow_html=True)
        raw=decode(row.get('raw_json'))
        signals=[('ph_mv','pH input','mV'),('turbidity_mv','Cloudiness input','mV'),('temperature_c','Probe temperature','°C'),('distance_cm','Surface distance','cm')]
        st.markdown('<div class="setup-signals">'+''.join(f'<div><span>{label}</span><strong>{"—" if raw.get(key) is None else f"{raw[key]:.1f} {unit}"}</strong></div>' for key,label,unit in signals)+'</div>',unsafe_allow_html=True)
        st.caption('Raw signals are live; forms below stay still while you type. A signal is not proof that wiring or calibration is correct.')
    monitor()

    def save_change(field,value):
        data=deepcopy(cfg);data[field]=value
        if field!='verified': data['verified']=False
        try:
            new=setup.store(device,data,revision)
        except ValueError as error:
            message=error.errors()[0]['msg'] if hasattr(error,'errors') else str(error)
            st.error(message);return
        st.session_state['setup_notice']=f'Saved revision {new}. The station will pick it up on its next connection. Calibration applies to new samples only.'
        st.rerun()
    if message:=st.session_state.pop('setup_notice',None): st.success(message)
    def capture(target,field,settled=None):
        try: st.session_state[target]=setup.capture(device,field)
        except ValueError as error: st.toast(str(error));return
        if settled: st.session_state[settled]=False
        st.toast('Fresh signal captured. Check the reference value, then save.')

    st.subheader('1 · Check and enable connections')
    st.caption('Enable one sensor at a time after checking its wiring. Disabled channels stay missing.')
    with st.form(prefix+'connections'):
        checked=st.checkbox('I checked wiring and voltage protection for the sensors I am enabling.',key=prefix+'wiring')
        enabled={}
        for key,label in zip(setup.FIELDS,['pH · SEN0161-V2 / GPIO34','Cloudiness · SEN0189 / GPIO35','Temperature · DS18B20 / GPIO27','Water level · JSN TRIG5 / ECHO18']):
            enabled[key]=st.checkbox(label,value=cfg['enabled'][key],key=prefix+'enable_'+key)
        if st.form_submit_button('Save enabled sensors',type='primary'):
            if any(enabled.values()) and not checked: st.error('Confirm the wiring check before enabling a sensor.')
            else: save_change('enabled',enabled)

    st.subheader('2 · Calibrate with known references')
    st.caption('Each save keeps an audit revision and clears the previous verification. Sensor fault states and out-of-range values stay missing.')
    for field,label in [('ph','pH · two known buffers'),('turbidity','Cloudiness · known NTU standards')]:
        with st.expander(label):
            st.write('Rinse between buffers, wait for a stable reading, and use reference values at the calibration temperature.' if field=='ph' else 'Use certified turbidity standards, consistent placement and no bubbles. Tap water is not a known NTU standard.')
            points=cfg[field] or []
            count=2 if field=='ph' else st.selectbox('Number of standards',[2,3,4,5],index=max(0,len(points)-2),key=prefix+'ntu_count')
            settled=prefix+field+'_settled'
            st.checkbox('The probe has settled in the reference solution.',key=settled)
            for i in range(count):
                st.button(f'Capture current signal for {"buffer" if field=="ph" else "standard"} {i+1}',key=prefix+field+f'_capture_{i}',disabled=not st.session_state[settled],on_click=capture,args=(prefix+field+f'_mv_{i}',field+'_mv',settled))
            with st.container():
                values=[]
                for i in range(count):
                    point=points[i] if i<len(points) else {'mv':None,'value':(7. if i==0 else 4.) if field=='ph' else 0.}
                    st.session_state.setdefault(prefix+field+f'_mv_{i}',point['mv'])
                    st.session_state.setdefault(prefix+field+f'_value_{i}',float(point['value']))
                    st.markdown(f'**Reference {i+1}**')
                    left,right=st.columns(2)
                    mv=left.number_input('Measured input (mV)',min_value=150.,max_value=3050.,value=None,step=1.,key=prefix+field+f'_mv_{i}')
                    val=right.number_input('Buffer pH' if field=='ph' else 'Standard NTU',min_value=0.,max_value=14. if field=='ph' else 10000.,value=None,step=.1,key=prefix+field+f'_value_{i}')
                    values.append({'mv':mv,'value':val})
                st.caption('Capture again or enter measured mV manually. Points must span your expected water readings; no extrapolation is used.')
                if st.button('Save pH calibration' if field=='ph' else 'Save cloudiness calibration',key=prefix+field+'_save'): save_change(field,values)

    with st.expander('Temperature · compare with a thermometer'):
        st.caption('Place both probes together and wait for them to stabilize. Correction is limited to ±5 °C; investigate larger differences.')
        st.button('Capture probe temperature',on_click=capture,args=(prefix+'temp_probe','temperature_c'))
        with st.container():
            measured=st.number_input('Probe temperature (°C)',min_value=-55.,max_value=125.,value=None,key=prefix+'temp_probe')
            reference=st.number_input('Reference thermometer (°C)',min_value=-55.,max_value=125.,value=None,key=prefix+'temp_reference')
            st.caption(f'Current correction: {cfg["temperature_offset"]:+.2f} °C. Raw temperature stays unchanged.')
            if st.button('Save temperature correction',key=prefix+'temp_save'):
                if measured is None or reference is None: st.error('Capture the probe and enter the reference temperature first.')
                else: save_change('temperature_offset',reference-measured)

    with st.expander('Water level · zero point and sensor range'):
        st.write('Confirm your JSN revision and trigger/echo mode. Mount above the water. At your chosen zero level, capture the distance from the sensor face to that level.')
        st.button('Capture zero-level distance',on_click=capture,args=(prefix+'level_reference','distance_cm'))
        level=cfg['level'] or {'reference':None,'minimum':None,'maximum':None}
        for key in level: st.session_state.setdefault(prefix+'level_'+key,level[key])
        with st.container():
            data={key:st.number_input(label,min_value=.1,max_value=1000.,value=None,step=.1,key=prefix+'level_'+key) for key,label in [('reference','Distance to zero level (cm)'),('minimum','Verified minimum distance (cm)'),('maximum','Verified maximum distance (cm)')]}
            st.caption('Water height = zero-level distance − measured distance. Blind-zone echoes, timeouts and negative heights stay missing.')
            if st.button('Save water-level calibration',key=prefix+'level_save'): save_change('level',data)

    st.subheader('3 · Verify the installed station')
    st.caption('Recheck pH buffers and NTU standards, compare temperature with a thermometer, and check at least two water heights with a ruler. This declaration does not certify water safety.')
    with st.form(prefix+'verify'):
        verified=st.checkbox('I physically checked all four enabled, calibrated sensors.',value=cfg['verified'])
        if st.form_submit_button('Save verification'): save_change('verified',verified)
    st.download_button('Download saved station settings',__import__('json').dumps(record,indent=2),f'{device}-calibration.json','application/json')
