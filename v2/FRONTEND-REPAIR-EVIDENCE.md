# V2 frontend repair evidence

22 October 2026. Implementation on `v2/rebuild`; no production database writes, commits or releases by this pass.

## Verification

- `npm run build --prefix v2/frontend`: TypeScript check and Vite production bundle pass.
- `npm test --prefix v2/frontend`: 30 tests pass (15 domain tests and 15 controller/JSX regressions).
- Controller tests transpile the real React modules through the installed Vite/Oxc transform and exercise their hooks with deferred platform responses. They are deterministic controller tests, not a substitute for actual browser interactions or Android device tests.
- The build regenerates the existing ignored `v2/mobile/web` output; native asset synchronization and release packaging remain separate steps.

## Findings addressed in this layer

| Finding | Change and evidence |
|---|---|
| V2-02 | Station/source changes immediately clear policy state; failed lookups remain visible and retry on refresh. Water interpretation waits for valid station policy. Deferred controller test switches A → B and rejects/retries B's load. |
| V2-03 | Physical verification requires valid reviewed watch settings. Geometry changes invalidate the form's watch-ready state while reloading. Controller test blocks verification with invalid watch policy. Server/native enforcement remains authoritative. |
| V2-05 | Watch saves use expected revision; conflicts keep current input and require explicit reload. Deferred controller conflict test. |
| V2-11 | Setup fetches the real station's own watch policy regardless of Demo selection. Controller verifies `source: esp32` and selected real station. |
| V2-12 | Calibration save commits only its submitted edit version; newer edits remain persisted under the returned base revision. Initial inputs are disabled until settings/draft restore completes. Deferred save test retains correction 2 after submitting correction 1. |
| V2-13 | History clears rows/cursor/count/detail on scope changes; main route remounts by scope. Badges use each record's source. Failed replacement request regression. |
| V2-14 | All event loads, including manual refreshes, share a generation guard. Late A response cannot replace B. |
| V2-15 | UI uses service-owned Demo controls; fixture helper uses the same bounded 120-step phase, 250 NTU cap and 150 cm cap. Long-run boundary tests. |
| V2-16 | No browser-owned generation timer or append loop remains. Two controller instances share pause state and handle conflicting scenario changes; neither writes samples. |
| V2-17 | Every isolated chart segment has a visible marker. Real Trend JSX test verifies two points separated by a missing sample draw two circles. |
| V2-18 | Events use explicit `measuredAt`, preserve the opaque sample ID separately, and label absent provenance unavailable. Regression uses `boot-a0b1-42`. |
| V2-19 | Navigation always has `aria-label`, title and focus styling, including collapsed rail. Browser accessibility verification still required. |
| V2-27 | Draft saving/saved/failed states track the matching write generation; retry is visible. Failed persistence test never shows “Draft saved here.” |
| V2-29 | Multiple-station header reflows into full-width station-selection row with 44px targets at phone widths. Actual 320px/390px screenshots and interactions remain parent acceptance work. |
| V2-30 | Unset geometry renders blank. Suggested values require an explicit action; zero capture requires explicit usable limits. Controller test confirms a missing reference is blank. |

Additional integration: read-only retained ledger conditions merge into Overview and Rill as last-known warnings; paired-browser list/revoke has a confirmation dialog; malformed legacy drafts are refused by the form without deleting their stored evidence.

## Interface assumptions

- `getWatch` / `saveWatch` return `{revision, settings, valid, needsReview?}`; save requires source, deviceId and expectedRevision.
- `getDemo` / `saveDemo` return `{revision, scenario, running, step, error?}`; save uses expectedRevision.
- `getAlertState({source,deviceId})` returns `{conditions:[{kind,level,title,detail,measuredAt,lastKnown}]}`.
- Draft key: `draft:esp32:<deviceId>`, value `{revision, settings}` or null. Incomplete numeric draft values may be null; final calibration saves remain strict.
- Events remain available through the read-only `alerts:<deviceId>` key. Fields: measuredAt, evaluatedAt, watchRevision, watchSettings, calibrationRevision; unknown legacy fields are not invented. Settings recheck events have a neutral Rechecked label and marker, distinct from recovery.
- Web session list returns `{items:[{id,label,lastSeen,current}]}`; revoke accepts `{sessionId}`.

## Pending acceptance

Actual desktop/mobile screenshots, zoom/reduced motion, download completion and real Android lifecycle/notification tests are not claimed by these controller tests. Parent release evidence must record them separately.

Browser follow-up repairs: capture actions show a visible reason for stale/faulty/missing/out-of-range signals; retained water warnings show their original measured time rather than the latest faulty packet. Shared eight-case sensor fixtures now run through Python, Java and browser derivation/evaluation.

The integrated browser pass found duplicate sibling React keys between Calibration and WatchSettings. Their keys now have separate prefixes; a scoped-identity regression prevents repeated keys during station switches. Parent browser verification checks orphaned forms disappear.
