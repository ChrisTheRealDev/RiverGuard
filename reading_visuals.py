"""Explain measurements without inferring water safety from a single sensor."""
from math import isfinite
from html import escape


def reading_guide(field, value, elevated=70, warning=100, missing_text='Waiting for this sensor'):
    if value is None or not isfinite(float(value)):
        return '<div class="reading-guide missing">'+escape(missing_text)+'</div>'
    value = float(value)
    if field == 'ph':
        title = 'Acidic side' if value < 6.5 else 'Alkaline side' if value > 8.5 else 'Near neutral'
        left, right, position = 'Acidic', 'Alkaline', value / 14
        detail = '7 is neutral; lower is more acidic.'
        gradient = '#dc9b7e,#bdb1ff,#7bcbb7'
    elif field == 'turbidity':
        title = 'Above cloudiness reference' if value > 50 else 'Within cloudiness reference'
        left, right, position = 'Less cloudy', 'More cloudy', value / 100
        detail = 'Cloudiness; not germs or chemicals.'
        gradient = '#77c8cf,#a4b8a5,#b69a64'
    elif field == 'temperature':
        title = 'Below temperature reference' if value < 20 else 'Above temperature reference' if value > 32 else 'Within temperature reference'
        left, right, position = 'Cooler', 'Warmer', value / 45
        detail = 'Water warmth in degrees Celsius.'
        gradient = '#7ebcdb,#bdb1ff,#e7a087'
    else:
        title = 'At warning level' if value >= warning else 'At watch level' if value >= elevated else f'{elevated-value:.1f} cm below watch'
        left, right, position = 'Station zero', f'Warning {warning:g} cm', value / warning
        detail = 'Height above the station’s zero.'
        gradient = '#79cbb5,#d6be7e,#e49791'
    position = min(100, max(0, position * 100))
    return f'<div class="reading-guide"><strong>{escape(title)}</strong><div class="reading-scale" role="img" aria-label="{escape(title)}; {escape(left)} to {escape(right)}" style="background:linear-gradient(90deg,{gradient})"><i style="left:{position:.1f}%"></i></div><div class="scale-labels"><span>{escape(left)}</span><span>{escape(right)}</span></div><small>{escape(detail)}</small></div>'
