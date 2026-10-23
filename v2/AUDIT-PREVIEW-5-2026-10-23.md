# Preview 5 audit — 23 October 2026

Baseline: `v2/rebuild`, commit `3d42f78`, release `v2-observatory-preview.5`.
This report records the published version before the subsequently requested repairs, simulation and Activity changes. The findings describe the baseline. See the repair evidence below for the current working-tree status.

## Findings

### A01 · P2 · Old calibration prevents capturing a new reference

**Reproduced in Chrome.** Register a station with pH references 1500 mV → 7 and 2000 mV → 4. Send a fresh 1400 mV signal with device health `ok`. In Calibrate, both capture buttons are disabled with “the sensor reports out of range.” Clearing the calibration draft still leaves capture disabled.

`frontend/src/components/Setup.tsx:34` checks derived health from the saved calibration, rather than distinguishing an invalid raw signal from one outside the old calibration coverage. A legitimate new calibration standard can therefore be blocked and misdiagnosed as a connection problem. Numeric manual entry remains possible.

**Repair direction:** validate raw capture health separately; apply the draft geometry when checking water-level captures. Retain rejection of stale, missing, timeout and ADC-limit signals.

### A02 · P2 · A pending request stalls every monitoring refresh

**Reproduced with a deliberately held network response.** Hold `/api/v2/phone/getMonitoring` while the other endpoints respond. After 6.5 seconds, only one monitoring request exists, the batch has not applied its results, and no error banner appears. Releasing the request by aborting it allows refreshing again.

`frontend/src/monitor.ts:15` waits for every request with `Promise.allSettled`; `inFlight` suppresses subsequent refreshes. `frontend/src/platform.ts:34` supplies no fetch deadline. An endpoint that remains pending can stall healthy reading/history/policy updates too. The local freshness clock still advances; this is not a claim that stale data remains marked fresh forever.

**Repair direction:** bounded request deadlines, cancellation when selection changes, and independent application of successful monitoring results.

### A03 · P2 · Repeated temperature correction instructions give the wrong result

**Confirmed by source and arithmetic.** The guide says to enter reference temperature minus displayed temperature. The saved field is an absolute offset from the raw probe value. With raw 26 °C, existing offset +1 °C and reference 28 °C, following the guide replaces the offset with +1 °C and leaves the display at 27 °C. The correct replacement is +2 °C.

Locations: `frontend/src/components/SetupGuide.tsx:50`, `server/signals.py:24` and the shared/native correction logic.

**Repair direction:** calculate against raw temperature, or explicitly add the new measured difference to the existing offset. Show a preview of the corrected result.

### A04 · P2 · A small phone hides the urgent water warning below the first screen

**Reproduced and visually inspected.** At 320×568, with a quality Watch and water Warning, the water card begins at y≈625 and its Warning badge at y≈647—entirely below the viewport. At 390×844 the badge is visible, but the full condition and next action require scrolling. Header and explanatory spacing consume much of the first screen; quality always precedes water regardless of severity.

Location: `frontend/src/components/Overview.tsx:11`, responsive condition/header styling. This is a prioritization problem, not horizontal overflow. Technical graphs intentionally remain lower on the page in V2.

**Repair direction:** put a compact highest-severity summary and next action above both cards; preserve readable spacing and expose both quality and rising-water status at narrow widths.

### A05 · P2 · Selected station and Connect target can disagree

**Reproduced in Chrome.** Open Station after switching from Demo to hardware, then select `audit-B` in the header. The header shows `audit-B`, while Connect’s Station ID can remain `riverguard-01`. Other steps use the selected hardware station, but registration/key/configuration actions use the separate Connect ID.

Location: `frontend/src/components/Setup.tsx:20–21`. The initial Connect ID is captured once and is not synchronized when station selection changes. The form can intentionally create another station, but that separate target is not clearly distinguished from the selected station.

**Repair direction:** explicitly separate “add station” from management of the selected station; make each credential/configuration action’s target unambiguous. Preserve unsaved inputs during selection changes.

