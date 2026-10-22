# V2 preview verification

Verification date: 22 October 2026. This is a separately installed preview, not a
claim that a physical river station or Android phone has passed acceptance.

## Automated evidence

- Shared monitoring domain: 13 Node tests pass; TypeScript and Vite build pass.
- Laptop service: 16 pytest tests pass, including future/delayed packets, hashed
  station credentials, browser sessions/origin/CSRF, pairing limits, concurrent
  calibration conflicts, raw immutable snapshots, more than 10,000 readings,
  complete cursor exports and concurrent-demo deduplication.
- Android: 26 pure JVM tests pass for receiver validation, limits, signal
  evaluation and persistent alert transitions. Signed Android assembly, lint and
  these tests also run in the V2 GitHub workflow.
- An independent 12,345-record history check confirmed full pagination without
  duplicates, station filtering and cursor snapshot consistency during insertion.
- ESP32 PlatformIO build passes with the pinned NodeMCU-32S toolchain. Static RAM
  is 47,776 bytes; flash is 963,153 bytes after the cache-identity correction.
- V2 frontend and Android npm audits report no known vulnerabilities after
  pinning Capacitor 7.6.9. This repairs the vendor's
  [internal proxy advisory](https://github.com/ionic-team/capacitor/security/advisories/GHSA-rvm3-566m-v7fv).

## Browser evidence

The actual application was inspected at measured CSS viewports of 1366×650,
1024×768, 390×844 and 320×568. Checks included home condition hierarchy, missing
station states, chart selection, narrow-screen readability, activity pagination,
sample details, all four setup steps, calibration draft restoration after refresh,
disabled fresh captures, and the clearly rule-based Rill guide.

Browser testing prompted fixes for 8px narrow chart controls (now a two-row
13px/44px selector), sample details opening below a long table (now an immediate
accessible dialog), timestamps omitting seconds, and demo generation continuing
while real sensors were selected. The firmware's cached receiver identity and
Android's notification channel/Stop race checks were independently reviewed.

## Still requires physical acceptance

- Install the signed V2 APK alongside the old app on a real phone.
- Start monitoring, allow/deny notifications, disable an individual channel and
  verify the displayed status and actual delivery.
- Lock the screen, switch applications, swipe the task away, use Stop, restart
  the phone, disconnect Wi-Fi and inspect the documented recovery behavior.
- Verify native SQLite persistence, keyboard behavior, document exports and
  battery/network resource behavior on the actual Android/OEM version.
- Wire real probes with voltage protection, calibrate against known references
  and test phone/laptop delivery simultaneously, including one receiver offline.
- Observe alert recovery/deduplication and missing-probe water warnings using
  real sensor packets. Compile success does not establish physical correctness.

No existing application source, release or production database was replaced.
V2 uses its own branch, database, ports and Android application identity.
