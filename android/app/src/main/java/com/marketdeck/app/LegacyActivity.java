package com.marketdeck.app;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.webkit.*;
import android.widget.FrameLayout;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.util.concurrent.*;

public class LegacyActivity extends Activity {
    private WebView web;
    private final ExecutorService requests = new ThreadPoolExecutor(3,3,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(24));
    private boolean ready=false;
    private boolean keyboardVisible=false;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(11,16,20));
        getWindow().setNavigationBarColor(Color.rgb(11,16,20));
        FrameLayout container=new FrameLayout(this);
        container.setBackgroundColor(Color.rgb(11,16,20));
        web=new WebView(this);web.setBackgroundColor(Color.rgb(11,16,20));
        container.addView(web,new FrameLayout.LayoutParams(-1,-1));setContentView(container);
        if(Build.VERSION.SDK_INT>=30)getWindow().setDecorFitsSystemWindows(false);
        container.setOnApplyWindowInsetsListener((v,insets)->{
            if(Build.VERSION.SDK_INT>=30) {
                int handled=WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout()|WindowInsets.Type.ime();
                android.graphics.Insets i=insets.getInsets(handled);
                setKeyboardVisible(insets.isVisible(WindowInsets.Type.ime()));
                // Resize the child's actual bounds, including its fixed-position HTML elements.
                v.setPadding(i.left,i.top,i.right,i.bottom);
                // Tell WebView the native container already handled these insets.
                return new WindowInsets.Builder(insets).setInsets(handled,android.graphics.Insets.NONE).setInsetsIgnoringVisibility(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout(),android.graphics.Insets.NONE).build();
            }
            v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets.replaceSystemWindowInsets(0,0,0,0);
        });
        container.requestApplyInsets();
        web.setVerticalScrollBarEnabled(false);web.setHorizontalScrollBarEnabled(false);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(false);
        web.addJavascriptInterface(new Bridge(),"MarketDeckNative");
        web.setWebViewClient(new WebViewClient(){
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri u=request.getUrl();String path=u.getPath();
                if("https".equals(u.getScheme()) && "app.marketdeck.local".equals(u.getHost()) && ("/day-trader.html".equals(path)||"/day-trader.js".equals(path)||"/day-trader.css".equals(path)||"/".equals(path)||"/app.js".equals(path)||"/features.js".equals(path)||"/coverage.js".equals(path)||"/demo.js".equals(path)||"/admin.js".equals(path)||"/ai-settings.js".equals(path)||"/demo.css".equals(path)||"/style.css".equals(path)||"/terminal.js".equals(path)||"/terminal.css".equals(path)||"/vendor/lightweight-charts.js".equals(path)||"/vendor/lightweight-charts.LICENSE.txt".equals(path)||"/vendor/lightweight-charts.NOTICE.txt".equals(path))) {
                    try{return new WebResourceResponse(path.endsWith(".js")?"application/javascript":path.endsWith(".css")?"text/css":"text/html","UTF-8",getAssets().open("/".equals(path)?"index.html":path.substring(1)));}catch(Exception ignored){}
                }
                return new WebResourceResponse("text/plain","UTF-8",403,"Blocked",java.util.Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){
                Uri u=r.getUrl();
                if(r.hasGesture() && ("https".equals(u.getScheme())||"http".equals(u.getScheme()))) try{startActivity(new Intent(Intent.ACTION_VIEW,u));}catch(Exception ignored){}
                return true;
            }
            @Override public void onPageFinished(WebView v,String url){ ready=true;applyKeyboardState();dispatchRoute(); }
        });
        if(Build.VERSION.SDK_INT>=33) getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0,()->web.evaluateJavascript("window.appBack&&appBack()",null));
        web.loadUrl("https://app.marketdeck.local/"+("day-trader".equals(getIntent().getStringExtra("workspace"))?"day-trader.html":""));
    }
    // API 33+ uses the registered OnBackInvokedCallback above; this is for API 26–32.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){if(web!=null)web.evaluateJavascript("window.appBack&&appBack()",null);}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);dispatchRoute();}
    private void dispatchRoute(){String route=getIntent().getStringExtra("route");if(ready&&route!=null){web.evaluateJavascript("window.openRoute&&openRoute("+JSONObject.quote(route)+")",null);getIntent().removeExtra("route");}}
    private void stateChanged(){if(web!=null)web.evaluateJavascript("window.dispatchEvent(new Event('native-state'))",null);}
    private void setKeyboardVisible(boolean visible){if(keyboardVisible!=visible){keyboardVisible=visible;if(ready)applyKeyboardState();}}
    private void applyKeyboardState(){if(web!=null)web.evaluateJavascript("document.documentElement.classList.toggle('keyboard-open',"+keyboardVisible+")",null);}
    private void enableNotifications(){
        if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},7);return;}
        Connection.prefs(this).edit().putBoolean("notifications",true).apply();
        startForegroundService(new Intent(this,NotificationService.class));stateChanged();
    }
    @Override public void onRequestPermissionsResult(int code,String[] p,int[] result){super.onRequestPermissionsResult(code,p,result);if(code==7&&result.length>0&&result[0]==PackageManager.PERMISSION_GRANTED)enableNotifications();else stateChanged();}
    final class Bridge {
        @JavascriptInterface public String settings(){
            try{return new JSONObject().put("endpoint",Connection.endpoint(LegacyActivity.this)).put("notifications",Connection.prefs(LegacyActivity.this).getBoolean("notifications",false)).put("permission",getSystemService(NotificationManager.class).areNotificationsEnabled()).put("stream",NotificationService.status).toString();}catch(Exception e){return "{}";}
        }
        @JavascriptInterface public String configure(String endpoint){
            try{String normalized=Connection.validate(endpoint);if(!normalized.equals(Connection.endpoint(LegacyActivity.this))){Connection.prefs(LegacyActivity.this).edit().putString("endpoint",normalized).remove("cursor").apply();runOnUiThread(()->{stopService(new Intent(LegacyActivity.this,NotificationService.class));if(Connection.prefs(LegacyActivity.this).getBoolean("notifications",false))enableNotifications();});}return "";}catch(Exception e){return e.getMessage();}
        }
        @JavascriptInterface public void request(String id,String method,String path,String body){
            try{requests.execute(()->{String value;try{value=new JSONObject().put("ok",true).put("body",Connection.request(LegacyActivity.this,method,path,body)).toString();}catch(Exception e){try{value=new JSONObject().put("ok",false).put("error",e instanceof java.net.ConnectException?"Cannot reach Market Deck. Check the server address and your SSH tunnel.":e.getMessage()==null?"Connection failed":e.getMessage()).toString();}catch(Exception ignored){value="{}";}}String result=value;runOnUiThread(()->{if(web!=null)web.evaluateJavascript("window.nativeReply("+JSONObject.quote(id)+","+result+")",null);});});}catch(RejectedExecutionException e){runOnUiThread(()->web.evaluateJavascript("window.nativeReply("+JSONObject.quote(id)+",{ok:false,error:'Too many requests. Try again.'})",null));}
        }
        @JavascriptInterface public void notifications(boolean enabled){runOnUiThread(()->{if(enabled)enableNotifications();else{Connection.prefs(LegacyActivity.this).edit().putBoolean("notifications",false).apply();stopService(new Intent(LegacyActivity.this,NotificationService.class));stateChanged();}});}
        @JavascriptInterface public void testNotification(){runOnUiThread(()->NotificationService.test(LegacyActivity.this));}
        @JavascriptInterface public void systemSettings(){runOnUiThread(()->startActivity(new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName())));}
        @JavascriptInterface public void closeWorkspace(){runOnUiThread(()->finish());}
        @JavascriptInterface public void openDayTrader(){runOnUiThread(()->startActivity(new Intent(LegacyActivity.this,LegacyActivity.class).putExtra("workspace","day-trader")));}
        @JavascriptInterface public void minimize(){runOnUiThread(()->moveTaskToBack(true));}
    }
    @Override protected void onResume(){
        super.onResume();
        if(Connection.prefs(this).getBoolean("notifications",false) && getSystemService(NotificationManager.class).areNotificationsEnabled())startForegroundService(new Intent(this,NotificationService.class));
        if(ready)stateChanged();
    }
    @Override protected void onDestroy(){requests.shutdownNow();if(web!=null){web.removeJavascriptInterface("MarketDeckNative");web.destroy();web=null;}super.onDestroy();}
}
