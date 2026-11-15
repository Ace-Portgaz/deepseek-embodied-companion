import com.rem.body.vision.ObservationPolicy;
import com.rem.body.vision.ObservationPolicy.Event;
import com.rem.body.vision.ObservationPolicy.Sample;
import com.rem.body.vision.ObservationPolicy.Result;
import java.util.ArrayList;
import java.util.List;

public final class ObservationPolicyTest {
    static int checks;
    static void check(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    static Sample face(long t,double x,double y,double size,double yaw,double pitch){return new Sample(t,true,x,y,size,yaw,pitch,false,0);}
    static Sample missing(long t){return new Sample(t,false,0,0,0,0,0,false,0);}
    static ObservationPolicy ready(){ObservationPolicy p=new ObservationPolicy();for(long t=0;t<=500;t+=125)p.accept(face(t,.5,.5,.25,0,0));return p;}
    public static void main(String[]args){
        ObservationPolicy p=new ObservationPolicy();
        check(p.accept(face(0,.5,.5,.25,0,0)).events.isEmpty(),"one detection does not announce arrival");
        p.accept(face(125,.5,.5,.25,0,0));
        check(p.accept(face(250,.5,.5,.25,0,0)).events.contains(Event.ARRIVED),"sustained detection announces arrival");
        check(p.accept(missing(500)).present,"brief loss retains presence");
        check(p.accept(missing(1900)).events.contains(Event.LEFT),"sustained loss announces departure");
        check(p.accept(missing(2200)).events.isEmpty(),"departure is emitted once");
        p=ready();Result r=null;for(long t=625;t<2000;t+=125)r=p.accept(face(t,.2,.7,.25,0,0));
        check(r.x>.6&&r.y<-.4,"front-facing mirror X and vertical sign are correct");
        double before=r.x;r=p.accept(missing(2400));check(Math.abs(r.x)<before,"lost gaze eases back");
        r=p.accept(face(2300,.9,.9,.25,0,0));check(Double.isFinite(r.x)&&r.events.isEmpty(),"out-of-order sample ignored");
        r=p.accept(face(2600,Double.NaN,.5,.25,0,0));check(Double.isFinite(r.x),"non-finite geometry never reaches renderer");
        p=ready();List<Event> events=new ArrayList<>();double[] nod={0,3,10,18,13,5,0,0};long t=625;
        for(double pitch:nod){events.addAll(p.accept(face(t,.5,.5,.25,0,pitch)).events);t+=125;}
        check(events.contains(Event.NOD),"dip-and-return nod detected");
        p=ready();events.clear();double[] shake={0,8,18,7,-10,-18,-5,0};t=625;
        for(double yaw:shake){events.addAll(p.accept(face(t,.5,.5,.25,yaw,0)).events);t+=125;}
        check(events.contains(Event.SHAKE)&&!events.contains(Event.NOD),"left-right-return shake distinguished from nod");
        p=ready();events.clear();for(t=625;t<10000;t+=125)events.addAll(p.accept(face(t,.5+.002*Math.sin(t),.5,.25,Math.sin(t),Math.cos(t))).events);
        check(events.isEmpty(),"stationary jitter does not emit actions");
        p=ready();events.clear();double[] wrist={.35,.45,.57,.45,.32,.45,.57};t=625;
        for(double x:wrist){events.addAll(p.accept(new Sample(t,true,.5,.5,.25,0,0,true,x)).events);p.accept(new Sample(t+125,true,.5,.5,.25,0,0,false,0,false));t+=250;}
        check(events.contains(Event.WAVE),"open palm with alternating path detected across unsampled frames");
        p=ready();events.clear();for(t=625;t<3000;t+=250)events.addAll(p.accept(new Sample(t,true,.5,.5,.25,0,0,true,.5)).events);
        check(!events.contains(Event.WAVE),"stationary palm not a wave");
        p=ready();events.clear();for(t=625;t<1700;t+=125)events.addAll(p.accept(face(t,.5,.5,.37,0,0)).events);
        check(events.contains(Event.APPROACH),"sustained relative scale increase detected");
        events.clear();for(;t<3000;t+=125)events.addAll(p.accept(face(t,.5,.5,.25,0,0)).events);
        check(events.contains(Event.RETREAT),"distance hysteresis detects return");
        p=ready();events.clear();for(t=625;t<2000;t+=125)events.addAll(p.accept(face(t,.5,.5,t%250==0?.37:.25,0,0)).events);
        check(!events.contains(Event.APPROACH),"scale spikes do not trigger approach");
        p=ready();events.clear();for(t=625;t<2200;t+=125)events.addAll(p.accept(face(t,.5,.5,.25,0,Math.min(25,(t-625)/30.0))).events);
        check(!events.contains(Event.NOD),"a held head tilt is not a nod");
        p=ready();events.clear();t=625;
        for(double x:wrist){p.accept(new Sample(t+150,true,.5,.5,.25,0,0,false,0,false));events.addAll(p.acceptHand(t,true,x));t+=300;}
        check(events.contains(Event.WAVE),"independent delayed hand stream detects wave without rewinding face time");
        check(p.acceptHand(t-1500,true,.1).isEmpty(),"stale hand result discarded");
        p=ready();events.clear();t=625;
        for(double roll:new double[]{0,.4,.6,.1,-.5,0,.5}){
            p.accept(new Sample(t+100,true,.5,.5,.25,0,0,false,0,false));
            events.addAll(p.acceptHand(t,true,.5,roll));t+=300;
        }
        check(events.contains(Event.WAVE),"stationary wrist with rocking open palm is a wave");
        p=ready();events.clear();t=625;
        for(double roll:new double[]{0,.4,.6,.1,-.5,0,.5}){
            p.accept(new Sample(t+100,true,.5,.5,.25,0,0,false,0,false));
            events.addAll(p.acceptHand(t,false,.5,roll));t+=300;
        }
        check(events.isEmpty(),"closed hand rocking does not wave");
        System.out.println("PASS: "+checks+" temporal observation checks");
    }
}
