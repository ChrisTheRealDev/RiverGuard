# RiverGuard V2 product brief

Status: requirements agreed; separate implementation in progress. No replacement
application or migration is active yet.

## Purpose

Help an ordinary river monitor quickly understand the observed water condition,
recognize a possible water-quality or rising-water issue, and know what to check
next. Support both the web/laptop app and standalone Android.

## Confirmed requirements

- Give water-quality signals and rising water equal prominence.
- Start with one station while leaving room for multiple stations later.
- Put a plain-language condition, the main reason, freshness and next action
  above technical sensor values. Reveal detailed graphs, tables, units, raw
  readings, calibration and diagnostics further down or on dedicated screens.
- Use more glass effects with readable graphs and tables. Maintain contrast,
  touch targets and usable spacing; motion must respect reduced-motion settings.
- Android must support explicitly enabled background monitoring and
  notifications while the screen is locked. Implementation and acceptance must
  distinguish background execution from a user force-stopping the application.
- Preserve the existing app, releases, stored data and source. Develop the new
  product separately under v2/ on branch v2/rebuild. The baseline is commit
  abec0bf24a9f91c8571196758be188b0cca4970c, including the standalone Android preview.
- Android monitoring must remain usable without a laptop or an AI model.

## Information hierarchy

1. Which station and source are being viewed; synthetic data is explicit.
2. What is happening: water-quality condition and water-level condition.
3. Why that condition is shown, how fresh the evidence is, and what to check.
4. A readable visual trend and recent actionable events.
5. Individual measurements, historical tables, exports and sensor diagnostics.

Use statements such as "No issues detected in available readings", "Needs
attention", and "Readings unavailable". A normal sensor range must not certify
drinking, swimming or overall water safety. Missing, stale or uncalibrated data
must remain visible alongside any known water-level warning.

## Final discovery decisions

- Separate local histories are acceptable; automatic history synchronization is
  outside the first V2 release.
- Visual direction: calm river observatory, deep teal, soft glass and space.
- Rill is an optional reading guide. Core monitoring works without AI.
- Both phone and laptop must receive the same station's real readings at once.
- Staying on the station's private Wi-Fi is sufficient. Off-site remote alerts
  are outside this release.
- Background service behavior, battery controls and real-phone acceptance remain
  implementation/verification concerns rather than unresolved product choices.

## Rebuild approach

Plan one shared monitoring domain and presentation system with explicit web and
Android adapters, rather than maintaining divergent safety/status rules. Select
the transport and storage architecture after the synchronization decision.
Preserve raw readings, calibration snapshots and their provenance. Do not migrate
or overwrite existing databases during discovery or UI prototyping.

Android collection and alert evaluation must run independently of the interface,
in a user-started native foreground service with visible monitoring status.
Validate the appropriate service type against Android's current requirements.
Distinguish active collection, permission-blocked alerts and disconnected Wi-Fi.
Do not promise operation after an explicit user stop or force-stop.

If histories synchronize, choose one station authority for calibration and alert
settings. Replicate immutable evidence with stable identities and resumable
cursors; do not merge live database files. Configuration edits require expected
revision checks. Consider a separate Android application ID for development
previews so the existing and new applications can be installed together.

## Acceptance direction

Inspect actual desktop and phone screenshots and interactions. Verify readable
status, gaps/stale states, calibration boundaries, background notification
deduplication, refresh/draft stability, keyboard operation and narrow-screen
layouts. Background collection and notifications require a physical Android
device test, including lock-screen operation and documented OS limitations.
