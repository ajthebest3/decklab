package com.marketdeck.app;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;

public class NotificationService extends Service {
    static volatile String status="off";
    private volatile boolean running=false;
    private volatile HttpURLConnection active;
    private Thread worker;
    static final String MONITOR="market_monitor", ALERTS="market_alerts";
    static void channels(Context c){
        NotificationManager m=c.getSystemService(NotificationManager.class);
        NotificationChannel monitor=new NotificationChannel(MONITOR,"Server connection",NotificationManager.IMPORTANCE_LOW);
        monitor.setDescription("Visible status while private market notifications are enabled");
        NotificationChannel alerts=new NotificationChannel(ALERTS,"Price alerts, research & paper fills",NotificationManager.IMPORTANCE_DEFAULT);
        alerts.setDescription("Events pushed from your Market Deck server");alerts.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE);
        m.createNotificationChannel(monitor);m.createNotificationChannel(alerts);
    }
    static PendingIntent open(Context c,String route,int id){
        return PendingIntent.getActivity(c,id,new Intent(c,MainActivity.class).putExtra("route",route).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
    }
    static void post(Context c,int id,String title,String body,String route){
        if(!c.getSystemService(NotificationManager.class).areNotificationsEnabled())return;
        Notification publicVersion=new Notification.Builder(c,ALERTS).setSmallIcon(R.drawable.ic_notification).setContentTitle("Market Deck").setContentText("You have a market update").build();
        Notification n=new Notification.Builder(c,ALERTS).setSmallIcon(R.drawable.ic_notification).setColor(0xffd5f584).setContentTitle(title).setContentText(body)
            .setStyle(new Notification.BigTextStyle().bigText(body)).setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(publicVersion).setAutoCancel(true).setOnlyAlertOnce(true).setContentIntent(open(c,route,id)).build();
        c.getSystemService(NotificationManager.class).notify("market-event",id,n);
    }
    static void test(Context c){channels(c);post(c,2,"Market Deck · test notification","Notifications are allowed on this phone. Server delivery also needs an active connection.","alerts");}
    private Notification monitor(String message){
        PendingIntent stop=PendingIntent.getService(this,0,new Intent(this,NotificationService.class).setAction("STOP"),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,MONITOR).setSmallIcon(R.drawable.ic_notification).setContentTitle("Market Deck notifications").setContentText(message).setOngoing(true).setOnlyAlertOnce(true).setContentIntent(open(this,"settings",0)).addAction(new Notification.Action.Builder(null,"Stop",stop).build()).build();
    }
    private void update(String message){status=message;getSystemService(NotificationManager.class).notify(1,monitor(message));}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&"STOP".equals(intent.getAction())){Connection.prefs(this).edit().putBoolean("notifications",false).apply();stopSelf();return START_NOT_STICKY;}
        if(!Connection.prefs(this).getBoolean("notifications",false)){stopSelf();return START_NOT_STICKY;}
        channels(this);
        if(Build.VERSION.SDK_INT>=34)startForeground(1,monitor("Connecting to your server…"),ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(1,monitor("Connecting to your server…"));
        if(!running){running=true;worker=new Thread(this::loop,"market-deck-notifications");worker.start();}
        return START_STICKY;
    }
    private void loop(){
        int delay=2;
        while(running){
            HttpURLConnection con=null;
            try{
                if(!getSystemService(NotificationManager.class).areNotificationsEnabled()){Connection.prefs(this).edit().putBoolean("notifications",false).apply();stopSelf();return;}
                con=Connection.open(this,"/api/mobile/stream");active=con;
                con.setReadTimeout(45000);con.setRequestProperty("Accept","text/event-stream");
                long cursor=Connection.prefs(this).getLong("cursor",-1);
                if(cursor>=0)con.setRequestProperty("Last-Event-ID",Long.toString(cursor));
                if(con.getResponseCode()!=200 || !String.valueOf(con.getContentType()).startsWith("text/event-stream"))throw new IOException("Stream unavailable");
                update("Connected · listening for market updates");delay=2;
                try(BufferedReader reader=new BufferedReader(new InputStreamReader(con.getInputStream(),StandardCharsets.UTF_8))){
                    String line,type="",data="",id="";
                    while(running&&(line=reader.readLine())!=null){
                        if(line.length()>16384)throw new IOException("Event too large");
                        if(line.isEmpty()){
                            if(!data.isEmpty()){
                                JSONObject item=new JSONObject(data);
                                if("notification".equals(type))post(this,(int)(item.getLong("id")%2000000000L)+10,item.getString("title"),item.getString("body"),item.getString("route"));
                                if(!id.isEmpty())Connection.prefs(this).edit().putLong("cursor",Long.parseLong(id)).commit();
                            }
                            type=data=id="";
                        }else if(line.startsWith("event: "))type=line.substring(7);
                        else if(line.startsWith("data: "))data=line.substring(6);
                        else if(line.startsWith("id: "))id=line.substring(4);
                    }
                }
            }catch(Exception e){if(running)update("Disconnected · retrying; check your tunnel");}
            finally{if(con!=null)con.disconnect();active=null;}
            if(running)try{Thread.sleep(delay*1000L+(long)(Math.random()*700));delay=Math.min(60,delay*2);}catch(InterruptedException e){Thread.currentThread().interrupt();break;}
        }
    }
    @Override public void onDestroy(){running=false;status="off";if(active!=null)active.disconnect();if(worker!=null)worker.interrupt();stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();}
    @Override public IBinder onBind(Intent i){return null;}
}
