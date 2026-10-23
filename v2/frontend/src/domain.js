(function (root, factory) {
  const api = factory();
  root.RiverGuardDomain = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const FIELDS = ['ph', 'turbidity', 'temperature', 'water_level'];
  const NAMES = { ph: 'Acidity', turbidity: 'Cloudiness', temperature: 'Temperature', water_level: 'Water level' };
  const DEFAULT_WATCH = { elevated: 70, warning: 100, rise_limit: 10 };
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const object = value => {
    if (typeof value === 'string') { try { value = JSON.parse(value); } catch (_) { return {}; } }
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  };
  function millis(value) {
    if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/i.test(value)) return NaN;
    return Date.parse(value);
  }
  function normalizedTime(value) { const stamp = millis(value); return Number.isFinite(stamp) ? new Date(stamp).toISOString() : null; }
  function pointsValid(points, field) {
    if (!Array.isArray(points) || (field === 'ph' ? points.length !== 2 : points.length < 2 || points.length > 5)) return false;
    if (!points.every(p => p && typeof p === 'object')) return false;
    const sorted = points.slice().sort((a, b) => a.mv - b.mv);
    if (!sorted.every(p => p && finite(p.mv) && p.mv >= 150 && p.mv <= 3050 && finite(p.value) && p.value >= 0 && p.value <= (field === 'ph' ? 14 : 10000))) return false;
    if (sorted.some((p, i) => i > 0 && p.mv - sorted[i - 1].mv < 1)) return false;
    if (field === 'ph') return Math.abs(sorted[1].value - sorted[0].value) >= .1;
    const direction = Math.sign(sorted[1].value - sorted[0].value);
    return direction !== 0 && sorted.every((p, i) => !i || Math.sign(p.value - sorted[i - 1].value) === direction);
  }
  function levelValid(level) {
    return !!level && ['reference', 'minimum', 'maximum'].every(k => finite(level[k]) && level[k] > 0 && level[k] <= 1000)
      && level.maximum > level.minimum && level.reference > level.minimum && level.reference <= level.maximum;
  }
  function validateCalibration(input) {
    const settings = object(input), errors = [];
    if (!settings.enabled || FIELDS.some(field => typeof settings.enabled[field] !== 'boolean')) errors.push('Specify whether each of the four sensors is enabled.');
    for (const field of ['ph', 'turbidity']) {
      if (settings[field] != null && !pointsValid(settings[field], field)) errors.push(field === 'ph'
        ? 'Use two different pH buffers between 0 and 14, with GPIO signals from 150 to 3050 mV and at least 1 mV apart.'
        : 'Use 2–5 known NTU standards from 0 to 10000, with strictly monotonic GPIO signals/values and at least 1 mV between signals.');
    }
    if (settings.level != null && !levelValid(settings.level)) errors.push('Water distance needs a positive minimum, a larger maximum, and a reference between them (up to 1000 cm).');
    if (!finite(settings.temperature_offset) || Math.abs(settings.temperature_offset) > 5) errors.push('Temperature correction must be a finite number between −5 and +5 °C.');
    if (typeof settings.verified !== 'boolean') errors.push('Record whether physical verification has been completed.');
    if (settings.verified && !(FIELDS.every(k => settings.enabled && settings.enabled[k]) && pointsValid(settings.ph, 'ph') && pointsValid(settings.turbidity, 'turbidity') && levelValid(settings.level))) errors.push('Physical verification needs all four sensors enabled and their calibration saved.');
    return { valid: errors.length === 0, errors };
  }
  function interpolate(mv, points, field) {
    if (!finite(mv) || !pointsValid(points, field)) return null;
    const sorted = points.slice().sort((a, b) => a.mv - b.mv);
    for (let i = 1; i < sorted.length; i++) {
      const a = sorted[i - 1], b = sorted[i];
      if (mv >= a.mv && mv <= b.mv) return a.value + (mv - a.mv) * (b.value - a.value) / (b.mv - a.mv);
    }
    return null;
  }
  function deriveReading(record, now = Date.now()) {
    record = object(record);
    const payload = Object.keys(object(record.payload)).length ? object(record.payload) : record;
    const source = record.source === 'simulation' || payload.source === 'simulation' || payload.mode === 'simulation' ? 'simulation' : 'esp32';
    const raw = { ...object(payload.raw || record.raw || record.raw_json) }, reported = object(payload.sensor_health || record.sensor_health || record.sensor_health_json);
    const settings = record.settings && typeof record.settings === 'object' ? record.settings : null;
    const timestamp = normalizedTime(record.timestamp || payload.timestamp), receivedAt = normalizedTime(record.receivedAt || record.received_at || (source === 'simulation' ? timestamp : null));
    const age = timestamp ? (now - millis(timestamp)) / 1000 : null, receiptAge = receivedAt ? (now - millis(receivedAt)) / 1000 : null;
    const fresh = finite(age) && age >= -5 && age <= 30 && finite(receiptAge) && receiptAge >= -5 && receiptAge <= 30;
    const values = {}, health = {};
    for (const field of FIELDS) {
      let value = null, state = 'missing';
      const fault = reported[field];
      if (source === 'simulation') {
        value = finite(payload[field]) ? payload[field] : null;
        state = value === null ? 'missing' : 'synthetic';
      } else if (!settings) state = 'calibration_unavailable';
      else if (!settings.enabled || settings.enabled[field] !== true) state = 'disabled';
      else if (typeof fault === 'string' && !['ok', 'uncalibrated', 'unknown', ''].includes(fault)) state = fault;
      else if (field === 'ph' || field === 'turbidity') {
        const mv = raw[field + '_mv'], adc = raw[field + '_adc'];
        if (!finite(mv)) state = 'missing';
        else if (mv < 150 || mv > 3050 || (adc != null && (!finite(adc) || adc <= 5 || adc >= 4090))) state = 'adc_limit';
        else if (!pointsValid(settings[field], field)) state = 'uncalibrated';
        else { value = interpolate(mv, settings[field], field); state = value === null ? 'out_of_range' : 'ok'; }
      } else if (field === 'temperature') {
        if (finite(raw.temperature_c) && finite(settings.temperature_offset) && Math.abs(settings.temperature_offset) <= 5) {
          value = raw.temperature_c + settings.temperature_offset;
          if (raw.temperature_c < -55 || raw.temperature_c > 125 || value < -55 || value > 125) value = null;
        }
        state = value === null ? 'missing' : 'ok';
      } else {
        const distance = raw.distance_cm, level = settings.level;
        if (!finite(distance)) state = 'timeout';
        else if (!levelValid(level)) state = 'uncalibrated';
        else if (distance < level.minimum || distance > level.maximum || distance > level.reference) state = 'out_of_range';
        else { value = level.reference - distance; state = 'ok'; }
      }
      if (value !== null && (!finite(value) || (field === 'ph' && (value < 0 || value > 14)) || (field === 'turbidity' && value < 0) || (field === 'water_level' && value < 0))) { value = null; state = 'out_of_range'; }
      values[field] = value; health[field] = state;
    }
    const revision = Number.isInteger(payload.config_revision) && payload.config_revision >= 0 ? payload.config_revision : Number.isInteger(record.revision) ? record.revision : null;
    // Hardware must retain a known captured revision/settings pair, never today's settings.
    if (source === 'esp32' && revision === null) for (const field of FIELDS) { values[field] = null; health[field] = 'calibration_unavailable'; }
    const calibrated = source === 'esp32' && settings && settings.verified === true && FIELDS.every(field => values[field] !== null) && revision !== null;
    const station = record.deviceId || record.device_id || payload.device_id || (source === 'simulation' ? 'demo-station' : 'unknown-station');
    return { id: record.id == null ? null : record.id, station_id: station, device_id: station, source, timestamp, received_at: receivedAt, receivedAt, revision,
      values, ...values, raw, health, sensor_health: health, settings, payload, calibrated: Boolean(calibrated), provisional: source === 'esp32' && !calibrated,
      fresh, age_seconds: age, connection_age_seconds: receiptAge, clock_ahead: (finite(age) && age < -5) || (finite(receiptAge) && receiptAge < -5),
      calibration_label: source === 'simulation' ? 'Synthetic demo' : calibrated ? 'Physically checked by owner · not certified' : 'Provisional · verify wiring and calibration' };
  }
  function watchSettings(watch) {
    watch = object(watch);
    const elevated = finite(watch.elevated) && watch.elevated >= 0 ? watch.elevated : DEFAULT_WATCH.elevated;
    const warning = finite(watch.warning) && watch.warning > elevated ? watch.warning : Math.max(DEFAULT_WATCH.warning, elevated + 1);
    return { elevated, warning, rise_limit: finite(watch.rise_limit) && watch.rise_limit > 0 ? watch.rise_limit : DEFAULT_WATCH.rise_limit };
  }
  function sameSegment(a, b) { return a && b && a.source === b.source && a.station_id === b.station_id && a.revision === b.revision; }
  function riseRate(readings) {
    if (!readings.length || !readings[readings.length - 1].fresh) return null;
    const tail = [];
    for (let i = readings.length - 1; i >= 0 && tail.length < 5; i--) {
      const row = readings[i], newer = tail[tail.length - 1];
      if (!finite(row.water_level) || !row.timestamp || (newer && (!sameSegment(row, newer) || millis(newer.timestamp) - millis(row.timestamp) > 30000))) break;
      tail.push(row);
    }
    if (tail.length < 5) return null;
    tail.reverse(); const first = millis(tail[0].timestamp), last = millis(tail[4].timestamp);
    if (last - first < 8000) return null;
    const xs = tail.map(row => (millis(row.timestamp) - first) / 1000), ys = tail.map(row => row.water_level);
    const meanX = xs.reduce((a, b) => a + b, 0) / 5, meanY = ys.reduce((a, b) => a + b, 0) / 5;
    const denominator = xs.reduce((sum, x) => sum + (x - meanX) ** 2, 0);
    return denominator ? Math.round(xs.reduce((sum, x, i) => sum + (x - meanX) * (ys[i] - meanY), 0) / denominator * 6000) / 100 : null;
  }
  function evaluate(records, watch, now = Date.now()) {
    const settings = watchSettings(watch), all = (Array.isArray(records) ? records : []).map(row => deriveReading(row, now)).sort((a, b) => (millis(a.timestamp) || 0) - (millis(b.timestamp) || 0) || Number(a.id || 0) - Number(b.id || 0));
    const newest = all[all.length - 1] || null;
    const rows = newest ? all.filter(row => row.station_id === newest.station_id && row.source === newest.source) : [];
    const latest = rows[rows.length - 1] || null, previous = rows.length > 1 ? rows[rows.length - 2] : null, deltas = {}, signals = [];
    const base = { latest, previous, deltas, signals, rate: null, missing: [], settings, tone: 'muted', title: 'Waiting for readings', reason: 'Connect a sensor station or start a clearly labelled demonstration.', action: 'Open Sensor setup to get started.', flood: 'Water level unavailable', age: latest ? latest.age_seconds : null };
    if (!latest) return base;
    const missing = FIELDS.filter(field => latest[field] === null), rate = riseRate(rows), historical = !latest.fresh;
    const add = (kind, severity, title, explanation) => signals.push({ kind, severity, title: (historical ? 'Last-known · ' : '') + title, explanation, timestamp: latest.timestamp });
    if (sameSegment(latest, previous) && latest.timestamp && previous.timestamp && millis(latest.timestamp) > millis(previous.timestamp)) for (const field of FIELDS) if (finite(latest[field]) && finite(previous[field])) deltas[field] = Math.round((latest[field] - previous[field]) * 1000) / 1000;
    for (const [field, low, high] of [['ph', 6.5, 8.5], ['turbidity', 0, 50], ['temperature', 20, 32]]) if (finite(latest[field]) && (latest[field] < low || latest[field] > high)) add(field + '_reference', 'Review', NAMES[field] + ' outside reference', 'Outside the prototype reference; inspect the sensor and context. This does not identify pollution or establish water safety.');
    let flood = 'Water level unavailable';
    if (finite(latest.water_level)) {
      flood = latest.water_level >= settings.warning ? 'At or above warning level' : latest.water_level >= settings.elevated ? 'At watch level' : 'Below watch level';
      if (latest.water_level >= settings.warning) add('water_warning', 'Warning', 'Water height above warning', `${latest.water_level.toFixed(1)} cm meets the ${settings.warning} cm station setting. Check the physical water height; this is not a flood forecast.`);
      else if (latest.water_level >= settings.elevated) add('water_watch', 'Watch', 'Water height at watch', `${latest.water_level.toFixed(1)} cm meets the ${settings.elevated} cm station setting.`);
    }
    if (finite(rate) && rate >= settings.rise_limit) add('water_rise', 'Warning', 'Rapid water rise', `Observed ${rate.toFixed(2)} cm/min meets the ${settings.rise_limit} cm/min rise setting, using five same-calibration samples.`);
    if (missing.length) signals.push({ kind: 'sensor_health', severity: 'Review', title: 'Some sensor readings are unavailable', explanation: missing.map(field => NAMES[field]).join(', ') + '. Check the connection, usable range and captured calibration revision.', timestamp: latest.timestamp });
    const warning = signals.some(signal => signal.severity === 'Warning'), watchSignal = signals.some(signal => signal.severity === 'Watch'), reference = signals.some(signal => signal.kind.endsWith('_reference'));
    let tone = warning ? 'alert' : watchSignal || reference ? 'watch' : missing.length ? 'muted' : 'calm';
    let title = warning ? 'Water-level warning' : watchSignal ? 'Water-level watch' : reference ? 'A reading needs attention' : missing.length ? 'Some sensors need attention' : 'No unusual signals';
    let reason = warning || watchSignal ? flood + (finite(rate) && rate >= settings.rise_limit ? ' · rise rate is above the configured setting.' : '.') : reference ? 'A sensor is outside the prototype reference.' : missing.length ? 'A complete river picture is not available.' : 'Available readings are within the prototype references.';
    if (missing.length && (warning || watchSignal)) reason += ' Other sensor readings are missing; the water-height signal remains important.';
    if (historical) {
      title = latest.clock_ahead ? 'Station clock needs checking' : warning || watchSignal ? 'Last-known ' + title.toLowerCase() : 'Waiting for fresh readings';
      reason = (latest.clock_ahead ? 'The station or receipt clock is ahead. ' : 'These are old or delayed readings. ') + reason;
      flood = 'Last-known · ' + flood;
      if (!warning && !watchSignal) tone = 'muted';
    }
    const action = latest.clock_ahead ? 'Check the station clock and reconnect before interpreting current conditions.' : historical ? 'Keep this app active and reconnect the station. Verify any last-known water warning physically.' : warning ? 'Check the tank, water height and sensor installation now.' : missing.length || reference ? 'Check sensors, calibration and the physical water conditions.' : watchSignal ? 'Watch the measured water height and inspect the installation.' : 'Keep monitoring. These reference checks do not establish water safety.';
    return { ...base, tone, title, reason, action, flood, rate, missing, settings };
  }
  function buildFacts(records, watch, now = Date.now()) {
    const status = evaluate(records, watch, now), reading = status.latest;
    const facts = ['Rule-based reading guide · AI chat is not included in this phone build.'];
    if (!reading) return facts.concat('No station measurements are saved yet. Start a demo or connect the ESP32.');
    facts.push(reading.source === 'simulation' ? 'These are synthetic demonstration readings.' : 'These measurements were captured from your sensor station.');
    if (reading.clock_ahead) facts.push('The station clock needs checking; these readings cannot describe current conditions.');
    else if (!reading.fresh) facts.push('The displayed sample is old or delayed. Reconnect the station before interpreting current conditions.');
    if (reading.provisional) facts.push('Hardware values are provisional. Software cannot verify voltage dividers, wiring or physical calibration.');
    facts.push(status.reason);
    if (finite(reading.ph)) facts.push(reading.ph === 7 ? 'pH 7 is neutral.' : `The captured water is ${reading.ph < 7 ? 'acidic' : 'alkaline'}; pH 7 is neutral.`);
    if (finite(reading.turbidity)) facts.push('NTU describes cloudiness from scattered light; it does not measure germs or identify chemicals.');
    if (finite(reading.temperature)) facts.push('°C means degrees Celsius: how warm the captured water is.');
    if (finite(reading.water_level)) facts.push('Water height is measured above your chosen station zero, not the river depth everywhere.');
    facts.push(finite(status.rate) ? `The observed water change is ${status.rate.toFixed(2)} cm/min (${status.rate < 0 ? 'falling' : status.rate > 0 ? 'rising' : 'steady'}).` : 'No water-rise speed is available: use five valid same-calibration samples spanning at least eight seconds.');
    facts.push('No drinking/swimming safety, chemical cause, official water-quality index or flood forecast can be established.');
    return facts;
  }
  function syntheticSample(scenario = 'Normal river', step = 0, now = Date.now()) {
    step = Math.max(0, Math.floor(finite(step) ? step : 0)) % 120; const active = step >= 10, seed = Math.floor(now / 240000) % 1000003;
    const randomAt = (index, channel) => { let x = (index + channel * 131 + seed * 8191) >>> 0; for (let i=0;i<2;i++) x = Math.imul(x ^ (x >>> 16), 0x45d9f3b) >>> 0; return ((x ^ (x >>> 16)) >>> 0) / 4294967295 * 2 - 1; };
    const variation = (channel, span=5) => { const position=step/span,index=Math.floor(position),t=position-index,blend=t*t*(3-2*t); return .8*(randomAt(index,channel)*(1-blend)+randomAt(index+1,channel)*blend)+.2*randomAt(step,channel+50); };
    // Independent slow drift and small jitter; shared with the service/native producers.
    const sample = { timestamp: new Date(now).toISOString(), ph: 7.2 + .12 * variation(1), turbidity: 14 + 4 * variation(2), temperature: 27 + .25 * variation(3,20), water_level: 30 + .3 * variation(4), scenario };
    if (active && /cloud|turbid|combined/i.test(scenario)) sample.turbidity = 65 + 120 * (1-Math.exp(-(step-10)/24)) + 6 * variation(2);
    if (active && /ph|combined/i.test(scenario)) sample.ph = 9.1;
    if (active && /temperat|combined/i.test(scenario)) sample.temperature = 35;
    if (active && /ris|water.level|combined/i.test(scenario)) sample.water_level = 45 + 100 * (1-Math.exp(-(step-10)/20)) + .6 * variation(4);
    if (active && /sudden/i.test(scenario)) { sample.ph = 5.8 + .12 * variation(1); sample.turbidity = 80 + 8 * variation(2); }
    return sample;
  }
  return { deriveReading, evaluate, buildFacts, validateCalibration, syntheticSample, DEFAULT_WATCH };
});
