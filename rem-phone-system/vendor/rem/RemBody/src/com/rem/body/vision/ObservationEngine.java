package com.rem.body.vision;

import android.content.Context;
import android.graphics.Bitmap;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import com.google.mediapipe.framework.image.BitmapImageBuilder;
import com.google.mediapipe.framework.image.MPImage;
import com.google.mediapipe.tasks.components.containers.Category;
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark;
import com.google.mediapipe.tasks.core.BaseOptions;
import com.google.mediapipe.tasks.core.Delegate;
import com.google.mediapipe.tasks.vision.core.RunningMode;
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker;
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult;
import com.google.mediapipe.tasks.vision.gesturerecognizer.GestureRecognizer;
import com.google.mediapipe.tasks.vision.gesturerecognizer.GestureRecognizerResult;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/** Bounded face and hand workers. Slow gestures never queue behind or stall gaze tracking. */
public final class ObservationEngine implements AutoCloseable, VisualFrameSource.Sink {
    public interface Listener {
        void ready();
        void result(ObservationPolicy.Result result);
        void events(List<ObservationPolicy.Event> events);
        void failed(String code);
    }
    private final Context context;
    private final Handler main;
    private final Listener listener;
    private final HandlerThread thread=new HandlerThread("RemVisionInference");
    private final HandlerThread handThread=new HandlerThread("RemHandInference");
    private final AtomicBoolean busy=new AtomicBoolean();
    private final AtomicBoolean handBusy=new AtomicBoolean();
    private final ObservationPolicy policy=new ObservationPolicy();
    private Handler worker,handWorker;
    private FrontCameraSource source;
    private FaceLandmarker face;
    private GestureRecognizer hand;
    private volatile boolean closed,loaded;
    private boolean faceReady,handReady;
    private volatile long frames,lastFrame,started,totalInferenceMs,maxInferenceMs,handFrames,faceMs,handMs;
    private volatile String faceDelegate="initializing";
    private volatile long detectedHandFrames,openHandFrames;
    private volatile String lastHandLabel="none";
    private long lastHand;
    private final Runnable watchdog=new Runnable(){
        @Override public void run(){
            if(closed)return;
            long now=SystemClock.elapsedRealtime();
            if((!loaded&&now-started>45000)||(loaded&&now-lastFrame>10000)){failed("vision_timeout");return;}
            main.postDelayed(this,3000);
        }
    };
    public ObservationEngine(Context context,Handler main,Listener listener){this.context=context.getApplicationContext();this.main=main;this.listener=listener;}
    public void start(){
        started=SystemClock.elapsedRealtime();lastFrame=started;thread.start();worker=new Handler(thread.getLooper());
        handThread.start();handWorker=new Handler(handThread.getLooper());main.postDelayed(watchdog,3000);
        worker.post(()->{
            try{
                if(closed)return;
                try{face=createFace(Delegate.GPU);faceDelegate="GPU";}
                catch(RuntimeException|LinkageError unavailable){face=createFace(Delegate.CPU);faceDelegate="CPU";}
                main.post(()->{faceReady=true;modelsReady();});
            }catch(RuntimeException|LinkageError e){android.util.Log.e("RemVision","Face initialization failed",e);failed("face_initialization");}
        });
        handWorker.post(()->{
            try{
                if(closed)return;
                hand=GestureRecognizer.createFromOptions(context,GestureRecognizer.GestureRecognizerOptions.builder()
                        .setBaseOptions(BaseOptions.builder().setModelAssetPath("vision/gesture_recognizer.task").build())
                        .setRunningMode(RunningMode.VIDEO).setNumHands(1)
                        .setMinHandDetectionConfidence(.6f).setMinHandPresenceConfidence(.6f).setMinTrackingConfidence(.6f).build());
                main.post(()->{handReady=true;modelsReady();});
            }catch(RuntimeException|LinkageError e){android.util.Log.e("RemVision","Hand initialization failed",e);failed("hand_initialization");}
        });
    }
    private void modelsReady(){
        if(closed||loaded||!faceReady||!handReady)return;
        loaded=true;lastFrame=SystemClock.elapsedRealtime();listener.ready();
        source=new FrontCameraSource(context);source.start(this);
    }
    private FaceLandmarker createFace(Delegate delegate){
        return FaceLandmarker.createFromOptions(context,FaceLandmarker.FaceLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath("vision/face_landmarker.task").setDelegate(delegate).build())
                .setRunningMode(RunningMode.VIDEO).setNumFaces(1)
                .setMinFaceDetectionConfidence(.6f).setMinFacePresenceConfidence(.6f).setMinTrackingConfidence(.6f)
                .setOutputFacialTransformationMatrixes(true).build());
    }
    @Override public boolean readyForFrame(){return loaded&&!closed&&!busy.get();}
    @Override public void frame(Bitmap bitmap,long timestamp){
        if(closed||!busy.compareAndSet(false,true)){bitmap.recycle();return;}
        if(!worker.post(()->{
            try{
                if(closed)return;
                long start=SystemClock.elapsedRealtime();
                maybeHand(bitmap,timestamp);
                ObservationPolicy.Sample sample;
                try(MPImage image=new BitmapImageBuilder(bitmap).build()) {
                    long faceStart=SystemClock.elapsedRealtime();
                    FaceLandmarkerResult faces=face.detectForVideo(image,timestamp);
                    faceMs+=SystemClock.elapsedRealtime()-faceStart;
                    sample=sample(faces,timestamp,false,0,false);
                }
                ObservationPolicy.Result result=policy.accept(sample);
                long duration=SystemClock.elapsedRealtime()-start;frames++;lastFrame=SystemClock.elapsedRealtime();
                totalInferenceMs+=duration;maxInferenceMs=Math.max(maxInferenceMs,duration);
                main.post(()->{if(!closed)listener.result(result);});
            }catch(RuntimeException|LinkageError e){android.util.Log.e("RemVision","Inference failed",e);failed("inference_failed");}
            finally{bitmap.recycle();busy.set(false);}
        })){bitmap.recycle();busy.set(false);}
    }
    private void maybeHand(Bitmap bitmap,long timestamp){
        if(timestamp-lastHand<280||!handBusy.compareAndSet(false,true))return;
        lastHand=timestamp;final Bitmap copy;
        try{copy=bitmap.copy(Bitmap.Config.ARGB_8888,false);}catch(RuntimeException e){handBusy.set(false);throw e;}
        if(!handWorker.post(()->{
            try{
                if(closed)return;
                long begin=SystemClock.elapsedRealtime();boolean palm=false;double center=0,roll=0;
                try(MPImage image=new BitmapImageBuilder(copy).build()){
                    GestureRecognizerResult hands=hand.recognizeForVideo(image,timestamp);
                    lastHandLabel="no_hand";
                    if(!hands.landmarks().isEmpty()){
                        detectedHandFrames++;
                        if(!hands.gestures().isEmpty())for(Category category:hands.gestures().get(0)){
                            lastHandLabel=category.categoryName();
                            if("Open_Palm".equals(category.categoryName())&&category.score()>=.4f)palm=true;
                        }
                        List<NormalizedLandmark> points=hands.landmarks().get(0);
                        int extended=0;
                        for(int tip:new int[]{8,12,16,20})if(distance(points.get(tip),points.get(0))>distance(points.get(tip-2),points.get(0))*1.15)extended++;
                        // Motion blur can temporarily suppress the canned static class; use open-finger geometry too.
                        palm=palm||extended>=3;
                        for(int joint:new int[]{5,9,13,17})center+=points.get(joint).x()/4.0;
                        // Physical aspect ratio matters for an angle in the portrait input image.
                        roll=Math.atan2((points.get(9).x()-points.get(0).x())*copy.getWidth(),
                                (points.get(0).y()-points.get(9).y())*copy.getHeight());
                        if(palm)openHandFrames++;
                    }
                }
                handFrames++;handMs+=SystemClock.elapsedRealtime()-begin;
                final boolean observedPalm=palm;final double observedCenter=center,observedRoll=roll;
                worker.post(()->{
                    if(closed)return;
                    List<ObservationPolicy.Event> events=policy.acceptHand(timestamp,observedPalm,observedCenter,observedRoll);
                    if(!events.isEmpty())main.post(()->{if(!closed)listener.events(events);});
                });
            }catch(RuntimeException|LinkageError e){android.util.Log.e("RemVision","Hand inference failed",e);failed("hand_inference_failed");}
            finally{copy.recycle();handBusy.set(false);}
        })){copy.recycle();handBusy.set(false);}
    }
    private static double distance(NormalizedLandmark a,NormalizedLandmark b){return Math.hypot(a.x()-b.x(),a.y()-b.y());}
    private static ObservationPolicy.Sample sample(FaceLandmarkerResult result,long time,boolean palm,double wrist,boolean handObserved){
        if(result.faceLandmarks().isEmpty())return new ObservationPolicy.Sample(time,false,0,0,0,0,0,palm,wrist,handObserved);
        List<NormalizedLandmark> points=result.faceLandmarks().get(0);
        double minX=1,minY=1,maxX=0,maxY=0;
        for(NormalizedLandmark p:points){minX=Math.min(minX,p.x());maxX=Math.max(maxX,p.x());minY=Math.min(minY,p.y());maxY=Math.max(maxY,p.y());}
        double yaw=0,pitch=0;
        if(result.facialTransformationMatrixes().isPresent()&&!result.facialTransformationMatrixes().get().isEmpty()) {
            // MediaPipe documents column-major 4x4 canonical-face transform. Ignore translation/scale.
            float[] m=result.facialTransformationMatrixes().get().get(0);
            yaw=Math.toDegrees(Math.atan2(-m[2],Math.hypot(m[0],m[1])));
            pitch=Math.toDegrees(Math.atan2(m[6],m[10]));
        }
        return new ObservationPolicy.Sample(time,true,(minX+maxX)/2,(minY+maxY)/2,
                Math.sqrt(Math.max(0,(maxX-minX)*(maxY-minY))),yaw,pitch,palm,wrist,handObserved);
    }
    @Override public void failed(String code){main.post(()->{if(!closed){listener.failed(code);close();}});}
    public String diagnostics(){
        long elapsed=Math.max(1,SystemClock.elapsedRealtime()-started);
        return "loaded="+loaded+" closed="+closed+" faceDelegate="+faceDelegate+" frames="+frames+" handFrames="+handFrames
                +" averageFps="+String.format(java.util.Locale.ROOT,"%.1f",frames*1000.0/elapsed)
                +" meanInferenceMs="+(frames==0?0:totalInferenceMs/frames)+" maxInferenceMs="+maxInferenceMs
                +" faceMeanMs="+(frames==0?0:faceMs/frames)+" handMeanMs="+(handFrames==0?0:handMs/handFrames)
                +" detectedHandFrames="+detectedHandFrames+" openHandFrames="+openHandFrames+" lastHandLabel="+lastHandLabel;
    }
    @Override public void close(){
        if(closed)return;closed=true;main.removeCallbacks(watchdog);
        if(source!=null){source.close();source=null;}
        if(worker!=null)worker.post(()->{try{if(face!=null){face.close();face=null;}}finally{thread.quitSafely();}});
        if(handWorker!=null)handWorker.post(()->{try{if(hand!=null){hand.close();hand=null;}}finally{handThread.quitSafely();}});
    }
}
