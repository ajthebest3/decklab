package com.marketdeck.app;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import org.json.*;
import java.util.*;

/** Private on-device read model. Financial orders are never queued offline. */
final class LocalStore extends SQLiteOpenHelper {
    LocalStore(Context c){super(c,"decklab-device.db",null,1);setWriteAheadLoggingEnabled(true);}
    @Override public void onCreate(SQLiteDatabase db){
        db.execSQL("CREATE TABLE snapshots(origin TEXT,path TEXT,body TEXT,received INTEGER,PRIMARY KEY(origin,path))");
        db.execSQL("CREATE TABLE instruments(origin TEXT,symbol TEXT,name TEXT,kind TEXT,region TEXT,currency TEXT,body TEXT,PRIMARY KEY(origin,symbol))");
        db.execSQL("CREATE TABLE device_items(origin TEXT,symbol TEXT,pinned INTEGER DEFAULT 0,note TEXT DEFAULT '',modified INTEGER,PRIMARY KEY(origin,symbol))");
        db.execSQL("CREATE TABLE drafts(origin TEXT,name TEXT,body TEXT,PRIMARY KEY(origin,name))");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldVersion,int newVersion){throw new IllegalStateException("A non-destructive migration is required");}
    synchronized void save(String origin,String path,String body){
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try{
            Object value=new JSONTokener(body).nextValue();
            if(path.equals("/api/state")&&(!(value instanceof JSONObject)||!"paper".equals(((JSONObject)value).optString("mode"))||((JSONObject)value).optJSONArray("assets")==null))throw new IllegalArgumentException("This is not a compatible Market Deck server");
            if(path.startsWith("/api/population")&&!path.contains("/detail")&&(!(value instanceof JSONObject)||((JSONObject)value).optJSONObject("total")==null))throw new IllegalArgumentException("Invalid portfolio snapshot");
            if(path.startsWith("/api/candles")&&!(value instanceof JSONArray))throw new IllegalArgumentException("Invalid candle data");
            if(path.equals("/api/health")&&(!(value instanceof JSONObject)||!((JSONObject)value).optBoolean("ok")))throw new IllegalArgumentException("Incompatible server health response");
            ContentValues cv=new ContentValues();cv.put("origin",origin);cv.put("path",path);cv.put("body",body);cv.put("received",System.currentTimeMillis());db.insertWithOnConflict("snapshots",null,cv,SQLiteDatabase.CONFLICT_REPLACE);
            JSONArray assets=value instanceof JSONObject?((JSONObject)value).optJSONArray(path.startsWith("/api/terminal")?"markets":"assets"):null;
            if(assets!=null)for(int i=0;i<assets.length();i++){
                JSONObject a=assets.optJSONObject(i);if(a==null||a.optString("symbol").isEmpty())continue;
                ContentValues item=new ContentValues();item.put("origin",origin);for(String k:new String[]{"symbol","name","kind","region","currency"})item.put(k,a.optString(k));item.put("body",a.toString());
                db.insertWithOnConflict("instruments",null,item,SQLiteDatabase.CONFLICT_REPLACE);
            }
            if(path.equals("/api/state")&&value instanceof JSONObject){
                JSONObject state=(JSONObject)value;JSONArray pins=state.optJSONArray("watchlist"),notes=state.optJSONArray("notes");
                if(pins!=null)for(int i=0;i<pins.length();i++)seedItem(db,origin,pins.optString(i),true,"");
                if(notes!=null)for(int i=0;i<notes.length();i++){JSONObject n=notes.optJSONObject(i);if(n!=null)seedItem(db,origin,n.optString("symbol"),false,n.optString("body"));}
            }
            // Bound chart/detail cache while retaining durable device notes and watchlist.
            db.execSQL("DELETE FROM snapshots WHERE origin=? AND path NOT IN (SELECT path FROM snapshots WHERE origin=? ORDER BY received DESC LIMIT 80)",new Object[]{origin,origin});
            db.setTransactionSuccessful();
        }catch(JSONException e){throw new IllegalArgumentException("Invalid server JSON",e);}finally{db.endTransaction();}
    }
    private void seedItem(SQLiteDatabase db,String origin,String symbol,boolean pinned,String note){
        if(symbol.isEmpty())return;
        try(Cursor c=db.rawQuery("SELECT modified FROM device_items WHERE origin=? AND symbol=?",new String[]{origin,symbol})){if(c.moveToFirst()){if(c.getLong(0)==0&&!note.isEmpty())db.execSQL("UPDATE device_items SET note=? WHERE origin=? AND symbol=? AND note=''",new Object[]{note,origin,symbol});return;}}
        ContentValues v=new ContentValues();v.put("origin",origin);v.put("symbol",symbol);v.put("pinned",pinned?1:0);v.put("note",note);v.put("modified",0);db.insertWithOnConflict("device_items",null,v,SQLiteDatabase.CONFLICT_IGNORE);
    }
    synchronized String read(String origin,String path){try(Cursor c=getReadableDatabase().rawQuery("SELECT body FROM snapshots WHERE origin=? AND path=?",new String[]{origin,path})){return c.moveToFirst()?c.getString(0):null;}}
    synchronized long received(String origin,String path){try(Cursor c=getReadableDatabase().rawQuery("SELECT received FROM snapshots WHERE origin=? AND path=?",new String[]{origin,path})){return c.moveToFirst()?c.getLong(0):0;}}
    synchronized JSONArray instruments(String origin,String query,String group,boolean pinned){
        String sql="SELECT a.body FROM instruments a LEFT JOIN device_items i ON a.origin=i.origin AND a.symbol=i.symbol WHERE a.origin=? AND (a.symbol LIKE ? ESCAPE '\\' OR a.name LIKE ? ESCAPE '\\')";
        ArrayList<String> args=new ArrayList<>();args.add(origin);String search="%"+query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%";args.add(search);args.add(search);
        if(pinned)sql+=" AND i.pinned=1";
        if("India".equals(group))sql+=" AND (a.region='India' OR a.symbol LIKE '%.NS')";
        else if("Stocks".equals(group))sql+=" AND a.kind IN ('equity','etf','tokenized_equity','tokenized_etf')";
        else if("Crypto".equals(group))sql+=" AND a.kind='crypto'";
        else if("Forex".equals(group))sql+=" AND a.kind='forex'";
        else if("Gold".equals(group))sql+=" AND a.kind='commodity_token'";
        sql+=" ORDER BY COALESCE(i.pinned,0) DESC,a.symbol LIMIT 300";
        JSONArray out=new JSONArray();try(Cursor c=getReadableDatabase().rawQuery(sql,args.toArray(new String[0]))){while(c.moveToNext())try{out.put(new JSONObject(c.getString(0)));}catch(JSONException ignored){}}return out;
    }
    synchronized JSONObject item(String origin,String symbol){
        try(Cursor c=getReadableDatabase().rawQuery("SELECT pinned,note,modified FROM device_items WHERE origin=? AND symbol=?",new String[]{origin,symbol})){
            if(c.moveToFirst())return new JSONObject().put("pinned",c.getInt(0)==1).put("note",c.getString(1)).put("modified",c.getLong(2));
        }catch(JSONException ignored){}return new JSONObject();
    }
    synchronized void updateItem(String origin,String symbol,Boolean pinned,String note){
        JSONObject prior=item(origin,symbol);ContentValues v=new ContentValues();v.put("origin",origin);v.put("symbol",symbol);v.put("pinned",pinned==null?prior.optBoolean("pinned",false)?1:0:pinned?1:0);v.put("note",note==null?prior.optString("note"):note);v.put("modified",System.currentTimeMillis());getWritableDatabase().insertWithOnConflict("device_items",null,v,SQLiteDatabase.CONFLICT_REPLACE);
    }
    synchronized String draft(String origin,String name){try(Cursor c=getReadableDatabase().rawQuery("SELECT body FROM drafts WHERE origin=? AND name=?",new String[]{origin,name})){return c.moveToFirst()?c.getString(0):"";}}
    synchronized void draft(String origin,String name,String body){ContentValues v=new ContentValues();v.put("origin",origin);v.put("name",name);v.put("body",body);getWritableDatabase().insertWithOnConflict("drafts",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
    synchronized int count(String origin){try(Cursor c=getReadableDatabase().rawQuery("SELECT COUNT(*) FROM instruments WHERE origin=?",new String[]{origin})){return c.moveToFirst()?c.getInt(0):0;}}
    synchronized void clearCache(String origin){SQLiteDatabase db=getWritableDatabase();db.beginTransaction();try{db.delete("snapshots","origin=?",new String[]{origin});db.execSQL("DELETE FROM instruments WHERE origin=? AND symbol NOT IN (SELECT symbol FROM device_items WHERE origin=? AND (pinned=1 OR note<>''))",new Object[]{origin,origin});db.setTransactionSuccessful();}finally{db.endTransaction();}}
}
