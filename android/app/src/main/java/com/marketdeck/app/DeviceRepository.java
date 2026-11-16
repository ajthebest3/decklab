package com.marketdeck.app;

import android.content.Context;
import android.os.*;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

/** Bounded background sync, cached reads first, endpoint-scoped storage. */
final class DeviceRepository {
    interface Transport{String request(String origin,String method,String path,String body)throws Exception;}
    private final Transport transport;
    interface Listener{void changed(String path,boolean success,String error);}
    interface Reply{void done(JSONObject result,String error);}
    final LocalStore store;
    final ResourceHealth resourceHealth=new ResourceHealth();
    private final Context context;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(16));
    private final ExecutorService actions=new ThreadPoolExecutor(1,1,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(4));
    private static final class Read {final String origin,path;final Connection.RequestHandle handle=new Connection.RequestHandle();Read(String o,String p){origin=o;path=p;}}
    private final ConcurrentHashMap<String,Read> reads=new ConcurrentHashMap<>();
    private void cancel(String key,Read read){read.handle.cancel();if(read.handle.task!=null)((ThreadPoolExecutor)worker).remove(read.handle.task);reads.remove(key,read);pending.remove(key);resourceHealth.cancelled(read.origin,read.path);}
    void selectResource(String prefix,String selectedPath){for(Map.Entry<String,Read> e:reads.entrySet())if(e.getValue().path.startsWith(prefix)&&!e.getValue().path.equals(selectedPath))cancel(e.getKey(),e.getValue());}
    private volatile long generation=0; private String currentOrigin="";
    synchronized long endpointGeneration(){String next=origin();if(!next.equals(currentOrigin)){currentOrigin=next;generation++;}return generation;}
    synchronized void endpointChanged(){currentOrigin=origin();generation++;for(Map.Entry<String,Read> e:reads.entrySet())cancel(e.getKey(),e.getValue());((ThreadPoolExecutor)worker).getQueue().clear();pending.clear();}
    private boolean current(String endpoint,long token){return !closed&&endpoint.equals(origin())&&token==endpointGeneration();}
    private final Set<String> pending=Collections.synchronizedSet(new HashSet<>());
    private final Map<String,Long> attempted=Collections.synchronizedMap(new LinkedHashMap<String,Long>(){protected boolean removeEldestEntry(Map.Entry<String,Long> eldest){return size()>512;}});
    private final Set<String> pauseVetoes=Collections.synchronizedSet(new HashSet<>());
    private volatile boolean closed=false;
    private Listener listener;
    DeviceRepository(Context c,Listener l){this(c,l,null);}
    DeviceRepository(Context c,Listener l,Transport t){context=c.getApplicationContext();listener=l;store=new LocalStore(context);transport=t;}
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
        final long token=endpointGeneration();final String endpoint=origin(),key=token+endpoint+path;long now=System.currentTimeMillis();
        if(closed||!force&&now<resourceHealth.get(endpoint,path).nextRetryMs||!force&&now-Math.max(attempted.getOrDefault(key,0L),store.received(endpoint,path))<minInterval||!pending.add(key))return;
        attempted.put(key,now);
        resourceHealth.attempted(endpoint,path,now);
        final Read read=new Read(endpoint,path);reads.put(key,read);
        FutureTask<Void> task=new FutureTask<>(()->{boolean ok=false;String error="";
            try{if(read.handle.cancelled||!current(endpoint,token))return;String body=transport==null?Connection.requestAt(endpoint,"GET",path,null,read.handle):transport.request(endpoint,"GET",path,null);if(read.handle.cancelled||!current(endpoint,token))return;Boolean ownerPause=null;
                if(path.equals("/api/v2/readiness")){JSONObject ready=new JSONObject(body),pause=ready.optJSONObject("owner_pause");
                    if(!"2.0".equals(ready.optString("contract_version"))||pause==null||!(pause.opt("active") instanceof Boolean))throw new IllegalArgumentException("Readiness unavailable for this server version");
                    ownerPause=(Boolean)pause.opt("active");if(ownerPause)rememberOwnerPause(endpoint,true);}
                store.save(endpoint,path,body);if(Boolean.FALSE.equals(ownerPause))rememberOwnerPause(endpoint,false);
                resourceHealth.succeeded(endpoint,path,System.currentTimeMillis());ok=true;}
            catch(Exception e){if(read.handle.cancelled)return;error=friendly(e);resourceHealth.failed(endpoint,path,System.currentTimeMillis(),error);}
            finally{if(reads.remove(key,read))pending.remove(key);final boolean success=ok;final String message=error;main.post(()->{if(!read.handle.cancelled&&current(endpoint,token)&&listener!=null)listener.changed(path,success,message);});}
        },null);read.handle.task=task;
        try{worker.execute(task);}catch(RejectedExecutionException e){reads.remove(key,read);pending.remove(key);resourceHealth.failed(endpoint,path,System.currentTimeMillis(),"Request queue full; not submitted");if(current(endpoint,token)&&listener!=null)listener.changed(path,false,"Request queue full; not submitted");}
    }
    void post(String path,JSONObject body,Reply reply){
        final long token=endpointGeneration();final String endpoint=origin();
        if(closed){reply.done(null,"Connection closed; action not sent");return;}
        try{actions.execute(()->{JSONObject result=null;String error="";try{if(!current(endpoint,token))throw new IllegalStateException("Connection changed; action not sent");if(sensitive(path)&&(!resourceHealth.get(endpoint,"/api/population?view=summary").fresh(System.currentTimeMillis(),45000)||ownerPauseVeto()))throw new IllegalStateException("Reconnect and review this action; no offline financial or research writes");result=new JSONObject(transport==null?Connection.requestAt(endpoint,"POST",path,body.toString()):transport.request(endpoint,"POST",path,body.toString()));}catch(Exception e){error=friendly(e);}final JSONObject value=result;final String message=error;main.post(()->{if(current(endpoint,token))reply.done(value,message);});});}
        catch(RejectedExecutionException e){reply.done(null,"Please wait for the current requests to finish.");}
    }
    private static boolean sensitive(String path){return path.startsWith("/api/population/")||path.startsWith("/api/demo/")||Arrays.asList("/api/orders","/api/order-preview","/api/settings","/api/research-settings","/api/research-run","/api/terminal/research","/api/alerts","/api/alert-delete").contains(path);}
    private static String friendly(Exception e){if(e instanceof java.net.ConnectException||e instanceof java.net.SocketTimeoutException)return "Server unavailable. Saved device data is still available. Check Termius and refresh.";return e.getMessage()==null?"Connection failed":e.getMessage().replaceAll("sk-[A-Za-z0-9_-]{8,}","[redacted]");}
    void close(){closed=true;listener=null;for(Map.Entry<String,Read> e:reads.entrySet())cancel(e.getKey(),e.getValue());worker.shutdownNow();actions.shutdownNow();/* SQLite stays open until process exit so in-flight safe reads cannot race a close. */}
}
