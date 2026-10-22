# Build the RiverGuard demonstration tank

This is a supervised indoor bench prototype, based on your supplied physical assembly notes. It is not an outdoor river installation. Finish the dry-table connection test first. Start with a real DS18B20 reading on the laptop before cutting the pole or drilling the electronics enclosure.

## 1. Gather the physical parts

- A ready-made transparent, watertight tank or container with a flat base, a lid/open top suitable for removable sensor hangers, and enough width for the ultrasonic beam. Do not fabricate or drill a glass tank for this first build.
- A rigid, level table, protective tray, ruler, filling jug, towels and a clearly marked maximum fill line.
- PVC pole and cross-arm, suitable fittings, brackets, two spaced clamps, and a stable separate stand or frame. Size the height from the calculation below, not from a guessed pole length.
- A splash-resistant plastic electronics enclosure with correctly sized cable glands, strain relief, ties and a removable probe hanger. The tank must not carry the pole/enclosure's weight.
- The four sensors and their interface boards, the wiring diagram's resistors, USB data cable and verified low-voltage supplies. TDS is not required.

Use your actual board and sensor dimensions to lay out the enclosure first. Have an experienced person handle cutting and drilling, with the electronics removed. Keep mains adapters and the laptop away from spills; only low-voltage leads approach the tank.

## 2. Plan the height before cutting anything

The JSN face points straight down at the water. Confirm the exact JSN revision, trigger/echo mode, beam clearance and operating range from its supplied documentation. Do not assume every JSN has the same 20-25 cm blind zone.

- H = vertical distance from transducer face to your chosen zero-height plane.
- W = highest water height above that zero plane.
- B = verified minimum measurable distance of the actual sensor.
- M = extra mounting/splash margin chosen for the assembly.

Choose **H >= W + B + M**. Also check that the face-to-water distance at the lowest water level stays inside the verified maximum range. Leave space for the beam: walls, a brace or another probe can cause the wrong echo. Test the real geometry before fixing the arm permanently.

Example only: if W is 20 cm, the actual verified B is 25 cm, and you choose 5 cm margin, H must be at least 50 cm above the zero plane. These are not measurements or default settings for your tank. A short tank may need a tall external cross-arm; tank height alone does not provide the required clearance.

## 3. Position the tank and build the stand

1. Leak-test the empty assembly area with the tank on its final flat support, electronics removed. Fill gradually and inspect for leaks, bowing or instability. Respect the container/table load ratings; one litre of water is roughly one kilogram.
2. Empty or lower the water before working around the stand. Fix the pole to its own stable frame or table mount using two spaced clamps and a braced/secured base. Do not attach the full weight to a thin tank rim.
3. Fit a rigid cross-arm above the water. Hold the transducer temporarily at the calculated height and check multiple ruler-measured distances with the app's raw distance signal. Move the arm if the sensor sees walls or brackets instead of water.
4. Secure the final mounts so the sensor cannot fall or twist into the water. Mark the transducer position and chosen zero plane; moving either later requires water-level recalibration.

## 4. Hang the probes and route the cables

1. Use removable hangers to hold the pH electrode and waterproof DS18B20 at repeatable immersion depths allowed by their suppliers. Keep them clear of the bottom, walls and each other. Do not clamp or load a fragile glass electrode tip.
2. Mount SEN0189 so only the permitted sensing section enters the water. Keep its upper body, cable junction and interface board dry unless the actual manufacturer's immersion instructions explicitly permit otherwise. Avoid bubbles and keep optical placement consistent between standards and test water.
3. Keep the JSN transducer above the maximum waterline. Its controller board belongs inside the dry enclosure; the ranging face looks downward, not underwater.
4. Put the ESP32, pH/turbidity interface boards, JSN controller and connections in the enclosure above the fill line and away from the filling path. Make cable entries face downward where practical. Fit glands/strain relief and make drip loops below the entries so water does not run along a cable into the box.
5. Avoid cutting probe cables or leaving the USB/board connections exposed to splashes. A plastic box with an unsealed cable entry is not weatherproof. Photograph the final routing for your team before closing the box.

## 5. Commission in the app, one channel at a time

1. With power disconnected, check the wiring against RiverGuard-Wiring.png. Keep **10k from signal to GPIO junction, 15k from junction to GND**, using separate pairs for turbidity and ECHO. The attached notes' 10k/20k divider reaches about 3.33 V at 5 V and is not used in this build. All grounds must join; 5 V never connects directly to a GPIO or 3V3.
2. Upload remote-v1 once with Wi-Fi, laptop URL and station ID. Start RiverGuard.cmd and open **Sensor setup**. Later enable/calibration changes happen in this page, not by editing firmware.
3. Enable temperature first. Then check pH in certified buffers, turbidity using standards and a consistent optical arrangement, and finally the JSN against known ruler distances. Allow each probe to settle; the capture button does not detect stability automatically.
4. Fill in controlled stages within the marked limit, keeping the water outside the verified blind zone. At the chosen zero-height plane, capture/enter the reference distance. Enter the actual JSN minimum/maximum distances and save. Compare computed water height at two or more measured water levels.
5. Recheck pH, NTU and temperature references after mounting, then save verification. Download station settings, a readings CSV and an observation report. Keep a calibration log and photos. Raw signals and calibration revisions remain separate from computed readings.

For a cloudiness demonstration, a small separate sample of clean water plus a little clean soil can show a relative response; it is not an NTU calibration or proof of pollution. Keep soil away from calibration buffers, rinse probes as instructed, and do not add unknown chemicals, detergent, live fish or real wastewater to this prototype. Keep pH buffers in separate labelled calibration containers rather than dosing the display tank.

## 6. Finish the demonstration

Disconnect low-voltage power before removing probes or changing mounts. Empty the tank safely, clean/store each probe according to its supplier (especially the pH electrode), and dry the enclosure exterior and work area. If water entered electronics, disconnect power and inspect before reuse.

## Check before presenting

- The stand is secure, the rim bears no electronics load, and no sensor can fall in.
- The maximum fill line leaves verified JSN clearance; reference distance matches the final fixed mount.
- Sensor connectors, all interface boards, supplies and laptop stay dry; cables have strain relief and drip loops.
- The app shows current ESP32 packets and an acknowledged settings revision, not synthetic readings or a stale packet.
- Disabled/uncalibrated/faulted channels stay missing; no fake zeros fill gaps.
- The model and reference bands remain experimental, with no claim of drinking/swimming safety, confirmed pollution or validated flood prediction.

The dimensions and immersion depths must come from your actual tank and sensor documentation. The separate PDF gives wiring and calibration steps; the physical arrangement diagram is Tank-Layout.png.
