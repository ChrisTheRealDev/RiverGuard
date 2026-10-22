# V2 repair closure checklist

22 October 2026 · `v2/rebuild` · original audit baseline `ba417ef`.

On 22 October 2026 the user explicitly requested publishing preview 2 for friend
testing, with the remaining acceptance checks disclosed. Implementation addresses
the 30 recorded findings. **This is not an all-closed
or release-accepted report.** Automated evidence, browser inspection and physical
Android/ESP32 acceptance are different gates. Native SQLite migrations, durable
notification delivery and actual phone lifecycle behavior remain unverified on
a device. No physical sensor commissioning was performed.

## Evidence and status rules

- **Implemented / automated:** production change exists and the named regression
  covers its software behavior. This does not substitute for the remaining checks
  listed in the last column.
- **Implemented / acceptance pending:** the change exists, but its decisive runtime
  behavior still requires Android SQLite/instrumentation, browser or hardware work.
- **Open report:** the user's failure has not been reproduced or resolved on the
  affected device; a passing check on another platform does not close it.

Evidence references used below:

- **PY:** [backend repair regressions](tests/test_repairs.py), plus preserved
  [backend coverage](tests/test_backend.py).
- **FE:** [frontend controller regressions](frontend/tests/controllers.test.cjs),
  [domain tests](frontend/tests/domain.test.cjs) and
  [frontend evidence](FRONTEND-REPAIR-EVIDENCE.md). Controllers exercise the real
  React modules with deferred platform responses; they are not browser tests.
- **JAVA:** [native repair regressions](mobile/android/app/src/test/java/com/riverguard/v2/RepairRegressionTest.java)
  and [native/firmware evidence](NATIVE-REPAIR-EVIDENCE.md). These exercise the
  production Java domain/ledger, not Android's actual SQLite, services or
  notification manager. Nine [Android SQLite instrumentation tests](mobile/android/app/src/androidTest/java/com/riverguard/v2/PhoneStoreRepairTest.java)
  have been authored but not executed on a device/emulator.
- **Shared interpretation fixtures:** [eight snapshots and six transition sequences](tests/fixtures/signal-repairs.json),
  consumed by [Python parity tests](tests/test_signal_parity.py), Java fixture
  tests and the frontend domain suite. They cover missing/stale measurements,
  calibration gaps, rise, recovery, settings rechecks and connection recovery.
- **FW:** [rollover regression](hardware/firmware/test/test_deadline/test_main.cpp)
  and [retry deadline implementation](hardware/firmware/include/retry_deadline.h).
- **Browser:** [interaction and screenshot evidence](BROWSER-REPAIR-EVIDENCE.md), with isolated QA artifacts under
  `D:\RiverGuard\output\v2-repair-2026-10-22`. The initial repair captures include
  `desktop-1366x650.png`, `mobile-320x568.png`, `overview-1366x768.png`,
  `overview-1280x720.png`, `overview-1024x768.png`, `overview-853x650.png`,
  `overview-390x844.png`, `calibration-mobile.png` and
  `isolated-chart-mobile.png`. The parent pass inspected
  actual screenshots and interactions at those measured CSS sizes. These are
  desktop-browser viewports, not physical-phone results. Do not publish its
  copied database or owner bootstrap link.

Latest reported verification:

- **197 Python tests plus 14 subtests passed** across the V1/V2 suite. After the
  final monitoring-health patch, the focused V2 suite passed **39 tests plus 14
  subtests**. The subsequent explicit export-snapshot transaction fix passed
  **two focused export tests**, including concurrent watch/reading changes.
  The earlier full-suite run is not claimed to include those later changes.
- **30 frontend tests passed**, with successful TypeScript/Vite build, as recorded
  by the frontend pass. This includes the new duplicate-sibling-key regression.
- **42 production-domain Java tests passed**, including shared fixture consumers.
- **ESP32 PlatformIO release build passed**, and **11 C++ deadline assertions
  passed** against the production helper.
