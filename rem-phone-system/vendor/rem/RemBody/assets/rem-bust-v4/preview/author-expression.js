const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

// Same per-parameter blending used by the verified 8812 author-model binding.
// The author's mouth-form direction is opposite to the generated bust rigs.
export function authorFrame(profile,weights,{blink=1,voice=0,voicePlaying=false,automatic=true,gaze={x:0,y:0},elapsed=0}={}){
 const parameters=new Map(profile.parameters.map(p=>[p.id,p]));
 const sums={},totals={},values={};let cheek=0;
 for(const [emotion,pose] of Object.entries(profile.poseDeltas)){
  const w=weights[emotion]||0;
  for(const [id,delta] of Object.entries(pose)){
   if(id==='ParamCheek'){cheek=1-(1-cheek)*(1-clamp(w*delta,0,1));continue;}
   sums[id]=(sums[id]||0)+w*delta;totals[id]=(totals[id]||0)+w;
  }
 }
 for(const [id,sum] of Object.entries(sums)){const p=parameters.get(id);values[id]=clamp(p.default+sum/Math.max(1,totals[id]),p.min,p.max);}
 values.ParamCheek=cheek;
 values.ParamEyeLOpen=(values.ParamEyeLOpen??1)*blink;
 values.ParamEyeROpen=(values.ParamEyeROpen??1)*blink;
 values.ParamMouthOpenY=Math.max(values.ParamMouthOpenY||0,voicePlaying?voice:0);
 if(automatic){
  values.ParamBreath=.22+.14*Math.sin(elapsed*1.3);
  for(const [id,offset] of Object.entries({ParamAngleX:gaze.x*6,ParamAngleY:gaze.y*4,ParamEyeBallX:gaze.x*.16,ParamEyeBallY:gaze.y*.12})){
   const p=parameters.get(id);values[id]=clamp((values[id]??p.default)+offset,p.min,p.max);
  }
 }
 return values;
}
