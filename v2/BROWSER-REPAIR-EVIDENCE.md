# Browser repair verification — 22 October 2026

Tested the production frontend through the Codex in-app Chromium browser against
an isolated database on ports 8512/8012. The normal V1/V2 installations and their
data were not used for these mutations. Stations named `audit-*` are synthetic
hardware-packet fixtures, not commissioned sensors.

## Viewports and visual checks

Measured CSS viewports: 1366×650, 1366×768, 1280×720, 1024×768, 853×650,
390×844 and 320×568. Viewport override inputs were adjusted for the browser's
1.5 device scale and checked using the rendered DOM. These are responsive-layout
checks, not proof of 125%/200% browser zoom or an actual phone keyboard.

Screenshots were captured and inspected in
`D:\RiverGuard\output\v2-repair-2026-10-22`. Overview captures use the viewport
in their filenames. The final desktop capture is `final-desktop-1366x650.png`.
At 320 CSS pixels the station selector occupied approximately 282×44 pixels,
with its own readable row. No horizontal page overflow was observed in the
overview checks. Collapsed navigation retained accessible names.

## Actions and observed outcomes

- Clicked all four chart selectors and all four reading explanations; tested
  close and Escape dismissal, More/Less detail, and Rill open/close.
- Two actual tabs shared the Demo scenario and running state. Changing to Normal
  and resuming in one tab updated the other; pausing there produced Resume in
  both. The frontend did not create a second producer.
- Switched Demo/real sources and real stations. History loaded 100 of 120 saved
  rows using pagination. Opened original raw/calibration evidence and event
  detail. Event measurement time was 20:42:46, with opaque `seed-115` shown
  separately, calibration revision 1 and the captured watch policy.
- A water warning remained visible despite subsequent missing water samples.
  Its final card showed Last known 20:42:46 while the latest sample time was
  20:42:54. This verifies the warning time is not taken from the later fault.
- A three-sample fixture with a missing middle value rendered two isolated
  circles and two independent single-point SVG paths. Inspected and saved
  `isolated-chart-mobile.png`; the gap was not bridged.
- Visited all four setup steps. Used receiver stop/start, second-receiver,
  wiring and tank disclosures. Stale/faulty capture buttons were disabled with
  visible explanations; verification remained blocked. No physical-verification
  checkbox was falsely accepted.
- Edited temperature correction to 0.5, navigated between steps and refreshed:
  the draft survived. Saving returned revision 2 and waiting-for-acknowledgement.
- Found an additional persistent duplicate calibration form when switching
  stations. Fixed duplicate sibling React keys and reloaded the rebuilt bundle.
  Switching from a configured station to `audit-unset` then rendered exactly
  one geometry field group. A new regression covers component identities.
- On `audit-unset`, saved correction 0.25 and refreshed. Correction persisted;
  all three unset geometry inputs stayed empty. Suggested values were not adopted.
- Listed paired browsers, opened Remove access, cancelled with Keep access,
  reopened and confirmed removal of a labelled disposable QA session. Only that
  session disappeared; the current session remained. Confirmation screenshot:
  `revoke-confirmation-mobile.png`.

## Limits and remaining acceptance

- Browser download interception returned `canceled` when exporting CSV. Backend
  export content/snapshot tests pass; a completed browser/native saved file is
  not claimed from this attempt.
- No connected Chrome/Samsung Internet Android browser or physical phone was
  available. Actual APK transfer/install/update, native confirmations/document
  saving, SQLite instrumentation, notifications, screen lock, virtual keyboard,
  background Wi-Fi reconnect and hardware commissioning remain pending.
- Exact 125%/200% zoom and operating-system reduced-motion acceptance remain
  pending. Responsive dimensions do not substitute for those tests.
- API/controller tests cover failed loads, late saves, conflicts and revocation
  authentication; this walkthrough does not reproduce every network race using
  actual paired physical devices.

Do not publish the QA database or its private launcher link with these screenshots.

## Preview 2 colour update

Reviewed the revised palette at 1366�768, 390�844 and 320�568 measured CSS
viewports. No horizontal overflow at 320px. Cloudiness and temperature selected
labels, lines and legends have matching computed colours; lavender/blue status
panels are distinct, with green/amber/red retained for status. Saved screenshots
are in `D:\RiverGuard\output\v2-run\v2-colour-desktop.png` and
`v2-colour-mobile.png`. The user's normal browser viewport was restored.


## 23 October 2026: colour and warning readability follow-up

The browser-control and Windows-control tool kernels both failed to initialise
(path-not-found). Used installed Chrome through Playwright headless with the real
built frontend and backend, a new isolated database and test-only bootstrap
session. The user's database and Demo scenario were not changed. This is browser
rendering evidence, not a physical-phone acceptance claim.

Inspected normal, changed-quality/watch and high-water warning screenshots at
1366x650, 1280x720, 1024x768, 390x844 and 320x568. All 15 renders have no horizontal
page overflow. Checked all four chart selectors, Rill opening/Escape dismissal,
visible 2px keyboard focus and reduced-motion rendering. Advancing the browser
clock and reloading retained explicitly labelled last-known warnings.

Found and repaired subtle warning borders, category artwork competing with
warning colours, small supporting copy and a fragmented 320px station name.
Watch/Warning labels now include an icon; warning artwork is hidden. Warning
signals sort before lower-priority signals in the three-item summary without
mutating evaluation data. The next-check panel inherits the warning emphasis.
Supporting warning copy is 14px, timestamps 12px, and narrow navigation labels
11px. The 320px header gives source controls their own row.

Sampled actual rendered backgrounds at three horizontal positions per warning
text element with foreground text hidden. Minimum sampled contrast was 6.05:1
across category labels, severity labels, headings, body copy, timestamps and next
check instructions. This is a targeted contrast check, not an all-page WCAG
certification.

Evidence: local output/colour-check screenshots, results.json (15 renders),
contrast.json and keyboard.json. Do not publish the test database.
Frontend build and all 31 tests pass, including warning-summary priority and
non-colour warning labelling. Updated compiled assets are served locally on 8510;
this follow-up does not replace the already published Preview 2 APK/ZIP.


## Preview 4: built-in setup guide

Used the actual built frontend/backend with an isolated station/database at 8514.
All guide topics expand in Connect, Check signals, Calibrate and Verify. Checked
1366x768, 390x844 and 320x568: 12 stage/viewport checks, no horizontal overflow;
screenshots inspected. Native details controls support keyboard Space expansion.
Synthetic Wi-Fi name/password remain intact when opening/closing the guide and
across monitoring refreshes. The loaded guide expands while offline without a
PDF viewer or external fetch. Phone-specific text/port is covered by component
tests; actual Android-device testing is still pending. Evidence remains local
in output/setup-guide-check; do not publish its database.
