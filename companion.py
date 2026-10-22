"""Offline, data-grounded river guide. No external chat service or invented facts."""
from datetime import datetime, timezone
import pandas as pd

def explain(question, frame, elevated=70, warning=100):
    q=question.lower()
    if any(word in q for word in ['drink','safe','toxic','swim']):
        return 'These sensors cannot establish drinking, swimming, or fish safety, or identify toxic chemicals. An anomaly is a reason to investigate, not proof of pollution.'
    if frame.empty:
        return 'I don’t have a reading from this source yet. Select Synthetic demonstration to explore, or connect your ESP32. I never replace a missing reading with zero.'
    row=frame.iloc[-1]
    origin='synthetic demonstration' if row.source=='simulation' else 'ESP32'
    stamp=pd.to_datetime(row.timestamp,utc=True)
    age=(datetime.now(timezone.utc)-stamp.to_pydatetime()).total_seconds()
    context=f'Using the latest {origin} sample ({stamp.tz_convert("Asia/Kuala_Lumpur"):%I:%M:%S %p} MYT). '
    if age>30: context+='This sample is stale; it does not describe current conditions. '
    if row.source=='esp32' and not row.calibrated: context+='Sensors are marked uncalibrated. '
    topics=[(['ph','acid'], 'ph','pH', 'pH','pH describes acidity or alkalinity. Around 7 is neutral; lower is more acidic, higher is more alkaline.'),
            (['turbid','cloud','mud'], 'turbidity','Turbidity','NTU','Turbidity describes water cloudiness from suspended material. A rise alone cannot tell us whether the cause is sediment or pollution.'),
            (['temp','warm','heat'], 'temperature','Temperature','°C','Temperature helps us spot changes in conditions. An unusual reading does not identify its cause.'),
            (['level','flood','rise'], 'water_level','Water level','cm','Water level is height above the station’s reference datum. This is a demonstration threshold watch, not a validated flood forecast.')]
    for words,key,label,unit,definition in topics:
        if any(word in q for word in words):
            value=row[key]
            value_text='unavailable' if pd.isna(value) else f'{value:.2f} {unit}'
            text=context+f'{label} is {value_text}. '+definition
            if key=='water_level': text+=f' Current demonstration thresholds: elevated at {elevated:g} cm; warning at {warning:g} cm.'
            return text
    if any(word in q for word in ['anomal','alert','pollut','ai','unusual']):
        return context+('The AI assessment is unavailable because measurements are incomplete.' if pd.isna(row.anomaly) else row.explanation)+' The model learned synthetic normal conditions. Its alerts are experimental and do not confirm pollution.'
    if any(word in q for word in ['hello','hi rill','who are']):
        return 'I’m Rill, your river companion. I’m an offline guide, not a general AI chatbot. Ask me about the current readings, pH, cloudy water, temperature, water level, or AI alerts.'
    if any(word in q for word in ['happen','summary','explain','river','reading','now','status']):
        pieces=[]
        for _,key,label,unit,_ in topics:
            value=row[key]
            if pd.isna(value): pieces.append(f'{label} is missing')
            elif key=='ph': pieces.append(f'pH {value:.2f} is '+('inside' if 6.5<=value<=8.5 else 'outside')+' the demo range of 6.5–8.5')
            elif key=='turbidity': pieces.append(f'turbidity {value:.1f} NTU is '+('above' if value>50 else 'below')+' the 50 NTU demo threshold')
            elif key=='temperature': pieces.append(f'temperature is {value:.1f} °C')
            else: pieces.append(f'water level is {value:.1f} cm, '+('at warning level' if value>=warning else 'elevated' if value>=elevated else 'below the elevated threshold'))
        return context+'; '.join(pieces)+'. These comparisons describe this prototype, not water safety.'
    return 'I can explain the readings, pH, turbidity, temperature, water level, and AI alerts. Try “What’s happening now?” or “Why is the water cloudy?” I don’t have a general-purpose language model connected.'
