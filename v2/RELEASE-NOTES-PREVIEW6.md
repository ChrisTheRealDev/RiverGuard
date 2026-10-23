# RiverGuard V2 Preview 6 — 23 October 2026

Preview 6 includes the eight audit repairs recorded in `AUDIT-PREVIEW-5-2026-10-23.md`, independently varying simulation readings, and five-minute Activity summaries.

- Demo sensors have separate slow drift and small random variations. Cloudiness and rising-water scenarios develop at variable rates while retaining their purpose. Values remain bounded and synthetic.
- Activity opens with five-minute ranges of loaded readings. Select **Individual readings** to inspect exact times and raw signals. Loading older samples extends coverage; boundary periods may be partial. Exports keep every sample and alerts keep exact event times.
- Calibration captures no longer confuse old calibration coverage with invalid raw signals. Temperature correction instructions use the raw probe temperature.
- Pending browser requests time out after ten seconds and monitoring can recover. Verification requires fresh usable readings on the saved revision in both Python and Android.
- Small phone screens show water status, quality status and the next action before the large cards. Setup drafts survive navigation between primary pages. Connection target follows station selection.
- Laptop host validation refreshes local network addresses while rejecting arbitrary hosts.

## Install or update

**Android:** install `RiverGuard-V2-Preview-6.apk` over the existing V2 app. Version `2.1.0-v2.preview.6`, version code 6, same package and signing identity. Do not uninstall if you want to retain local data. The APK ZIP alternative contains the identical APK. The phone can operate independently; no AI model is required.

**Laptop:** extract `RiverGuard-V2-Laptop-Preview-6.zip`. Install Python 3.14 on PATH. Run `v2/Setup RiverGuard V2.cmd`, then `v2/Start RiverGuard V2.cmd`. Initial dependency setup needs internet; running the compiled interface does not require Node.js. Dashboard port: 8510; ESP32 receiver: 8010.

For an existing installation, stop its service and back up its data before replacing application files. Retain `v2/data` and private station configuration. Do not run two receivers on the same ports. Existing firmware credentials remain valid; this update does not require replacing a station key.

## Verification and limits

The repair checks passed 43 Python tests plus 14 subtests, 34 frontend tests and 42 Android host unit tests. Browser repair checks exercised desktop and phone layouts, station targeting, preserved drafts, reference capture, grouped/original history, request timeout and recovery. Release verification separately checks the signed APK, bundled assets, clean laptop extraction and anonymously downloaded release bytes.

Physical-phone install/update, document saving, background/notification behaviour and real sensor commissioning still need device testing. These are preview builds; sensor checks do not establish drinking/swimming safety or predict floods. Keep previous releases and matching database backups for rollback.
