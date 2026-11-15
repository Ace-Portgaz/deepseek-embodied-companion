// Native parameter poses. Every outfit has its own continuous pose targets.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export function bustEmotionFrame(profile,weights,{blink=1,voice=0,voicePlaying=false,automatic=true,gaze={x:0,y:0},elapsed=0}={}){
 const defaults=Object.fromEntries(profile.parameters.map(p=>[p.id,p.default]));
 const out={...defaults},sum=Object.values(weights).reduce((a,b)=>a+b,0),normalizer=Math.max(1,sum);
 for(const[emotion,weight]of Object.entries(weights)){
  if(!weight)continue;
  for(const[id,value]of Object.entries(profile.poses[emotion]||{}))out[id]+=(value-defaults[id])*weight/normalizer;
 }
 // Blush accumulates independently; mixed affection and shyness need not cancel.
 out.ParamBlush=1-Object.entries(weights).reduce((v,[k,w])=>v*(1-w*(profile.poses[k]?.ParamBlush||0)),1);
 if(automatic){
  const t=elapsed*profile.motion.speed,joy=weights.JOY||0,sleepy=weights.SLEEPY||0;
  out.ParamAngleX+=gaze.x*7;
  out.ParamAngleY+=gaze.y*5+Math.sin(t*.83)*(.5+sleepy*1.4);
  out.ParamAngleZ+=Math.sin(t)*profile.motion.sway*(.2+joy*.8);
  out.ParamBodyAngleZ+=Math.sin(t-.4)*profile.motion.sway*.22;
  out.ParamBounce+=Math.max(0,Math.sin(t*2))*profile.motion.bounce*joy;
  out.ParamBreath=.35+.22*Math.sin(elapsed*1.45);
  out.ParamEyeBallX+=gaze.x*.65;out.ParamEyeBallY+=gaze.y*.55;
 }
 out.ParamEyeLOpen*=blink;out.ParamEyeROpen*=blink;
 out.ParamMouthOpenY=Math.max(out.ParamMouthOpenY,voicePlaying?voice:0);
 return Object.fromEntries(profile.parameters.map(p=>[p.id,clamp(out[p.id],p.min,p.max)]));
}
