package com.marketdeck.app;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import org.json.*;
import java.text.*;
import java.util.*;

/** Device-rendered financial chart. Provider bars only; no HTML or generated prices. */
final class NativeChart extends View {
    private final Paint p=new Paint(3);private JSONArray rows=new JSONArray();private String currency="USD";
    private int ink=0xff19313d,muted=0xff73838a,accent=0xff007c79,negative=0xffc24868,edge=0xffe0e5e3;
    private boolean candles=false;private float zoom=1;private int hover=-1,offset=0;private float downX,downY;private int downOffset;private String series=""; private String identity="",source="Source unavailable";
    private boolean inspecting=false;
    private final ScaleGestureDetector scaling;private android.os.Bundle restored;
    NativeChart(Context c){super(c);setFocusable(true);setMinimumHeight(dp(220));setContentDescription("Price chart. Drag to inspect observations. Pinch to zoom. Arrow keys move the cursor.");scaling=new ScaleGestureDetector(c,new ScaleGestureDetector.SimpleOnScaleGestureListener(){@Override public boolean onScale(ScaleGestureDetector d){zoom=Math.max(1,Math.min(10,zoom*d.getScaleFactor()));hover=-1;invalidate();return true;}});}
    int sp(float x){return Math.round(x*getResources().getDisplayMetrics().scaledDensity);}
    int dp(float x){return Math.round(x*getResources().getDisplayMetrics().density);}
    void colors(int text,int dim,int green,int red,int line){ink=text;muted=dim;accent=green;negative=red;edge=line;invalidate();}
    void data(JSONArray value,boolean candle,String cur){data(value,candle,cur,"legacy",candle?"price":"portfolio",candle?"candles":"equity","default","Source unavailable");}
    void data(JSONArray value,boolean candle,String cur,String origin,String instrument,String kind,String interval,String provenance){
        String nextIdentity=origin+"\n"+instrument+"\n"+kind+"\n"+interval;
        if(!identity.equals(nextIdentity)){fit();identity=nextIdentity;}
        source=provenance;
        setContentDescription(instrument+" · "+kind+" · "+interval+" · "+cur+" · "+source+". Use arrow keys or accessibility actions to inspect observations.");
        JSONArray incoming=value==null?new JSONArray():value;String next=(candle?"candles":"equity")+":"+cur;
        if(!series.equals(next)){zoom=1;offset=0;hover=-1;series=next;}
        else if(incoming.toString().equals(rows.toString()))return;
        rows=incoming;candles=candle;currency=cur==null?"USD":cur;
        if(restored!=null){if(identity.equals(restored.getString("identity"))){zoom=Math.max(1,Math.min(10,restored.getFloat("zoom",1)));offset=Math.max(0,restored.getInt("offset",0));hover=restored.getInt("hover",-1);}restored=null;}
        offset=Math.min(offset,Math.max(0,rows.length()-2));hover=Math.min(hover,rows.length()-1);invalidate();
    }
    android.os.Bundle saveState(){android.os.Bundle b=new android.os.Bundle();b.putString("identity",identity);b.putFloat("zoom",zoom);b.putInt("offset",offset);b.putInt("hover",hover);return b;}
    void restoreState(android.os.Bundle b){restored=b;}
    void fit(){zoom=1;offset=0;hover=-1;invalidate();}
    private double number(JSONObject r,String k){return r.optDouble(k,Double.NaN);}
    private String price(double v){if(!Double.isFinite(v))return "—";return ("USD".equals(currency)?"$":"INR".equals(currency)?"₹":currency+" ")+new DecimalFormat(Math.abs(v)<1?"0.######":"#,##0.00").format(v);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);int count=rows.length();float w=getWidth(),h=getHeight(),left=dp(5),right=w-dp(75),top=dp(25),bottom=h-dp(30);p.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));p.setTextSize(sp(12));p.setColor(muted);
        if(count<2){c.drawText("No saved price history yet",dp(12),h/2,p);return;}
        int visible=Math.max(2,(int)(count/zoom)),end=Math.max(2,count-offset),start=Math.max(0,end-visible);double lo=Double.POSITIVE_INFINITY,hi=Double.NEGATIVE_INFINITY;
        for(int i=start;i<end;i++){JSONObject r=rows.optJSONObject(i);if(r==null)continue;double a=number(r,candles?"low":"usd"),b=number(r,candles?"high":"usd");if(Double.isFinite(a)&&Double.isFinite(b)){lo=Math.min(lo,a);hi=Math.max(hi,b);}}
        if(!Double.isFinite(lo)||!Double.isFinite(hi)){c.drawText("No valid observed values",dp(12),h/2,p);return;}
        double pad=Math.max((hi-lo)*.12,Math.max(.000001,Math.abs(hi)*.00001));lo-=pad;hi+=pad;double span=hi-lo;p.setTextSize(sp(12));right=Math.max(left+dp(20),w-Math.min(w*.48f,Math.max(dp(75),Math.max(p.measureText(price(lo)),p.measureText(price(hi)))+dp(10))));
        p.setStrokeWidth(dp(1));for(int i=0;i<4;i++){float y=top+(bottom-top)*i/3;p.setColor(edge);c.drawLine(left,y,right,y,p);p.setColor(muted);p.setTextSize(sp(12));c.drawText(android.text.TextUtils.ellipsize(price(hi-span*i/3),new android.text.TextPaint(p),Math.max(1,w-right-dp(10)),android.text.TextUtils.TruncateAt.END).toString(),right+dp(8),y+dp(3),p);}
        Path path=new Path();boolean begun=false;float step=(right-left)/Math.max(1,end-start-1);
        for(int i=start;i<end;i++){JSONObject r=rows.optJSONObject(i);if(r==null)continue;float x=left+(i-start)*step;double v=number(r,candles?"close":"usd");if(!Double.isFinite(v))continue;float y=(float)(top+(hi-v)/span*(bottom-top));
            if(candles){double open=number(r,"open"),high=number(r,"high"),low=number(r,"low");if(!Double.isFinite(open)||!Double.isFinite(high)||!Double.isFinite(low))continue;p.setColor(v>=open?accent:negative);p.setStrokeWidth(dp(1));c.drawLine(x,(float)(top+(hi-high)/span*(bottom-top)),x,(float)(top+(hi-low)/span*(bottom-top)),p);float oy=(float)(top+(hi-open)/span*(bottom-top));float half=Math.max(dp(1),Math.min(dp(7),step*.32f));c.drawRect(x-half,Math.min(oy,y),x+half,Math.max(Math.min(oy,y)+dp(1),Math.max(oy,y)),p);}
            else{if(!begun){path.moveTo(x,y);begun=true;}else path.lineTo(x,y);}
        }
        if(!candles&&begun){Path fill=new Path(path);fill.lineTo(right,bottom);fill.lineTo(left,bottom);fill.close();p.setShader(new LinearGradient(0,top,0,bottom,(accent&0xffffff)|0x33000000,accent&0xffffff,Shader.TileMode.CLAMP));p.setStyle(Paint.Style.FILL);c.drawPath(fill,p);p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(dp(2));p.setColor(accent);c.drawPath(path,p);p.setStyle(Paint.Style.FILL);}
        SimpleDateFormat fmt=new SimpleDateFormat("HH:mm",Locale.getDefault());p.setColor(muted);p.setTextSize(sp(12));JSONObject first=rows.optJSONObject(start),last=rows.optJSONObject(end-1);if(first!=null)c.drawText(fmt.format(new Date((long)(first.optDouble("ts")*1000))),left,h-dp(10),p);if(last!=null)c.drawText(fmt.format(new Date((long)(last.optDouble("ts")*1000))),right-dp(32),h-dp(10),p);
        if(hover>=start&&hover<end){JSONObject r=rows.optJSONObject(hover);if(r!=null){double v=number(r,candles?"close":"usd");float x=left+(hover-start)*step;p.setColor(muted);p.setStrokeWidth(dp(1));c.drawLine(x,top,x,bottom,p);p.setColor(ink);p.setTextSize(sp(13));String label=price(v)+"  ·  "+fmt.format(new Date((long)(r.optDouble("ts")*1000)));c.drawText(label,left,dp(15),p);setContentDescription(label+" · "+source);}}
    }
    @Override public boolean onTouchEvent(android.view.MotionEvent e){if(rows.length()<2)return false;if(!inspecting){if(e.getActionMasked()==MotionEvent.ACTION_UP){setInspection(true);performClick();}return true;}scaling.onTouchEvent(e);if(e.getActionMasked()==MotionEvent.ACTION_DOWN){downX=e.getX();downY=e.getY();downOffset=offset;if(getParent()!=null)getParent().requestDisallowInterceptTouchEvent(false);requestFocus();}if(e.getActionMasked()==MotionEvent.ACTION_MOVE)if(getParent()!=null)getParent().requestDisallowInterceptTouchEvent(e.getPointerCount()>1||Math.abs(e.getX()-downX)>Math.abs(e.getY()-downY));
        if(!scaling.isInProgress()){if(zoom>1&&e.getActionMasked()==MotionEvent.ACTION_MOVE&&e.getPointerCount()==1&&Math.abs(e.getX()-downX)>Math.abs(e.getY()-downY)){int visibleCount=Math.max(2,(int)(rows.length()/zoom));offset=Math.max(0,Math.min(Math.max(0,rows.length()-visibleCount),downOffset+Math.round((e.getX()-downX)/Math.max(1,getWidth()-dp(80))*visibleCount)));}int count=rows.length(),visible=Math.max(2,(int)(count/zoom)),end=Math.max(2,count-offset),start=Math.max(0,end-visible);hover=Math.max(start,Math.min(end-1,start+Math.round(Math.max(0,Math.min(1,(e.getX()-dp(5))/Math.max(1,getWidth()-dp(80))))*(end-start-1))));invalidate();}
        if(e.getActionMasked()==MotionEvent.ACTION_UP){performClick();if(getParent()!=null)getParent().requestDisallowInterceptTouchEvent(false);}if(e.getActionMasked()==MotionEvent.ACTION_CANCEL)if(getParent()!=null)getParent().requestDisallowInterceptTouchEvent(false);return true;}
    @Override public boolean performClick(){super.performClick();return true;}
    int pageCount(){return Math.max(1,(rows.length()+99)/100);}
    boolean inspecting(){return inspecting;}
    void setInspection(boolean active){inspecting=active;setContentDescription((active?"Chart inspection active. Horizontal drag or pinch; swipe vertically to scroll page.":"Chart inspection off. Tap to inspect; vertical swipe scrolls page.")+" · "+source);invalidate();}
    String table(){return table(0);}
    String table(int page){page=Math.max(0,Math.min(pageCount()-1,page));int begin=page*100,end=Math.min(rows.length(),begin+100);StringBuilder out=new StringBuilder("Showing "+(rows.length()==0?0:begin+1)+"–"+end+" of "+rows.length()+" observations. Page "+(page+1)+" of "+pageCount()+"\n"+identity.replace('\n',' ')+"\n"+source+"\n"+currency+" · source timestamps\n");
        for(int i=begin;i<end;i++){JSONObject r=rows.optJSONObject(i);if(r==null)continue;out.append(new Date((long)(r.optDouble("ts")*1000))).append(" · ");if(candles)for(String k:new String[]{"open","high","low","close"})out.append(k).append(' ').append(price(number(r,k))).append("  ");else out.append(price(number(r,"usd")));out.append('\n');}return out.toString();}
    @Override public void onInitializeAccessibilityNodeInfo(android.view.accessibility.AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(info);info.addAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD);info.addAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD);info.addAction(new android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction(0x01020001,"Reset chart range"));}
    @Override public boolean performAccessibilityAction(int action,android.os.Bundle args){if(action==0x01020001){fit();return true;}if(action==android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_FORWARD||action==android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD){onKeyDown(action==android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_FORWARD?KeyEvent.KEYCODE_DPAD_RIGHT:KeyEvent.KEYCODE_DPAD_LEFT,null);JSONObject r=rows.optJSONObject(hover);if(r!=null){setContentDescription(price(number(r,candles?"close":"usd"))+" · "+new Date((long)(r.optDouble("ts")*1000))+" · "+source);sendAccessibilityEvent(android.view.accessibility.AccessibilityEvent.TYPE_VIEW_SELECTED);}return true;}return super.performAccessibilityAction(action,args);}
    @Override public boolean onKeyDown(int key,KeyEvent e){if(rows.length()==0)return false;if(key==KeyEvent.KEYCODE_DPAD_LEFT||key==KeyEvent.KEYCODE_DPAD_RIGHT){hover=Math.max(0,Math.min(rows.length()-1,(hover<0?rows.length()-1:hover)+(key==KeyEvent.KEYCODE_DPAD_LEFT?-1:1)));int visible=Math.max(2,(int)(rows.length()/zoom));if(hover>=rows.length()-offset)offset=Math.max(0,rows.length()-hover-1);if(hover<rows.length()-offset-visible)offset=Math.max(0,rows.length()-hover-visible);invalidate();return true;}return super.onKeyDown(key,e);}
}
