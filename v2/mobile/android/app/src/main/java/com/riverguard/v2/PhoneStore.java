package com.riverguard.v2;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import static com.riverguard.v2.PhoneValidation.*;

/** Private append-only readings and immutable versioned calibration snapshots. */
public final class PhoneStore extends SQLiteOpenHelper implements PhoneReceiver.Backend {
    public PhoneStore(Context context) { super(context, "riverguard-v2.db", null, 1); setWriteAheadLoggingEnabled(true); }
    @Override public void onConfigure(SQLiteDatabase db) { db.setForeignKeyConstraintsEnabled(true); }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT NOT NULL)");
        db.execSQL("CREATE TABLE stations(device_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,last_received TEXT,last_measured TEXT,ack_revision INTEGER)");
        db.execSQL("CREATE TABLE configurations(device_id TEXT NOT NULL,revision INTEGER NOT NULL,settings TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(device_id,revision),FOREIGN KEY(device_id) REFERENCES stations(device_id))");
        db.execSQL("CREATE TABLE readings(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,device_id TEXT NOT NULL,timestamp TEXT NOT NULL,measured_ms INTEGER NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL,settings_json TEXT,sample_id TEXT,UNIQUE(source,device_id,sample_id))");
        db.execSQL("CREATE TABLE alert_events(id INTEGER PRIMARY KEY AUTOINCREMENT,device_id TEXT NOT NULL,event_json TEXT NOT NULL)");
        db.execSQL("CREATE INDEX alert_station ON alert_events(device_id,id DESC)");
        db.execSQL("CREATE INDEX station_measurement ON readings(source,device_id,measured_ms DESC,id DESC)");
    }
    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) { throw new IllegalStateException("Unsupported phone database upgrade. Preserve this app's data."); }

    public synchronized JSONObject getState(String key) {
        stateKey(key);
        if(key.startsWith("alerts:")) {
            String device=station(key.substring(7));JSONArray events=new JSONArray();
            try(Cursor c=getReadableDatabase().rawQuery("SELECT event_json FROM alert_events WHERE device_id=? ORDER BY id DESC LIMIT 100",new String[]{device})){while(c.moveToNext())events.put(object(c.getString(0)));}
            return json("value",events);
        }
        try (Cursor c = getReadableDatabase().rawQuery("SELECT value FROM state WHERE key=?", new String[]{key})) {
            Object value = JSONObject.NULL;
            if (c.moveToFirst()) {
                try { value = new org.json.JSONTokener(c.getString(0)).nextValue(); }
                catch (org.json.JSONException error) { throw new Problem(500,"Saved phone preferences cannot be read."); }
            }
            return json("value",value);
        }
    }
    public synchronized JSONObject setState(String key, Object value) {
        stateKey(key);
        if(key.startsWith("watch:")){station(key.substring(6));if(!(value instanceof JSONObject))throw new Problem(422,"Specify watch settings.");value=SignalEvaluator.watch((JSONObject)value);}
        String encoded;
        String wrapped = new JSONArray().put(value == null ? JSONObject.NULL : value).toString();
        if (wrapped == null) throw new Problem(422,"Invalid saved preference.");
        encoded = wrapped.substring(1, wrapped.length()-1);
        if (encoded.getBytes(StandardCharsets.UTF_8).length > 65536) throw new Problem(413,"This phone preference is too large.");
        ContentValues row=new ContentValues(); row.put("key",key); row.put("value",encoded);
        getWritableDatabase().insertWithOnConflict("state",null,row,SQLiteDatabase.CONFLICT_REPLACE);
        return json("saved",true);
    }
    private static void stateKey(String key) { if(key==null || !key.matches("[A-Za-z0-9_.:-]{1,128}")) throw new Problem(422,"Invalid preference key."); }
    public synchronized boolean receiverEnabled() { return Boolean.TRUE.equals(getState("receiver.enabled").opt("value")); }
    public synchronized void receiverEnabled(boolean enabled) { setState("receiver.enabled",enabled); }

    public synchronized JSONObject register(String device,boolean rotate) {
        station(device); SQLiteDatabase db=getWritableDatabase(); String token=token();
        db.beginTransaction();
        try {
            boolean exists=exists(db,"SELECT 1 FROM stations WHERE device_id=?",device);
            if(exists&&!rotate) throw new Problem(409,"Station already registered. Replace its credential only if you can upload the new private configuration.");
            ContentValues row=new ContentValues();row.put("token_hash",digest(token));
            if(exists) db.update("stations",row,"device_id=?",new String[]{device});
            else { row.put("device_id",device); db.insertOrThrow("stations",null,row); }
            db.setTransactionSuccessful();return json("deviceId",device,"token",token);
        } finally { db.endTransaction(); }
    }
    public synchronized String authenticate(String header) {
        if(header==null||!header.matches("Bearer [A-Za-z0-9_-]{32,200}")) throw new Problem(401,"Station credential required.");
        String hash=digest(header.substring(7));
        try(Cursor c=getReadableDatabase().rawQuery("SELECT device_id FROM stations WHERE token_hash=?",new String[]{hash})) {
            if(!c.moveToFirst()) throw new Problem(401,"Station credential is invalid or revoked.");
            return c.getString(0);
        }
    }
    public synchronized JSONObject settings(String device) { station(device); return settings(getReadableDatabase(),device,null); }
    private JSONObject settings(SQLiteDatabase db,String device,Integer revision) {
        String sql="SELECT revision,settings FROM configurations WHERE device_id=?"+(revision==null?" ORDER BY revision DESC LIMIT 1":" AND revision=?");
        String[] args=revision==null?new String[]{device}:new String[]{device,String.valueOf(revision)};
        try(Cursor c=db.rawQuery(sql,args)) {
            if(c.moveToFirst()) return json("revision",c.getInt(0),"settings",object(c.getString(1)));
        }
        if(revision!=null&&revision!=0) throw new Problem(409,"Unknown calibration revision. Resync the station configuration.");
        return json("revision",0,"settings",defaults());
    }
    public synchronized JSONObject saveSettings(String device,long expected,JSONObject incoming) {
        station(device); if(expected<0||expected>=Integer.MAX_VALUE) throw new Problem(422,"Invalid configuration revision.");
        JSONObject normalized=PhoneValidation.settings(incoming);SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            if(!exists(db,"SELECT 1 FROM stations WHERE device_id=?",device)) throw new Problem(404,"Register this station first.");
            JSONObject previous=settings(db,device,null);
            if(previous.optLong("revision")!=expected) throw new Problem(409,"Settings changed. Reload the saved configuration before saving again.");
            JSONObject before=copy(previous.optJSONObject("settings")),after=copy(normalized);
            put(before,"verified",false);put(after,"verified",false);
            if(!equivalent(before,after)) put(normalized,"verified",false);
            ContentValues row=new ContentValues();row.put("device_id",device);row.put("revision",expected+1);row.put("settings",normalized.toString());row.put("created_at",Instant.now().toString());
            db.insertOrThrow("configurations",null,row);db.setTransactionSuccessful();return json("revision",expected+1,"settings",normalized);
        } finally { db.endTransaction(); }
    }
    private static boolean equivalent(Object a,Object b) {
        if(a==JSONObject.NULL||a==null) return b==null||b==JSONObject.NULL;
        if(a instanceof JSONObject&&b instanceof JSONObject) {
            JSONObject aa=(JSONObject)a,bb=(JSONObject)b;if(aa.length()!=bb.length())return false;
            java.util.Iterator<String> keys=aa.keys();while(keys.hasNext()){String k=keys.next();if(!bb.has(k)||!equivalent(aa.opt(k),bb.opt(k)))return false;}return true;
        }
        if(a instanceof JSONArray&&b instanceof JSONArray) {JSONArray aa=(JSONArray)a,bb=(JSONArray)b;if(aa.length()!=bb.length())return false;for(int i=0;i<aa.length();i++)if(!equivalent(aa.opt(i),bb.opt(i)))return false;return true;}
        if(a instanceof Number&&b instanceof Number)return Double.compare(((Number)a).doubleValue(),((Number)b).doubleValue())==0;
        return a.equals(b);
    }
    private static boolean exists(SQLiteDatabase db,String sql,String value) {try(Cursor c=db.rawQuery(sql,new String[]{value})){return c.moveToFirst();}}
    public synchronized JSONObject configuration(String device) {
        JSONObject cfg=settings(device);long now=System.currentTimeMillis();
        return json("device_id",device,"protocol","remote-v1","revision",cfg.optInt("revision"),"enabled",cfg.optJSONObject("settings").optJSONObject("enabled"),"server_time",Instant.ofEpochMilli(now).toString(),"server_epoch_seconds",now/1000);
    }
    public synchronized JSONObject ingest(String authenticated,JSONObject packet) {
        long now=System.currentTimeMillis(),measured=hardware(packet,now);String device=packet.optString("device_id");
        if(!authenticated.equals(device)) throw new Problem(403,"A station can submit only its own readings.");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            int revision=packet.optInt("config_revision");JSONObject cfg=settings(db,device,revision).optJSONObject("settings");
            String received=Instant.ofEpochMilli(now).toString();
            ContentValues row=new ContentValues();row.put("source","esp32");row.put("device_id",device);row.put("timestamp",Instant.ofEpochMilli(measured).toString());row.put("measured_ms",measured);row.put("received_at",received);row.put("payload",packet.toString());row.put("settings_json",cfg.toString());row.put("sample_id",packet.optString("sample_id"));
            long id=db.insertWithOnConflict("readings",null,row,SQLiteDatabase.CONFLICT_IGNORE);
            if(id==-1) {
                try(Cursor existing=db.rawQuery("SELECT payload FROM readings WHERE source='esp32' AND device_id=? AND sample_id=?",new String[]{device,packet.optString("sample_id")})) {
                    if(!existing.moveToFirst()||!equivalent(object(existing.getString(0)),packet))throw new Problem(409,"This sample ID was already used for different readings. Keep each retry unchanged.");
                }
            }
            ContentValues heartbeat=new ContentValues();heartbeat.put("last_received",received);
            try(Cursor latest=db.rawQuery("SELECT timestamp,payload FROM readings WHERE source='esp32' AND device_id=? ORDER BY measured_ms DESC,id DESC LIMIT 1",new String[]{device})) {
                if(latest.moveToFirst()){heartbeat.put("last_measured",latest.getString(0));heartbeat.put("ack_revision",object(latest.getString(1)).optInt("config_revision"));}
            }
            db.update("stations",heartbeat,"device_id=?",new String[]{device});db.setTransactionSuccessful();return json("stored",true,"duplicate",id==-1);
        } finally {db.endTransaction();}
    }
    public synchronized JSONObject appendDemo(JSONObject incoming) {
        JSONObject payload=demo(incoming);long measured=timestamp(payload,System.currentTimeMillis());
        ContentValues row=new ContentValues();row.put("source","simulation");row.put("device_id","demo-station");row.put("timestamp",Instant.ofEpochMilli(measured).toString());row.put("measured_ms",measured);row.put("received_at",Instant.now().toString());row.put("payload",payload.toString());row.put("sample_id",UUID.randomUUID().toString());
        getWritableDatabase().insertOrThrow("readings",null,row);return json("stored",true);
    }
    public synchronized JSONArray stations() {
        JSONArray items=new JSONArray();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT device_id,last_received,last_measured,ack_revision,(SELECT MAX(revision) FROM configurations WHERE configurations.device_id=stations.device_id) FROM stations ORDER BY device_id",null)) {
            while(c.moveToNext())items.put(json("deviceId",c.getString(0),"lastReceived",c.isNull(1)?null:c.getString(1),"lastMeasured",c.isNull(2)?null:c.getString(2),"acknowledgedRevision",c.isNull(3)?null:c.getLong(3),"revision",c.isNull(4)?0:c.getLong(4)));
        }return items;
    }
    private static long singleLong(SQLiteDatabase db,String sql,String[] args) {try(Cursor c=db.rawQuery(sql,args)){return c.moveToFirst()?c.getLong(0):0;}}
    public synchronized JSONObject readings(String source,String device,int limit,String cursor) {
        source(source);station(device);if(limit<1||limit>500)throw new Problem(422,"Page size must be from1 to500.");
        SQLiteDatabase db=getReadableDatabase();long ceiling=singleLong(db,"SELECT COALESCE(MAX(id),0) FROM readings WHERE source=? AND device_id=?",new String[]{source,device});
        Long lastMs=null,lastId=null;
        if(cursor!=null&&!cursor.isEmpty()) {
            if(cursor.length()>2048)throw new Problem(422,"Invalid history cursor.");
            JSONObject p;
            try {p=object(new String(Base64.decode(cursor,Base64.URL_SAFE|Base64.NO_WRAP),StandardCharsets.UTF_8));}catch(IllegalArgumentException error){throw new Problem(422,"Invalid history cursor.");}
            if(!source.equals(p.optString("source"))||!device.equals(p.optString("deviceId")))throw new Problem(422,"This history cursor belongs to another station.");
            ceiling=integer(p,"ceiling",0,Long.MAX_VALUE);lastMs=integer(p,"ms",0,Long.MAX_VALUE);lastId=integer(p,"id",1,Long.MAX_VALUE);
        }
        String where="source=? AND device_id=? AND id<=?";String[] base={source,device,String.valueOf(ceiling)};
        long total=singleLong(db,"SELECT COUNT(*) FROM readings WHERE "+where,base);
        String[] args=base;
        if(lastMs!=null){where+=" AND (measured_ms<? OR (measured_ms=? AND id<?))";args=new String[]{source,device,String.valueOf(ceiling),String.valueOf(lastMs),String.valueOf(lastMs),String.valueOf(lastId)};}
        JSONArray items=new JSONArray();String next=null;
        try(Cursor c=db.rawQuery("SELECT id,source,device_id,timestamp,received_at,payload,settings_json,measured_ms FROM readings WHERE "+where+" ORDER BY measured_ms DESC,id DESC LIMIT "+(limit+1),args)) {
            JSONObject last=null;long ms=0;
            while(c.moveToNext()) {
                if(items.length()==limit){JSONObject token=json("source",source,"deviceId",device,"ceiling",ceiling,"ms",ms,"id",last.optLong("id"));next=Base64.encodeToString(token.toString().getBytes(StandardCharsets.UTF_8),Base64.URL_SAFE|Base64.NO_WRAP|Base64.NO_PADDING);break;}
                last=json("id",c.getLong(0),"source",c.getString(1),"deviceId",c.getString(2),"timestamp",c.getString(3),"receivedAt",c.getString(4),"payload",object(c.getString(5)),"settings",c.isNull(6)?null:object(c.getString(6)));items.put(last);ms=c.getLong(7);
            }
        }return json("items",items,"nextCursor",next,"total",total);
    }
    public synchronized JSONArray evaluateAlerts(String device,long now) {
        JSONObject readings=readings("esp32",device,120,null),watch=(JSONObject)getState("watch:"+device).optJSONObject("value");
        JSONObject evaluation=SignalEvaluator.evaluate(readings.optJSONArray("items"),watch,now);
        // An empty station has no captured evidence; connection startup has its own UI status.
        if(readings.optJSONArray("items").length()==0)return new JSONArray();
        String key="alert-status:"+device;JSONObject previous=getState(key).optJSONObject("value");
        JSONObject change=AlertLedger.apply(previous,evaluation,now),next=change.optJSONObject("state");JSONArray events=change.optJSONArray("events");
        if(previous!=null&&equivalent(previous,next)&&events.length()==0)return events;
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            setState(key,next);
            for(int i=0;i<events.length();i++){JSONObject event=events.optJSONObject(i);put(event,"deviceId",device);ContentValues row=new ContentValues();row.put("device_id",device);row.put("event_json",event.toString());db.insertOrThrow("alert_events",null,row);}
            db.setTransactionSuccessful();
        } finally{db.endTransaction();}
        return events;
    }
    /** No delete/update exists for readings: ceiling-ID produces an immutable export snapshot. */
    public void export(String source,String device,Writer writer) throws IOException {
        source(source);station(device);final SQLiteDatabase db;final long ceiling;
        synchronized(this) {db=getReadableDatabase();ceiling=singleLong(db,"SELECT COALESCE(MAX(id),0) FROM readings WHERE source=? AND device_id=?",new String[]{source,device});}
        writer.write("id,source,device_id,timestamp,received_at,sample_id,config_revision,ph,turbidity,temperature,water_level,raw_json,settings_json,payload_json\r\n");
        try(Cursor c=db.rawQuery("SELECT id,source,device_id,timestamp,received_at,sample_id,payload,settings_json FROM readings WHERE source=? AND device_id=? AND id<=? ORDER BY measured_ms,id",new String[]{source,device,String.valueOf(ceiling)})) {
            while(c.moveToNext()) {
                JSONObject p=object(c.getString(6));boolean simulation="simulation".equals(c.getString(1));
                Object[] cells={c.getLong(0),c.getString(1),c.getString(2),c.getString(3),c.getString(4),c.getString(5),p.opt("config_revision"),simulation?p.opt("ph"):null,simulation?p.opt("turbidity"):null,simulation?p.opt("temperature"):null,simulation?p.opt("water_level"):null,p.optJSONObject("raw"),c.isNull(7)?null:c.getString(7),p};
                for(int i=0;i<cells.length;i++){if(i>0)writer.write(',');writer.write(csv(cells[i]));}writer.write("\r\n");
            }
        }writer.flush();
    }
}
