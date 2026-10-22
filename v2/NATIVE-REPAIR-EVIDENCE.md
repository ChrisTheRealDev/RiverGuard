# V2 native and firmware repair evidence

22 October 2026 (Asia/Kuala_Lumpur). Implementation evidence, not physical-device acceptance.

## Changes

- V2-01 / 04 / 25: explicit active/clear/unknown evidence; positive distinct-sample recovery; policy/calibration changes use `settings_changed` and subsequent `rechecked`, never measured recovery. Ingest stores each accepted packet, processing position, ledger and events in one transaction. Delayed packets stay historical. New events retain measurement time, evaluation time, calibration revision and watch revision/settings. The interface can read unresolved last-known conditions through `getAlertState`.
- V2-03 / 05 / 23 / 30: source-scoped revisioned watch settings with CAS conflicts, observable-height validity and acknowledgement requirements before verification. Geometry changes invalidate physical verification. Existing real `demo-station` identities survive; new registrations reserve the name. Unknown geometry remains null.
- V2-07 / 25: CSV numeric values derive from captured calibration, retaining raw measurements. Export policy is explicitly labelled as export-time context; event JSON preserves actual captured policy separately.
- V2-10 / 26: public preferences use an allowlist and validated draft structures. Malformed ledger records are quarantined, disclosed as degraded monitoring and isolated from other stations. Extreme numeric values return validation errors.
- V2-15 / 16: one app-scoped producer owns revisioned Demo controls. Four bounded deterministic scenarios reset phase on selection changes. Generic browser-side appendDemo is rejected. Demo never enters the real-station notification ledger.
- V2-20 / 21 / 28: durable notification outbox separates recording from delivery, retries relevant active conditions after permission/channel restoration, and suppresses superseded entries. A 60-second first-packet grace period produces a connection event. Successful runtime recovery restores the ongoing notification text.
- V2-22: scheduled-state flags replace zero-sentinel deadlines for both network workers; the shared `deadlineReady` function uses bounded rollover-safe signed differences.

## Preservation and upgrade

Native schema 1 upgrades transactionally to schema 2. At singleton startup, before SQLiteOpenHelper begins migration, the old database is opened, WAL is checkpointed/truncated, then the handle is closed and a private byte-complete backup is fsynced beside it. Android does not expose SQLite's C backup API. A failed checkpoint or copy aborts the upgrade. SQLiteOpenHelper wraps all schema/state changes in its upgrade transaction.

Raw readings, calibration records, credentials and original event JSON are preserved. Legacy policy provenance is explicitly unavailable. Ambiguous old Demo/hardware watch settings are copied into separate scopes and marked for review. Old drafts are copied to source-scoped keys. Historical active conditions are retained for fresh rechecking; historical rows are not silently replayed under current policy.

Rollback requires the prior app plus its matching pre-migration database backup. Do not open schema 2 with the old app or uninstall the phone app to update.

Staged package version: `2.1.0-v2.preview.2`, Android versionCode `2`; application ID remains `com.riverguard.v2`. Signing identity is unchanged. No release has been published by this implementation pass.

## Checks performed

- **42 pure-Java JVM tests passed** using ECJ with Java 8 source compatibility and the existing JRE/JSON/JUnit toolchain. This includes 14 added repair regression tests plus two shared-fixture consumer tests.
- **Two Python shared-fixture tests passed**, consuming the same eight snapshot vectors and six transition sequences as Java. Fixture: `tests/fixtures/signal-repairs.json`. Cases include missing probes, stale samples, calibration gaps, water rise, valid recovery, policy rechecks and connection recovery.
- `PhoneStore.java` compiled successfully against the available Android API stub jar. This checks Java/API compatibility for the storage class, not Android SQLite execution.
- **Full Android SDK/Gradle debug application and instrumentation APK builds passed**, followed by **42 Gradle host unit tests with zero failures, errors or skips**. A lower-memory retry after the initial disk-space stop exposed a CP1252 middle-dot byte in `MonitoringService.java`; it was replaced with an ASCII Java Unicode escape. All 19 production Java files passed UTF-8 validation. The instrumentation APK compiled, but its nine SQLite tests were not run on a phone/emulator.
- **ESP32 PlatformIO release build passed** for pinned `nodemcu-32s` dependencies. RAM: 47,776 / 327,680 bytes. Flash: 963,277 / 1,310,720 bytes. Existing OneWire preprocessor warnings were emitted; no firmware errors.
- **11 compile-time C++ deadline assertions passed** using the actual ESP32 compiler and production deadline helper. They cover the signed 24.85-day boundary, unsigned rollover, scheduled zero and unscheduled operation.
- Added **nine Android instrumentation tests** using uniquely named private test databases. They cover each-packet excursions, duplicate retries, fault/delayed recovery, watch CAS and geometry, notification outbox state, first-packet timeout, export derivation, reserved preferences, migration backups, and still-active pending warnings after policy changes. These tests are authored but have not run on an Android device/emulator in this pass.

## Remaining acceptance

Final corrected-source incremental tasks `assembleDebug`, `assembleDebugAndroidTest`
and `testDebugUnitTest` passed. Both APK debug signatures verified, and all seven
compiled browser files byte-matched the application APK. Local build artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Debug application APK | 6,630,652 | `6be4494e9a58b66af58da61220daa790115f00789653c7beb11c1251c6cac5a0` |
| Debug instrumentation APK | 570,974 | `a947397ec3ab5bd7d8df74f8645bfa5444cac35756ca2ac348c45d65ebaf0675` |

Detailed local logs and verification are retained under
`D:\RiverGuard\.build-tools\v2-android-qa`, including
`ANDROID-BUILD-EVIDENCE.md` and `FINAL-APK-VERIFICATION.json`.
These build outputs are not included in the portable source/laptop preview.

The successful debug build does not establish release signing, installation/update compatibility or device execution. The local preview contains source and compiled browser assets, not a debug APK presented as a release update. No phone/emulator was connected here. Installation/update, actual SQLite migration, bridge calls, notification permission/channel behavior, native exports, lock-screen/Doze/OEM behavior and Wi-Fi reconnection remain physical acceptance gates. Firmware compilation and deadline proofs do not verify wet sensors, wiring, blind zones or an actual long-running ESP32.

## Signed preview 2

Release APK version 2.1.0-v2.preview.2 (code 2) passed signature verification,
matched the preview 1 certificate, and is not debuggable. All seven current web
assets match its contents. Release unit tests: 42 passed; lint: zero errors,
18 warnings. APK SHA-256: `e21b36913c54e94e80956019faafbff0e68b3c5281b8d4aad62a5046cf36d5b9`.
Publication for friend testing is user-authorized; device acceptance remains
pending. Existing releases and signing identity are preserved.
