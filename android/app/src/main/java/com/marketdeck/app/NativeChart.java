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
    private boolean candles=false;private float zoom=1;private int hover=-1,offset=0;private float downX,downY;private int downOffset;private String series="";
    private final ScaleGestureDetector scaling;
    NativeChart(Context c){super(c);setFocusable(true);setMinimumHeight(dp(220));setContentDescription("Price chart. Drag to inspect observations. Pinch to zoom. Arrow keys move the cursor.");scaling=new ScaleGestureDetector(c,new ScaleGestureDetector.SimpleOnScaleGestureListener(){@Override public boolean onScale(ScaleGestureDetector d){zoom=Math.max(1,Math.min(10,zoom*d.getScaleFactor()));hover=-1;invalidate();return true;}});}
    int dp(float x){return Math.round(x*getResources().getDisplayMetrics().density);}
    void colors(int text,int dim,int green,int red,int line){ink=text;muted=dim;accent=green;negative=red;edge=line;invalidate();}
    void data(JSONArray value,boolean candle,String cur){
        JSONArray incoming=value==null?new JSONArray():value;String next=(candle?"candles":"equity")+":"+cur;
        if(!series.equals(next)){zoom=1;offset=0;hover=-1;series=next;}
        else if(incoming.toString().equals(rows.toString()))return;
        rows=incoming;candles=candle;currency=cur==null?"USD":cur;
        offset=Math.min(offset,Math.max(0,rows.length()-2));hover=Math.min(hover,rows.length()-1);invalidate();
    }
    void fit(){zoom=1;offset=0;hover=-1;invalidate();}
    private double number(JSONObject r,String k){return r.optDouble(k,Double.NaN);}
    private String price(double v){if(!Double.isFinite(v))return "—";return ("USD".equals(currency)?"$":"INR".equals(currency)?"₹":currency+" ")+new DecimalFormat(Math.abs(v)<1?"0.######":"#,##0.00").format(v);}
    @Override protected void onDraw(Canvas c){super.onDraw(c);int count=rows.length();float w=getWidth(),h=getHeight(),left=dp(5),right=w-dp(75),top=dp(25),bottom=h-dp(30);p.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));p.setTextSize(dp(10));p.setColor(muted);
        if(count<2){c.drawText("No saved price history yet",dp(12),h/2,p);return;}
        int visible=Math.max(2,(int)(count/zoom)),end=Math.max(2,count-offset),start=Math.max(0,end-visible);double lo=Double.POSITIVE_INFINITY,hi=Double.NEGATIVE_INFINITY;
        for(int i=start;i<end;i++){JSONObject r=rows.optJSONObject(i);if(r==null)continue;double a=number(r,candles?"low":"usd"),b=number(r,candles?"high":"usd");if(Double.isFinite(a)&&Double.isFinite(b)){lo=Math.min(lo,a);hi=Math.max(hi,b);}}
        if(!Double.isFinite(lo)||!Double.isFinite(hi)){c.drawText("No valid observed values",dp(12),h/2,p);return;}
        double pad=Math.max((hi-lo)*.12,Math.max(.000001,Math.abs(hi)*.00001));lo-=pad;hi+=pad;double span=hi-lo;
        p.setStrokeWidth(dp(1));for(int i=0;i<4;i++){float y=top+(bottom-top)*i/3;p.setColor(edge);c.drawLine(left,y,right,y,p);p.setColor(muted);p.setTextSize(dp(9));c.drawText(price(hi-span*i/3),right+dp(8),y+dp(3),p);}
        Path path=new Path();boolean begun=false;float step=(right-left)/Math.max(1,end-start-1);
        for(int i=start;i<end;i++){JSONObject r=rows.optJSONObject(i);if(r==null)continue;float x=left+(i-start)*step;double v=number(r,candles?"close":"usd");if(!Double.isFinite(v))continue;float y=(float)(top+(hi-v)/span*(bottom-top));
            if(candles){double open=number(r,"open"),high=number(r,"high"),low=number(r,"low");if(!Double.isFinite(open)||!Double.isFinite(high)||!Double.isFinite(low))continue;p.setColor(v>=open?accent:negative);p.setStrokeWidth(dp(1));c.drawLine(x,(float)(top+(hi-high)/span*(bottom-top)),x,(float)(top+(hi-low)/span*(bottom-top)),p);float oy=(float)(top+(hi-open)/span*(bottom-top));float half=Math.max(dp(1),Math.min(dp(7),step*.32f));c.drawRect(x-half,Math.min(oy,y),x+half,Math.max(Math.min(oy,y)+dp(1),Math.max(oy,y)),p);}
            else{if(!begun){path.moveTo(x,y);begun=true;}else path.lineTo(x,y);}
        }
        if(!candles&&begun){Path fill=new Path(path);fill.lineTo(right,bottom);fill.lineTo(left,bottom);fill.close();p.setShader(new LinearGradient(0,top,0,bottom,(accent&0xffffff)|0x33000000,accent&0xffffff,Shader.TileMode.CLAMP));p.setStyle(Paint.Style.FILL);c.drawPath(fill,p);p.setShader(null);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(dp(2));p.setColor(accent);c.drawPath(path,p);p.setStyle(Paint.Style.FILL);}
        SimpleDateFormat fmt=new SimpleDateFormat("HH:mm",Locale.getDefault());p.setColor(muted);p.setTextSize(dp(9));JSONObject first=rows.optJSONObject(start),last=rows.optJSONObject(end-1);if(first!=null)c.drawText(fmt.format(new Date((long)(first.optDouble("ts")*1000))),left,h-dp(10),p);if(last!=null)c.drawText(fmt.format(new Date((long)(last.optDouble("ts")*1000))),right-dp(32),h-dp(10),p);
        if(hover>=start&&hover<end){JSONObject r=rows.optJSONObject(hover);if(r!=null){double v=number(r,candles?"close":"usd");float x=left+(hover-start)*step;p.setColor(muted);p.setStrokeWidth(dp(1));c.drawLine(x,top,x,bottom,p);p.setColor(ink);p.setTextSize(dp(11));String label=price(v)+"  ·  "+fmt.format(new Date((long)(r.optDouble("ts")*1000)));c.drawText(label,left,dp(15),p);setContentDescription(label);}}
    }
    @Override public boolean onTouchEvent(android.view.MotionEvent e){scaling.onTouchEvent(e);if(e.getActionMasked()==MotionEvent.ACTION_DOWN){downX=e.getX();downY=e.getY();downOffset=offset;getParent().requestDisallowInterceptTouchEvent(false);requestFocus();}if(e.getActionMasked()==MotionEvent.ACTION_MOVE)getParent().requestDisallowInterceptTouchEvent(e.getPointerCount()>1||Math.abs(e.getX()-downX)>Math.abs(e.getY()-downY));
        if(!scaling.isInProgress()){if(zoom>1&&e.getActionMasked()==MotionEvent.ACTION_MOVE&&e.getPointerCount()==1&&Math.abs(e.getX()-downX)>Math.abs(e.getY()-downY)){int visibleCount=Math.max(2,(int)(rows.length()/zoom));offset=Math.max(0,Math.min(Math.max(0,rows.length()-visibleCount),downOffset+Math.round((e.getX()-downX)/Math.max(1,getWidth()-dp(80))*visibleCount)));}int count=rows.length(),visible=Math.max(2,(int)(count/zoom)),end=Math.max(2,count-offset),start=Math.max(0,end-visible);hover=Math.max(start,Math.min(end-1,start+Math.round(Math.max(0,Math.min(1,(e.getX()-dp(5))/Math.max(1,getWidth()-dp(80))))*(end-start-1))));invalidate();}
        if(e.getActionMasked()==MotionEvent.ACTION_UP){performClick();getParent().requestDisallowInterceptTouchEvent(false);}if(e.getActionMasked()==MotionEvent.ACTION_CANCEL)getParent().requestDisallowInterceptTouchEvent(false);return true;}
    @Override public boolean performClick(){super.performClick();return true;}
    @Override public boolean onKeyDown(int key,KeyEvent e){if(key==KeyEvent.KEYCODE_DPAD_LEFT||key==KeyEvent.KEYCODE_DPAD_RIGHT){hover=Math.max(0,Math.min(rows.length()-1,(hover<0?rows.length()-1:hover)+(key==KeyEvent.KEYCODE_DPAD_LEFT?-1:1)));int visible=Math.max(2,(int)(rows.length()/zoom));if(hover>=rows.length()-offset)offset=Math.max(0,rows.length()-hover-1);if(hover<rows.length()-offset-visible)offset=Math.max(0,rows.length()-hover-visible);invalidate();return true;}return super.onKeyDown(key,e);}
}
