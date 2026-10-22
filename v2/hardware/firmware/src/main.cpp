#include <Arduino.h>
#include "retry_deadline.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Preferences.h>
#include <esp_system.h>
#include <time.h>
#include <sys/time.h>
#include <mbedtls/sha256.h>
#if __has_include("../include/station_config.h")
#include "../include/station_config.h"
#else
#include "../include/station_config.example.h"
#endif
#ifndef RIVERGUARD_SECONDARY_API_URL
#define RIVERGUARD_SECONDARY_API_URL ""
#endif
#ifndef RIVERGUARD_SECONDARY_API_TOKEN
#define RIVERGUARD_SECONDARY_API_TOKEN ""
#endif

// Each network worker owns its HTTP requests and pending packet. A disconnected
// receiver cannot block the other worker or the sensor sampling loop.
struct Packet { String body; };
struct Destination {
  const char* url;
  const char* token;
  const char* cacheKey;
  JsonDocument config;
  QueueHandle_t queue=nullptr;
  bool configured=false;
  Destination(const char* endpoint,const char* credential,const char* key):url(endpoint),token(credential),cacheKey(key) {}
};
Destination destinations[2] = {
  {API_URL,API_TOKEN,"primary"},
  {RIVERGUARD_SECONDARY_API_URL,RIVERGUARD_SECONDARY_API_TOKEN,"secondary"}
};
const char* fields[]={"ph","turbidity","temperature","water_level"};
SemaphoreHandle_t settingsMutex;
Preferences preferences;
OneWire oneWire(TEMP_PIN);
DallasTemperature thermometer(&oneWire);
String bootId;
unsigned long sampleCounter=0,nextSample=0,lastWifiRetry=0;
bool temperatureStarted=false,levelStarted=false;

String cacheIdentity(const Destination& destination) {
  String identity=String(DEVICE_ID)+"\n"+destination.url+"\n"+destination.token;
  unsigned char digest[32];mbedtls_sha256_ret((const unsigned char*)identity.c_str(),identity.length(),digest,0);
  char hex[65];for(int i=0;i<32;i++)snprintf(hex+i*2,3,"%02x",digest[i]);
  return String(hex);
}

