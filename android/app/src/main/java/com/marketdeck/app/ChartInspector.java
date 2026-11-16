package com.marketdeck.app;

import android.app.AlertDialog;
import android.content.Context;
import android.view.View;
import android.widget.*;

/** Accessible, explicitly paged equivalent of every observed Canvas point. */
final class ChartInspector {
    static void show(Context c,NativeChart chart){
        int dp=Math.round(c.getResources().getDisplayMetrics().density*16);
        LinearLayout root=new LinearLayout(c);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp,dp,dp,dp);
        TextView values=new TextView(c);values.setTextSize(14);values.setTextIsSelectable(true);values.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        ScrollView scroll=new ScrollView(c);scroll.addView(values);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout controls=new LinearLayout(c);root.addView(controls);Button previous=new Button(c),next=new Button(c);previous.setText("Previous page");next.setText("Next page");previous.setMinHeight(dp*3);next.setMinHeight(dp*3);
        controls.addView(previous,new LinearLayout.LayoutParams(0,-2,1));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.leftMargin=dp/2;controls.addView(next,lp);
        final int[] page={0};Runnable bind=()->{values.setText(chart.table(page[0]));previous.setEnabled(page[0]>0);next.setEnabled(page[0]+1<chart.pageCount());scroll.scrollTo(0,0);};
        previous.setOnClickListener(v->{page[0]--;bind.run();});next.setOnClickListener(v->{page[0]++;bind.run();});bind.run();
        AlertDialog dialog=new AlertDialog.Builder(c).setTitle("Observed values and source times").setView(root).setPositiveButton("Close",null).create();dialog.show();if(dialog.getWindow()!=null)dialog.getWindow().setLayout(-1,Math.round(c.getResources().getDisplayMetrics().heightPixels*.85f));
    }
}
