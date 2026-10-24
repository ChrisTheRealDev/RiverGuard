# RiverGuard Android 2.3.0

Android 2.3.0 brings the Windows 2.3.0 visual palette to the standalone V2 app: stronger mint and lavender accents, consistent reading colours, teal surfaces, clearer input borders and focus states, matching native launch/system colours, and compact-screen dialog and welcome layouts. The Android interface keeps its existing offline features, native storage, background monitoring controls, setup guide, simulation and Activity summaries.

Install `RiverGuard-Android-2.3.0.apk` over V2 Preview 6. The package remains `com.riverguard.v2`, signed with the existing release identity; version name is `2.3.0` and version code is `7`. Do not uninstall to update if you want to retain your readings and settings. This is the V2 app; the older `com.riverguard.app` standalone app has separate storage and is not migrated.

This Android source is on `v2/rebuild`, tagged `android-v2.3.0`. The Windows 2.3.0 release is separate. No Python, laptop or AI model is required to use the APK.

Validation: frontend tests and production build, V2 backend tests, Android release unit tests and lint, signature and package metadata, bundled frontend comparison and published download checksum. Browser layout checks cover narrow phone screens, station setup, Activity and Rill. Physical-phone installation/update, background operation and real sensor reception still need device acceptance.
