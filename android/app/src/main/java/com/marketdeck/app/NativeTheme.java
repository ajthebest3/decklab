package com.marketdeck.app;
import android.content.Context;
/** Shared New Era native tokens; density adjusts spacing, never system font scale. */
final class NativeTheme {
    static final int BG=0xff08080b,PANEL=0xff121218,EDGE=0xff34343f,INK=0xfff4f1f8,DIM=0xffb1adbf,ACCENT=0xffefd0bb;
    static boolean comfortable(Context c){return Connection.prefs(c).getBoolean("comfortable_density",true);}
    static int spacing(Context c){return comfortable(c)?18:12;}
}
