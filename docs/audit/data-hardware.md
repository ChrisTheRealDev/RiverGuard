> Audit snapshot, 22 October 2026. Raw databases, personal transcripts, screenshots, logs and session material are excluded. Findings remain unfixed.

# RiverGuard data and hardware audit — 22 October 2026

Read-only audit of the current React/FastAPI application, storage, station setup, firmware and hardware material. No application source or production database was changed. Small reproductions used temporary SQLite databases; the single performance measurement used the parent's isolated `output/audit-2026-10-22/review.db` copy. A dummy predictor was used in isolated writes, with no AI model inference. Severity: P1 substantially blocks a core workflow; P2 incorrect or confusing behavior in a supported/important scenario; P3 smaller usability/documentation issue.

## Confirmed findings

### DH01 — P1: Full-history chart requests perform unbounded work and delay live updates

- **Location:** [data_service.py:244](../../data_service.py#L244), [data_service.py:249](../../data_service.py#L249), [data_service.py:202](../../data_service.py#L202), [data_service.py:214](../../data_service.py#L214).
- **Trigger:** Choose All history on an accumulated station, or request a 50-row signal-history page.
- **Evidence:** One isolated `overview_data('simulation','demo-station','ph','all')` call on the review copy took **17.106 seconds after imports**, despite returning only **80 chart points** (2,265-second buckets; 474 signal episodes). No model call was involved. The chart path loads every station reading and recalculates every historical signal; alert pagination likewise loads and evaluates the whole station before slicing the page.
- **Impact:** A chart that appears bounded still grows in CPU/memory/latency with all stored readings. Repeated live refreshes compete with ingestion/chat/browser work. Pagination does not bound the expensive part of signal history.
- **Recommendation:** Aggregate/window in SQL, compute or cache signal results keyed to station/threshold/calibration revisions, and return recent alerts separately from selected chart history. Bound each request's work without dropping scientific evidence.
- **Closure check:** The prior data review explicitly acknowledged this full-history limitation. It must not be counted as closed simply because the old global 10,000-row cap was removed. The parent owns the browser timing/context and final prioritization.

### DH02 — P2: Reset & replay can reuse IDs and mix two runs inside one history snapshot

- **Location:** [core.py:66](../../core.py#L66), [core.py:189](../../core.py#L189), [data_service.py:151](../../data_service.py#L151), [data_service.py:166](../../data_service.py#L166); the alert cursor also uses an insertion-ID anchor at [data_service.py:204](../../data_service.py#L204).
- **Trigger:** Open a paginated simulation history, reset the simulation from another paired browser/window, then load more in the first window. SQLite `INTEGER PRIMARY KEY` can reuse deleted IDs.
- **Evidence:** In an isolated database, first-page water levels were `[3, 2]`. After deleting simulation rows and inserting a new run with older measurement times and reused IDs, the old cursor returned `[93, 92]` rather than refusing the stale snapshot. It still reported a total of four.
- **Impact:** The first browser silently combines records from the old and new run, defeating the promised snapshot boundary and potentially presenting the wrong historical sequence. This does not require forged cursors.
- **Recommendation:** Bind cursors to a durable dataset/run generation changed by destructive reset, or use nonreused row identities plus explicit invalidation. Reject old-generation cursors with a clear refresh action.

### DH03 — P2, conditional legacy-data failure: Preserved invalid timestamps can break station navigation

- **Location:** [core.py:76](../../core.py#L76), [data_service.py:72](../../data_service.py#L72), [data_service.py:239](../../data_service.py#L239), [river_status.py:17](../../river_status.py#L17).
- **Trigger:** Migrate/import a legacy station whose only reading has an invalid or timezone-less timestamp.
- **Evidence:** A temporary legacy database containing `timestamp='not-a-date'` migrated and preserved the row with `measured_ms=NULL`. Then `data.stations('esp32')` raised `ValueError: Invalid isoformat string: 'not-a-date'`; its overview raised `TypeError: int() argument must be ... not 'NoneType'`.
- **Impact:** One preserved bad station can fail the source-wide station picker; selecting it cannot show a usable overview. A bad row mixed into otherwise valid history can also fail strict chart/history parsing.
- **Recommendation:** Keep the original evidence but explicitly mark/quarantine invalid-time rows for live selection and temporal calculations; expose a diagnostic/export rather than treating them as usable measurements.
- **Limit:** Current authenticated ingestion validates timestamps. This reproduces a migration/corrupt/imported-history condition, not an ordinary packet accepted by the current endpoint. The probe also confirmed a valid very old ISO date does not itself fail the current pandas version.

### DH04 — P2: Reading-card arrows report calibration changes as river changes

- **Location:** [data_service.py:236](../../data_service.py#L236), [frontend/src/App.tsx:47](../../frontend/src/App.tsx#L47).
- **Trigger:** Save a new temperature offset, pH calibration or water reference between successive samples.
- **Evidence:** With raw temperature fixed at 27 °C, isolated revision 1/offset 0 produced 27 °C and revision 2/offset +1 produced 28 °C. Overview returned those rows as previous/latest, and the card unconditionally calculates `latest - previous`, yielding an apparent +1 °C river change.
- **Impact:** Graph/rise segmentation correctly avoids calibration jumps, but the prominent change arrows still suggest a physical change. This can be especially confusing immediately after following the calibration wizard.
- **Recommendation:** Suppress the delta across calibration/revision or relevant sensor-configuration changes and show a concise calibration-updated state. Keep raw/derived records intact.
- **Coordination:** Parent is merging this with the dashboard audit, so count it once.

### DH05 — P2: Multi-day chart axes and tooltips omit the date

- **Location:** [frontend/src/Chart.tsx:9](../../frontend/src/Chart.tsx#L9), [frontend/src/Chart.tsx:11](../../frontend/src/Chart.tsx#L11).
- **Trigger:** View All history spanning more than one day.
- **Evidence:** Tick formatting uses only hours/minutes for every interval over a minute; the tooltip formats only hours/minutes/seconds. Parent browser inspection confirmed repeated tick labels `12:00, 00:00, 12:00, 00:00`; screenshot: chart-all-history.png (local audit evidence; not included).
- **Impact:** Equal clock times from different days cannot be distinguished from the axis/hover, weakening the usefulness of complete history.
- **Recommendation:** Include local dates in multi-day ticks and always include the date in a historical tooltip.
- **Coordination:** Parent owns/merges the browser finding; count once.

### DH06 — P2: Successfully received retries do not refresh connection heartbeat

- **Location:** [core.py:143](../../core.py#L143), [core.py:145](../../core.py#L145), [core.py:148](../../core.py#L148), [data_service.py:65](../../data_service.py#L65), [ui_api.py:325](../../ui_api.py#L325).
- **Trigger:** The server stores a packet but its HTTP response is lost. The firmware correctly retries the unchanged sample ID; during repeated lost responses it cannot advance to a new sample.
- **Evidence:** An isolated existing sample had first-receipt time over 60 seconds old. Saving the identical sample ID again returned successfully without inserting a duplicate, but station listing still reported `connected=false` and the old `last_received`. Every duplicate is ignored without separate last-seen tracking.
- **Impact:** The app tells the user that the station is disconnected even while authenticated packets are arriving. The measurement should correctly stay stale, but connectivity and measurement freshness are meant to be separate.
- **Recommendation:** Preserve first-receipt evidence for the sample while updating a separate station heartbeat on every accepted authenticated transmission, including deduplicated retries.

### DH07 — P2 configuration gap: Verified tank geometry can make default absolute warnings unreachable

- **Location:** [data_service.py:16](../../data_service.py#L16), [data_service.py:96](../../data_service.py#L96), [station_setup.py:102](../../station_setup.py#L102), [hardware/Tank-Assembly.md:26](../../hardware/Tank-Assembly.md#L26), [hardware/Tank-Assembly.md:43](../../hardware/Tank-Assembly.md#L43).
- **Trigger:** Commission a small tank using the documented example geometry, leaving default watch/warning levels unchanged.
- **Evidence:** A valid verified calibration `reference=50 cm, minimum=25 cm` allows derived heights only from 0 through 25 cm. Its station still receives watch 70 cm and warning 100 cm, with no warning or setup prompt; neither absolute threshold is reachable within the usable sensor span. The commissioning steps do not instruct setting a tank-appropriate watch/warning height.
- **Impact:** Users can finish a verified demonstration that cannot show an absolute-level watch/warning before distance goes invalid. A rapid-rise warning may still trigger, so this is not a claim that all alerts stop.
- **Recommendation:** Show achievable height range during setup and prompt users to choose meaningful tank-specific thresholds; warn about thresholds outside that range. Do not automatically substitute unvalidated flood limits.

### DH08 — P3: Zero-height capture accepts a known blind-zone echo

- **Location:** [station_setup.py:102](../../station_setup.py#L102), [station_setup.py:121](../../station_setup.py#L121), [hardware/README.md:39](../../hardware/README.md#L39).
- **Trigger:** Recalibrate water level while a fresh raw echo is below the already saved verified minimum distance.
- **Evidence:** With saved minimum 25 cm, a 20 cm echo was correctly derived as missing with health `out_of_range`, but `capture('tank','distance_cm')` returned `20.0`. The capture fault list omits `out_of_range`; docs broadly say known-faulted signals are rejected.
- **Impact:** The wizard fills a zero-level reference with a distance already known to be outside the sensor's usable range. Keeping the old minimum correctly prevents saving that reference, so this is a confusing capture/error sequence rather than proof of a silently accepted bad calibration.
- **Recommendation:** Distinguish analog out-of-calibration-span captures (which are necessary to recalibrate) from known ultrasonic blind-zone/range faults and give a move-the-sensor explanation.

## Validation gaps and risks, not confirmed physical failures

1. **Non-monotonic NTU calibration is accepted as verified.** [station_setup.py:40](../../station_setup.py#L40) sorts signals and checks unique known values, but accepts `[(1000 mV,100 NTU),(1500 mV,0 NTU),(2000 mV,50 NTU)]` with `verified=true`. This is source/probe-confirmed permissiveness; no actual standards or sensor curve were measured. At least flag a calibration that reverses direction as a possible swapped reference, unstable sample, unsuitable span or sensor issue and require deliberate review, rather than silently treating entry validation as calibration quality.
2. **No physical qualification yet.** JSN revision/trigger logic, 12 µs trigger compatibility, beam clearance, wet probe behavior, ADC stability, supply/regulator margin and actual calibration accuracy remain untested. Firmware compilation and syntactically valid settings are not plug-and-play hardware proof. The docs disclose this correctly.
3. **Offline acquisition is intentionally limited.** Firmware has one RAM pending sample and pauses new acquisition on retries; reboot can lose it. NTP is required before first sample. These are documented limitations, not newly discovered silent data retention features.
4. **HTTP is unencrypted on the private LAN.** Current guides explicitly disclose this; pairing/token permissions do not encrypt transport. Security/auth owner has the broader security audit.
5. **Current partial-data headline policy may hide other abnormal available probes.** [river_status.py:180](../../river_status.py#L180) prioritizes missingness over non-water pH/cloudiness/temperature anomalies. Available high water warnings correctly retain priority. Whether the primary status should additionally name available abnormal readings is a product decision; no unambiguous specification violation is asserted here.

## Hardware and diagram cross-check

Inspected actual `hardware/RiverGuard-Wiring.png`, `hardware/Tank-Layout.png`, corresponding SVG/source, all eight cached rendered pages of the current 21-Oct PDF, and firmware pin/constants. The PDF render timestamps follow the PDF timestamp. No confirmed wrong resistor topology, sensor pin mapping or contradictory tank-height formula was found.

- Both protected signals consistently use sensor output → 10k → GPIO junction → 15k → GND; ratio 0.6 gives nominal 5 V → 3.0 V and 4.5 V → 2.7 V. Separate resistor pairs and shared ground are clear.
- pH V2 goes directly to GPIO34 at a documented 3V3 supply; turbidity A uses divider/GPIO35; DS18B20 DQ/GPIO27 has its 4.7k pullup to3V3; JSN TRIG/GPIO5 and divided ECHO/GPIO18 match firmware.
- Power notes avoid tying an external5V rail to USB-powered board VIN, require checking the exact USB-C board, and keep high-voltage supplies/laptop away from water.
- Tank clearance uses `H >= W + B + M`, explicitly requires the actual JSN minimum/maximum and beam clearance, and keeps the stand's load off the tank. The diagrams are illustrative rather than claimed physical scale.
- The printable guide and PNG wiring details match current Markdown. The older standalone PNG footer date does not change electrical contents. PDF pages3/6 use tight lower margins but the inspected text remains readable and does not overlap the footer.

Primary sources re-opened22Oct:

- [DFRobot SEN0161-V2 specifications](https://wiki.dfrobot.com/sen0161-v2/):3.3–5.5V supply,0–3.0V output; the supplied probe is laboratory grade. This supports the pictured V2 connection, not any unspecified older pH board.
- [DFRobot SEN0189 specifications](https://wiki.dfrobot.com/sen0189):5V supply and analog output up to4.5V support needing the shown divider.
- [Espressif Arduino-ESP32 ADC documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html):classic ESP32 ADC11dB documented measurable range150–3100mV; current firmware150–3050mV checks are conservative.
- [Analog Devices DS18B20 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf):external-power3.0–5.5V and pulled-up OneWire support the shown3V3 arrangement. No exact JSN revision or USB-C clone schematic was available, so those electrical claims were not declared verified.

## Earlier closure claims rechecked

Source review still shows station/time SQL filtering before reading pagination, indexed measurement-time ordering, separate raw/calibrated/calibration metadata, schema version3 with pre-upgrade online backup and closing connections, current-threshold labels in historical signal history/CSV, formula escaping for textual CSV cells, revision-separated chart/rise calculations, and last-known stale water warning wording. The new isolated probes do not replace the parent's complete regression suite. Importantly, ID reuse after reset, calibration arrows and full-history latency show that those broad closure statements do not mean all related workflows are correct.

No fixes were made. Parent owns the combined audit, current full-suite result, browser evidence and prioritization.

