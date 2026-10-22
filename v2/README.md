# RiverGuard V2

A calmer river observatory for Android and the laptop. V2 leads with two simple
questions: **does the water show an issue, and is the level rising?** Detailed
measurements, graphs, history tables and sensor diagnostics remain available
without overwhelming the first view.

Development is on branch `v2/rebuild`. The app on `main` and the existing GitHub
Releases remain available. This directory uses separate app storage, ports and
Android application identity. No automatic migration or deletion of old data.

## Agreed scope

- Shared responsive design: deep teal, soft glass, clear type and comfortable
  spacing. Graphs and tables support the explanation.
- One station initially, with water quality and rising water shown separately.
- Android works without a laptop or AI model. Monitoring can be explicitly
  started in the background with visible status and notifications.
- Same private Wi-Fi; off-site collection is outside this release.
- ESP32 can deliver to phone and laptop at the same time. Each has its own
  history, credentials, calibration and watch settings; these are not synced.
- Rill is an optional guide explaining observed readings. No AI model is required
  and no rule-based note is presented as an AI response.

## Development and operation

The shared frontend is in `frontend/`, the separate Android package in `mobile/`,
the laptop service in `server/`, and dual-receiver ESP32 code in `hardware/`.
Use the repository's locked Python environment for the laptop service. Install
the locked Node dependencies in frontend and mobile when building; an installed
Android APK has no Node/Python requirement.

```powershell
cd v2/frontend
npm ci
npm test
npm run build
cd ../..
python v2/serve.py
```

The new laptop defaults are web port **8510** and sensor port **8010**, separate
from the existing application. The Android sensor receiver uses the phone's
port **8000**. See the service's `--help` for isolated review arguments.

## Interpretation and availability

"No issues detected" refers only to available, calibrated, fresh sensor evidence.
It does not certify drinking/swimming safety, identify pollutants or predict
floods. Missing, delayed, faulty or provisional readings remain explicit.

Phone monitoring needs station Wi-Fi, user-enabled background monitoring and
working OS/network resources. Notifications need notification permission. An
explicit stop/force-stop ends collection; this is not a promise of uninterrupted
background operation. Keep an appropriate receiver active at the station.

Initial firmware upload still needs programming tools. Later calibration is
editable in each app. Use known standards and physically verify the probes and
required voltage dividers. Actual phone, tank and sensor acceptance is separate
from automated builds and browser preview tests.

Read [the product brief](PRODUCT-BRIEF.md) and
[the hardware setup](hardware/README.md) for details.