- **Full Android SDK/Gradle build passed:** `assembleDebug` and
  `assembleDebugAndroidTest`, plus **42 Gradle host unit tests passed** with zero
  failures, errors or skips. After the initial low-disk stop, a lower-memory
  retry exposed and corrected a source encoding defect; 19 Java files were
  validated as UTF-8. **Nine Android SQLite instrumentation tests compiled but
  remain unexecuted.** Debug artifacts are not a signed release update and are
  excluded from the laptop/source preview ZIP. No device acceptance is claimed.
- **Eight release-download verifier tests passed**, plus complete and resumed
  anonymous transfers for all three existing APKs.

Any subsequent build/check results must be recorded separately, without treating
pending phone checks as passed.

## Finding-by-finding record

| Finding | Repair and concrete evidence | Remaining closure requirement |
| --- | --- | --- |
| V2-01 — false recovery on missing evidence | Explicit active/clear/unknown evidence; three distinct usable clear samples; changed settings resolve as `rechecked`, never a claimed environmental recovery. PY `test_missing_or_faulted_readings_never_recover_water_warning`, `test_policy_change_is_not_river_recovery`, `test_recheck_resolves_without_poisoning_future_recovery`; JAVA `missingProbeCannotRecoverActiveWarning`, `changedCalibrationOrPolicyCannotClaimMeasuredRecovery`, `continuingHighAfterPolicyChangeResolvesAsRechecked`. Retained conditions feed Overview/Rill. | Implemented with domain coverage. Native persisted ledger/upgrade acceptance pending; inspect last-known warning in actual UI. |
| V2-02 — previous station thresholds retained | Policy state clears on selection, failed loads stay visible, retry reloads correct scope. FE `station switch cannot reuse old thresholds; failed lookup stays visible and retries`. | Implemented / controller coverage. Paired-browser station-switch acceptance pending final browser results. |
| V2-03 — unreachable watch marks can pass verification | Geometry/policy validity and acknowledgement checked before verification; changed calibration invalidates verification. PY `test_watch_cas_scope_and_geometry`; JAVA `missingOrImpossibleGeometryIsNotCommissionable`; FE `verification is blocked while watch policy is invalid even with acknowledged calibrated probes`. | Implemented / automated. Native SQLite transaction and real sensor acknowledgement/physical checks pending. |
| V2-04 — measured excursions skipped between ticks | Durable per-station processing position; accepted samples processed individually with transactional events and ledger. Delayed packets cannot regress current state. PY `test_short_excursion_and_restart_processing_are_durable`, `test_delayed_packet_does_not_regress_current_or_count_as_recovery`. Native `PhoneStore.processSamples` runs with ingest transaction. | Python software regression coverage. Native SQLite ingest/restart/rollback tests pending. |
| V2-05 — watch saves silently overwrite | Source-scoped watch revisions and expected-revision conflicts. PY `test_watch_cas_scope_and_geometry`; FE `real setup loads real watch policy independently of Demo; conflict keeps input`. | Implemented / automated. Two paired browsers and native persisted conflicts pending final acceptance. |
| V2-06 — SQLite blocks async HTTP loop | Bounded worker execution moves synchronous database work off the shared event loop; atomic operations remain intact. PY `test_write_lock_does_not_block_async_http_loop`. | Implemented / automated. Production-load soak is not claimed by the controlled contention test. |
| V2-07 — blank hardware CSV measurement columns | Export derives numbers from each captured calibration, retaining raw and settings evidence. PY `test_hardware_csv_uses_captured_calibration_not_current`, `test_export_captures_policy_and_ceilings_in_one_snapshot`; native exporter uses `SignalEvaluator.Reading`. | Python coverage, including a read transaction capturing policy/ceilings under concurrent changes. Completed native document export and saved-file content verification pending. |
| V2-08 — installations collide on browser cookie | Persistent installation-specific cookie names and legacy-session transition. PY `test_cookie_names_isolate_installations_and_peer_revocation`, `test_migration_backup_preserves_old_events_and_sessions`. | Implemented / automated. Browser coexistence/logout check pending final browser pass. |
| V2-09 — cannot revoke a paired browser | Session list, labels/last activity and individual revocation, with UI confirmation; equal paired access retained. PY `test_cookie_names_isolate_installations_and_peer_revocation`. | API coverage and actual mobile-layout confirmation: Cancel preserved the QA peer; confirming Remove access removed only that peer and retained the current session. Physical phone still pending. |
| V2-10 — public preferences can corrupt internal ledger | Public key/schema restrictions; malformed internal state quarantined and station errors isolated. PY `test_public_state_cannot_access_internal_ledgers`, `test_corrupt_ledger_quarantined_without_losing_samples`, parametrized `test_invalid_ledger_conditions_are_quarantined`; JAVA `fractionalLedgerValuesAreCorrupt`, `draftsAllowUnfinishedNumbersButRejectMalformedShapes`. | Implemented / automated validation. Native quarantine/storage and degraded-notification runtime pending. |
| V2-11 — Demo policy appears in hardware setup | Setup independently requests the real station's `esp32` policy. FE `real setup loads real watch policy independently of Demo; conflict keeps input`. | Implemented / controller coverage. Actual Station destinations and real-station flows exercised; station-switch retest confirmed one calibration field/form after the additional key fix. |
| V2-12 — save/load overwrites newer calibration draft | Submitted edit generation separated from newer draft; load completes before editing; late save retains edits using returned revision. FE `calibration save preserves newer input and persisted draft with new revision`. | Controller coverage; actual 0.5 °C draft survived navigation and refresh, then saved as revision 2 with acknowledgement pending. Browser-found duplicate form was fixed, regression-tested and retested as one form after station switching. Physical phone keyboard pending. |
| V2-13 — old history shown under new station/source | Rows, detail, cursor and count clear by scope; late responses ignored; badges derive from returned record. FE `history clears old source rows and pagination while replacement fails`. | Implemented / controller coverage. Browser switching/loading/failure inspection pending final results. |
| V2-14 — stale manual event refresh replaces another station | Manual and effect refreshes share request generation guards. FE `late manual event refresh for A cannot replace B events; opaque IDs stay identifiers`. | Implemented / controller coverage. Paired/browser interactions pending final results. |
| V2-15 — Demo values exceed validation limits | Bounded repeating scenario phases in service/native generator and shared fixture helper. PY `test_demo_shared_pause_cas_and_long_running_bounds`; FE `Demo remains bounded for long-running producers and restarts each scenario phase`; JAVA `allDemoScenariosRemainValidAfterLongRuntime`. | Implemented / automated; Rising scenario and Pause exercised in the actual browser. Long-running actual application behavior remains a soak check. |
| V2-16 — tabs compete to generate Demo readings | Single backend/native producer; revisioned shared controls, no frontend sample-writing timer. PY `test_demo_shared_pause_cas_and_long_running_bounds`; FE `two Demo controllers share authoritative pause and conflict state without writing samples`. | Automated controls coverage and two actual browser tabs verified shared Normal/Resume → Pause; both displayed Resume afterwards. Native application lifecycle remains pending. |
| V2-17 — isolated valid graph points disappear | Single-point segments render visible markers without connecting across missing samples/calibration gaps. FE `valid isolated chart points on both sides of a gap each have a marker`. | JSX and actual-browser acceptance: two isolated DOM circles and two move-only paths verified; `isolated-chart-mobile.png` inspected. |
| V2-18 — sample identifier rendered as invalid date | Separate explicit measurement time and opaque identifier; legacy unknown time/provenance labelled unavailable. FE `late manual event refresh for A cannot replace B events; opaque IDs stay identifiers`; JAVA `eventsRetainMeasurementAndPolicyEvidence`. | Implemented / automated; populated event details in the actual browser displayed a real timestamp separately from an opaque sample ID. |
| V2-19 — collapsed navigation has no names | Permanent accessible names, titles and focus styling. Frontend source/evidence records the change. | Names confirmed in actual collapsed navigation at 853 CSS px; final full keyboard/zoom acceptance remains separate. |
| V2-20 — blocked notification never delivered later | Durable native outbox; permission/channel reconciliation checks current relevance; changed-policy pending warnings are renewed. JAVA `policyChangeRefreshesStillActiveWarningDeliveryEvidence` covers replacement event generation. | Implemented / acceptance pending: actual SQLite outbox persistence, permission/channel denial/re-enable, obsolete suppression, restart delivery and Android notification dispatch. |
| V2-21 — no first-reading timeout notification | Persisted station grace timing; 60-second no-first-packet connection warning; three fresh packets resolve connectivity independently of environmental policy. JAVA `firstConnectionWarningRecoversAfterThreeValidPackets`; native `PhoneStore.evaluateAlerts`. | Implemented / acceptance pending: real timer, persisted state, receiver lifecycle and notification dispatch. |
| V2-22 — ESP32 upload stops after signed timer boundary | Explicit scheduled retry state and unsigned rollover-safe deadline helper for receiver workers. FW regression targets signed and unsigned boundary values. | PlatformIO release build and 11 deadline assertions passed. Physical sustained uptime and two receiver operation pending. |
| V2-23 — hardware `demo-station` shares Demo settings | Watch and draft data scoped independently; existing reserved hardware ID retained, new registration rejected; ambiguous migrated settings require review. PY `test_watch_cas_scope_and_geometry`, `test_migration_backup_preserves_old_events_and_sessions`; native migration/register paths. | Python coverage. Native schema migration/legacy reserved-ID acceptance pending. |
| V2-24 — failed monitor still reports healthy | Health and monitoring info inspect task liveness, heartbeat and station errors; worker supervision restarts unexpected failures. PY `test_failed_monitor_is_not_reported_healthy`. | Implemented / controlled failure coverage. Ordinary spontaneous crashes were not previously observed. |
| V2-25 — missing alert interpretation provenance | New events carry measurement/evaluation times, calibration/watch revisions and applied settings; export includes event evidence and separately labelled export-time policy. PY `test_last_known_warning_and_event_export_survive_fault`; JAVA `eventsRetainMeasurementAndPolicyEvidence`. | Python and Java event coverage. Actual native CSV/document verification pending; legacy unknown provenance stays unknown. |
| V2-26 — enormous integer causes HTTP 500 | Numeric bounds/type checks reject unsupported values safely. PY `test_huge_numeric_input_is_validation_error`; JAVA `hugeNumericInputIsValidationFailure`. | Implemented / automated. |
| V2-27 — draft falsely labelled saved | Saving/saved/failed states track completed write generation with visible retry. FE `failed draft write never claims saved; missing geometry stays blank`; malformed draft restore also covered. | Implemented / controller coverage. Actual storage-failure and refresh interaction pending final browser/device acceptance. |
| V2-28 — ongoing Android error notification sticks | Successful runtime recovery updates the ongoing notification to normal monitoring text. Native `PhoneRuntime.tick` and `MonitoringService.showRuntimeHealthy`. | Implemented / acceptance pending: Android notification UI error → recovery transition. |
| V2-29 — narrow station selector collapses to arrow | Phone header reflows; station selector gets readable space and minimum 44px targets. Actual 320px viewport inspection measured a readable 282×44px station control; 390px screenshot also inspected. | Browser geometry/visual acceptance performed. Physical phone touch/keyboard acceptance remains pending. |
| V2-30 — displayed default geometry was not saved | Unset geometry renders blank; suggested values require explicit adoption; null stays null until deliberately saved. PY `test_null_geometry_stays_null_until_explicitly_saved`; FE `failed draft write never claims saved; missing geometry stays blank`. | Automated and actual-browser save/reload acceptance: `audit-unset` retained a saved 0.25 °C correction after refresh while all three geometry fields stayed blank. Native SQLite acceptance remains pending. |

