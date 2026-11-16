package com.marketdeck.app;
import android.os.Bundle;
import java.util.*;
/** Allowlisted, origin-bound presentation state. No credentials or pending commands. */
final class ScreenState {
    static final String[] TEXT={"route","symbol","range","researchSymbol","search","marketGroup","activityKind","activityBot","directoryQuery","directoryRegion","dashboardSymbol","dashboardBot"};
    static Bundle restore(Bundle saved,String origin){return saved!=null&&origin.equals(saved.getString("stateOrigin"))?saved:new Bundle();}
    static void strings(Bundle out,String... values){if(values.length!=TEXT.length)throw new IllegalArgumentException("Presentation fields mismatch");for(int i=0;i<TEXT.length;i++)out.putString(TEXT[i],values[i]);}
    static void saveScrolls(Bundle out,Map<String,Integer> values){Bundle b=new Bundle();for(Map.Entry<String,Integer> e:values.entrySet())b.putInt(e.getKey(),e.getValue());out.putBundle("scrolls",b);}
    static void restoreScrolls(Bundle in,Map<String,Integer> values){Bundle b=in.getBundle("scrolls");if(b!=null)for(String key:b.keySet())values.put(key,b.getInt(key));}
}
