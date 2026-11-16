package com.marketdeck.app;

import org.json.*;
import java.util.*;

/** Read-only specialist presentation. Never receives admin or provider credentials. */
final class SpecialistController {
    static String roster(JSONObject data){
        StringBuilder out=new StringBuilder("Saved server assignments · read-only\nChanges require a fresh online review in Advanced workspace.\n\n");
        JSONObject routes=data.optJSONObject("assignments");
        if(routes==null||routes.length()==0)out.append("No saved assignments available.\n");
        else {ArrayList<String> keys=new ArrayList<>();routes.keys().forEachRemaining(keys::add);Collections.sort(keys);for(String key:keys){JSONObject r=routes.optJSONObject(key);if(r==null)continue;out.append(key).append("\n");for(String field:new String[]{"provider","model","effort"})if(r.has(field))out.append(field).append(": ").append(r.optString(field)).append('\n');out.append('\n');}}
        JSONArray bots=data.optJSONArray("bots");if(bots!=null)for(int i=0;i<bots.length();i++){JSONObject b=bots.optJSONObject(i);if(b!=null)out.append(b.optString("bot")).append(" · ").append(b.optString("state","unknown")).append('\n');}
        return out.toString();
    }
    static String dayTrader(JSONObject data){
        StringBuilder out=new StringBuilder("US stock research · planning only\nNo broker execution. Planning budgets are not funded capital or approved account risk.\n\n");
        JSONArray jobs=data.optJSONArray("jobs");if(jobs==null||jobs.length()==0)out.append("No downloaded jobs available.\n");else for(int i=0;i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);if(j!=null)out.append('#').append(j.optLong("id")).append(" · ").append(j.optString("tool")).append(" · ").append(j.optString("state","unknown")).append("\n").append(j.optJSONArray("symbols")).append("\n").append(j.optString("error")).append("\n\n");}
        return out.toString();
    }
    static String job(JSONObject data){StringBuilder out=new StringBuilder("US research only · saved job #"+data.optLong("id")+" · "+data.optString("state","unknown")+"\n");JSONObject result=data.optJSONObject("result"),steps=result==null?null:result.optJSONObject("steps");if(steps==null)return out+"No structured stages available. Open Advanced workspace for the full retained result.";Iterator<String> names=steps.keys();while(names.hasNext()){String name=names.next();JSONObject step=steps.optJSONObject(name);if(step==null)continue;out.append('\n').append(name).append(" · ").append(step.optString("state","unknown")).append('\n').append(step.optString("error")).append('\n');JSONObject values=step.optJSONObject("data");if(values!=null)out.append(values.toString()).append('\n');}return out.toString();}
}
