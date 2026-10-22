# RiverGuard Android companion

Imported from https://github.com/alamien060512-alt/RiverGuard-Android at revision
a42f293, with this documentation and the original MIT license retained.

Start RiverGuard on the laptop, connect both devices to the same private Wi-Fi,
enter the laptop address (port 8501), and use a pairing code from Station settings.
Python and local AI run on the laptop. Pairing grants shared installation access;
HTTP is unencrypted.

## Upstream build instructions

Requires Node.js 20+, JDK 21 and Android SDK Platform 35/build tools. On Windows,
run `build-apk.bat` from this folder. The script runs npm ci, Capacitor sync and
Gradle assembleDebug. Expected APK: android/app/build/outputs/apk/debug/app-debug.apk.

## Verification limit

No APK was built or device-tested for this import. The upstream tracked Android
tree has Gradle configuration but no android/app source module, despite settings
referencing it. Restore or generate a complete native Android project and verify
it before distributing an APK. No inherited build workflow is enabled here.

Original copyright and MIT license: see LICENSE.
