package com.marketdeck.app;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=28,qualifiers="w390dp-h844dp-xhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class NativeAppTest {
    Context context;String origin="http://localhost:8790";LocalStore store;
    @Before public void setup()throws Exception{context=RuntimeEnvironment.getApplication();context.deleteDatabase("decklab-device.db");Connection.prefs(context).edit().clear().commit();context.getSharedPreferences("foundation-safety",Context.MODE_PRIVATE).edit().clear().commit();store=new LocalStore(context);seed();}
    @After public void close(){store.close();}
    private JSONObject json(Object... pairs)throws Exception{JSONObject o=new JSONObject();for(int i=0;i<pairs.length;i+=2)o.put(String.valueOf(pairs[i]),pairs[i+1]);return o;}
    void seed()throws Exception{double now=System.currentTimeMillis()/1000.;JSONArray assets=new JSONArray();assets.put(json("symbol","RELIANCE.NS","name","Reliance Industries","kind","equity","region","India","currency","INR","price",1300,"asof",now,"source","NSE observed book"));assets.put(json("symbol","BTC/USD","name","Bitcoin","kind","crypto","region","Global","currency","USD","price",60000,"asof",now,"source","Kraken"));assets.put(json("symbol","AAPLx/USD","name","Apple tokenized exposure","kind","tokenized_equity","region","US","currency","USD","price",200,"asof",now,"source","Kraken"));
        store.save(origin,"/api/state",json("mode","paper","assets",assets,"watchlist",new JSONArray().put("BTC/USD"),"notes",new JSONArray().put(json("symbol","BTC/USD","body","Existing server note")),"portfolio",json("cash",100000,"equity",100000,"pnl",0),"orders",new JSONArray(),"alerts",new JSONArray(),"news",new JSONArray()).toString());
        JSONArray bots=new JSONArray().put(json("bot","Model-01","equity_usd",49900,"equity_inr",4500000,"initial",50000,"pnl_usd",-100,"points",-5,"positions",new JSONArray().put(json("symbol","RELIANCE.NS","qty",2)),"population",json("state","active","model","gpt-test","ai_route",json("model","gpt-test"))));
        JSONArray history=new JSONArray();for(int i=0;i<30;i++)history.put(json("ts",now-(30-i)*60,"usd",9998000+i*10));
        store.save(origin,"/api/population?view=summary",json("total",json("equity_usd",9999000,"equity_inr",900000000,"initial_usd",10000000,"pnl_usd",-1000),"portfolio",json("reserve_usd",9200000),"settings",json("enabled",false,"entries_enabled",false,"max_entry_usd",250),"stats",json("open_positions",37,"closed_episodes",1504),"bots",bots,"history",history,"control_schema",new JSONArray()).toString());
        JSONArray stages=new JSONArray();String[] names={"Scout","Filter","Analyst","Executor","Risk","Logger"};for(int i=0;i<names.length;i++)stages.put(json("name",names[i],"value",i==0?3:i==5?42:0,"state",i==3?"stopped":"observing","detail","Explicit test fixture for "+names[i]));
        JSONArray checks=new JSONArray();String[] rules={"Executable market adapter","Fresh observed quote","Market turnover threshold","Fresh currency conversion","Verified lot metadata","Portfolio running","New entries allowed","Loss brake clear"};for(int i=0;i<rules.length;i++)checks.put(json("key","rule"+i,"title",rules[i],"passed",i<5,"detail","Saved fixture check detail"));
        JSONArray observations=new JSONArray();for(int i=0;i<30;i++)observations.put(json("ts",now-(30-i)*60,"price",1300+i*2));
        store.save(origin,"/api/terminal",json("focus",assets.getJSONObject(0),"history",observations,"stages",stages,"rules",checks,"agents",new JSONArray().put(json("bot","Model-01","model","gpt-test","score",62,"score_reason","Recorded fixture review; not a trading outcome.","entry_braked",true,"loss_streak",3)),"selected_bot","Model-01","settings",json("max_entry_usd",250,"max_allocation_pct",5,"entries_enabled",false),"statistics",json("closed_net",-1000,"fees",74,"wins",12,"losses",24,"closed",36,"fills",42,"wins_pct",33.33),"events",new JSONArray().put(json("ts",now,"kind","stopped","message","Simulation paused by owner; saved fixture event")),"markets",assets,"briefs",new JSONArray().put(json("symbol","RELIANCE.NS","model","gpt-test","state","completed","created",now,"body","Saved Mirai reply")),"mirai",json("key_configured",true)).toString());
        JSONArray bars=new JSONArray();for(int i=0;i<30;i++)bars.put(json("ts",now-(30-i)*300,"open",1300+i,"high",1302+i,"low",1299+i,"close",1301+i));store.save(origin,"/api/candles?symbol=RELIANCE.NS&span=1D",bars.toString());
    }
    ActivityController<MainActivity> launch(){return Robolectric.buildActivity(MainActivity.class).create().start().visible();}
    TextView find(View v,String exact){if(v instanceof TextView&&(((TextView)v).getText().toString().contains(exact)||(v instanceof EditText&&String.valueOf(((EditText)v).getHint()).equals(exact))))return (TextView)v;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++){TextView found=find(((ViewGroup)v).getChildAt(i),exact);if(found!=null)return found;}return null;}
    View root(MainActivity a){return a.findViewById(android.R.id.content);}
    boolean containsWebView(View v){if(v instanceof android.webkit.WebView)return true;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)if(containsWebView(((ViewGroup)v).getChildAt(i)))return true;return false;}
    void go(MainActivity a,String route)throws Exception{Method m=MainActivity.class.getDeclaredMethod("go",String.class);m.setAccessible(true);m.invoke(a,route);}
    void image(MainActivity a,String name,int width,int height)throws Exception{View decor=a.getWindow().getDecorView();decor.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));decor.layout(0,0,width,height);Bitmap b=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);decor.draw(new Canvas(b));File file=new File(System.getProperty("user.dir"),"build/native-screens/"+name+".png");file.getParentFile().mkdirs();try(FileOutputStream out=new FileOutputStream(file)){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();}
    @Test public void databaseSurvivesRestartAndKeepsNotesOffline()throws Exception{store.updateItem(origin,"RELIANCE.NS",true,"Device note");store.close();store=new LocalStore(context);assertEquals("Device note",store.item(origin,"RELIANCE.NS").getString("note"));assertTrue(store.item(origin,"RELIANCE.NS").getBoolean("pinned"));assertNotNull(store.read(origin,"/api/population?view=summary"));}
    @Test public void endpointIsolationPreventsAccountMixing()throws Exception{assertNull(store.read("https://other.invalid","/api/population?view=summary"));assertEquals(0,store.instruments("https://other.invalid","","All",false).length());}
    @Test public void serverNotesAndWatchlistImportWithoutOverwritingLocalEdits()throws Exception{assertEquals("Existing server note",store.item(origin,"BTC/USD").getString("note"));assertTrue(store.item(origin,"BTC/USD").getBoolean("pinned"));store.updateItem(origin,"BTC/USD",false,"My local edit");seed();assertFalse(store.item(origin,"BTC/USD").getBoolean("pinned"));assertEquals("My local edit",store.item(origin,"BTC/USD").getString("note"));}
    @Test public void cachedSearchAndMarketGroupsWorkOffline(){assertEquals(1,store.instruments(origin,"Reliance","India",false).length());assertEquals(1,store.instruments(origin,"","Crypto",false).length());assertEquals(2,store.instruments(origin,"","Stocks",false).length());assertEquals(0,store.instruments(origin,"%","All",false).length());}
    @Test public void clearingDownloadsPreservesDeviceWatchlistAndNotes(){store.updateItem(origin,"RELIANCE.NS",true,"Private note");store.clearCache(origin);assertTrue(store.item(origin,"RELIANCE.NS").optBoolean("pinned"));assertEquals("Private note",store.item(origin,"RELIANCE.NS").optString("note"));assertEquals(1,store.instruments(origin,"RELIANCE.NS","All",true).length());assertNull(store.read(origin,"/api/population?view=summary"));}
    @Test public void invalidServerDataCannotReplaceGoodPortfolio()throws Exception{String previous=store.read(origin,"/api/population?view=summary");try{store.save(origin,"/api/population?view=summary","{\"wrong\":true}");fail();}catch(IllegalArgumentException expected){}assertEquals(previous,store.read(origin,"/api/population?view=summary"));}
    @Test public void primaryHomeIsNativeAndReadsSavedPortfolioImmediately()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();assertFalse(containsWebView(root(a)));assertNotNull(find(root(a),"$9,999,000"));assertNotNull(find(root(a),"Trading stopped · saved portfolio"));image(a,"terminal-home",780,1688);Field sf=MainActivity.class.getDeclaredField("scroll");sf.setAccessible(true);((ScrollView)sf.get(a)).scrollTo(0,1500);image(a,"terminal-details",780,1688);}}
    @Test public void nativeNavigationAndOfflineMarketsHaveNoWebView()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();go(a,"markets");assertFalse(containsWebView(root(a)));assertNotNull(find(root(a),"Search saved symbols or companies"));go(a,"bots");assertNotNull(find(root(a),"Bots"));go(a,"research");assertNotNull(find(root(a),"Saved Mirai reply"));assertFalse(containsWebView(root(a)));image(a,"paper-research",780,1688);}}
    @Test public void nativeChartDrawsSavedCandlesWithoutBrowser()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();Field f=MainActivity.class.getDeclaredField("symbol");f.setAccessible(true);f.set(a,"RELIANCE.NS");go(a,"detail");assertFalse(containsWebView(root(a)));assertNotNull(find(root(a),"₹1,300"));image(a,"paper-instrument",780,1688);}}
    @Test public void darkThemeUsesNativeScreens()throws Exception{Connection.prefs(context).edit().putBoolean("native_night",true).commit();try(ActivityController<MainActivity> c=launch()){assertFalse(containsWebView(root(c.get())));image(c.get(),"graphite-home",780,1688);}}
    @Test public void smallPhoneAndLargeTextRemainNavigable()throws Exception{RuntimeEnvironment.setQualifiers("w320dp-h640dp-xhdpi");RuntimeEnvironment.setFontScale(1.3f);try(ActivityController<MainActivity> c=launch()){assertNotNull(find(root(c.get()),"⌕\nMarkets"));assertFalse(containsWebView(root(c.get())));image(c.get(),"small-large-text",640,1280);}}
    @Test public void nativeControlsDoNotStartTradingOnOpen()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();go(a,"controls");assertNotNull(find(root(a),"Portfolio stopped"));assertNotNull(find(root(a),"Start configured bots"));assertFalse(new JSONObject(store.read(origin,"/api/population?view=summary")).getJSONObject("settings").getBoolean("enabled"));}}
    @Test public void researchDraftPersistsAcrossNativeNavigation()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();go(a,"research");Field f=MainActivity.class.getDeclaredField("researchInput");f.setAccessible(true);((EditText)f.get(a)).setText("Keep this question on device");go(a,"markets");go(a,"research");assertEquals("Keep this question on device",((EditText)f.get(a)).getText().toString());}}
    @Test public void offlineStartIsBlockedWithoutARequest()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();go(a,"controls");find(root(a),"Start configured bots").performClick();assertTrue(org.robolectric.shadows.ShadowToast.getTextOfLatestToast().contains("Connect before changing trading state"));}}
    @Test public void nativeStartShowsReviewBeforeSubmitting()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();Field repository=MainActivity.class.getDeclaredField("repo");repository.setAccessible(true);((DeviceRepository)repository.get(a)).resourceHealth.succeeded(origin,"/api/population?view=summary",System.currentTimeMillis());go(a,"controls");find(root(a),"Start configured bots").performClick();AlertDialog dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();assertNotNull(dialog);assertTrue(dialog.isShowing());dialog.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();assertFalse(new JSONObject(store.read(origin,"/api/population?view=summary")).getJSONObject("settings").getBoolean("enabled"));}}
    @Test @Config(sdk=35) public void modernAndroidPrimaryScreenIsNative()throws Exception{try(ActivityController<MainActivity> c=launch()){assertFalse(containsWebView(root(c.get())));assertNotNull(find(root(c.get()),"$9,999,000"));image(c.get(),"android-15-home",780,1688);}}
    @Test public void failedMiraiReplyShowsTheActualSavedError()throws Exception{store.save(origin,"/api/terminal",json("briefs",new JSONArray().put(json("symbol","RELIANCE.NS","model","fixture","state","failed","body","","error","Authentication needs attention"))).toString());try(ActivityController<MainActivity> c=launch()){go(c.get(),"research");assertNotNull(find(root(c.get()),"Authentication needs attention"));}}
    @Test public void financialConfirmationCannotCrossServerConnections()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();Connection.prefs(context).edit().putString("endpoint","https://another.invalid").commit();Method m=MainActivity.class.getDeclaredMethod("guardedPost",String.class,String.class,JSONObject.class,DeviceRepository.Reply.class);m.setAccessible(true);final boolean[] called={false};m.invoke(a,origin,"/api/population/start",new JSONObject(),(DeviceRepository.Reply)(result,error)->called[0]=true);assertFalse(called[0]);assertTrue(org.robolectric.shadows.ShadowToast.getTextOfLatestToast().contains("Connection changed"));}}
    @Test public void adminRequiresUnlockAndDoesNotCachePasskey()throws Exception{try(ActivityController<MainActivity> c=launch()){MainActivity a=c.get();go(a,"admin");assertNotNull(find(root(a),"Unlock Admin"));assertNull(store.read(origin,"/api/admin/status"));}}

    @Test public void chartRefreshRetainsInspectionAndZoom()throws Exception{
        NativeChart chart=new NativeChart(context);JSONArray rows=new JSONArray();for(int i=0;i<40;i++)rows.put(json("ts",1700000000+i,"usd",100+i));
        chart.data(rows,false,"USD");Field zoom=NativeChart.class.getDeclaredField("zoom"),hover=NativeChart.class.getDeclaredField("hover"),offset=NativeChart.class.getDeclaredField("offset");zoom.setAccessible(true);hover.setAccessible(true);offset.setAccessible(true);zoom.setFloat(chart,3);hover.setInt(chart,25);offset.setInt(chart,4);
        chart.data(new JSONArray(rows.toString()),false,"USD");assertEquals(3,zoom.getFloat(chart),0);assertEquals(25,hover.getInt(chart));assertEquals(4,offset.getInt(chart));
        rows.put(json("ts",1700000040,"usd",141));chart.data(rows,false,"USD");assertEquals(3,zoom.getFloat(chart),0);assertEquals(25,hover.getInt(chart));
        chart.data(rows,true,"INR");assertEquals(1,zoom.getFloat(chart),0);assertEquals(-1,hover.getInt(chart));
    }
    @Test public void zoomedChartCanPanIntoEarlierHistory()throws Exception{
        NativeChart chart=new NativeChart(context);android.widget.FrameLayout parent=new android.widget.FrameLayout(context);parent.addView(chart);parent.layout(0,0,800,500);chart.layout(0,0,800,500);
        JSONArray rows=new JSONArray();for(int i=0;i<100;i++)rows.put(json("ts",1700000000+i,"usd",100+i));chart.data(rows,false,"USD");Field zoom=NativeChart.class.getDeclaredField("zoom"),offset=NativeChart.class.getDeclaredField("offset");zoom.setAccessible(true);offset.setAccessible(true);zoom.setFloat(chart,4);
        chart.setInspection(true);android.view.MotionEvent down=android.view.MotionEvent.obtain(0,0,android.view.MotionEvent.ACTION_DOWN,100,200,0),move=android.view.MotionEvent.obtain(0,20,android.view.MotionEvent.ACTION_MOVE,500,200,0);chart.onTouchEvent(down);chart.onTouchEvent(move);assertTrue(offset.getInt(chart)>0);down.recycle();move.recycle();
        chart.fit();assertEquals(0,offset.getInt(chart));assertEquals(1,zoom.getFloat(chart),0);
    }

    @Test public void nativeHomeContainsReferenceTerminalAndExpandableChecks()throws Exception{
        try(ActivityController<MainActivity> c=launch()){
            MainActivity a=c.get();assertNotNull(find(root(a),"DeckLab Terminal"));assertNotNull(find(root(a),"SCOUT / OBSERVED MARKETS"));assertNotNull(find(root(a),"EXECUTOR + RISK / MARKET VIEW"));assertNotNull(find(root(a),"LOGGER / ACTIVITY STREAM"));
            TextView rule=find(root(a),"Executable market adapter");assertNotNull(rule);((View)rule.getParent()).performClick();assertNotNull(find(root(a),"Saved fixture check detail"));assertFalse(containsWebView(root(a)));
        }
    }
    @Test @Config(qualifiers="w768dp-h1024dp-xhdpi") public void terminalRendersAtTabletWidth()throws Exception{
        try(ActivityController<MainActivity> c=launch()){assertNotNull(find(root(c.get()),"DeckLab Terminal"));image(c.get(),"terminal-tablet",1536,2048);}
    }

    @Test public void terminalCachedQuotesBecomeDelayedWithAge()throws Exception{
        try(ActivityController<MainActivity> c=launch()){
            Field field=MainActivity.class.getDeclaredField("terminalDashboard");field.setAccessible(true);TerminalDashboard terminal=(TerminalDashboard)field.get(c.get());Method fresh=TerminalDashboard.class.getDeclaredMethod("fresh",JSONObject.class);fresh.setAccessible(true);double now=System.currentTimeMillis()/1000.;
            JSONObject quote=json("quote_fresh",true,"kind","crypto","asof",now,"fetched",now);assertEquals(true,fresh.invoke(terminal,quote));
            quote.put("asof",now-180);assertEquals(false,fresh.invoke(terminal,quote));
            quote.put("asof",now-30).put("fetched",now-130);assertEquals(false,fresh.invoke(terminal,quote));
            quote.put("asof",now+60).put("fetched",now);assertEquals(false,fresh.invoke(terminal,quote));
        }
    }
    @Test public void dayTraderOpensBundledAnalysisWithoutTrading()throws Exception{
        try(ActivityController<MainActivity> c=launch()){
            MainActivity a=c.get();go(a,"more");TextView launch=find(root(a),"Day Trader · US stock analysis");assertNotNull(launch);launch.performClick();
            Intent intent=org.robolectric.Shadows.shadowOf(a).getNextStartedActivity();assertNotNull(intent);assertEquals("day-trader",intent.getStringExtra("workspace"));
            try(ActivityController<LegacyActivity> workspace=Robolectric.buildActivity(LegacyActivity.class,intent).create()){
                Field f=LegacyActivity.class.getDeclaredField("web");f.setAccessible(true);android.webkit.WebView web=(android.webkit.WebView)f.get(workspace.get());
                assertEquals("https://app.marketdeck.local/day-trader.html",org.robolectric.Shadows.shadowOf(web).getLastLoadedUrl());
                assertTrue(Connection.GET.contains("/api/day-trader"));assertTrue(Connection.POST.contains("/api/day-trader/run"));assertFalse(Connection.POST.contains("/api/day-trader/order"));
            }
            assertFalse(new JSONObject(store.read(origin,"/api/population?view=summary")).getJSONObject("settings").getBoolean("enabled"));
        }
    }
    @Test public void ownerPauseUsesFreshMatchingOriginReadiness()throws Exception{
        try(ActivityController<MainActivity> c=launch()){
            MainActivity a=c.get();Field f=MainActivity.class.getDeclaredField("repo");f.setAccessible(true);DeviceRepository r=(DeviceRepository)f.get(a);
            long now=System.currentTimeMillis();r.resourceHealth.succeeded(origin,"/api/population?view=summary",now);
            store.save(origin,"/api/v2/readiness",json("contract_version","2.0","owner_pause",json("active",true)).toString());
            r.resourceHealth.succeeded(origin,"/api/v2/readiness",now);
            Method online=MainActivity.class.getDeclaredMethod("online");online.setAccessible(true);
            assertEquals(false,online.invoke(a));
            Method update=MainActivity.class.getDeclaredMethod("updateData");update.setAccessible(true);update.invoke(a);
            assertNotNull(find(root(a),"OWNER PAUSE ACTIVE"));
            r.resourceHealth.failed(origin,"/api/v2/readiness",now+1,"offline");
            assertEquals(false,online.invoke(a));
            store.save(origin,"/api/v2/readiness",json("contract_version","2.0","owner_pause",json("active",false)).toString());
            r.resourceHealth.succeeded(origin,"/api/v2/readiness",now);
            assertEquals(true,online.invoke(a));
            Connection.prefs(context).edit().putString("endpoint","https://another.invalid").commit();
            assertEquals(false,online.invoke(a));
        }
    }

    @Test public void ownerPauseSafetyLatchSurvivesCacheClearAndRepositoryRestart()throws Exception{
        DeviceRepository first=new DeviceRepository(context,null);first.rememberOwnerPause(origin,true);
        first.store.clearCache(origin);assertTrue(first.ownerPauseVeto());first.close();
        DeviceRepository second=new DeviceRepository(context,null);assertTrue(second.ownerPauseVeto());
        second.rememberOwnerPause(origin,false);assertFalse(second.ownerPauseVeto());second.close();
    }

    @Test public void malformedOwnerPauseSafetyStateFailsClosed()throws Exception{
        context.getSharedPreferences("foundation-safety",Context.MODE_PRIVATE).edit().putString(origin,"malformed").commit();
        DeviceRepository repository=new DeviceRepository(context,null);assertTrue(repository.ownerPauseVeto());repository.close();
    }

}
