# RiverGuard Android companion

Based on https://github.com/alamien060512-alt/RiverGuard-Android at revision
a42f293, with its original MIT license retained. The missing Android app module
has been restored using the locked Capacitor template, with native connection
recovery, Back navigation and authenticated downloads added for this build.

Start RiverGuard on the laptop, connect both devices to the same private Wi-Fi,
enter the laptop address (port 8501), and use a pairing code from Station settings.
Python and local AI run on the laptop. Pairing grants shared installation access;
HTTP is unencrypted.

## Upstream build instructions

Requires Node.js 20+, JDK 21 and Android SDK Platform 35/build tools. On Windows,
run `build-apk.bat` from this folder. The script runs npm ci, Capacitor sync and
Gradle assembleDebug. Expected APK: android/app/build/outputs/apk/debug/app-debug.apk.

## Download and install

Get the APK from this repository's GitHub Releases, not the source-code ZIP.
Allow installation from your browser when Android asks. Open RiverGuard, enter
the laptop's private IPv4 address, and pair using its eight-digit code. Android
Back offers a return to the connection screen; saved chats remain on the laptop.

This is a **debug-signed preview**, suitable for direct installation, not a Play
Store production release. Future builds signed with a different preview key may
require uninstalling the old preview and pairing again. The laptop's saved chats
and readings are unaffected. Only private IPv4 Wi-Fi addresses are supported.

## Build verification

The Android APK workflow installs locked npm dependencies, runs launcher tests,
syncs Capacitor, builds the app, runs native URL-boundary tests and Android lint,
then verifies the APK signature, application ID, launch activity and bundled
launcher assets. It produces a checksum and downloadable build evidence.

An APK build and browser check do not substitute for a real phone test. Physical
phone installation, virtual keyboard, pairing and Wi-Fi transitions still need
acceptance on your device. Python, Ollama and the sensor receiver are not bundled
into the APK. Keep the laptop service running on the same trusted private Wi-Fi.

Original copyright and MIT license: see LICENSE.
