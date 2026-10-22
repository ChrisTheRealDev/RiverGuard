#pragma once
// One-time configuration. Enable and calibrate sensors in the app.
// Copy to station_config.h and keep private; it is excluded from the share ZIP.
const char* WIFI_SSID = "CONFIGURE_ME";
const char* WIFI_PASSWORD = "CONFIGURE_ME";
const char* API_URL = "http://YOUR_LAPTOP_LAN_IP:8000/api/v1/readings";
const char* DEVICE_ID = "riverguard-01";
// Generate this private station credential in Sensor setup > Connect.
const char* API_TOKEN = "GENERATE_IN_SENSOR_SETUP";
const char* NTP_SERVER = "pool.ntp.org";
constexpr int PH_PIN=34, TURBIDITY_PIN=35, TEMP_PIN=27, TRIG_PIN=5, ECHO_PIN=18;
constexpr unsigned long SAMPLE_INTERVAL_MS=5000;
// remote-v1 starts disabled and polls the app for enabled states.
// Changes to Wi-Fi, URL or pins still require a firmware upload.
