"""One bounded, persisted demonstration producer per installation."""
import math
from .store import Problem, encode, iso, number, boolean

SCENARIOS = ('Normal river', 'Cloudier water', 'Sudden change', 'Rising water level')
INITIAL = {'revision': 0, 'scenario': SCENARIOS[0], 'running': True, 'step': 0, 'lastSlot': -1, 'error': None}


def sample(scenario, step, now):
    phase = step % 120
    # Time changes the seed between cycles; replaying a captured time is reproducible.
    seed = int(now//240000) % 1000003
    def random_at(index, channel):
        x = (index + channel*131 + seed*8191) & 0xffffffff
        for _ in range(2):
            x = ((x ^ (x >> 16)) * 0x45d9f3b) & 0xffffffff
        return (x ^ (x >> 16))/4294967295*2-1
    def variation(channel, span=5):
        position = phase/span; index = math.floor(position); t = position-index
        blend = t*t*(3-2*t)
        drift = random_at(index, channel)*(1-blend)+random_at(index+1, channel)*blend
        return .8*drift+.2*random_at(phase, channel+50)
    result = dict(timestamp=iso(now), ph=7.2+.12*variation(1), turbidity=14+4*variation(2),
                  temperature=27+.25*variation(3,20), water_level=30+.3*variation(4), scenario=scenario)
    if phase >= 10:
        if scenario == SCENARIOS[1]: result['turbidity'] = 65+120*(1-math.exp(-(phase-10)/24))+6*variation(2)
        if scenario == SCENARIOS[2]: result.update(ph=5.8+.12*variation(1), turbidity=80+8*variation(2))
        if scenario == SCENARIOS[3]: result['water_level'] = 45+100*(1-math.exp(-(phase-10)/20))+.6*variation(4)
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
