# RiverGuard station setup (remote-v1)

Open **Setup** in the app navigation for the **Connect**, **Check signals**, **Calibrate** and **Verify** steps. The printable walkthrough is **output/pdf/RiverGuard-Friend-Setup.pdf**; the diagram is **hardware/RiverGuard-Wiring.png** (editable SVG beside it).

## One initial upload

1. Run **Setup RiverGuard.cmd** once, then **Start RiverGuard.cmd** on the laptop. Keep the launcher open; it opens an authenticated local browser session. The app is on port 8501 and the sensor receiver on port 8000. Rill needs Ollama, but ingestion and calibration do not.
2. Use `ipconfig` to find the laptop's Wi-Fi IPv4 address. Keep both devices on the same trusted private Wi-Fi. From another device, `http://LAPTOP_IP:8000/health` should report `status: ok`. Check private Windows firewall rules and Wi-Fi client isolation if needed. This public health check does not authorize sensor writes.
3. In **Setup > Connect**, enter an ID such as `riverguard-01` and choose **Register new station**. Enter the 2.4 GHz Wi-Fi name/password and receiver URL, `http://LAPTOP_IP:8000/api/v1/readings`. Choose **Download station_config.h**. Put the downloaded file in **hardware/firmware/include** and verify the GPIO assignments against your board labels. It includes `API_TOKEN`, a private credential bound to this station, as well as the network details. The token is shown once: retain a secure copy and never share this header. Existing stations keep their original private file.
4. Install VS Code with PlatformIO IDE, open **hardware/firmware** and use Build/Upload. Alternatively, with PlatformIO Core CLI already installed, build/upload from the app root:

```
pio run --project-dir hardware/firmware
pio run --project-dir hardware/firmware --target upload
pio device monitor --baud 115200
```

5. Open Serial Monitor at 115200 baud. After NTP sync, a submitted JSON sample should be followed by **Receiver status: 201**. In **Setup > Check signals**, confirm the wiring and voltage protection, then enable Temperature first. Select **Sensors** as the reading source and your station in the top bar to see its readings.

Existing unauthenticated firmware needs this one authenticated upgrade. All channels initially stay disabled. There are no calibration constants in the new firmware configuration. Later enable/calibration changes happen in the app without a reflash. Wi-Fi, URL, pin changes or a replacement `API_TOKEN` require another firmware upload. Private station_config.h is excluded from Git and the share ZIP. The template remains available for experienced users, but its placeholder token cannot authenticate.

Station requests require `Authorization: Bearer API_TOKEN`; each token can submit and poll only its own station. Browser sessions have separate permissions. HTTP 401/403 means the token is missing, mismatched or revoked: check the matching private configuration before reconnecting. NTP time is required; packets more than five seconds ahead are rejected. No board has been flashed or physically tested by this project.

## Use a trusted phone

On the authenticated laptop, open **Settings > Create pairing code**. On a phone connected to the same private Wi-Fi, open **http://LAPTOP_IP:8501** and enter the eight-digit code within five minutes. The code is single use. Pairing grants full app access, including calibration and shared chats; pair only trusted devices. Remove a browser's access from **Settings > Paired devices**. Pairing does not encrypt HTTP Wi-Fi traffic. Keep both ports on the trusted private network and do not expose them to the internet.

## App workflow

1. In Setup > Connect, register a new station before uploading, or open the exact ID of an existing station.
2. Check the wiring and voltage protection, then enable each installed probe. Save enabled sensors. The station polls on its next sample/retry cycle; the page shows saved revision versus the revision acknowledged by a received packet. Offline stations stay pending.
3. Check the live raw signals and sensor health. An analog voltage alone cannot prove that a probe is physically connected.
4. For pH, use two certified buffers spanning the intended readings. Confirm the probe has settled; capture each signal or enter measured ADC-pin mV, enter buffer pH and Save pH calibration. No extrapolation or automatic temperature compensation is used.
5. For cloudiness, use 2-5 certified NTU standards. Capture or enter matching ADC-pin mV and NTU values. The app sorts pairs by mV and uses piecewise interpolation only inside the measured span. Arbitrary tap/muddy water is not a known NTU standard.
6. For temperature, compare the DS18B20 with a reference thermometer at equilibrium. Capture the raw temperature and enter the reference; save an offset up to +/-5 C. Investigate larger differences. Original temperature stays in raw data.
7. For water level, verify the JSN revision and its trigger/echo mode and distance limits. Capture distance at the chosen zero-height plane, enter the verified minimum and maximum, then save. Height = reference distance minus measured distance. Blind-zone echoes, timeouts and negative heights stay missing.
8. Physically verify all four enabled and calibrated channels, then Save verification. Any settings change clears verification. Download saved settings for your records. A partial station remains provisional.