## Actual browser acceptance performed

The parent pass used the isolated QA database and inspected screenshots at
1366×650, 1366×768, 1280×720, 1024×768, 853×650, 390×844 and 320×568 CSS pixels.
It exercised all four metric selectors and explanation dialogs, Escape,
More/Less, Rill opening/closing, Rising Demo and Pause. Real-station history
loaded 100 of 120 readings; raw samples and event details were inspected.

Station checks included Connect stop/start, wiring/tank disclosures, all four
wizard steps, visibly blocked stale captures and the 0.5 °C temperature draft
persisting across navigation/refresh. Saving calibration returned revision 2
with acknowledgement still pending; no physical verification was asserted.

This pass found an additional duplicated-calibration-form defect during station
switching. The frontend pass fixed sibling-key uniqueness and added a regression;
the final actual-browser retest confirmed one field/form after station switching.
An uncalibrated station retained its saved 0.25 °C correction after refresh while
all three water-geometry fields remained blank. Two actual tabs shared Demo
Normal/Resume → Pause state. A chart fixture with two isolated valid samples
rendered two visible circles without joining the gap; its screenshot was inspected.
Peer removal was cancelled and then confirmed in the mobile layout; only the QA
peer was removed. The final desktop capture showed the retained water warning at
20:42:46 separately from the latest faulty sample at 20:42:54. QA servers stopped,
the temporary owner link was removed and browser viewport/tabs were restored.

The browser provider cancelled the file transfer when Export was clicked. API
content checks pass, but **a completed browser-saved export remains pending**.
Actual 125%/200% zoom, reduced-motion preferences and a real Android phone/virtual
keyboard remain unverified. Viewport resizing is not claimed as actual zoom or
phone acceptance.

## V1 Android download report — separate and still open on the phone

See [distribution repair evidence](../docs/downloads-repair-evidence.md),
[version-specific Android download instructions](../docs/ANDROID-DOWNLOADS.md)
and [anonymous transfer verifier](../scripts/release_downloads.py).

- The original standalone APK is unchanged. A byte-identical APK inside a ZIP
  alternative is staged locally; its checksum and ZIP integrity were checked.
- All three existing public APKs completed anonymous full and fresh-URL resumed
  HTTP transfers with matching byte counts/hashes. Eight verifier regressions
  passed. These checks do not emulate Android Download Manager.
- No corrupt upload or broken HTTP range support was reproduced here.
- **Open:** affected-phone Chrome/Samsung Internet download completion and the
  original stall cause. Also pending: actual install/update and publication of
  the ZIP alternative after the release gate. Do not label this report resolved
  based solely on a desktop download passing.

## Acceptance still required before release

1. Preserve the successful debug-build evidence; produce a release-signed Android
   update using the existing signing identity only after the remaining gates.
   A compiled instrumentation APK does not mean its device tests ran.