void number(JsonObject object,const char* key,float value) {
  if(isfinite(value))object[key]=value;else object[key]=nullptr;
}
bool validConfig(JsonDocument& config) {
  if(config["protocol"]!="remote-v1"||config["device_id"]!=DEVICE_ID||
     !config["revision"].is<unsigned long>()) return false;
  for(const char* field:fields)if(!config["enabled"][field].is<bool>())return false;
  return true;
}
void bootstrapClock(JsonDocument& config) {
  // Only fresh authenticated configuration can supply a clock, never NVS cache.
  if(time(nullptr)>=1700000000||!config["server_epoch_seconds"].is<double>())return;
  double epoch=config["server_epoch_seconds"].as<double>();
  if(!isfinite(epoch)||epoch<1704067200.0||epoch>=4102444800.0)return;
  if(sizeof(time_t)<8&&epoch>2147483647.0)return;
  timeval value={};value.tv_sec=static_cast<time_t>(epoch);
  settimeofday(&value,nullptr);
}
void pollConfiguration(Destination& destination) {
  String url(destination.url);int path=url.indexOf("/api/v1/readings");
  if(path<0)return;
  url=url.substring(0,path)+"/api/v1/device-config?device_id="+DEVICE_ID;
  HTTPClient http;
  http.setConnectTimeout(1000);http.setTimeout(1500);
  if(!http.begin(url))return;
  http.addHeader("Authorization",String("Bearer ")+destination.token);
  int status=http.GET();int length=http.getSize();
  if(status==200&&length>=0&&length<=3072) {
    String body=http.getString();JsonDocument candidate;
    if(body.length()<=3072&&!deserializeJson(candidate,body)&&validConfig(candidate)) {
      bootstrapClock(candidate);
      xSemaphoreTake(settingsMutex,portMAX_DELAY);
      bool changed=destination.config.isNull()||destination.config["revision"]!=candidate["revision"]||
        destination.config["cache_identity"].as<String>()!=cacheIdentity(destination);
      for(const char* field:fields)if(destination.config["enabled"][field]!=candidate["enabled"][field])changed=true;
      if(changed) {
        candidate.remove("server_time");candidate.remove("server_epoch_seconds");
        candidate["cache_identity"]=cacheIdentity(destination);
        destination.config.set(candidate);
        // Identity and configuration are committed in one NVS value. A reboot
        // cannot associate an old configuration with a newly entered receiver.
        String saved;serializeJson(candidate,saved);
        preferences.putString(destination.cacheKey,saved);
      }
      xSemaphoreGive(settingsMutex);
    }
  }
  http.end();
}
void networkWorker(void* value) {
  Destination& destination=*static_cast<Destination*>(value);
  Packet* pending=nullptr;
  unsigned long nextPost=0,nextConfig=0,retryMs=2000;
  bool postScheduled=false,configScheduled=false;
  while(true) {
    if(WiFi.status()!=WL_CONNECTED){vTaskDelay(pdMS_TO_TICKS(250));continue;}
    unsigned long now=millis();
    if(deadlineReady(configScheduled,now,nextConfig)) {
      pollConfiguration(destination);nextConfig=millis()+10000;configScheduled=true;
    }
    if(!pending)xQueueReceive(destination.queue,&pending,0);
    if(!pending||!deadlineReady(postScheduled,millis(),nextPost)){vTaskDelay(pdMS_TO_TICKS(50));continue;}
    HTTPClient http;http.setConnectTimeout(1500);http.setTimeout(2500);
    int status=-1;
    if(http.begin(destination.url)) {
      http.addHeader("Authorization",String("Bearer ")+destination.token);
      http.addHeader("Content-Type","application/json");status=http.POST(pending->body);
    }
    http.end();
    if(status>=200&&status<300) {
      delete pending;pending=nullptr;retryMs=2000;postScheduled=false;
    }else if(status==401||status==403) {
      Serial.printf("%s credential rejected; check that receiver's private setup.\n",destination.cacheKey);
      delete pending;pending=nullptr;nextPost=millis()+30000;postScheduled=true;
    }else if(status>=400&&status<500&&status!=408&&status!=429) {
      Serial.printf("%s rejected one sample (%d); check time, revision and sensor health.\n",destination.cacheKey,status);
      delete pending;pending=nullptr;nextPost=millis()+2000;postScheduled=true;
    }else {
      nextPost=millis()+retryMs;postScheduled=true;retryMs=min(retryMs*2,30000UL);
    }
  }
}
struct AnalogSample {float adc,mv;bool valid;};
AnalogSample analogSample(int pin) {
  unsigned long adc=0,mv=0;
  for(int i=0;i<16;i++){adc+=analogRead(pin);mv+=analogReadMilliVolts(pin);delay(2);}
  float raw=adc/16.0f,voltage=mv/16.0f;
  return {raw,voltage,raw>5&&raw<4090&&voltage>=150&&voltage<=3050};
}
void collect() {
  time_t measured=time(nullptr);if(measured<1700000000)return;
  JsonDocument snapshots[2];bool active[4]={false,false,false,false};
  xSemaphoreTake(settingsMutex,portMAX_DELAY);
  for(int i=0;i<2;i++)if(destinations[i].configured&&!destinations[i].config.isNull()) {
    snapshots[i].set(destinations[i].config);
    for(int f=0;f<4;f++)active[f]=active[f]||(snapshots[i]["enabled"][fields[f]]|false);
  }
  xSemaphoreGive(settingsMutex);
  JsonDocument sample;
  sample["device_id"]=DEVICE_ID;sample["mode"]="hardware";
  sample["setup_protocol"]="remote-v1";
  sample["sample_id"]=bootId+"-"+String(sampleCounter++);
  char stamp[25];tm utc;gmtime_r(&measured,&utc);
  strftime(stamp,sizeof(stamp),"%Y-%m-%dT%H:%M:%SZ",&utc);sample["timestamp"]=stamp;
  JsonObject raw=sample["raw"].to<JsonObject>(),health=sample["sensor_health"].to<JsonObject>();
  for(int f=0;f<4;f++)health[fields[f]]=active[f]?"uncalibrated":"disabled";
  if(active[0]) {
    AnalogSample value=analogSample(PH_PIN);raw["ph_adc"]=(int)roundf(value.adc);raw["ph_mv"]=value.mv;
    if(!value.valid)health["ph"]="adc_limit";
  }
  if(active[1]) {
    AnalogSample value=analogSample(TURBIDITY_PIN);raw["turbidity_adc"]=(int)roundf(value.adc);raw["turbidity_mv"]=value.mv;
    if(!value.valid)health["turbidity"]="adc_limit";
  }
  if(active[2]) {
    if(!temperatureStarted){thermometer.begin();thermometer.setResolution(12);thermometer.setWaitForConversion(true);temperatureStarted=true;}
    thermometer.requestTemperatures();float value=thermometer.getTempCByIndex(0);
    if(value==DEVICE_DISCONNECTED_C||value<-55||value>125)value=NAN;
    number(raw,"temperature_c",value);health["temperature"]=isfinite(value)?"ok":"missing";
  }
  if(active[3]) {
    if(!levelStarted){pinMode(TRIG_PIN,OUTPUT);digitalWrite(TRIG_PIN,LOW);pinMode(ECHO_PIN,INPUT);levelStarted=true;}
    digitalWrite(TRIG_PIN,LOW);delayMicroseconds(3);digitalWrite(TRIG_PIN,HIGH);delayMicroseconds(12);digitalWrite(TRIG_PIN,LOW);
    unsigned long pulse=pulseIn(ECHO_PIN,HIGH,45000);
    number(raw,"distance_cm",pulse?pulse*0.0343f/2.0f:NAN);if(!pulse)health["water_level"]="timeout";
  }
  sample["calibrated"]=false;sample["tds_ppm"]=nullptr;
  for(int i=0;i<2;i++) {
    if(snapshots[i].isNull())continue;
    JsonDocument target;target.set(sample);target["config_revision"]=snapshots[i]["revision"];
    JsonObject targetRaw=target["raw"].as<JsonObject>();
    for(const char* field:fields)if(!(snapshots[i]["enabled"][field]|false)) {
      target["sensor_health"][field]="disabled";
      if(String(field)=="ph"){targetRaw.remove("ph_mv");targetRaw.remove("ph_adc");}
      else if(String(field)=="turbidity"){targetRaw.remove("turbidity_mv");targetRaw.remove("turbidity_adc");}
      else if(String(field)=="temperature")targetRaw.remove("temperature_c");
      else targetRaw.remove("distance_cm");
    }
    Packet* packet=new Packet;serializeJson(target,packet->body);
    if(xQueueSend(destinations[i].queue,&packet,0)!=pdTRUE) {
      delete packet;Serial.printf("%s pending queue full; new sample skipped (not durable logging).\n",destinations[i].cacheKey);
    }
  }
}
void setup() {
  Serial.begin(115200);analogReadResolution(12);analogSetAttenuation(ADC_11db);
  settingsMutex=xSemaphoreCreateMutex();
  if(!settingsMutex){Serial.println("No memory for settings lock.");while(true)delay(1000);}
  preferences.begin("riverguard-v2",false);
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,NTP_SERVER);
  bootId=String((uint32_t)(ESP.getEfuseMac()>>32),HEX)+String((uint32_t)ESP.getEfuseMac(),HEX)+"-"+String(esp_random(),HEX);
  for(int i=0;i<2;i++) {
    Destination& destination=destinations[i];
    destination.configured=strlen(destination.url)>0&&strlen(destination.token)>0;
    if(!destination.configured)continue;
    String saved=preferences.getString(destination.cacheKey,"");JsonDocument cached;
    if(saved.length()&&!deserializeJson(cached,saved)&&validConfig(cached)&&
       cached["cache_identity"].as<String>()==cacheIdentity(destination))destination.config.set(cached);
    destination.queue=xQueueCreate(1,sizeof(Packet*));
    if(!destination.queue) {
      destination.configured=false;Serial.printf("%s worker unavailable; receiver disabled.\n",destination.cacheKey);
    }
  }
  // Finish loading all NVS entries before any network task may write NVS.
  for(Destination& destination:destinations)if(destination.configured&&
      xTaskCreatePinnedToCore(networkWorker,destination.cacheKey,8192,&destination,1,nullptr,0)!=pdPASS) {
    destination.configured=false;Serial.printf("%s worker unavailable; receiver disabled.\n",destination.cacheKey);
  }
}
void loop() {
  if(WiFi.status()!=WL_CONNECTED&&millis()-lastWifiRetry>15000){WiFi.reconnect();lastWifiRetry=millis();}
  if(static_cast<long>(millis()-nextSample)>=0) {
    nextSample=millis()+SAMPLE_INTERVAL_MS;collect();
  }
  delay(20);
}
