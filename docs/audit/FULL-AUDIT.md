> Audit snapshot, 22 October 2026. Raw databases, personal transcripts, screenshots, logs and session material are excluded. Findings remain unfixed.

# RiverGuard full audit — 22 October 2026

Audit only: **31 findings — 3 P1, 20 P2 and 8 P3**, after merging the duplicate worker-health finding. No application fixes, model changes, production-data edits, dependency upgrades or release rebuilds were made. These findings describe the current implementation; they are not a claim that every possible defect has been discovered.

The application is substantially more usable than the earlier Streamlit version. The normal overview fits the tested laptop viewports, the complete export works, and the automated suites pass. However, chat failure handling, answer verification, background-task supervision and large-history performance still need repair before treating this as a reliable shared sensor installation. Physical hardware acceptance remains outstanding.

P1 means a high-priority core-workflow or answer-boundary defect. P2 means materially incorrect, unreliable or confusing behavior in the stated scenario. P3 means a narrower usability, resilience or documentation problem. Conditional legacy cases and source-confirmed races are explicitly labelled below.

## Scope and evidence

Reviewed the React/TypeScript frontend, FastAPI APIs, SQLite queries/migrations, authentication/pairing, durable chat jobs, local-model selection, answer verification, simulation, calibration, ESP32 firmware, wiring/tank documentation, startup/shutdown, dependency manifests and friend ZIP. Browser work used a SQLite backup copy at `<workspace>/output\audit-2026-10-22\review.db`, isolated ports 8507/8007 and a separate browser origin. Destructive and fault-injection probes used temporary databases or extracted package copies. Existing production services on 8501/8000 were left running.

Detailed evidence and repair recommendations are retained in the component reviews:

- [Rill and conversation audit](rill.md)
- [Security, lifecycle and distribution audit](security.md)
- [Data, firmware and hardware audit](data-hardware.md)

The tables below are the consolidated register. R05 and OPS-01 are one issue, not two. Multi-day graph labelling is counted once, with the related reading-table precision problem included under it.

## Highest-priority findings

