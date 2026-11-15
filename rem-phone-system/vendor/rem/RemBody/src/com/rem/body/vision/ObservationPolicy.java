package com.rem.body.vision;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;

/** Temporal interpretation of geometry, not identity or inferred mental state. No Android dependency. */
public final class ObservationPolicy {
    public enum Event { ARRIVED, LEFT, NOD, SHAKE, WAVE, APPROACH, RETREAT }
    public static final class Sample {
        public final long time;
        public final boolean face, palm, handObserved;
        public final double x, y, size, yaw, pitch, wristX;
        public Sample(long time, boolean face, double x, double y, double size,
                      double yaw, double pitch, boolean palm, double wristX) {
            this(time,face,x,y,size,yaw,pitch,palm,wristX,true);
        }
        public Sample(long time, boolean face, double x, double y, double size,
                      double yaw, double pitch, boolean palm, double wristX, boolean handObserved) {
            this.time=time; this.face=face; this.x=x; this.y=y; this.size=size;
            this.yaw=yaw; this.pitch=pitch; this.palm=palm; this.wristX=wristX;
            this.handObserved=handObserved;
        }
    }
    public static final class Result {
        public final double x,y;
        public final boolean present;
        public final List<Event> events;
        Result(double x,double y,boolean present,List<Event> events) {
            this.x=x;this.y=y;this.present=present;this.events=events;
        }
    }
    private final EnumMap<Event,Long> emitted=new EnumMap<>(Event.class);
    private final List<Sample> history=new ArrayList<>();
    private final Wave wave=new Wave(.045),rollWave=new Wave(.28);
    private long lastTime=-1,lastSeen=-1,candidateSince=-1,nearSince=-1,farSince=-1;
    private boolean present,near;
    private double sx,sy,baselineSize,previousX,previousY;
    private int seen;
    private long lastHandTime=-1;
    private long lastOpenHand=-1;

    /** Called on the face-policy worker after independent hand inference; never rewinds gaze time. */
    public List<Event> acceptHand(long time,boolean palm,double wristX){
        return acceptHand(time,palm,wristX,Double.NaN);
    }
    public List<Event> acceptHand(long time,boolean palm,double centerX,double roll){
        List<Event> events=new ArrayList<>();
        if(time<=lastHandTime||lastTime-time>800)return events;
        lastHandTime=time;
        if(!present){wave.reset();rollWave.reset();lastOpenHand=-1;return events;}
        if(!palm||!Double.isFinite(centerX)){
            if(lastOpenHand<0||time-lastOpenHand>900){wave.reset();rollWave.reset();}
            return events;
        }
        lastOpenHand=time;
        boolean translated=wave.update(time,centerX);
        boolean rocked=Double.isFinite(roll)&&rollWave.update(time,roll);
        if(translated||rocked){emit(Event.WAVE,time,4500,events);wave.reset();rollWave.reset();}
        return events;
    }

