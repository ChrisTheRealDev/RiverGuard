#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Preferences.h>
#include <esp_system.h>
#include <time.h>
#include <sys/time.h>
#if __has_include("../include/station_config.h")
#include "../include/station_config.h"
#else
#include "../include/station_config.example.h"
#endif

OneWire oneWire(TEMP_PIN);
DallasTemperature thermometer(&oneWire);
Preferences preferences;
JsonDocument remote;
String pending,bootId;
unsigned long counter=0,nextAttempt=0,retryMs=2000,lastWifiRetry=0;
bool temperatureStarted=false,levelStarted=false;
bool enabled(const char* key) { return remote["enabled"][key] | false; }
void number(JsonObject obj,const char* key,float value) { if(isfinite(value)) obj[key]=value; else obj[key]=nullptr; }
void useReceiverClockIfUnset(JsonDocument& candidate) {
  // Prefer an existing NTP/RTC clock. Only a fresh, accepted configuration
  // response may bootstrap time; never reuse the cached NVS response's date.
  if(time(nullptr)>=1700000000 || !candidate["server_epoch_seconds"].is<double>()) return;
  double epoch=candidate["server_epoch_seconds"].as<double>();
  if(!isfinite(epoch) || epoch<1704067200.0 || epoch>=4102444800.0) return; // 2024..2099 UTC.
  if(sizeof(time_t)<8 && epoch>2147483647.0) return; // Older ESP32 time_t must not overflow.
  struct timeval receiverTime={};receiverTime.tv_sec=static_cast<time_t>(epoch);
  if(settimeofday(&receiverTime,nullptr)==0) Serial.println("Clock set from receiver; keep the phone clock correct.");
}
void pollConfiguration() {
  String url(API_URL); int path=url.indexOf("/api/v1/readings");
  if(path<0) return;
  url=url.substring(0,path)+"/api/v1/device-config?device_id="+DEVICE_ID;
  HTTPClient http; http.begin(url); http.setConnectTimeout(1000); http.setTimeout(1500);
  http.addHeader("Authorization",String("Bearer ")+API_TOKEN);
  if(http.GET()==200 && http.getSize()<=2048) {
    String body=http.getString(); JsonDocument candidate;
    if(!deserializeJson(candidate,body) && candidate["protocol"]=="remote-v1" && candidate["device_id"]==DEVICE_ID && candidate["revision"].is<unsigned long>()) {
      bool valid=true;
      for(const char* key:{"ph","turbidity","temperature","water_level"}) if(!candidate["enabled"][key].is<bool>()) valid=false;
      if(valid) useReceiverClockIfUnset(candidate);
      if(valid && (remote.isNull() || remote["revision"]!=candidate["revision"])) {
        remote=candidate;
        // Only write on a revision change; never on each sample.
        preferences.putString("config",body);
        Serial.printf("Station settings applied: revision %lu\n",remote["revision"].as<unsigned long>());
      }
    }
  }
  http.end();
}
struct AnalogSample { float adc,mv; bool valid; };
AnalogSample analogSample(int pin) {
  unsigned long adc=0,mv=0;
  for(int i=0;i<16;i++) { adc+=analogRead(pin); mv+=analogReadMilliVolts(pin); delay(2); }
  float raw=adc/16.0f,voltage=mv/16.0f;
  return {raw,voltage,raw>5&&raw<4090&&voltage>=150&&voltage<=3050};
}
void collect() {
  time_t now=time(nullptr);
  if(now<1700000000) { Serial.println("Waiting for NTP or receiver clock"); return; }
  JsonDocument doc;
  doc["device_id"]=DEVICE_ID;doc["mode"]="hardware";
  doc["setup_protocol"]="remote-v1";doc["config_revision"]=remote["revision"] | 0;
  doc["sample_id"]=bootId+"-"+String(counter++);
  char stamp[25];struct tm utc;gmtime_r(&now,&utc);
  strftime(stamp,sizeof(stamp),"%Y-%m-%dT%H:%M:%SZ",&utc);doc["timestamp"]=stamp;
  JsonObject raw=doc["raw"].to<JsonObject>(),health=doc["sensor_health"].to<JsonObject>();
  for(const char* key:{"ph","turbidity","temperature","water_level"}) health[key]=enabled(key)?"uncalibrated":"disabled";
  if(enabled("ph")) {
    AnalogSample a=analogSample(PH_PIN);raw["ph_adc"]=(int)roundf(a.adc);raw["ph_mv"]=a.mv;
    if(!a.valid) health["ph"]="adc_limit";
  }
  if(enabled("turbidity")) {
    AnalogSample a=analogSample(TURBIDITY_PIN);raw["turbidity_adc"]=(int)roundf(a.adc);raw["turbidity_mv"]=a.mv;
    if(!a.valid) health["turbidity"]="adc_limit";
  }
  if(enabled("temperature")) {
    if(!temperatureStarted) { thermometer.begin();thermometer.setResolution(12);thermometer.setWaitForConversion(true);temperatureStarted=true; }
    thermometer.requestTemperatures();float temp=thermometer.getTempCByIndex(0);
    if(temp==DEVICE_DISCONNECTED_C||temp<-55||temp>125) temp=NAN;
    number(raw,"temperature_c",temp);health["temperature"]=isfinite(temp)?"ok":"missing";
  }
  if(enabled("water_level")) {
    if(!levelStarted) { pinMode(TRIG_PIN,OUTPUT);digitalWrite(TRIG_PIN,LOW);pinMode(ECHO_PIN,INPUT);levelStarted=true; }
    digitalWrite(TRIG_PIN,LOW);delayMicroseconds(3);digitalWrite(TRIG_PIN,HIGH);delayMicroseconds(12);digitalWrite(TRIG_PIN,LOW);
    unsigned long pulse=pulseIn(ECHO_PIN,HIGH,45000);
    number(raw,"distance_cm",pulse?pulse*0.0343f/2.0f:NAN);
    if(!pulse) health["water_level"]="timeout";
  }
  // Raw signals only. The receiver applies the exact acknowledged calibration revision.
  doc["calibrated"]=false;doc["tds_ppm"]=nullptr;
  serializeJson(doc,pending);Serial.println(pending);
}
void setup() {
  Serial.begin(115200);analogReadResolution(12);analogSetAttenuation(ADC_11db);
  preferences.begin("riverguard",false);
  String saved=preferences.getString("config","");
  if(saved.length()) { if(deserializeJson(remote,saved)||remote["device_id"]!=DEVICE_ID) remote.clear(); }
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,NTP_SERVER);
  bootId=String((uint32_t)(ESP.getEfuseMac()>>32),HEX)+String((uint32_t)ESP.getEfuseMac(),HEX)+"-"+String(esp_random(),HEX);
}
void loop() {
  if((long)(millis()-nextAttempt)<0) { delay(20);return; }
  nextAttempt=millis()+SAMPLE_INTERVAL_MS;
  if(WiFi.status()!=WL_CONNECTED) {
    if(millis()-lastWifiRetry>15000) { WiFi.reconnect();lastWifiRetry=millis(); }
    Serial.println("Waiting for Wi-Fi");return;
  }
  pollConfiguration();
  if(pending.isEmpty()) collect();
  if(pending.isEmpty()) return;
  HTTPClient http;http.begin(API_URL);http.setConnectTimeout(3000);http.setTimeout(5000);
  http.addHeader("Authorization",String("Bearer ")+API_TOKEN);
  http.addHeader("Content-Type","application/json");int code=http.POST(pending);
  Serial.printf("Receiver status: %d\n",code);
  if(code>=200&&code<300) { pending="";retryMs=2000; }
  else if(code==401||code==403) { Serial.println("Station credential rejected. Generate a private configuration in Sensor setup and upload it.");pending="";nextAttempt=millis()+30000; }
  else if(code==422) { Serial.println("Measurement rejected. Check sensor ranges and NTP clock.");configTime(0,0,NTP_SERVER);pending=""; }
  else if(code>=400&&code<500&&code!=408&&code!=429) { Serial.println(http.getString());pending=""; }
  else { nextAttempt=millis()+retryMs;retryMs=min(retryMs*2,30000UL); }
  http.end();
}
