package com.riverguard.v2;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashSet;
import java.util.Set;
import static com.riverguard.v2.PhoneValidation.*;

/** Persistent alert transitions. One continuing condition produces one notification. */
public final class AlertLedger {
    private AlertLedger() {}
    public static JSONObject apply(JSONObject previous,JSONObject evaluation,long now) {
        JSONObject state=previous==null?json("conditions",new JSONObject()):copy(previous);
        JSONObject conditions=state.optJSONObject("conditions");if(conditions==null){conditions=new JSONObject();put(state,"conditions",conditions);}
        JSONArray events=new JSONArray(),signals=evaluation.optJSONArray("signals");if(signals==null)signals=new JSONArray();
        String sample=evaluation.optString("sample","");boolean newSample=!sample.equals(state.optString("sample",""));
        Set<String> active=new HashSet<>();
        for(int i=0;i<signals.length();i++) {
            JSONObject signal=signals.optJSONObject(i);if(signal==null)continue;String kind=signal.optString("kind");active.add(kind);
            JSONObject old=conditions.optJSONObject(kind);int level=signal.optInt("level");
            if(old==null||!old.optBoolean("active")||old.optInt("level")<level)events.put(json("kind",kind,"phase","active","level",level,"title",signal.optString("title"),"detail",signal.optString("detail"),"timestamp",java.time.Instant.ofEpochMilli(now).toString(),"sample",sample));
            put(conditions,kind,json("active",true,"level",level,"clearCount",0));
        }
        if(newSample&&evaluation.optBoolean("fresh")) {
            java.util.Iterator<String> names=conditions.keys();
            while(names.hasNext()) {
                String kind=names.next();JSONObject old=conditions.optJSONObject(kind);
                if(active.contains(kind)||old==null||!old.optBoolean("active"))continue;
                int count=old.optInt("clearCount")+1;put(old,"clearCount",count);
                if(count>=3) {put(old,"active",false);events.put(json("kind",kind,"phase","recovered","level",0,"title","Reading check returned within its reference","detail","Three fresh readings no longer show the previous "+kind.replace('_',' ')+" condition. This does not establish water safety.","timestamp",java.time.Instant.ofEpochMilli(now).toString(),"sample",sample));}
            }
        }
        put(state,"sample",sample);return json("state",state,"events",events);
    }
}
