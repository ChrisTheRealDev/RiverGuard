# Standalone Android preview

This Android version runs its dashboard and local database on the phone. It does
not connect to Python, Ollama or a laptop. The first screen is a clearly labelled
synthetic demonstration so the installed app can be explored immediately.

## What works without the internet

- Bundled dashboard, explained measurement cards, sample chart and signal checks.
- Native SQLite storage for real and synthetic samples, preferences and versioned
  calibration. Calibration drafts remain on the phone when navigating away.
- Paginated history and an export containing all station raw readings and their
  exact captured calibration snapshots.
- Station registration and credentials, in-app sensor configuration/calibration,
  local wiring/tank instructions and a downloadable setup PDF.
- An authenticated HTTP/TCP sensor receiver on port 8000 while the app is visible
  and the receiver is enabled. The ESP32 and phone need the same private Wi-Fi;
  the Wi-Fi itself does not need internet access.

## AI is not included

There is no on-device model, cloud AI, chatbot or pretend AI fallback in this
build. Rill's River notes are explicitly rule-based explanations of the selected
readings. A future supported on-device model would require a separate download
and device-specific quality/memory/performance acceptance.

## Connect real sensors

1. Connect the phone and ESP32 to the same trusted private Wi-Fi. Keep the phone
   clock correct; a fresh authenticated configuration response can bootstrap an
   unset ESP32 clock when public NTP is unavailable.
2. In Sensors → Connect, enable the receiver and note its phone IP address.
3. Register a station. Its credential is returned once; save the private firmware
   configuration after entering Wi-Fi details. Never share that file.
4. Initially compile/upload the firmware with Arduino IDE or PlatformIO. This
   first flash still needs appropriate programming tools; the APK does not flash
   a board over USB. Set API_URL to the phone, not a laptop.
5. Check signals, enable only the probes actually connected, calibrate with known
   references, choose tank-appropriate watch levels, then physically verify.

The receiver preserves raw packets and the exact calibration revision. ADC
counts are never treated as NTU. Missing/faulted/out-of-range signals remain
unavailable. Voltage dividers, board revision, sensor range and wet calibration
must still be checked on real hardware. Optional unconfirmed TDS is not supported.

## Important operating limits

Sensor reception runs **only while RiverGuard is visible** and enabled. Locking
the screen or switching apps stops the listener. This release is not a permanent
background logger. The ESP32 retains only its existing single pending RAM sample
while retrying; it is not durable offline logging. Demo generation is separate
and labelled synthetic. These checks do not certify drinking safety, identify
pollution or forecast floods.

HTTP sensor traffic is unencrypted. Device credentials are station-scoped and
stored hashed; only bundled local pages can invoke the native database bridge.
There is no public hosting or user account system. Android cloud/device backups
are excluded; use explicit exports before replacing a phone or uninstalling.

## Installation and updates

Download the standalone APK from GitHub Releases. Android may ask permission to
install from your browser. This standalone release uses a persistent release
signing identity so subsequent APKs signed with that identity can update in place.

The earlier 1.x laptop companion was debug-signed using a different identity. You
must uninstall that old companion before installing the first standalone APK.
It stored no sensor database on the phone; its laptop readings/chats stay on the
laptop. **After moving to standalone, do not uninstall to update**: uninstalling
erases the phone's readings, calibration and credentials. Export first if an
uninstall is unavoidable. Old laptop data is not automatically copied into the
new phone database.

## Development and acceptance

From mobile/, install locked dependencies (`npm ci` and `npm ci --prefix
../frontend`), run `npm test`, `npm run check:offline`, `npm run build:offline`,
then `npx cap sync android`. Android builds require JDK 21 and SDK 35. The GitHub
workflow builds and signs the release, runs native tests/lint, and records APK
metadata, a signature certificate and SHA-256 checksum. Signing keys are never
committed. The browser preview uses IndexedDB and cannot listen for sensor packets;
the APK uses SQLite and the native receiver.

Build and browser evidence do not substitute for real-phone acceptance. Physical
installation, screen/keyboard behavior, Wi-Fi reception, packet calibration,
native document exports and battery/lifecycle behavior must be verified on the
actual device before relying on it for collection.
