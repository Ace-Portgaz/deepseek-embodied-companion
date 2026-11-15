// Camera geometry -> bounded model parameters. Independent from voice, expressions and physics.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export function createVisualFollow(){
 let enabled=false,last=-Infinity,x=0,y=0,sx=0,sy=0,mix=0,action=null,clock=0;
 return {
  target(tx,ty,active,now=performance.now()){
   if(!Number.isFinite(tx)||!Number.isFinite(ty))throw Error('Invalid visual target');
   enabled=Boolean(active);last=now;x=clamp(tx,-1,1);y=clamp(ty,-1,1);
  },
  respond(event){
   if(!['ARRIVED','LEFT','NOD','SHAKE','WAVE','APPROACH','RETREAT'].includes(event))throw Error('Invalid observation event');
   action={event,start:clock};
  },
  step(dt,now=performance.now()){
   clock+=dt;const live=enabled&&now-last<1200;
   const a=1-Math.exp(-dt/.12),b=1-Math.exp(-dt/.35);
   sx+=((live?x:0)-sx)*a;sy+=((live?y:0)-sy)*a;mix+=((live?1:0)-mix)*b;
   if(action&&clock-action.start>2.2)action=null;
  },
  apply(frame,parameters){
   const next={...frame},bounds=new Map(parameters.map(p=>[p.id,p]));
   const put=(id,value)=>{const p=bounds.get(id);if(p)next[id]=clamp(value,p.min,p.max);};
   if(mix>.001){
    put('ParamEyeBallX',(frame.ParamEyeBallX||0)*(1-mix)+sx*.72*mix);
    put('ParamEyeBallY',(frame.ParamEyeBallY||0)*(1-mix)+sy*.60*mix);
    put('ParamAngleX',(frame.ParamAngleX||0)+sx*7*mix);
    put('ParamAngleY',(frame.ParamAngleY||0)+sy*5*mix);
   }
   if(action){
    const t=clock-action.start,envelope=Math.sin(Math.PI*clamp(t/2.2,0,1));
    if(action.event==='NOD')put('ParamAngleY',(next.ParamAngleY||0)-7*Math.sin(t*Math.PI*2)*envelope);
    else if(action.event==='SHAKE')put('ParamAngleX',(next.ParamAngleX||0)+7*Math.sin(t*Math.PI*2)*envelope);
    else put('ParamAngleZ',(next.ParamAngleZ||0)+4*envelope);
   }
   return next;
  },
  state(){return {enabled,x:sx,y:sy,mix,action:action?.event||null};},
  reset(){enabled=false;last=-Infinity;x=y=sx=sy=mix=0;action=null;}
 };
}
