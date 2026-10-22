# V2 repair preview — 22 October 2026

V2 observatory preview 2 (`v2-observatory-preview.2`), prepared for friend testing
at the user's request on 22 October 2026. This is a prerelease, not a claim of
completed physical acceptance. Existing V1 downloads remain available.

## Run the laptop preview

Extract the entire ZIP into a new folder. Install Python 3.14 with Python on PATH,
then open `v2/Setup RiverGuard V2.cmd` followed by `v2/Start RiverGuard V2.cmd`.
Initial setup downloads the pinned Python dependencies. The compiled interface is
included, so Node.js is not needed to run it. Default ports are 8510 and 8010.
Use a new installation for review; do not copy a production database into this
preview without keeping a matching backup. Keep access on trusted private Wi-Fi.

## Included repairs

Monitoring retains warnings through unknown evidence, processes accepted samples
durably and records interpretation provenance. Watch settings use revisions;
calibration drafts survive delayed saves. Demo has one shared producer. Charts
show isolated points, narrow headers remain readable, and native monitoring has
notification-outbox and first-reading-grace implementations. Water quality now
uses lavender, water level uses blue, and acidity/cloudiness/temperature/level
have matching distinct chart, selector and reading-card accents. Warning colours
remain separate from the category palette.

See [all 30 findings and their evidence](REPAIR-CLOSURE.md),
[browser inspection](BROWSER-REPAIR-EVIDENCE.md),
[frontend checks](FRONTEND-REPAIR-EVIDENCE.md) and
[native/firmware checks](NATIVE-REPAIR-EVIDENCE.md).

## Android and outstanding acceptance

The Android release APK is supplied separately from the laptop ZIP. It uses the
existing V2 signing identity and a higher version code, so install it over the
previous V2 preview without uninstalling. V1 uses a separate app ID.
The debug application and instrumentation APKs also compiled, and 42 host unit
tests passed. No debug APK is presented as a release update.
Nine native SQLite instrumentation tests compiled but have not run on Android. Actual
phone install/update, permissions, background behavior, document export and
physical sensors remain pending. Exact browser zoom/reduced-motion and completed
browser download checks also remain pending. Publication for testing does not close those
acceptance checks or the affected phone's V1 APK download report.

## Package contents and verification

`SHA256SUMS.txt` inside the archive hashes each included file. Adjacent `.sha256`
and `.verification.json` files record the ZIP hash, size and integrity checks.
The allowlist includes the laptop service, built frontend, frontend/native/ESP32
source and regression tests, lock files, launchers and setup/tank/wiring guides.
It excludes credentials, databases, logs, station configuration, signing keys,
local SDK settings, downloaded SDK/build caches, dependency folders and APKs.
The project's standard Gradle wrapper and version properties are included;
Android development still requires its SDK, Java and downloaded dependencies.

Before upgrades, preserve the application's transactional migration backup. For
rollback, stop the app and restore the matching pre-upgrade database **and** old
build together, preserving any newer readings separately. Do not open a migrated
database with an older app. Do not uninstall the phone app to retry a download.

## Preview 2 build verification

Signed release build and 42 release unit tests passed; Android lint has zero
errors (18 advisory warnings). The release certificate matches published V2
preview 1. All seven frontend files in the APK match the current build.
The final backend run passed 40 tests and 14 subtests; all 11 download/package
regressions passed. Physical device tests remain pending.
