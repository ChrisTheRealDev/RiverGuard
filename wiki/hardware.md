# A physical reference gives a signal meaning

[Home](Home.md) · [Rill](rill-ai.md) · Next: [Decisions](decisions.md)

A sensor value is only as useful as its reference. A voltage needs a calibration standard; an ultrasonic distance needs a chosen zero-height plane; a timestamp needs a synchronized clock. RiverGuard keeps these assumptions visible instead of hiding them inside the firmware.

The full procedure and wiring requirements live in [hardware/README.md](../hardware/README.md), [Tank Assembly](../hardware/Tank-Assembly.md) and the [wiring diagram](../hardware/RiverGuard-Wiring.png). Follow those documents for physical work. This page explains how the station and software fit together.

## One initial upload, then revisioned settings

Setup walks through Connect, Check signals, Calibrate and Verify. Registration creates a station-specific credential. The downloaded private `station_config.h` contains that credential, Wi-Fi details, receiver URL and pin assignments. It belongs in the firmware project's private include directory and must not be shared with a source package.

After the initial upload, the ESP32 retrieves enabled channels and a revision from the receiver. The laptop stores the complete calibration for every revision. The packet acknowledges its revision and carries raw signals, health information and a stable sample ID. The receiver applies that historical revision to the original sample.

Saving settings is therefore not the same as the station applying them. The UI shows saved and acknowledged revisions separately. An offline station remains pending. Editing sensor settings clears verification; a browser click cannot replace checking the physical installation.

## Four measurements, four assumptions

For pH, measured signals from known buffers establish the calibration span. For cloudiness, certified NTU standards establish interpolation points; arbitrary clear and muddy water do not provide known NTU values. For temperature, a reference thermometer establishes an offset. For water level, the measured zero-plane distance and usable sensor range establish the conversion from distance to height.

[station_setup.py](../station_setup.py), `calibrate()` at line 74, enforces these mappings on the laptop. `capture()` at line 111 refuses stale or faulted raw signals. A capture records a sample; it does not decide that the probe has settled in its reference solution.

If a probe times out, is disabled or lies outside its usable range, its derived measurement stays unavailable. The other channels can still provide evidence. Replacing missing data with zero would introduce a false physical observation.

## Network recovery has a limit

The firmware keeps one pending packet in RAM and retries with the same sample ID. New sampling pauses during retries. The backend deduplicates the identified sample, but power loss can lose that pending packet. This is not a durable offline logger.

A newly received packet may still be an old measurement. Receipt age indicates connection activity; measurement age indicates how recently the river was observed. NTP synchronization and the receiver's future-time check keep that distinction meaningful.

## What software checks cannot establish

Automated tests can verify that revision 4 uses revision 4's calibration. They cannot establish that the voltage divider was built correctly, the sensor model matches the purchased board, the reference solution is valid or the installation is stable. The hardware guide records those acceptance requirements and the current lack of physical board validation.

Read the guide's voltage protection and power plan before connecting parts. TDS remains outside the supported contract until its sensor model is confirmed. Keep physical acceptance evidence separate from browser screenshots and passing tests.
