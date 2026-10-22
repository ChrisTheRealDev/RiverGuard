"""Conservative checks for known unsupported river claims, not a truth proof.

These checks intentionally reject some ambiguous prose. They neither replace
the language model with preset replies nor certify every remaining claim.
"""
import math
import re

NAMES={'ph':('pH','pH'),'turbidity':('Cloudiness','NTU'),
       'temperature':('Temperature','°C'),'water_level':('Water level','cm')}


def _number(value):
    return f'{value:g}'


def authoritative_facts(context):
    latest=context.get('latest') or {}
    thresholds=context.get('demo_thresholds',{})
    lines=['SOURCE: '+context.get('data_kind','No measurements')+'.']
    if context.get('clock_ahead'):
        lines.append('TIME: INVALID. Station clock is ahead of the laptop. Check the clock; do not describe current conditions or call this old data.')
    elif context.get('stale'):
        lines.append('TIME: OLD. Captured readings are stale, not current conditions.')
    else:
        lines.append('TIME: Fresh when captured. Describe the captured sample, not an unmeasured later condition.')
    if not latest:
        return '\n'.join(lines+['No station measurement is available. Do not invent any values.'])
    lines.append('Captured at: '+str(latest.get('timestamp')))
    if latest.get('source')=='esp32' and not latest.get('calibrated'):
        lines.append('CALIBRATION: UNVERIFIED. Real sensor values are provisional; say so.')
    for key,(name,unit) in NAMES.items():
        value=latest.get(key)
        lines.append(f'{name}: UNAVAILABLE (missing/unhealthy sensor).' if value is None else f'{name}: {_number(value)} {unit}.')
    level=latest.get('water_level');watch=thresholds.get('elevated_cm',70);warning=thresholds.get('warning_cm',100)
    if level is not None:
        category='AT/ABOVE WARNING' if level>=warning else 'ABOVE WATCH BUT BELOW WARNING' if level>=watch else 'BELOW WATCH AND BELOW WARNING'
        lines.append(f'HEIGHT FACT: {_number(level)} cm is {category}; watch {_number(watch)} cm, warning {_number(warning)} cm.')
    rate=context.get('observed_rise_cm_per_min');limit=thresholds.get('warning_rise_cm_per_min',10)
    if rate is None:
        lines.append('SPEED FACT: Observed rise is UNAVAILABLE. '+context.get('trend_note','Not enough valid same-calibration samples. Do not invent a speed or interval.'))
    else:
        direction='FALLING' if rate<0 else 'RISING' if rate>0 else 'STEADY'
        relation='CROSSES' if rate>=limit else 'DOES NOT CROSS'
        lines.append(f'SPEED FACT: {_number(rate)} cm/min, {direction}; {relation} rise warning {_number(limit)} cm/min. Speed and height use different units.')
    status=context.get('dashboard_status',{})
    lines.append('CAPTURED STATUS: '+status.get('title','No complete assessment')+'. '+status.get('reason',''))
    if status.get('action'):lines.append('NEXT STEP: '+status['action'])
    lines.append('Reference comparisons:')
    for field,(low,high) in [('ph',(6.5,8.5)),('turbidity',(0,50)),('temperature',(20,32))]:
        value=latest.get(field)
        if value is not None:
            relation='WITHIN' if low<=value<=high else 'BELOW' if value<low else 'ABOVE'
            label,unit=NAMES[field]
            lines.append(f'{label} {_number(value)} {unit} is {relation} the DEMO reference {_number(low)}–{_number(high)} {unit}.')
    lines.append('No drinking/swimming/animal safety, confirmed pollution, chemical cause, official WQI or flood prediction can be established.')
    return '\n'.join(lines)