2. Finish the browser checks still pending above, including
   exact 125%/200% zoom, reduced motion, outstanding
   confirmations and completed file transfers. Preserve the already inspected
   viewport screenshots and interaction evidence; do not replace those results
   with overflow measurements alone.
3. Run Android SQLite migration/rollback and outbox/service acceptance on a real
   phone or appropriate Android instrumentation environment. Test permission and
   channel restoration, first packet timeout, restart, lock/background behavior,
   Wi-Fi reconnection, document saving and preserved data after signed updates.
4. Keep actual ESP32/tank wiring, voltage dividers, calibration, blind zones,
   two receivers and sustained uptime as explicit physical-hardware acceptance.
5. Keep prior APKs/ZIPs and normal user data intact. The user authorized a labelled preview 2 release for friend testing. Keep the
   outstanding checks visible; publication does not authorize an all-findings-closed claim.

## Backups and rollback

Python startup uses SQLite's backup API before its transactional schema upgrade.
Android prepares a private pre-upgrade backup after checkpointing and closing the
old database, then SQLiteOpenHelper migrates transactionally. Android restoration
still needs device/instrumentation validation.

Do not open a migrated database with an older application. Stop the relevant
services, preserve the current database and any new readings, and restore the
matching pre-upgrade backup together with the matching previous app build. A
rollback can discard post-upgrade records unless separately preserved/exported;
never silently replace current user data. Do not uninstall a standalone Android
app as a download retry, because uninstalling erases its private data.

No real hardware acceptance, affected-phone download success, release publication
or complete native-storage validation is implied by this checklist.