### A06 · P2 · Leaving Station silently discards connection and watch drafts

**Reproduced in Chrome.** Enter a Wi-Fi name, navigate to Your river and return: the field is empty. Change Watch height from 10 to 11 without saving, leave Station and return: it has reverted to 10. There is no unsaved-change prompt. Switching wizard steps preserves Connect fields, and calibration drafts have persistence; those protections do not cover all setup fields.

Locations: `frontend/src/components/Setup.tsx:21,42`, page mounting in `frontend/src/App.tsx`.

**Repair direction:** preserve non-secret drafts across navigation and warn before discarding unsaved work. Keep sensitive credentials/passwords out of durable storage unless an explicit storage design is adopted.

### A07 · P2 · Backend accepts verification without current usable measurements

**Reproduced against an isolated Python store; native equivalent confirmed by source.** Save a complete configuration and compatible watch marks, ingest an hour-old sample acknowledging revision 1 with cloudiness missing, then submit unchanged settings with `verified=true`. The backend accepts revision 2 and verification. The UI normally disables this action, but the data-layer invariant is missing and a stale UI/race or direct authenticated request can bypass it.

Locations: `server/store.py:337`, `mobile/android/app/src/main/java/com/riverguard/v2/PhoneStore.java:186`. Both enforce configuration completeness, compatible thresholds and acknowledgement; neither checks current fresh usable measurements at save time.

**Repair direction:** validate the required current evidence inside the verification write transaction and return a specific recoverable error. This still records a human declaration, not certification of water safety.

### A08 · P2 · Laptop receiver rejects its new address after a network address change

**Reproduced with controlled address substitution.** Create the service while its address is `192.168.1.20`, then report its address as `192.168.1.21`. A request to the new address receives HTTP 400 “Invalid host header.” The advertised addresses are refreshed, but TrustedHost’s allowlist is captured only at startup.

Locations: `server/app.py:116–120,141`. The guide tells users to update the firmware receiver address but omits the currently necessary laptop-service restart. A DHCP address change or switch of network can therefore remain broken even after the ESP32 configuration is corrected.

**Repair direction:** safely reconcile local interface addresses with the host allowlist, or explicitly detect the change and require a service restart. Retain host-header protection.

## Checks and evidence

Fresh checks performed during this audit:

- Python: **40 tests and 14 subtests passed**, using `pytest v2/tests -q`. One Starlette/httpx deprecation warning.
- Frontend: **33 tests passed**.
- Real Chrome browser against an isolated database and backend on 8514: Overview, Activity and all four Station/setup-guide steps at **1366×650, 1366×768, 1280×720, 1024×768, 390×844 and 320×568**. No horizontal overflow or browser page errors in this walkthrough.
- All four graph selections, all four reading explanation dialogs, technical-detail toggle, Rill reading guide, Escape dismissal and focus restoration checked.
- History pagination loaded **132 readings**; completed CSV contained **132 data rows**. Record detail, event expansion and refresh controls exercised.
- Browser pairing, cancellation of revocation, confirmed revocation and rejected access after reload exercised.
- Two browser tabs agreed on Pause, Resume and all four Demo scenarios. Reduced-motion media mode exercised.
- Fresh anonymous full downloads and split/resumed transfers of the Preview 5 APK, APK ZIP and laptop ZIP matched their published checksums and staged build bytes. Attachment headers passed.
- Reviewed Python access/data/monitoring code, frontend state and setup handling, Android store/receiver/service/notification paths, firmware scheduling and release packaging. No new confirmed credential-boundary or CSV formula-injection failure found in the exercised paths; this is not a security certification.

Local evidence is under `output/preview5-audit/`: `browser-results.json`, `interaction-results.json`, `probe-results.json`, reproduction scripts and screenshots. These files are ignored working artifacts; retain them with this report for investigation. Public transfer evidence is in `output/release-staging/v2-publish-preview5/public-download-verification.json`.

Release-build evidence inspected, **not rerun as part of the baseline audit**: 42 Android host unit tests passed, Android lint had 0 errors/18 warnings, APK is non-debuggable with the preceding release’s signing certificate, bundled web assets match the frontend build, and a fresh laptop-ZIP extraction previously passed service/frontend smoke checks.

