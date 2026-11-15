package com.rem.body.character;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.Color;
import android.net.Uri;
import android.os.Looper;
import android.view.View;
import android.view.Display;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** Standalone staging component. The containing app supplies played-audio amplitude. */
public final class BustRemView extends WebView {
    public interface Listener { void ready(); void failed(String message); }
    private static final Set<String> AXES=new HashSet<>(Arrays.asList("JOY","SHY","AFFECTION","SAD","IRRITATED","SURPRISED","SLEEPY","CURIOUS"));
    private static final String ROOT="rem-bust-v4/";
    private boolean ready,resumed,released;
    private Listener listener;
    private String outfit="lpk-original";
    private final JSONObject tones=new JSONObject();
    private RemMotionSensor motionSensor;
    private boolean motionEnabled=true,motionActive;
    private double motionSensitivity=1;

    @SuppressLint({"SetJavaScriptEnabled","AddJavascriptInterface"})
    public BustRemView(Context context) {
        super(context);mainThread();setBackgroundColor(Color.TRANSPARENT);
        motionSensor=new RemMotionSensor(context,(x,y,z,w)->{
            if(!motionActive||released||!ready)return;
            Display display=getDisplay();int angle=display==null?0:display.getRotation()*90;
            js("RemModel.setDeviceRotation(["+x+","+y+","+z+","+w+"],"+angle+")");
        });
        WebSettings s=getSettings();s.setJavaScriptEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setDomStorageEnabled(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return true;}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){return asset(request);}
        });
        addJavascriptInterface(new Bridge(),"RemHost");loadUrl("https://rem.local/preview/render.html");
    }
    public void setListener(Listener value){mainThread();listener=value;if(ready&&value!=null)value.ready();}
    public boolean isCharacterReady(){return ready;}
    public void setOutfit(String id){mainThread();if(id==null||!id.matches("[a-z0-9-]+"))throw new IllegalArgumentException("Outfit ID");outfit=id;if(ready)select();}
    private void select(){js("RemModel.setOutfit("+JSONObject.quote(outfit)+").catch(e=>RemHost.failed(e.message))");}
    public void setTone(Map<String,Double> values){mainThread();JSONObject checked=weights(values);try{for(String key:values.keySet())tones.put(key,values.get(key));}catch(Exception e){throw new IllegalArgumentException(e);}if(ready)js("RemModel.setTone("+checked+")");}
    public void react(Map<String,Double> values,double attack,double hold,double release){mainThread();JSONObject checked=weights(values);if(!Double.isFinite(attack)||!Double.isFinite(hold)||!Double.isFinite(release)||attack<=0||hold<0||release<=0)throw new IllegalArgumentException("Reaction timing");if(ready)js("RemModel.react("+checked+",{attack:"+attack+",hold:"+hold+",release:"+release+"})");}
    public void calm(){mainThread();for(String key:AXES)tones.remove(key);if(ready)js("RemModel.calm()");}
    /** Use an RMS/envelope measured from audio that is actually playing. */
    public void setSpeech(double level,boolean playing){mainThread();if(!Double.isFinite(level))throw new IllegalArgumentException("Speech amplitude");if(ready)js("RemModel.setVoice("+Math.max(0,Math.min(1,level))+","+(playing&&resumed)+")");}
    public void setGaze(double x,double y){mainThread();if(!Double.isFinite(x)||!Double.isFinite(y))throw new IllegalArgumentException("Gaze");if(ready)js("RemModel.setGaze("+x+","+y+")");}
    /** Structured local geometry only; the web renderer never receives camera frames. */
    public void setVisualTarget(double x,double y,boolean active){mainThread();if(!Double.isFinite(x)||!Double.isFinite(y))throw new IllegalArgumentException("Visual target");if(ready)js("RemModel.setVisualTarget("+x+","+y+","+active+")");}
    public void respondToObservation(String event){mainThread();if(!event.matches("ARRIVED|LEFT|NOD|SHAKE|WAVE|APPROACH|RETREAT"))throw new IllegalArgumentException("Observation event");if(ready)js("RemModel.respondToObservation("+JSONObject.quote(event)+")");}
    /** Enabled by default; starts only while ready, resumed, attached and visible. */
    public void setMotionEnabled(boolean enabled){mainThread();motionEnabled=enabled;updateMotion();}
    public boolean isMotionAvailable(){return motionSensor!=null&&motionSensor.available();}
    public boolean isMotionRunning(){return motionActive;}
    /** geomagnetic-fallback does not imply a physical gyroscope. */
    public String getMotionSource(){return motionSensor==null?"none":motionSensor.source;}
    public void setMotionSensitivity(double value){mainThread();if(!Double.isFinite(value)||value<.25||value>2)throw new IllegalArgumentException("Motion sensitivity: 0.25..2");motionSensitivity=value;if(ready)js("RemModel.setMotionSensitivity("+value+")");}
    public void recenterMotion(){mainThread();if(ready)js("RemModel.recenterMotion()");}
    private void updateMotion(){
        if(motionSensor==null)return;
        boolean wanted=motionEnabled&&ready&&resumed&&!released&&isAttachedToWindow()&&isShown()&&getWindowVisibility()==View.VISIBLE;
        boolean active;if(wanted)active=motionSensor.start();else{motionSensor.stop();active=false;}
        if(active!=motionActive){motionActive=active;if(ready)js("RemModel.setMotionEnabled("+active+","+JSONObject.quote(motionSensor.source)+")");}
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();updateMotion();}
    @Override protected void onDetachedFromWindow(){if(motionSensor!=null)motionSensor.stop();if(motionActive&&ready)js("RemModel.setMotionEnabled(false)");motionActive=false;super.onDetachedFromWindow();}
    @Override protected void onVisibilityChanged(View changedView,int visibility){super.onVisibilityChanged(changedView,visibility);updateMotion();}
    @Override protected void onWindowVisibilityChanged(int visibility){super.onWindowVisibilityChanged(visibility);updateMotion();}
    public void resumeCharacter(){mainThread();if(released)return;resumed=true;onResume();if(ready)js("RemModel.setPaused(false)");updateMotion();}
    public void pauseCharacter(){mainThread();if(released)return;resumed=false;updateMotion();if(ready)js("RemModel.setVoice(0,false);RemModel.setPaused(true)");onPause();}
    public void releaseCharacter(){mainThread();if(released)return;pauseCharacter();released=true;ready=false;removeJavascriptInterface("RemHost");stopLoading();destroy();}
    private void js(String code){if(!released)evaluateJavascript(code,null);}
    private final class Bridge {
        @JavascriptInterface public void ready(String inventory){post(()->{if(released)return;ready=true;select();js("RemModel.setTone("+tones+");RemModel.setPaused("+(!resumed)+");RemModel.setMotionSensitivity("+motionSensitivity+")");updateMotion();if(listener!=null)listener.ready();});}
        @JavascriptInterface public void failed(String message){post(()->{if(!released&&listener!=null)listener.failed(message);});}
    }
    private static JSONObject weights(Map<String,Double> values){JSONObject result=new JSONObject();try{for(Map.Entry<String,Double> e:values.entrySet()){Double v=e.getValue();if(!AXES.contains(e.getKey())||v==null||!Double.isFinite(v)||v<0||v>1)throw new IllegalArgumentException("Emotion weight");result.put(e.getKey(),v);}}catch(Exception e){throw new IllegalArgumentException(e);}return result;}
    private static void mainThread(){if(Looper.myLooper()!=Looper.getMainLooper())throw new IllegalStateException("Use the Android main thread");}
    private WebResourceResponse asset(WebResourceRequest request){
        Uri u=request.getUrl();String path=u.getPath();if(!"GET".equals(request.getMethod())||!"https".equals(u.getScheme())||!"rem.local".equals(u.getHost())||u.getPort()!=-1||path==null||path.contains("..")||path.contains("\\")||path.contains("\0"))return missing();
        String relative=path.startsWith("/")?path.substring(1):path;if(!(relative.equals("catalog.json")||relative.startsWith("preview/")||relative.startsWith("models/")))return missing();
        String mime=relative.endsWith(".html")?"text/html":relative.endsWith(".js")?"application/javascript":relative.endsWith(".json")?"application/json":relative.endsWith(".png")?"image/png":relative.endsWith(".wav")?"audio/wav":"application/octet-stream";
        try{return new WebResourceResponse(mime,mime.startsWith("text/")||mime.contains("javascript")||mime.contains("json")?"UTF-8":null,200,"OK",Collections.singletonMap("Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:"),getContext().getAssets().open(ROOT+relative));}catch(Exception e){return missing();}
    }
    private static WebResourceResponse missing(){return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));}
}
