import {BookOpen,ChevronDown} from 'lucide-react';

const steps=['Connect','Check signals','Calibrate','Verify'];

/** Local instructions: no PDF viewer, external fetch or setup-state writes. */
export default function SetupGuide({step,phone,receiverPort}:{step:number;phone:boolean;receiverPort:number}){
 return <details className="glass setup-guide">
  <summary><BookOpen size={20}/><span><strong>Setup guide</strong><small>{steps[step]} · Instructions available offline</small></span><ChevronDown size={18}/></summary>
  <div className="setup-guide-content">
   <p className="guide-intro">{step!==0?['','Check each connected probe before calibrating it. You can save enabled probes even while waiting for the ESP32.','Have your reference buffers, cloudiness standards, thermometer and ruler ready.','Set the watch marks, then compare the readings with real references. Only record checks you have actually done.'][step]:phone?'Your phone receives and stores the readings directly. No laptop needs to stay running. A computer is needed once to upload the ESP32 firmware.':'This laptop receives and stores the readings. Keep the V2 service running. The Android app can also work on its own, with a separate history and calibration.'}</p>
   <p className="guide-context">Open a topic for help, then use the setup controls below. Your inputs stay here when you switch steps.</p>
   {step===0&&<>
    <details><summary>1. Join Wi-Fi and start the receiver</summary><ol>
     <li>Put the ESP32 and this {phone?'phone':'laptop'} on the same trusted router network. The ESP32 needs 2.4 GHz Wi-Fi. Avoid guest networks that isolate devices.</li>
     <li>Tap <strong>Start monitoring</strong> below if the receiver is off, then wait for <strong>Receiver is running</strong>. Stop the older RiverGuard receiver if it is using the same port.</li>
     {phone&&<li>Tap <strong>Allow notifications</strong> for locked-screen alerts. Check the phone’s actual background behaviour before relying on it.</li>}
     <li>Check <strong>This receiver address</strong>. Use this {phone?'phone':'laptop'}’s private Wi-Fi IPv4 address with <code>http://</code> and port <strong>{receiverPort}</strong>. Example only: <code>http://192.168.1.23:{receiverPort}</code>. Do not use <code>localhost</code> or the dashboard’s browser port.</li>
     <li>If the address is blank, find this device’s IPv4 address in its Wi-Fi/network details and enter it below.</li>
    </ol></details>
    <details><summary>2. Save your private station configuration</summary><ol>
     <li>Choose a <strong>Station ID</strong>, such as <code>riverguard-01</code>, and tap <strong>Create station key</strong>.</li>
     <li>Enter the router’s <strong>Wi-Fi name</strong> and <strong>Wi-Fi password</strong>. Leave <strong>Add a second receiver</strong> empty when using only this device.</li>
     <li>Tap <strong>Save private station_config.h</strong> and save before leaving or refreshing. A newly created key is only held in memory until then.</li>
     <li>{phone?'Transfer the saved file privately to the computer used for flashing.':'Keep the saved file ready for flashing.'} It contains your Wi-Fi password and station credential; do not share it publicly.</li>
    </ol><p className="guide-note"><strong>Already receiving real readings?</strong> Keep the existing key and firmware. Replacing the key invalidates the credential in the ESP32 and requires a new configuration upload. Updating V2 itself does not require replacing the key or uninstalling the app.</p></details>
    <details><summary>3. Check the wiring and tank</summary><p>Power off before changing wires. Open <strong>Build it with care</strong> below for the built-in wiring and tank diagrams.</p><ul>
     <li>Keep boards, connectors and power supplies dry. Leak-test the tank and use a rigid sensor stand.</li>
     <li>The SEN0189 turbidity output and JSN-SR04T ECHO each need their own voltage divider. Never connect 5 V directly to an ESP32 GPIO. Follow the diagram and confirm actual board labels and voltages.</li>
     <li>DS18B20 data needs the pull-up shown in the wiring diagram. Optional TDS is not supported.</li>
     <li>Keep the ultrasonic sensor level and outside its blind zone even at the fullest water height. Mark the physical zero and ruler heights.</li>
    </ul></details>
    <details><summary>4. Upload the ESP32 firmware once</summary><ol>
     <li>On a computer, extract the entire V2 laptop ZIP from your release download. It contains the firmware; you do not need to run the laptop dashboard for a phone-only setup.</li>
     <li>Install Visual Studio Code and the official PlatformIO IDE extension. First-time tool installation needs internet access.</li>
     <li>Open <code>v2/hardware/firmware</code> in VS Code. This is the folder containing <code>platformio.ini</code>. Let PlatformIO finish installing the project tools.</li>
     <li>Copy your saved <code>station_config.h</code> into <code>v2/hardware/firmware/include/</code>, beside the example file. Keep the exact filename, not <code>station_config.h.txt</code>.</li>
     <li>Connect the NodeMCU-32S with a USB <strong>data</strong> cable. In PlatformIO, choose <strong>Project Tasks → nodemcu-32s → General → Upload</strong>. Wait for success, press reset/EN and keep the ESP32 powered.</li>
     <li>Keep monitoring running, select <strong>Real station</strong> in the top menu, then choose <strong>Check signals</strong> above. Later calibration is done here without uploading firmware again.</li>
    </ol><p>Upload will not connect? Try a data cable, check the board’s USB-to-serial driver and use its documented BOOT/reset procedure.</p></details>
    <details><summary>Optional: send to a phone and laptop together</summary><p>Register the same station ID in each app. Each receiver creates its own credential. In <strong>Add a second receiver</strong>, enter the other receiver’s address and key before saving the private configuration. Android uses port <strong>8000</strong>; the laptop’s default sensor port is <strong>8010</strong>. Calibrate and set watch marks in each app independently. Histories are not synchronized.</p></details>
   </>}
   {step===1&&<>
    <ol className="guide-steps"><li>Select <strong>Real station</strong> in the top menu. Demo values are synthetic.</li><li>Enable only the probes actually wired, then tap <strong>Save enabled probes</strong>.</li><li>Wait for <strong>Station acknowledged</strong> and fresh raw signals. Sampling is every 5 seconds; allow about 30 seconds for connection and settings updates.</li><li>Look for changing numeric signals and check each health label. Missing, timeout or out-of-range readings need a connection/range check.</li><li>Calibrated values may still be blank. A responsive raw signal is the first checkpoint, not proof of correct wiring or calibration. Continue to <strong>Calibrate</strong> when the signals are usable.</li></ol>
    <p className="guide-note">Do not enable an absent sensor to make the status look complete. A stale or faulty signal cannot be captured for calibration.</p>
   </>}
   {step===2&&<>
    <details><summary>Acidity: two known pH buffers</summary><p>Use two different known buffers, such as pH 7 and pH 4. Rinse between buffers and let each signal settle. Enter the <strong>Known pH</strong>, then tap <strong>Capture fresh signal</strong> for the matching reference. Do this for both buffers.</p></details>
    <details><summary>Cloudiness: known NTU standards</summary><p>Enter each standard’s <strong>Known NTU</strong> and capture its settled signal. Clear-looking water is not automatically zero NTU. If you lack known standards, leave cloudiness uncalibrated rather than inventing a value.</p></details>
    <details><summary>Water level: measure the installed distances</summary><p>Mark a physical zero height. Enter the sensor-to-zero distance and the installed sensor’s verified minimum and maximum distances. Keep the fullest water surface outside the blind zone. Capture the zero-level distance only when the water is actually at your zero mark.</p><p><strong>Use suggested starting values</strong> fills a draft; those values are not measurements. The usable height is the zero-level distance minus the verified minimum distance.</p></details>
    <details><summary>Temperature and saving</summary><p>Compare with a reference thermometer. Enter only the measured correction: reference temperature minus raw probe temperature (shown in Check signals). This replaces the previous correction; if using the corrected display instead, add the measured difference to the existing correction, within −5 to +5 °C. Tap <strong>Save calibration changes</strong>, then wait for <strong>Station acknowledged</strong>.</p><p>Saved and acknowledged are different: acknowledged means the ESP32 has fetched the saved settings. Historical readings keep their original calibration.</p></details>
    <p className="guide-note">After saving water-level geometry, review the watch marks below. Changing geometry can invalidate previous watch settings and physical verification.</p>
   </>}
   {step===3&&<>
    <ol className="guide-steps"><li>Under <strong>When should water get your attention?</strong>, choose a <strong>Watch height</strong>, a higher <strong>Warning height</strong> and a positive <strong>Rise warning</strong>. Both heights must fit within the usable height shown. For example, a 50 cm zero-level distance and 25 cm minimum distance give 25 cm of usable height; choose marks for your own tank, not these example numbers. Tap <strong>Save watch settings</strong>.</li><li>Compare all four probes with known references: both pH buffers, cloudiness standards, a thermometer and at least two ruler-measured water heights. Check voltage protection and sensor health.</li><li>Only after doing those checks, tick <strong>I physically checked all four enabled and calibrated sensors</strong> and tap <strong>Record physical check</strong>.</li><li>Return to <strong>Your river</strong> with <strong>Real station</strong> selected. Confirm fresh readings and compare the displayed water level with your ruler.</li></ol>
    <p className="guide-note"><strong>Button still disabled?</strong> Verification needs all four enabled/calibrated probes, valid watch marks, fresh usable readings, no unsaved edits and acknowledgement of the saved revision.</p>
    <p>{phone?'Keep the phone powered and on the same Wi-Fi. Check that readings stay fresh after locking/unlocking. Reopen V2 and start monitoring after a reboot or force-stop; battery controls may interrupt collection.':'Keep the Python service running and this laptop on the station’s network. Closing the browser alone does not stop collection.'} Sensor checks cannot certify drinking/swimming safety or predict floods.</p>
   </>}
   <details className="guide-troubleshooting"><summary>Something not working?</summary><dl>
    <dt>No readings after a minute</dt><dd>Check Receiver is running, the Wi-Fi name/password and this receiver’s IP/port. Avoid guest-network isolation and check this device’s date/time. PlatformIO Serial Monitor at 115200 baud can show rejected-credential or sample messages.</dd>
    <dt>Blank values or disabled capture</dt><dd>Enable the probe, save, wait for acknowledgement and inspect the displayed fault/range reason. Usable raw readings still need valid calibration.</dd>
    <dt>Wi-Fi, IP address or station key changed</dt><dd>Save a new private configuration and upload it to the ESP32 again. Do not replace a key merely to reconnect. A stable router address reservation can prevent unexpected IP changes.</dd>
    {phone&&<><dt>No alerts while the screen is locked</dt><dd>Check notification permission and monitoring status. Test the phone’s background/battery behaviour and Wi-Fi connection. Reboot or force-stop requires starting monitoring again.</dd></>}
   </dl></details>
  </div>
 </details>;
}
