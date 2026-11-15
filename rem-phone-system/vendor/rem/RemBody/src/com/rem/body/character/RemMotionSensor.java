package com.rem.body.character;

import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Handler;
import android.os.Looper;

/** Foreground-only fused orientation, delivered on the UI thread at <= 30 Hz. */
final class RemMotionSensor implements SensorEventListener {
    interface Sink { void rotation(float x,float y,float z,float w); }
    private final SensorManager manager;
    private final Sensor sensor;
    private final Sink sink;
    private final float[] quaternion=new float[4];
    private boolean running;
    private long lastTimestamp;
    final String source;

    RemMotionSensor(Context context,Sink sink) {
        this.sink=sink;
        manager=(SensorManager)context.getApplicationContext().getSystemService(Context.SENSOR_SERVICE);
        Sensor found=null;String name="none";
        if(manager!=null){
            found=manager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);
            if(found!=null)name="game-rotation-vector";
            else {found=manager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);if(found!=null)name="rotation-vector";}
            if(found==null){found=manager.getDefaultSensor(Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR);if(found!=null)name="geomagnetic-fallback";}
        }
        sensor=found;source=name;
    }
    boolean available(){return sensor!=null;}
    boolean running(){return running;}
    boolean start(){
        if(running)return true;
        if(sensor==null)return false;
        lastTimestamp=0;
        running=manager.registerListener(this,sensor,33333,new Handler(Looper.getMainLooper()));
        return running;
    }
    void stop(){if(running){running=false;manager.unregisterListener(this);}lastTimestamp=0;}
    @Override public void onSensorChanged(SensorEvent event){
        if(!running||event.sensor!=sensor||event.values.length<3||event.timestamp<=lastTimestamp)return;
        if(lastTimestamp!=0&&event.timestamp-lastTimestamp<33333333L)return;
        SensorManager.getQuaternionFromVector(quaternion,event.values); // Android order: w,x,y,z.
        for(float v:quaternion)if(!Float.isFinite(v))return;
        lastTimestamp=event.timestamp;
        sink.rotation(quaternion[1],quaternion[2],quaternion[3],quaternion[0]);
    }
    @Override public void onAccuracyChanged(Sensor sensor,int accuracy){}
}
