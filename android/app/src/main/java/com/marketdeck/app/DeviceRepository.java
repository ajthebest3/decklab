package com.marketdeck.app;

import android.content.Context;
import android.os.*;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/** Bounded background sync, cached reads first, endpoint-scoped storage. */
final class DeviceRepository {
    interface Listener{void changed(String path,boolean success,String error);}
    interface Reply{void done(JSONObject result,String error);}
    final LocalStore store;
    final ResourceHealth resourceHealth=new ResourceHealth();
    private final Context context;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(16));
    private final Set<String> pending=Collections.synchronizedSet(new HashSet<>());
    private final Map<String,Long> attempted=Collections.synchronizedMap(new LinkedHashMap<String,Long>(){protected boolean removeEldestEntry(Map.Entry<String,Long> eldest){return size()>512;}});
    private final Set<String> pauseVetoes=Collections.synchronizedSet(new HashSet<>());
    private volatile boolean closed=false;
    private Listener listener;
    DeviceRepository(Context c,Listener l){context=c.getApplicationContext();listener=l;store=new LocalStore(context);}
    String origin(){return Connection.endpoint(context);}
    JSONObject object(String path){try{String s=store.read(origin(),path);return s==null?new JSONObject():new JSONObject(s);}catch(JSONException e){return new JSONObject();}}
    JSONArray array(String path){try{String s=store.read(origin(),path);return s==null?new JSONArray():new JSONArray(s);}catch(JSONException e){return new JSONArray();}}
    long received(String path){return store.received(origin(),path);}
    ResourceHealth.Snapshot health(String path){return resourceHealth.get(origin(),path);}
    void rememberOwnerPause(String endpoint,boolean active)throws java.io.IOException{
        if(active)pauseVetoes.add(endpoint);
        if(!context.getSharedPreferences("foundation-safety",Context.MODE_PRIVATE).edit().putBoolean(endpoint,active).commit())throw new java.io.IOException("Owner pause safety state could not be saved");
        if(!active)pauseVetoes.remove(endpoint);
    }
    boolean ownerPauseVeto(){
        String endpoint=origin();if(pauseVetoes.contains(endpoint))return true;
        try{if(context.getSharedPreferences("foundation-safety",Context.MODE_PRIVATE).getBoolean(endpoint,false))return true;}
        catch(ClassCastException malformedSafetyState){return true;}
        JSONObject ready=object("/api/v2/readiness"),pause=ready.optJSONObject("owner_pause");
        return "2.0".equals(ready.optString("contract_version"))&&pause!=null&&Boolean.TRUE.equals(pause.opt("active"));
    }
    void fetch(String path,long minInterval,boolean force){
        final String endpoint=origin(),key=endpoint+path;long now=System.currentTimeMillis();
        if(closed||!force&&now-Math.max(attempted.getOrDefault(key,0L),store.received(endpoint,path))<minInterval||!pending.add(key))return;
        attempted.put(key,now);
        resourceHealth.attempted(endpoint,path,now);
        try{worker.execute(()->{boolean ok=false;String error="";
            try{String body=Connection.requestAt(endpoint,"GET",path,null);Boolean ownerPause=null;
                if(path.equals("/api/v2/readiness")){JSONObject ready=new JSONObject(body),pause=ready.optJSONObject("owner_pause");
                    if(!"2.0".equals(ready.optString("contract_version"))||pause==null||!(pause.opt("active") instanceof Boolean))throw new IllegalArgumentException("Readiness unavailable for this server version");
                    ownerPause=(Boolean)pause.opt("active");if(ownerPause)rememberOwnerPause(endpoint,true);}
                store.save(endpoint,path,body);if(Boolean.FALSE.equals(ownerPause))rememberOwnerPause(endpoint,false);
                resourceHealth.succeeded(endpoint,path,System.currentTimeMillis());ok=true;}
            catch(Exception e){error=friendly(e);resourceHealth.failed(endpoint,path,System.currentTimeMillis(),error);}
            finally{pending.remove(key);final boolean success=ok;final String message=error;main.post(()->{if(!closed&&endpoint.equals(origin())&&listener!=null)listener.changed(path,success,message);});}
        });}catch(RejectedExecutionException e){pending.remove(key);resourceHealth.failed(endpoint,path,System.currentTimeMillis(),"Request queue full; not submitted");if(endpoint.equals(origin())&&listener!=null)listener.changed(path,false,"Request queue full; not submitted");}
    }
    void post(String path,JSONObject body,Reply reply){
        final String endpoint=origin();
        try{worker.execute(()->{JSONObject result=null;String error="";try{result=new JSONObject(Connection.requestAt(endpoint,"POST",path,body.toString()));}catch(Exception e){error=friendly(e);}final JSONObject value=result;final String message=error;main.post(()->{if(!closed&&endpoint.equals(origin()))reply.done(value,message);});});}
        catch(RejectedExecutionException e){reply.done(null,"Please wait for the current requests to finish.");}
    }
    private static String friendly(Exception e){if(e instanceof java.net.ConnectException||e instanceof java.net.SocketTimeoutException)return "Server unavailable. Saved device data is still available. Check Termius and refresh.";return e.getMessage()==null?"Connection failed":e.getMessage().replaceAll("sk-[A-Za-z0-9_-]{8,}","[redacted]");}
    void close(){closed=true;listener=null;worker.shutdownNow();/* SQLite stays open until process exit so in-flight safe reads cannot race a close. */}
}