| ID | Priority | Finding and consequence | Evidence / source |
| --- | --- | --- | --- |
| R01 | P1 | **Another browser's failed reply can inherit an older job's verification and action target.** If canonical failure B arrives while the metadata request for B fails, retained job A supplies verification, model and Retry/Continue ID. An unverified B draft can appear expanded and actions target A; the server rejects the stale action. | Deterministic reproduction using actual frontend state helpers/derived expressions: failure B, rendered unverified false, Continue true, submitted ID A. [RillChat.tsx:34](../../frontend/src/RillChat.tsx#L34), [chatState.ts:45](../../frontend/src/chatState.ts#L45). A complete browser network-fault sequence remains untested. |
| R02 | P1 | **The answer guard misses prohibited drinking-safety and flood-forecast paraphrases.** Hypothetical outputs “In this demo, the river is drinkable.” and “In this demo, no flooding is expected.” pass the guard. Passing verification cannot be treated as factual assurance. | Direct pure-verifier reproduction. These were test strings, not observed model answers. [rill_verification.py:70](../../rill_verification.py#L70), [chat_service.py:523](../../chat_service.py#L523). |
| DH01 | P1 | **Full-history graphs and alert pages perform unbounded historical signal work.** An 80-point graph still loads/evaluates all station records; pagination slices after expensive evaluation. Polling increasingly competes with chat and ingestion. | Isolated `overview_data(..., 'all')` on roughly 21,000 saved readings took **17.106 seconds after imports**, returning 80 points and 474 signal episodes. [data_service.py:244](../../data_service.py#L244), [data_service.py:202](../../data_service.py#L202). |

## Rill correctness, speed and lifecycle

| ID | Priority | Finding and consequence | Evidence / source |
| --- | --- | --- | --- |
| R03 | P2 | Reference/threshold numbers can be misrepresented as measured values. The allowed-number union does not consistently check the number's factual role. | For actual pH 7.2, temperature 27.4°C and height 35cm, demo-prefixed “latest pH is 14”, “measured temperature is 20°C” and “current water level is 100cm” passed. Pure verifier tests. [rill_verification.py:91](../../rill_verification.py#L91). |
| R04 | P2 | Completed replies use freshness captured at generation start. A long generation may describe readings as current after they have become stale; completed messages omit the captured-reading timestamp shown while generating. | A 65-second-old sample with stored `stale=false` passed a current-temperature assertion; refreshing context age correctly rejected it. [chat_service.py:508](../../chat_service.py#L508), [RillChat.tsx:57](../../frontend/src/RillChat.tsx#L57). |
| R05 / OPS-01 | P2 | An unhandled background SQLite error can kill the chat worker or simulator while health still says OK. Chat requests can continue being accepted into an unserviced queue. | Separate temporary-DB injections reproduced a dead chat worker with queued job and accepting service, and a dead simulation task with `running=true` and HTTP health 200. [chat_service.py:463](../../chat_service.py#L463), [ui_api.py:48](../../ui_api.py#L48), [ui_api.py:188](../../ui_api.py#L188). |
| R06 | P2 | An accepted question with a lost POST response can acquire a new request ID after polling observes its job, allowing a duplicate submission of the retained draft. | Extracted current request-ID function reproduced changed identity when only the observed parent job changed. Full lost-response browser integration was not exercised. [RillChat.tsx:37](../../frontend/src/RillChat.tsx#L37), [chat_service.py:325](../../chat_service.py#L325). |
| R07 | P2 | The compact AI prompt drops available pH/cloudiness/temperature changes and their sample interval. Natural questions about these trends cannot be grounded in facts that were computed but not supplied. | Payload with pH delta 0.73 over 5 seconds omitted both facts. [rill_ai.py:126](../../rill_ai.py#L126), [rill_verification.py:17](../../rill_verification.py#L17). |
| R08 | P2 | Repeated Continue operations can exceed the fixed 4,096-token input context. Complete accumulated prefixes are unbounded, risking provider-dependent truncation or failure. | A synthetic 20,000-word prefix produced roughly 102,000 prompt characters with `num_ctx=4096`. Actual provider overflow behavior was not tested. [rill_ai.py:154](../../rill_ai.py#L154), [chat_service.py:372](../../chat_service.py#L372). |
| R12 | P2 | Continue eligibility disagrees with the saved partial/backend. Valid cancelled/failed partials lose Continue; an incomplete reply with empty text can offer an action the server rejects. | Actual UI predicate replay, compared with backend terminal-state requirements. [RillChat.tsx:43](../../frontend/src/RillChat.tsx#L43), [chat_service.py:349](../../chat_service.py#L349). |
| R09 | P3 | Correct general educational answers can be rejected for omitting unrelated stale/calibration warnings, even without a station-condition claim. | “What does pH mean?” definition rejected under stale/provisional station context. [rill_verification.py:77](../../rill_verification.py#L77). |
| R10 | P3 | One broken or disappearing installed-model entry aborts the entire model catalogue, hiding otherwise usable models. | Mock HTTP catalogue with one valid entry and one `/api/show` 404 rejected the whole list. [rill_models.py:61](../../rill_models.py#L61). |
| R11 | P3 | A model selected in another paired browser does not update the cached selected-model hint in Rill. Retry can name the old model until refresh, although the backend uses the persisted selection. | Source-confirmed inconsistent session/inventory updates; paired-browser UI reproduction outstanding. [App.tsx:18](../../frontend/src/App.tsx#L18), [ModelSettings.tsx:12](../../frontend/src/ModelSettings.tsx#L12). |

Local AI remains `llama3.2:3b` by default. No new real answer generation or 20-question quality benchmark was performed in this audit. Prior measurements in the baseline artifact (local audit evidence; not included) recorded a 77.139-second cold completion; subsequent earlier measurements were approximately 25.649–29.034 seconds warm, with first text around 18.925–21.751 seconds. These are historical measurements on this laptop, not new audit results or a speed guarantee. Opening the audit chat can invoke the app's normal empty model-preparation request.

The requested Qwen 3.5 4B model was not installed or qualified: the earlier download requirement was about 3.4GB with approximately 2.8GB free on D:. No claim of equal quality or a few-second response is supported yet. The existing benchmark script explicitly targets llama3.2:3b; selecting another model does not make those historical results apply to it.

## Data, calibration and monitoring

| ID | Priority | Finding and consequence | Evidence / source |
| --- | --- | --- | --- |
| DH02 | P2 | Reset & replay can reuse SQLite IDs, allowing an old history cursor to combine records from different simulation runs. | Temporary database: old first page levels `[3,2]`, then old cursor returned new-run `[93,92]` after reset/reused IDs. [core.py:66](../../core.py#L66), [data_service.py:151](../../data_service.py#L151). |
| DH03 | P2 | **Conditional legacy/import case:** preserved invalid timestamps can fail station listing and overview rather than appear as quarantined evidence. Current ingestion rejects these timestamps. | Migrated `not-a-date` row kept `measured_ms=NULL`; station listing raised ValueError and overview TypeError. [core.py:76](../../core.py#L76), [data_service.py:72](../../data_service.py#L72). |
| DH04 | P2 | Reading-card arrows cross calibration revisions and report calibration adjustments as physical river changes, despite correct graph/rise segmentation. | Constant raw 27°C, offset changed 0→+1, displayed delta +1°C. [data_service.py:236](../../data_service.py#L236), [App.tsx:47](../../frontend/src/App.tsx#L47). |
| DH05 | P2 | Multi-day chart ticks/hover omit dates. Related reading-table and detail timestamps omit seconds, making closely spaced samples visually indistinguishable. | Browser All history ticks repeated `12:00, 00:00, 12:00, 00:00`. [Chart.tsx:9](../../frontend/src/Chart.tsx#L9), [HistoryReports.tsx:19](../../frontend/src/HistoryReports.tsx#L19). Chart screenshot (local audit evidence; not included). |
| DH06 | P2 | Accepted duplicate packet retries do not refresh connection heartbeat. The app can report disconnected while authenticated packets arrive; the measurement itself should remain stale. | Replayed old identical sample ID: no duplicate row, but old `last_received` and `connected=false`. [core.py:143](../../core.py#L143), [data_service.py:65](../../data_service.py#L65). |
| DH07 | P2 | Tank commissioning can finish with unreachable default absolute warning levels and no setup warning. | Documented reference 50cm/minimum 25cm permits height 0–25cm, but defaults remain watch 70/warning 100cm. Rise alerts can still work. [station_setup.py:102](../../station_setup.py#L102), [data_service.py:16](../../data_service.py#L16), [Tank-Assembly.md:26](../../hardware/Tank-Assembly.md#L26). |
| DH08 | P3 | Zero-level capture can fill a known blind-zone echo, followed by a confusing save rejection. The existing minimum still prevents saving that invalid reference. | Saved minimum 25cm, raw echo 20cm marked out-of-range, yet capture returned 20.0. [station_setup.py:121](../../station_setup.py#L121). |

## Browser usability and accessibility

| ID | Priority | Finding and consequence | Evidence / source |
| --- | --- | --- | --- |
| UI01 | P2 | **Unsaved calibration inputs vanish on normal navigation.** There is no discard warning or recovery after leaving Sensor setup. | Entered pH reference input 1500mV, saw Unsaved changes, navigated Overview→Sensors→Calibrate: field blank. No save clicked. [SensorSetup.tsx:12](../../frontend/src/SensorSetup.tsx#L12), conditional mount [App.tsx:37](../../frontend/src/App.tsx#L37). Before (local audit evidence; not included), after (local audit evidence; not included). |
| UI02 | P2 | **Keyboard focus escapes Rill after dismissing Rename.** The chat remains modal while keyboard navigation reaches the dashboard behind it. | Rill→Manage conversation→Rename→Escape left active element BODY; Tab focused background “Skip to main content”. [ui.tsx:9](../../frontend/src/ui.tsx#L9). Screenshot (local audit evidence; not included). |
| UI05 | P2 | **Source-confirmed cross-station async race:** capture/save responses for station A are applied without checking whether the user switched to station B. The external station selector remains available during setup operations. | Capture unconditionally calls its old callback after await; save installs A's base/info/draft after awaited requests. May contaminate B's inputs and, with matching revisions, a subsequent save. Not reproduced with delayed browser networking in this audit. [SensorSetup.tsx:17](../../frontend/src/SensorSetup.tsx#L17), [SensorSetup.tsx:18](../../frontend/src/SensorSetup.tsx#L18), [App.tsx:31](../../frontend/src/App.tsx#L31). |
| UI03 | P3 | Intermediate-width status reflow makes water-watch text wrap into narrow, almost word-per-line columns. No horizontal overflow is needed to make it hard to read. | Actual CSS viewport 684×325; desktop/tablet flex rule remains until the 600px mobile grid. [styles.css:18](../../frontend/src/styles.css#L18). Screenshot (local audit evidence; not included) (filename rounded target; actual width 684). |
| UI04 | P3 | History controls declare ARIA tabs but do not implement expected arrow-key/roving-focus behavior or panel associations. | Focus Readings, ArrowRight: focus/selection remain Readings. Tab/Enter remain usable. [HistoryReports.tsx:18](../../frontend/src/HistoryReports.tsx#L18). |

The normal Overview fit at **1366×650, 1366×768, 1280×720 and 1024×768 CSS pixels** in the tested state. At 1366×650 the plot area was at least 240px tall, with status, four readings, chart and recent alerts visible. Phone views at **390×844 and 320×568** stacked the chart and alerts without horizontal document overflow. A 320×350 short-viewport chat check retained a separate composer. This does not certify every long alert/title or physical keyboard behavior.

Browser controls exercised included primary navigation, source selection, four reading explanations, all graph metric buttons, time windows, reading details, signal details, all three history tabs, setup wizard steps, Rill history/rename/delete confirmation, draft typing and Escape. Deletion was cancelled; no chat was deleted or renamed. Calibration captures/saves, station registration, credential rotation and physical sensor verification were not performed against production. Existing API tests and isolated probes cover parts of these paths; this is not a claim that every destructive control was clicked.

Screenshots were visually inspected, not just overflow measurements. Windows display scaling required converting requested physical viewport dimensions to actual CSS viewport dimensions; recorded layouts (local audit evidence; not included) contain actual values. The early `overview-1366-650.png` file is misnamed and actually represents 911×433; use `overview-css1366-650.png` for the laptop result. Actual browser zoom at 125%/200% was **not** verified; the narrow reflow probe is not a substitute for that acceptance test.

## Security, availability and release

| ID | Priority | Finding and consequence | Evidence / source |
| --- | --- | --- | --- |
| SEC-01 | P2 | Recursive packaging is not a strict privacy allowlist. Future ZIPs can silently include private configuration/database variants. **No leak was established in today's ZIP.** | In an extracted temporary copy, synthetic `frontend/audit-export.sqlite3` and `hardware/.env.local` both survived packaging with exit 0. [package_app.py:12](../../package_app.py#L12). |
| OPS-02 | P2 | A second server on alternate ports with the same database marks the first server's healthy active replies as interrupted. Port checks do not establish database ownership. | Two temporary ChatService instances with a mocked healthy blocked stream: second startup changed first job generating→failed. [chat_service.py:148](../../chat_service.py#L148), [serve.py:123](../../serve.py#L123). |
| OPS-03 | P2 | Graceful shutdown has no finite deadline for open SSE streams; application cancellation is sequenced after connection draining. | Isolated Uvicorn synthetic SSE remained alive after shutdown requested until client closed; source confirms installed default timeout None. Not a production shutdown test. [serve.py:58](../../serve.py#L58), [ui_api.py:159](../../ui_api.py#L159). |
| DEP-01 | P2 | The Python lock contains versions matched by current security advisories: certifi 2026.10.18 and Pillow 12.3.0. Reachability differs from merely having a vulnerable dependency. | OSV batch query of 55 pinned Python packages returned these two affected packages; full advisory details saved locally. See dependency assessment below. |
| REL-01 | P3 | Release manifest/checklist hashes describe an older archive, so their smoke evidence cannot be attributed to the current ZIP. | Current ZIP 102 members versus documented 95, with different hash/size. RELEASE-CHECKLIST.md:67 (local audit evidence; not included). |
| DOC-01 | P3 | The friend README refers to benchmark/release evidence deliberately excluded from the friend ZIP. | Referenced `output/redesign/RELEASE-CHECKLIST.md` is absent from archive. [README.md:75](../../README.md#L75). |

No authentication bypass was established in the supported flows reviewed. Existing regressions passed for browser/device separation, station-scoped bearer credentials, rotation, pairing expiry/revocation, CSRF/origin/Host checks and body-size bounds. Cookies are HttpOnly/SameSite Strict; tokens are hashed. These checks do not constitute an exhaustive penetration test. Paired browsers deliberately share full installation access.

The dashboard and ESP32 receiver use **HTTP over TCP**, normally ports **8501 and 8000**. Local Ollama normally uses **TCP 11434**. `localhost` identifies this computer; it does not itself choose TCP versus UDP. ESP32 NTP is a separate UDP service. Pairing controls access but does not encrypt private-Wi-Fi HTTP, as documented. No firewall, router or public exposure settings were changed.

### Dependency assessment

The official OSV batch query matched the pinned certifi version against [GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), concerning bundled emSign roots associated with compromised intermediate CA keys. The returned fixed boundary is 2026.10.19. This matters to TLS-using clients; the default local HTTP model connection does not use that trust store for transport.

Pillow 12.3.0 matched multiple image-decoding advisories, including [GHSA-8g5g-8vmr-9782](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782), an ImagingJpegDecode heap buffer overflow with returned fixed version 13.0.0. The current React/FastAPI interface serves fixed assets; no user-supplied image decoding/upload path was identified. Pillow is principally retained with the legacy Streamlit dependencies. Thus this is an actionable dependency-maintenance finding, not evidence that the current UI exposes an exploitable image endpoint. Confirm compatibility before a later upgrade/removal.

The certifi GHSA/PYSEC aliases are the same issue, not separate findings. Full results: query summary (local audit evidence; not included), advisory details (local audit evidence; not included). Only public package names/versions were sent to advisory services.

`npm audit --json` timed out. A separate direct npm registry bulk advisory query covering 152 unique package names and their locked versions returned HTTP 200 with no matches. That bounded response is recorded in npm-advisory-query.json (local audit evidence; not included); it is **not** a successful npm-audit CLI run or proof of zero vulnerabilities. `pip check` passed, which tests dependency compatibility rather than vulnerability status.

## Verification results

| Check | Result / limit |
| --- | --- |
| Backend regression suite | **158 passed**, one existing Starlette/httpx deprecation warning, 87.43 seconds. Log (local audit evidence; not included). Explicit `tests` directory used so extracted-package tests under output were not collected twice. |
| Frontend tests | **17 passed** using `npm test`. |
| TypeScript | `npm exec tsc -- --noEmit --incremental false` exited 0. No frontend rebuild. |
| Python environment | `pip check`: no broken requirements. No clean installation performed. |
| Authenticated complete export | HTTP 200, **21,914 CSV data rows**, 7,193,625 bytes, 0.923s on isolated copy. Report HTTP 200, 3.749s; evaluation CSV HTTP 200, 0.236s. Results (local audit evidence; not included). One measured run each, not a load benchmark. |
| Current friend ZIP | CRC passed; all 102 archived members byte-match current source. Actual size **4,464,510 bytes**. SHA256 **fc36d319595c95c93181698c59870918ce41950e37034b0a449ce9f1b4f7dd39**. The current artifact was not rebuilt. |
| Browser | Desktop/phone viewport inspection and interaction checks described above, using isolated data. No app-code changes. |
| Fault/edge probes | Temporary DBs, mocked streams/HTTP and pure state/verifier functions reproduced the qualified findings above. No production outage or fabricated live sensor data. |

Passing tests establish the cases they cover. They do not close these newly reproduced cases, many of which are absent from the current suites.

## Hardware and remaining acceptance work

The wiring PNG/SVG, tank drawing, firmware assignments and eight cached rendered pages of the current printable guide were checked. No confirmed wrong divider topology or contradictory pin mapping was found. Protected signals consistently show sensor output → 10kΩ → GPIO junction → 15kΩ → ground, giving nominal 5V→3.0V and 4.5V→2.7V. DS18B20 uses its 4.7kΩ pull-up to 3V3. These calculations and document consistency do not prove a particular assembled board is electrically correct.

Manufacturer references reviewed: [DFRobot SEN0161-V2](https://wiki.dfrobot.com/sen0161-v2/), [DFRobot SEN0189](https://wiki.dfrobot.com/sen0189), [Espressif ADC documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html), [DS18B20 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf).

Additional risks/limitations are not counted as confirmed physical failures:

- Non-monotonic NTU reference points can be marked verified. A synthetic 100→0→50 NTU calibration passed entry validation. This merits a plausibility warning or deliberate review; no actual sensor/reference curve was measured.
- Actual JSN revision, USB-C board schematic, supply margin, trigger compatibility, beam clearance, wet-probe behavior, ADC noise and calibration accuracy require real hardware tests. No new firmware compile or flash was performed in this audit. Optional unconfirmed TDS remains outside the required driver set.
- Firmware keeps one pending sample in RAM, pauses acquisition during retries and requires NTP before sampling. Durable offline logging is an explicitly excluded feature, not newly implemented retention.
- Missingness can dominate non-water abnormalities in the main headline; high-water warnings retain priority. Whether available abnormal pH/cloudiness/temperature should also be named is an unresolved product-policy choice.
- A real paired phone, its virtual keyboard, screen-reader announcements, true 125%/200% browser zoom, prolonged network transitions and a fresh Windows install were not accepted here.
- A newly selected local model needs the full grounded-question and resource/latency benchmark under normal load. No equal-quality/few-second claim is justified by model size alone.

## Recommended repair sequence — not implemented

1. Correct matching-job failure rendering/actions and safety/measurement verification; add the exact failing cases to acceptance tests.
2. Supervise background workers, enforce one database owner and bound shutdown. Make failures actionable instead of silently accepting unserviceable work.
3. Bound/cache historical evaluation, invalidate reset cursors, fix calibration deltas, heartbeat semantics and date precision.
4. Preserve calibration drafts and station-scope async results; repair nested focus restoration, tab keyboard behavior and intermediate-width status reflow.
5. Finish chat request reconciliation/continuation/prompt budgeting, catalogue resilience and authoritative model metadata. Then benchmark the actual chosen local model without discarding grounding facts for speed.
6. Harden packaging exclusions, review dependency advisories, regenerate artifact-specific evidence and conduct clean-machine/real-phone/physical-sensor acceptance.

Keep the present ZIP and database backup available for rollback. The audit artifacts include private copied conversations/readings and temporary owner-session material; they are local review evidence and should not be included in the friend package.

**No fixes were made.**