## Limits and remaining acceptance work

- No Android phone was connected (`adb devices` returned none). Native install/update, document saving, virtual keyboard, locked-screen notifications, permission re-enable, Wi-Fi reconnection and battery restrictions remain unverified on physical hardware.
- Phone layouts above are desktop-Chrome viewport tests, not Android WebView/device acceptance. Native Android SQLite instrumentation was not run in this audit.
- True 125%/200% browser zoom was not exercised; prior equivalent-width tests are not a substitute. Full assistive-technology testing remains pending.
- The in-app browser automation surface failed to initialize. Browser checks used actual headless Chrome and inspected screenshots instead of claiming to have controlled the user's live tab. User databases and running service were not changed by the audit.
- Physical voltage protection, probe accuracy, ultrasonic blind zone, tank commissioning and simultaneous ESP32 delivery to phone/laptop still require hardware.
- The older reported Android-browser download stall is not closed by successful anonymous transfers on this laptop. Chrome/Samsung Internet on the affected phone still needs a successful download.
- V2 Rill is the optional reading guide, not the V1 local-model chatbot. No V1 model-speed benchmark was run.

## Follow-up scope requested during the audit

The user additionally requested less-uniform simulation and five-minute Activity summaries. Those are separate enhancements after this baseline; they do not close A01–A08. Preserve all raw readings and exact alert times while changing the Activity presentation.

## Repair evidence after authorization

The user subsequently requested fixes and a new release. Repairs are on `v2/rebuild` and included in Preview 6; published Preview 5 assets remain unchanged.

| Finding | Change | Evidence |
|---|---|---|
| A01 | Capture checks reported raw faults and ADC limits separately from the old calibration coverage. Draft geometry controls distance capture. | Chrome captured the 1400 mV reference previously blocked. Existing faulted-capture regression passes. |
| A02 | Browser requests have a ten-second abort deadline covering headers and JSON body consumption. Failure releases the refresh guard. | Chrome held-request experiment showed a visible timeout, then successful refresh recovery. |
| A03 | Guide and calibration form specify reference minus raw temperature, replacing the absolute offset. | Source inspection against the 26/27/28 °C reproduction. |
| A04 | A compact mobile status summary exposes water status, quality status and the next action above the large cards. | Chrome screenshots at 320×568 and 390×844; warning/action fully inside the first screen. |
| A05 | Connect target follows header selection; its state is scoped to the actual station. | Chrome selected audit-B and observed audit-B in Station ID. |
| A06 | Station stays mounted while navigating between primary pages, preserving connection secrets in memory and watch drafts. | Chrome retained Wi-Fi name and unsaved watch height across Your river → Station. Refresh still clears transient connection fields, as disclosed in setup instructions. |
| A07 | Python and Android validate current fresh complete evidence at the expected calibration revision before accepting verification. | Python rejects stale and missing-probe cases, accepts complete fresh evidence. Android implementation compiles; physical/instrumented acceptance remains pending. |
| A08 | Host validation refreshes the exact local interface addresses every five seconds, doing address lookup outside the HTTP event loop. Arbitrary hosts remain rejected. | Python accepts changed local address and rejects evil.example. |

Additional changes: Demo uses independent seeded drift and jitter for each probe, with nonlinear scenario progression instead of identical waves and flat plateaus. Python, Java and browser generators use the same algorithm. Activity defaults to five-minute minimum–maximum ranges of loaded samples; explicit individual-reading mode and full exports preserve exact samples. Partial window coverage is disclosed. Alerts retain exact timestamps.

Validation: **43 Python tests + 14 subtests, 34 frontend tests, 42 Android host tests passed**; TypeScript/Vite production build passed. Fresh browser repair evidence is `output/preview5-audit/after-results.json` and `after-*.png`. Native output is `native-test.log`. Preview 6 includes the rebuilt APK and laptop ZIP; phone/hardware acceptance limits above still apply.
