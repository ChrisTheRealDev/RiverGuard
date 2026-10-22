"""One bounded, persisted demonstration producer per installation."""
import math
from .store import Problem, encode, iso, number, boolean

SCENARIOS = ('Normal river', 'Cloudier water', 'Sudden change', 'Rising water level')
INITIAL = {'revision': 0, 'scenario': SCENARIOS[0], 'running': True, 'step': 0, 'lastSlot': -1, 'error': None}


def sample(scenario, step, now):
    phase = step % 120
    wave = math.sin(phase*.7)
    result = dict(timestamp=iso(now), ph=7.2+.08*wave, turbidity=14+2*wave,
                  temperature=27+.2*wave, water_level=30+.15*wave, scenario=scenario)
    if phase >= 10:
        if scenario == SCENARIOS[1]: result['turbidity'] = min(250, 65+(phase-10)*2)
        if scenario == SCENARIOS[2]: result.update(ph=5.8, turbidity=80)
        if scenario == SCENARIOS[3]: result['water_level'] = min(150, 45+(phase-10)*4)
    return result


def state(db):
    import json
    row = db.execute("SELECT value FROM state WHERE key='runtime:demo'").fetchone()
    return json.loads(row[0]) if row else dict(INITIAL)


def save(db, value):
    db.execute("INSERT INTO state VALUES ('runtime:demo',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encode(value),))


def control(store, expected, scenario, running):
    number(expected, 0, 2147483646, True); boolean(running)
    if scenario not in SCENARIOS: raise Problem(422, 'Choose one of the four demonstration scenarios.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = state(db)
        if current['revision'] != expected: raise Problem(409, 'Demo controls changed elsewhere. Refresh and try again.')
        if current['scenario'] != scenario: current['step'] = 0
        current.update(revision=expected+1, scenario=scenario, running=running, error=None)
        save(db, current)
        return current


def tick(store, now):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = state(db)
        slot = int(now//2000)
        if not current['running'] or current['lastSlot'] == slot: return current
        value = sample(current['scenario'], current['step'], now)
        value.update(device_id='demo-station', mode='simulation')
        store._append(db, 'simulation', 'demo-station', value, None, now, 'demo-slot-'+str(slot))
        current.update(step=(current['step']+1)%120, lastSlot=slot, error=None)
        save(db, current)
        return current
