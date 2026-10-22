#pragma once
// Copy to station_config.h. Never commit/share the private copy.
const char* WIFI_SSID = "CONFIGURE_ME";
const char* WIFI_PASSWORD = "CONFIGURE_ME";
const char* DEVICE_ID = "riverguard-01";
const char* API_URL = "http://PHONE_IP:8000/api/v1/readings";
const char* API_TOKEN = "PHONE_STATION_CREDENTIAL";
// Optional second receiver. Register the SAME device ID on the laptop and use
// its own credential. Use the laptop V2 receiver port (8010 by default).
#define RIVERGUARD_SECONDARY_API_URL "http://LAPTOP_IP:8010/api/v1/readings"
#define RIVERGUARD_SECONDARY_API_TOKEN "LAPTOP_STATION_CREDENTIAL"
const char* NTP_SERVER = "pool.ntp.org";
constexpr int PH_PIN=34, TURBIDITY_PIN=35, TEMP_PIN=27, TRIG_PIN=5, ECHO_PIN=18;
constexpr unsigned long SAMPLE_INTERVAL_MS=5000;
