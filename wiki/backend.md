# How a sample becomes evidence

[Home](Home.md) · [Architecture](architecture.md) · Next: [Frontend](frontend.md)

Start with an analog voltage. It is evidence that an electrical signal was observed. It is not yet pH or NTU. RiverGuard preserves both the signal and the interpreted measurement so that a useful-looking number never erases the assumptions behind it.

## Receive, validate, calibrate, store

[api.py](../api.py), `Reading` at line 31, defines the accepted packet. It rejects non-finite values, unsupported fields and measurements more than five seconds ahead of the laptop. Missing probes can remain missing. A made-up zero would become a real data point in every downstream chart and calculation.

`ingest()` at line 102 checks that the authenticated station matches the payload, calls [station_setup.py](../station_setup.py)'s `calibrate()` at line 74, then calls [core.py](../core.py)'s `save()` at line 140. For managed `remote-v1` packets, calibration uses the packet's acknowledged configuration revision. Unknown revisions produce a conflict so the station can resynchronize.

For example, two measured buffer voltages define a pH interpolation. A voltage outside that calibrated span stays unavailable instead of being extrapolated into a plausible number. The stored row retains raw JSON, sensor health, computed values and calibration identity. Historical measurements are not rewritten when today's calibration changes.

`save()` records UTC measurement and receipt times and uses a unique source/station/sample-ID index. Retrying the same identified packet does not create another sample. Legacy packets without an ID do not get that deduplication guarantee.

## There are two different kinds of checks

`core.assess()` at line 133 uses an Isolation Forest trained on 1,500 synthetic normal samples. Its inputs are pH, cloudiness and temperature. Water level is handled separately. When the model flags a sample, the explanation names the largest standardized deviations from the synthetic baseline. Those deviations help someone inspect the result; they are not a causal explanation of the model or proof of pollution.

[river_status.py](../river_status.py), `evaluate_measurement()` at line 130, combines available readings, reference comparisons, freshness, calibration status and water-level checks. This deterministic policy is shared by the overview, historical signals and Rill's captured interpretation.

The order of the policy matters. A water warning must remain visible even if another probe is missing. An old warning becomes a last-known condition rather than a claim about the present. Historical evaluation ignores wall-clock staleness, but uses current saved watch thresholds. Raw observations are durable; their interpretation can change when those thresholds change.

## A rate needs more than two attractive dots

`observed_rise()` at line 53 fits a slope using recent valid measurements from the current calibration segment. It needs at least five samples spanning eight seconds, within a thirty-second window. It returns centimeters per minute. An absolute height threshold is in centimeters; those quantities cannot be compared directly.

Imagine moving the ultrasonic zero point by 20 cm. Joining samples across that change would look like a sudden physical rise. `calibration_segments()` at line 21 splits the sequence at each revision transition, including a rollback. Charts and rate calculations respect those boundaries.

## Build a consistent picture

[data_service.py](../data_service.py), `overview_data()` at line 224, reads settings and measurements inside one SQLite read transaction. Status, cards and chart therefore describe one database snapshot even if a new packet arrives during the request. [charting.py](../charting.py), `summarize()` at line 19, produces bounded interval averages with minimum/maximum bands and gaps. The line is an aggregate, not every raw sample.

`reading_page()` at line 126 binds pagination to a source, station, time filter and insertion anchor. A cursor from another view is rejected. Complete CSV export uses a database snapshot and retains raw evidence and interpretation settings; dangerous spreadsheet prefixes in text are escaped while numeric measurements remain numeric.

For changes, start with the relevant policy tests: [river status](../tests/test_river_status.py), [data contracts](../tests/test_data_redesign.py), [station setup](../tests/test_station_setup.py) and [charting](../tests/test_charting.py). Test the misleading case first: stale, missing, delayed, duplicated or recalibrated data.