def verify_reply(text,context,question='',partial=False):
    """Return explicit failure reasons for the supported checks only."""
    reasons=[];latest=context.get('latest') or {};lower=text.lower()
    settings=context.get('demo_thresholds',{})
    def add(reason):
        if reason not in reasons:reasons.append(reason)
    def negated(prefix):
        return bool(re.search(r"\b(?:not|no|cannot|can't|unable|isn't|aren't|doesn't|don't|hasn't|haven't|tidak|tak|bukan|belum)\b",prefix,re.I))
    # A negation in an unrelated clause must not excuse a later assertion:
    # "no germ count is available, so this water is safe" remains unsafe.
    sentences=re.split(r'(?<=[.!?;])\s+|\n+|,\s*|\b(?:but|however|so|yet|although|and)\b',lower)
    for sentence in sentences:
        for match in re.finditer(r'(?:safe.{0,25}(?:drink|swim|fish|animal|otter)|safe drinking|(?:water|river) (?:is|looks|seems) (?:definitely |completely )?safe|aman.{0,25}(?:diminum|minum)|selamat.{0,25}minum|you (?:can|should) drink)',sentence):
            if not negated(sentence[max(0,match.start()-65):match.start()]):
                add('The reply suggests drinking or animal safety that these sensors cannot establish.')
        for match in re.finditer(r'(?:confirmed pollution|pollution[- ]free|no pollution|no pollutants|not toxic|non[- ]?toxic|no signs.{0,25}(?:toxicity|poison|pollution)|tidak ada tanda.{0,25}keracunan)',sentence):
            if not negated(sentence[max(0,match.start()-45):match.start()]):add('The reply claims a pollution or toxicity conclusion unsupported by the sensors.')
    if context.get('clock_ahead'):
        if not partial and not re.search(r'\b(?:clock|ahead|future|jam|masa depan)\b',lower):add('The reply omits the invalid station-clock warning.')
        if re.search(r'\b(?:old readings|stale readings)\b',lower):add('Future-dated measurements were incorrectly described as old readings.')
    elif not partial and context.get('stale') and not re.search(r'\b(?:old|stale|outdated|delayed|historical|lama)\b',lower):
        add('The reply treats old captured readings as current conditions.')
    if not partial and latest.get('source')=='esp32' and not latest.get('calibrated') and not re.search(r'\b(?:provisional|uncalibrated|unverified|calibrat|not verified)',lower):
        add('The reply omits that the real sensor values are provisional.')
    station_question=bool(re.search(r'\b(?:our|current|latest|river|water|station|reading|sensor|sungai|bacaan)\b',question,re.I))
    bare_refusal=bool(re.fullmatch(r"\s*i (?:can't|cannot) (?:make that statement|say that|do that)[.!]?\s*",lower))
    if not partial and not bare_refusal and context.get('data_kind')=='synthetic demo' and station_question and not re.search(r'demo|synthetic|simulat',lower):
        add('The reply does not identify the station interpretation as synthetic demonstration data.')
    foreign_markers=set(re.findall(r'\b(?:air|sungai|ini|aman|selamat|tidak|diminum|minum|keracunan|berdasarkan|bacaan)\b',lower))
    if len(foreign_markers)>=3:
        add('The draft uses language this English dashboard cannot reliably check. Retry for an English answer.')
    allowed={'cm':[],'cm/min':[],'NTU':[0,50],'C':[20,32],'pH':[0,7,14,6.5,8.5]}
    for key,(_,unit) in NAMES.items():
        if latest.get(key) is not None:allowed['C' if unit=='°C' else unit].append(latest[key])
    allowed['cm'] += [settings.get('elevated_cm',70),settings.get('warning_cm',100)]
    allowed['cm/min'] += [settings.get('warning_rise_cm_per_min',10)]
    rate=context.get('observed_rise_cm_per_min')
    if rate is not None:allowed['cm/min'].append(rate)
    # A warning setting is a legitimate number to quote, but it must never be
    # presented as the measured speed. Check that role separately from units.
    measured_speed=r'\b(?:observed rise|measured (?:rise|speed|rate)|rose|fell|rising|falling|(?:rise|speed|rate)\s+(?:is|of|at|:))\b(?:(?!\b(?:warning|threshold|setting|limit)\b).){0,55}?([+-]?\d+(?:\.\d+)?)\s*cm\s*(?:/|per\s+)\s*min(?:ute)?s?'
    for sentence in sentences:
        for claim in re.finditer(measured_speed,sentence):
            if re.search(r'\b(?:warning|threshold|setting|limit)\s+(?:rise\s+)?$',sentence[:claim.start()]):continue
            if negated(sentence[:claim.start()]):continue
            value=float(claim[1])
            if rate is None or not math.isclose(value,float(rate),abs_tol=max(.15,abs(float(rate))*.02)):
                add('The reply presents a setting or unsupported value as the observed water-rise speed.')
    delta=context.get('change_since_previous_sample',{})
    for key,(_,unit) in NAMES.items():
        if delta.get(key) is not None:allowed['C' if unit=='°C' else unit].append(delta[key])
    pattern=r'(?P<number>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>cm\s*(?:/|per\s+)\s*(?:min(?:ute)?s?)|cm\b|NTU\b|°\s*C\b|degrees?\s+Celsius\b|pH\b)'
    for match in re.finditer(pattern,text,re.I):
        value=float(match['number']);unit=match['unit'].lower()
        if value<0 and match.start()>0 and text[match.start()-1].isdigit():
            value=abs(value)  # ASCII range separator, e.g. 20-32 °C, not -32 °C.
        unit='cm/min' if unit.startswith('cm') and ('/' in unit or 'per' in unit) else 'cm' if unit=='cm' else 'NTU' if unit=='ntu' else 'pH' if unit=='ph' else 'C'
        if not any(math.isclose(value,float(candidate),abs_tol=max(.15,abs(float(candidate))*.02)) for candidate in allowed[unit]):
            add(f'The reply includes an unsupported value ({match.group(0)}).')
    if station_question or re.search(r'\b(?:our|current|latest|measured|your)\b',lower):
        for match in re.finditer(r'\bph\s*(?:(?:reading|value)\s*)?(?:is|at|of|=|:)?\s*([+-]?\d+(?:\.\d+)?)',lower):
            value=float(match[1])
            if latest.get('ph') is None and re.search(r'\bph\s*(?:(?:reading|value)\s*)?(?:is|at|=|:)',match[0]):
                add('The reply reports a measured pH although that sensor is unavailable.')
            elif not any(math.isclose(value,float(item),abs_tol=.15) for item in allowed['pH']):
                add('The reply includes an unsupported pH value.')
    # Values may each be legitimate while the comparison is dimensionally
    # wrong: a rise of 120 cm/min cannot exceed a height threshold of 70 cm.
    for sentence in re.split(r'[;\n]+',lower):
        for speed in re.finditer(r'[+-]?\d+(?:\.\d+)?\s*cm\s*(?:/|per\s+)\s*min(?:ute)?s?',sentence):
            remainder=sentence[speed.end():]
            comparison=re.search(r'\b(?:above|below|over|under|exceeds?|crossed|higher|lower)\b.{0,45}?\d+(?:\.\d+)?\s*cm\b(?!\s*(?:/|per\b))',remainder)
            if comparison and not re.search(r'\b(?:water[- ]level|height|depth)\b',remainder[:comparison.start()]) and not negated(remainder[:comparison.start()]):
                add('The reply compares a rise speed with a water-height threshold; those units differ.')
    if latest.get('ph') is None and re.search(r'(?:current|latest|our|your|measured).{0,25}ph.{0,20}(?:is|at|=|:)\s*\d',lower):
        add('The reply reports a measured pH although that sensor is unavailable.')
    if rate is None and re.search(r'(?:rising|rose|rise|falling|fell).{0,35}(?:rate|\d+\s*cm)',lower):
        # A quoted warning setting is allowed; an observed speed is not.
        for sentence in sentences:
            if re.search(r'(?:rising|rose|falling|fell).{0,35}\d+\s*cm',sentence) and not negated(sentence) and not re.search(r'unavailable|cannot|could not|threshold|setting',sentence):
                add('The reply invents an observed rise despite an unavailable trend.')
    level=latest.get('water_level');watch=settings.get('elevated_cm',70);warning=settings.get('warning_cm',100)
    for sentence in sentences:
        if level is not None and not negated(sentence):
            if level<warning and (rate is None or rate<settings.get('warning_rise_cm_per_min',10)) and re.search(r'\b(?:crossed|exceeded|above|over)\b.{0,20}\bwarning\b|\bat(?: the)? warning\b|flood (?:warning|action)',sentence):
                add('The reply incorrectly classifies a below-warning level as a warning.')
            if level>=warning and re.search(r'below.{0,15}warning|under.{0,15}warning',sentence):add('The reply incorrectly calls a warning-level measurement below warning.')
            if level>=watch and re.search(r'below.{0,15}watch|under.{0,15}watch',sentence):add('The reply incorrectly calls an elevated level below watch.')
        for field,terms,low,high in [('temperature',r'temperature|celsius|°c',20,32),('ph',r'\bph\b',6.5,8.5),('turbidity',r'turbidity|cloudiness|ntu',0,50)]:
            value=latest.get(field)
            if value is None or not re.search(terms,sentence) or negated(sentence):continue
            if low<=value<=high and re.search(r'(?:above|outside|exceeded|below).{0,30}(?:reference|range)',sentence):add(f'The reply contradicts the captured {field} reference comparison.')
            if not low<=value<=high and re.search(r'within.{0,20}(?:reference|range)',sentence):add(f'The reply contradicts the captured {field} reference comparison.')
    return {'passed':not reasons,'reasons':reasons,'can_continue':not reasons,
            'limitations':'Conservative checks for known unsupported claims; not a proof of semantic correctness.'}