    public Result accept(Sample s) {
        List<Event> events=new ArrayList<>();
        if(s.time<=lastTime) return new Result(sx,sy,present,events);
        double dt=lastTime<0?.125:Math.min(.5,(s.time-lastTime)/1000.0);
        lastTime=s.time;
        boolean valid=s.face&&finite(s.x,s.y,s.size,s.yaw,s.pitch)&&s.size>.025;
        if(valid) {
            if(lastSeen<0||s.time-lastSeen>450||Math.hypot(s.x-previousX,s.y-previousY)>.3) {
                history.clear();seen=0;candidateSince=s.time;wave.reset();
            }
            previousX=s.x;previousY=s.y;lastSeen=s.time;seen++;
            if(!present&&seen>=3&&s.time-candidateSince>=200) {
                present=true;baselineSize=s.size;near=false;
                emit(Event.ARRIVED,s.time,8000,events);
            }
            // Raw analysis is unmirrored. Reflect X to follow the user's physical side of the screen.
            double tx=deadzone(clamp((.5-s.x)*2.8,-1,1),.025);
            double ty=deadzone(clamp((.5-s.y)*2.5,-1,1),.025);
            sx+=(tx-sx)*(1-Math.exp(-dt/.13));sy+=(ty-sy)*(1-Math.exp(-dt/.13));
            if(present) {
                history.add(s);
                while(!history.isEmpty()&&s.time-history.get(0).time>1600)history.remove(0);
                gestures(s,events);
                // Bounding-box scale is only a relative distance cue, never centimetres.
                if(!near&&s.size>baselineSize*1.35) {
                    if(nearSince<0)nearSince=s.time;
                    if(s.time-nearSince>=450){near=true;nearSince=-1;emit(Event.APPROACH,s.time,7000,events);}
                } else nearSince=-1;
                if(near&&s.size<baselineSize*1.12) {
                    if(farSince<0)farSince=s.time;
                    if(s.time-farSince>=450){near=false;farSince=-1;emit(Event.RETREAT,s.time,7000,events);}
                } else farSince=-1;
                if(!near&&nearSince<0)baselineSize+=(s.size-baselineSize)*(1-Math.exp(-dt/18));
            }
        } else {
            seen=0;candidateSince=-1;history.clear();nearSince=farSince=-1;
            if(lastSeen<0||s.time-lastSeen>400) {
                sx*=Math.exp(-dt/.4);sy*=Math.exp(-dt/.4);
            }
            if(present&&s.time-lastSeen>=1600) {
                present=false;near=false;emit(Event.LEFT,s.time,6000,events);
            }
        }
        if(!present)wave.reset();
        else if(s.handObserved) {
            if(s.palm&&Double.isFinite(s.wristX)) {
                if(wave.update(s.time,s.wristX))emit(Event.WAVE,s.time,4500,events);
            } else wave.reset();
        }
        return new Result(clamp(sx,-1,1),clamp(sy,-1,1),present,events);
    }
    private void gestures(Sample s,List<Event> events) {
        if(history.size()<5)return;
        Sample first=history.get(0);
        if(s.time-first.time<400)return;
        double minPitch=first.pitch,maxPitch=first.pitch,minYaw=first.yaw,maxYaw=first.yaw;
        for(Sample p:history){minPitch=Math.min(minPitch,p.pitch);maxPitch=Math.max(maxPitch,p.pitch);minYaw=Math.min(minYaw,p.yaw);maxYaw=Math.max(maxYaw,p.yaw);}
        if(maxPitch-minPitch>=14&&Math.abs(s.pitch-first.pitch)<5&&maxYaw-minYaw<18) {
            emit(Event.NOD,s.time,3000,events);history.clear();
        } else if(maxYaw-first.yaw>=12&&first.yaw-minYaw>=12&&Math.abs(s.yaw-first.yaw)<8&&maxPitch-minPitch<18) {
            emit(Event.SHAKE,s.time,3000,events);history.clear();
        }
    }
    private void emit(Event event,long time,long cooldown,List<Event> events) {
        Long previous=emitted.get(event);
        if(previous==null||time-previous>=cooldown){emitted.put(event,time);events.add(event);}
    }
    private static boolean finite(double...v){for(double x:v)if(!Double.isFinite(x))return false;return true;}
    private static double clamp(double v,double a,double b){return Math.max(a,Math.min(b,v));}
    private static double deadzone(double v,double d){return Math.abs(v)<d?0:v;}

    /** Open palm plus three substantial alternating lateral legs; a still palm is not a wave. */
    private static final class Wave {
        final double amplitude;
        Wave(double amplitude){this.amplitude=amplitude;}
        long start=-1,last=-1;double anchor,extreme;int direction,turns;
        void reset(){start=last=-1;direction=turns=0;}
        boolean update(long now,double x) {
            if(start<0||now-last>1000||now-start>3000){start=now;anchor=extreme=x;direction=turns=0;}
            last=now;
            if(direction==0){if(Math.abs(x-anchor)>=amplitude){direction=x>anchor?1:-1;extreme=x;}return false;}
            if((x-extreme)*direction>=0)extreme=x;
            else if((extreme-x)*direction>=amplitude){direction=-direction;extreme=x;turns++;}
            if(turns>=2&&now-start>=350){reset();return true;}
            return false;
        }
    }
}
