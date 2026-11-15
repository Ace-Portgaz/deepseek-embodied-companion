package com.rem.body.vision;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.ImageFormat;
import android.graphics.Matrix;
import android.hardware.camera2.*;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Range;
import android.util.Size;
import java.nio.ByteBuffer;
import java.util.Collections;

/** ImageReader only: no camera preview is composited over Rem, saved or transmitted. */
public final class FrontCameraSource implements VisualFrameSource {
    private final CameraManager manager;
    private final HandlerThread thread=new HandlerThread("RemCameraFrames");
    private Handler handler;
    private volatile boolean closed;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private Sink sink;
    private int rotation;
    private boolean opening;
    private long lastFrame;
    public FrontCameraSource(Context context){manager=(CameraManager)context.getSystemService(Context.CAMERA_SERVICE);}

    @SuppressLint("MissingPermission") @Override public void start(Sink value) {
        sink=value;thread.start();handler=new Handler(thread.getLooper());
        handler.post(()->{
            if(closed)return;
            try {
                String id=null;CameraCharacteristics selected=null;
                for(String candidate:manager.getCameraIdList()) {
                    CameraCharacteristics c=manager.getCameraCharacteristics(candidate);
                    if(Integer.valueOf(CameraCharacteristics.LENS_FACING_FRONT).equals(c.get(CameraCharacteristics.LENS_FACING))){id=candidate;selected=c;break;}
                }
                if(id==null)throw new IllegalStateException("front_missing");
                Integer orientation=selected.get(CameraCharacteristics.SENSOR_ORIENTATION);
                rotation=orientation==null?0:orientation;
                StreamConfigurationMap map=selected.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
                Size best=null;double score=Double.MAX_VALUE;
                for(Size size:map.getOutputSizes(ImageFormat.YUV_420_888)) {
                    double next=Math.abs(size.getWidth()-640)+Math.abs(size.getHeight()-480);
                    if(next<score){score=next;best=size;}
                }
                if(best==null)throw new IllegalStateException("yuv_missing");
                reader=ImageReader.newInstance(best.getWidth(),best.getHeight(),ImageFormat.YUV_420_888,2);
                reader.setOnImageAvailableListener(this::available,handler);
                final Range<Integer> fps=chooseFps(selected.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES));
                opening=true;
                manager.openCamera(id,new CameraDevice.StateCallback(){
                    @Override public void onOpened(CameraDevice device){
                        opening=false;
                        if(closed){device.close();thread.quitSafely();return;}camera=device;
                        try{device.createCaptureSession(Collections.singletonList(reader.getSurface()),new CameraCaptureSession.StateCallback(){
                            @Override public void onConfigured(CameraCaptureSession capture){
                                if(closed){capture.close();return;}session=capture;
                                try{CaptureRequest.Builder request=device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                                    request.addTarget(reader.getSurface());request.set(CaptureRequest.CONTROL_MODE,CaptureRequest.CONTROL_MODE_AUTO);
                                    if(fps!=null)request.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,fps);
                                    capture.setRepeatingRequest(request.build(),null,handler);
                                }catch(Exception e){fail("capture_start");}
                            }
                            @Override public void onConfigureFailed(CameraCaptureSession capture){capture.close();fail("session_config");}
                        },handler);}catch(Exception e){fail("session_create");}
                    }
                    @Override public void onDisconnected(CameraDevice device){opening=false;device.close();if(closed)thread.quitSafely();else fail("camera_disconnected");}
                    @Override public void onError(CameraDevice device,int error){opening=false;device.close();if(closed)thread.quitSafely();else fail("camera_error_"+error);}
                },handler);
            }catch(Exception e){opening=false;fail("front_camera_open");}
        });
    }
    private static Range<Integer> chooseFps(Range<Integer>[] ranges){
        if(ranges==null)return null;Range<Integer> best=null;
        for(Range<Integer> r:ranges)if(r.getUpper()>=15&&(best==null||Math.abs(r.getUpper()-15)<Math.abs(best.getUpper()-15)))best=r;
        return best;
    }
    private void available(ImageReader source){
        try(Image image=source.acquireLatestImage()) {
            if(image==null||closed||!sink.readyForFrame())return;
            long now=SystemClock.elapsedRealtime();if(now-lastFrame<120)return;lastFrame=now;
            Bitmap raw=convert(image),upright=raw;
            if(rotation!=0){Matrix matrix=new Matrix();matrix.postRotate(rotation);upright=Bitmap.createBitmap(raw,0,0,raw.getWidth(),raw.getHeight(),matrix,false);if(upright!=raw)raw.recycle();}
            if(closed)upright.recycle();else sink.frame(upright,now);
        }catch(Exception e){if(!closed)fail("frame_conversion");}
    }
    private static Bitmap convert(Image image){
        android.graphics.Rect crop=image.getCropRect();
        // Detection networks resize internally; avoid rotating/converting unnecessary full-size pixels.
        int step=crop.width()>=640?2:1,w=crop.width()/step,h=crop.height()/step;int[] pixels=new int[w*h];
        Image.Plane[] planes=image.getPlanes();ByteBuffer y=planes[0].getBuffer(),u=planes[1].getBuffer(),v=planes[2].getBuffer();
        int yo=y.position(),uo=u.position(),vo=v.position();
        for(int row=0;row<h;row++)for(int col=0;col<w;col++){
            int cx=crop.left+col*step,cy=crop.top+row*step;
            int yy=(y.get(yo+cy*planes[0].getRowStride()+cx*planes[0].getPixelStride())&255)-16;
            int uu=(u.get(uo+(cy/2)*planes[1].getRowStride()+(cx/2)*planes[1].getPixelStride())&255)-128;
            int vv=(v.get(vo+(cy/2)*planes[2].getRowStride()+(cx/2)*planes[2].getPixelStride())&255)-128;
            int c=298*Math.max(0,yy);
            int r=bound((c+409*vv+128)>>8),g=bound((c-100*uu-208*vv+128)>>8),b=bound((c+516*uu+128)>>8);
            pixels[row*w+col]=0xff000000|(r<<16)|(g<<8)|b;
        }
        return Bitmap.createBitmap(pixels,w,h,Bitmap.Config.ARGB_8888);
    }
    private static int bound(int n){return Math.max(0,Math.min(255,n));}
    private void fail(String code){if(!closed){sink.failed(code);close();}}
    @Override public void close(){
        if(closed)return;closed=true;
        if(handler!=null)handler.post(()->{
            if(session!=null){session.close();session=null;}
            if(camera!=null){camera.close();camera=null;}
            if(reader!=null){reader.close();reader=null;}
            if(!opening)thread.quitSafely();
        });
    }
}