Captures reject stale or known-faulted signals and require measurement/receipt age between -5 and 30 seconds. A capture is one live sample, not automatic stability detection; wait for the reference to settle. Live signals update without resetting calibration drafts. Manual calibration entry remains available while a station is offline; it is explicitly pending, not proof of application. Saves use revisions to reject edits based on outdated settings.

## Wiring essentials

| Sensor | Signal GPIO | Power / required protection |
|---|---|---|
| SEN0161-V2 | A to 34 | Verified V2: 3V3 supply; specified output 0-3.0 V |
| SEN0189 | A through divider to 35 | Regulated 5 V; analog mode |
| DS18B20 | DQ to 27 | 3V3 external power; 4.7k ohm from DQ to 3V3 |
| JSN-SR04T | TRIG 5 / ECHO through divider to 18 | Verify exact revision, supply and 3.3 V trigger compatibility; GPIO5 is a boot strap |

For each of the two dividers: sensor signal -> 10k ohm -> GPIO junction -> 15k ohm -> GND. Nominal 5 V becomes 3.0 V; 4.5 V becomes 2.7 V. Use 1% resistors, verify the protected voltage before connecting GPIO, and join all grounds. Never connect 5 V directly to a GPIO or 3V3. With ESP32 USB power, use a separate regulated 5 V sensor rail without tying it into the board 5V/VIN pin; USB-C board power protection is unconfirmed. Confirm DS18B20 wire functions instead of assuming colours. See the diagram and PDF for meter checks and the full power plan.

## Persistence and data contract

Station enable states and revision are cached using ESP32 Preferences; NVS writes occur only when the revision changes. The receiver persists complete calibration revisions in its SQLite database. Settings use compare-and-swap to reject stale browser saves. Back up the database to retain calibration history; calibration is not stored in a shared source ZIP.

Authenticated GET /api/v1/device-config?device_id=riverguard-01 supplies the protocol, enabled states and revision for that token's station. Configuration changes go through the authenticated app; sensor credentials do not grant browser/admin access. Managed packets include setup_protocol=remote-v1, config_revision, timestamp, unique sample_id, raw signals and sensor_health. The receiver applies the exact historical revision acknowledged in that packet, then stores raw signals, computed values, revision and calibration ID (app-rN) separately. A queued old packet never picks up today's calibration, and retries do not duplicate samples. Historical readings are not rewritten. Unknown revisions return 409 so the station resynchronizes. Legacy payloads still require a station token; faulted values are excluded from derived readings and retained as reported raw evidence.

The firmware holds one pending packet in RAM; it is not a durable offline queue, and power loss can lose that packet. New samples pause during HTTP retries. Measurement age remains separate from receipt age; delayed arrivals do not replace newer measurements as current conditions. Graphs and rise calculations break at calibration changes. History & reports exports every station reading, preserving raw fields, calibration IDs and the threshold revision used for interpretation. Historical alerts are evaluated under the current saved station thresholds. TDS stays excluded pending a confirmed sensor model. Anomaly detection remains trained on synthetic data; these readings do not establish pollution, water safety, official WQI or validated flood predictions.

## References

- https://wiki.dfrobot.com/sen0161-v2/
- https://wiki.dfrobot.com/sen0189
- https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html
- https://docs.espressif.com/projects/arduino-esp32/en/latest/api/preferences.html
- https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf
