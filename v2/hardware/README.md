# V2 station firmware

The V2 ESP32 can send the same measurement to the phone and laptop simultaneously.
Each receiver stores its own history and has its own station credential and
calibration. Register the **same device ID** on both installations. Enable the
physical probes in each receiver's setup. Calibrate each receiver independently;
settings and histories are not synchronized and may produce different displayed
values if you choose different calibration points or watch thresholds.

1. Build the tank and wiring using the existing hardware guides in the repository.
   The SEN0189 and JSN-SR04T ECHO need separate voltage dividers. TDS is unsupported.
2. Start Android monitoring and the V2 laptop service on the same private Wi-Fi.
3. Register the station in each app and save both private credentials.
4. Copy firmware/include/station_config.example.h to station_config.h. Put phone
   URL/token in API_URL/API_TOKEN; laptop URL/token in the two SECONDARY macros.
   If using only one receiver, set the secondary URL and token to empty strings.
5. Compile/upload with PlatformIO using the pinned nodemcu-32s environment. This
   initial flash requires programming tools. Later calibration is in each app.
6. Check signals, calibrate with known references, and verify physical measurements
   on both installations. A receiver applies its own exact acknowledged revision.

Each destination has its own network task, bounded HTTP timeout, exponential
retry and small RAM pending queue. A failed destination does not block the other
or stop sampling. Samples share timestamp and sample ID; packet enabled fields
and configuration revision are specific to the receiving installation. Pending
queues are not durable: newly sampled data may be skipped while a destination is
offline, and power loss clears RAM. The app must show stale/gap states honestly.

Use a trusted private network: sensor HTTP is not encrypted. Keep the phone on
that Wi-Fi. User-started Android background monitoring is still subject to OS,
Wi-Fi and battery behavior, and a force-stop ends collection. Do not treat this
as a guaranteed always-on unattended logger. Real hardware checks remain pending.

## Retry deadline regression

The repaired network workers track whether a deadline is scheduled separately from
its timestamp. Zero is a valid timestamp after millis rollover. Compile-time cases
in `firmware/test/test_deadline/test_main.cpp` exercise the production helper around
the signed boundary and rollover; both receivers use that same helper. The firmware
build still needs physical long-running and network-interruption acceptance.
