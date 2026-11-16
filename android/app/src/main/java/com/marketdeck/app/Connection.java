package com.marketdeck.app;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.HashSet;
import java.util.Arrays;

final class Connection {
    static final Set<String> GET = new HashSet<>(Arrays.asList("/api/state", "/api/health", "/api/v2/readiness", "/api/candles", "/api/microstructure", "/api/search", "/api/mobile/notifications", "/api/chat", "/api/catalog", "/api/coverage", "/api/instrument", "/api/news", "/api/demo", "/api/demo/detail", "/api/population", "/api/population/detail", "/api/ai-settings", "/api/ai-models", "/api/admin/info", "/api/terminal", "/api/day-trader"));
    static final Set<String> POST = new HashSet<>(Arrays.asList("/api/watchlist", "/api/note", "/api/order-preview", "/api/orders", "/api/alerts", "/api/alert-delete", "/api/settings", "/api/research-settings", "/api/research-run", "/api/track", "/api/ai", "/api/chat", "/api/demo/settings", "/api/demo/run", "/api/population/settings", "/api/population/run", "/api/population/start", "/api/population/stop", "/api/ai-settings", "/api/ai-models", "/api/ai-assignments", "/api/ai-roster", "/api/ai-test", "/api/admin/unlock", "/api/admin/status", "/api/admin/command", "/api/admin/cancel", "/api/admin/resolve", "/api/admin/lock", "/api/admin/passkey", "/api/terminal/research", "/api/day-trader/run"));
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("connection", Context.MODE_PRIVATE); }
    static String endpoint(Context c) { return prefs(c).getString("endpoint", "http://localhost:8790"); }
    static String validate(String value) throws Exception {
        URI uri = new URI(value.trim());
        String host = uri.getHost(), scheme = uri.getScheme();
        boolean local = "127.0.0.1".equals(host) || "localhost".equals(host) || "10.0.2.2".equals(host);
        if (host == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null ||
                !("https".equals(scheme) || ("http".equals(scheme) && local)) ||
                !(uri.getPath().isEmpty() || uri.getPath().equals("/")) || uri.getPort() == 0)
            throw new IllegalArgumentException("Use a localhost tunnel address or a private HTTPS origin, without a path.");
        return scheme + "://" + host + (uri.getPort() == -1 ? "" : ":" + uri.getPort());
    }
    static HttpURLConnection open(Context c, String path) throws Exception { return openAt(endpoint(c),path); }
    static HttpURLConnection openAt(String endpoint, String path) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(endpoint + path).openConnection();
        con.setConnectTimeout(12000); con.setReadTimeout(25000); con.setInstanceFollowRedirects(false);
        con.setRequestProperty("Accept", "application/json");
        con.setRequestProperty("User-Agent", "MarketDeck-Android/1.0");
        if (new URL(endpoint).getHost().equals("10.0.2.2")) con.setRequestProperty("Host", "127.0.0.1:8790");
        return con;
    }
    static String request(Context c, String method, String path, String body) throws Exception { return requestAt(endpoint(c),method,path,body); }
    static final class RequestHandle {
        volatile HttpURLConnection connection;volatile boolean cancelled;volatile java.util.concurrent.FutureTask<Void> task;
        synchronized void attach(HttpURLConnection value)throws IOException{if(cancelled){value.disconnect();throw new IOException("Read cancelled");}connection=value;}
        synchronized void cancel(){cancelled=true;if(connection!=null)connection.disconnect();if(task!=null)task.cancel(true);}
    }
    static String requestAt(String endpoint,String method,String path,String body) throws Exception {return requestAt(endpoint,method,path,body,null);}
    static String requestAt(String endpoint,String method,String path,String body,RequestHandle handle) throws Exception {
        if (!path.startsWith("/api/") || path.contains("#") || path.contains("\\") || path.contains("..") || path.contains("\r") || path.contains("\n")) throw new IOException("Unsupported API path");
        String route = path.split("\\?",2)[0];
        if (!(method.equals("GET") && GET.contains(route)) && !(method.equals("POST") && POST.contains(route))) throw new IOException("Unsupported API request");
        HttpURLConnection con = openAt(endpoint,path);
        if(handle!=null)handle.attach(con);
        try {
            con.setRequestMethod(method);
            if (method.equals("POST")) {
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                if(bytes.length > (route.equals("/api/ai-assignments") ? 120000 : 20000)) throw new IOException("Request too large");
                con.setDoOutput(true); con.setRequestProperty("Content-Type", "application/json"); con.setFixedLengthStreamingMode(bytes.length);
                try(OutputStream out = con.getOutputStream()) { out.write(bytes); }
            }
            int status = con.getResponseCode();
            InputStream source = status < 400 ? con.getInputStream() : con.getErrorStream();
            String result = read(source);
            if(status < 200 || status >= 300) {
                String error = "Server returned HTTP " + status;
                try { error = new JSONObject(result).optString("error",error); } catch(Exception ignored) { }
                throw new IOException(error);
            }
            return result;
        } finally { con.disconnect(); }
    }
    static String read(InputStream source) throws IOException {
        if(source == null) return "{}";
        try(InputStream in=source; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192]; int n;
            while((n=in.read(buf))!=-1) { out.write(buf,0,n); if(out.size()>4000000) throw new IOException("Response too large"); }
            return out.toString("UTF-8");
        }
    }
}
