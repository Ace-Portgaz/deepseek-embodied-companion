import {createViewer} from './runtime.js';
import {createVisualFollow} from './visual-follow.js';
import {authorFrame} from './author-expression.js';
import {bustEmotionFrame} from './bust-emotion-frame.js';
import {createDeviceMotion,applyDeviceMotion} from './device-motion.js';
const base=new URL('../',import.meta.url),clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export const AXES=['JOY','SHY','AFFECTION','SAD','IRRITATED','SURPRISED','SLEEPY','CURIOUS'];
export async function createBustRenderer(container,{onError,onChange}={}){
 const response=await fetch(new URL('catalog.json',base));if(!response.ok)throw Error('胸像清单读取失败');const catalog=await response.json();
 let viewer,canvas,inventory,activeId,profile,expressionProfile,loading=false,generation=0,disposed=false,paused=false,automatic=true,elapsed=0,last=performance.now();
 let target=Object.fromEntries(AXES.map(k=>[k,0])),weights={...target},voice=0,voicePlaying=false,manual=null,reactions=[],gaze={x:0,y:0},smoothGaze={x:0,y:0},raf;
 const visual=createVisualFollow();
 const motion=createDeviceMotion();let motionPose={x:0,y:0,z:0};
 const motionVisibility=()=>{motion.suspend(paused||document.hidden);};
 document.addEventListener('visibilitychange',motionVisibility);motionVisibility();
 const output=frame=>viewer.setCaptureParameters(visual.apply(applyDeviceMotion(frame,motionPose,inventory.parameters),inventory.parameters));
 function checkWeights(values){for(const [k,v] of Object.entries(values))if(!AXES.includes(k)||!Number.isFinite(v)||v<0||v>1)throw Error('情绪值应为 0–1：'+k);}
 function submit(){
  if(!viewer)return;
  if(manual){viewer.setCaptureParameters(manual);return;}
  const w=weights,blink=automatic&&elapsed%4.2<.18?1-Math.sin(Math.PI*(elapsed%4.2)/.18)**2:1;
  if(profile){output(authorFrame(profile,w,{blink,voice,voicePlaying,automatic,gaze:smoothGaze,elapsed}));return;}
  if(expressionProfile){output(bustEmotionFrame(expressionProfile,w,{blink,voice,voicePlaying,automatic,gaze:smoothGaze,elapsed}));return;}
  const eye=clamp(1-.20*w.JOY-.16*w.SHY-.48*w.SLEEPY+.15*w.SURPRISED,.2,1);
  output({ParamEyeLOpen:eye*blink,ParamEyeROpen:eye*blink,ParamMouthForm:clamp(.65*w.JOY+.25*w.AFFECTION-.5*w.SAD-.5*w.IRRITATED,-1,1),ParamMouthOpenY:Math.max(voicePlaying?voice:0,.3*w.SURPRISED),ParamAngleX:clamp(automatic?smoothGaze.x*8+3*w.CURIOUS-2*w.SHY:0,-10,10),ParamAngleY:clamp(automatic?smoothGaze.y*6-3*w.SHY-2*w.SAD:0,-8,8),ParamAngleZ:automatic?2*w.CURIOUS-2*w.AFFECTION:0,ParamBodyAngleX:0,ParamBodyAngleY:0,ParamBodyAngleZ:0,ParamBreath:automatic?.15+.1*Math.sin(elapsed*1.3):0});
 }
 async function select(id){
  const item=catalog.outfits.find(x=>x.id===id);if(!item)throw Error('未找到胸像款式');if(viewer&&activeId===id){generation++;loading=false;return true;}const token=++generation;loading=true;
  const nextCanvas=document.createElement('canvas');nextCanvas.style.opacity='0';nextCanvas.setAttribute('aria-label',item.name+'可动胸像');container.append(nextCanvas);let next;
  try{
   const url=new URL(item.model,base),moc=await fetch(new URL('Rem.moc3',url));if(!moc.ok)throw Error('模型文件读取失败');
   const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await moc.arrayBuffer())),x=>x.toString(16).padStart(2,'0')).join('');if(sha!==item.sha256)throw Error('模型校验失败');
   let nextProfile=null,nextExpressionProfile=null;
   if(item.profile){const response=await fetch(new URL(item.profile,base));if(!response.ok)throw Error('原版参数配置读取失败');nextProfile=await response.json();if(nextProfile.modelSha256!==sha)throw Error('原版参数配置与模型不匹配');}
   if(item.expressionProfile){const response=await fetch(new URL(item.expressionProfile,base));if(!response.ok)throw Error('表情配置读取失败');nextExpressionProfile=await response.json();if(nextExpressionProfile.kind!=='expressive-bust'||nextExpressionProfile.modelSha256!==sha)throw Error('表情配置与模型不匹配');}
   const viewConfig=item.framing?{drawing:{width:item.framing.width,height:item.framing.height},regions:{full:{x:0,y:0,w:item.framing.width,h:item.framing.height}}}:undefined;
   let info;next=await createViewer({canvas:nextCanvas,modelUrl:url.href,viewConfig,onReady:i=>info=i,onError});next.setAutoPlay(false);
   if(nextProfile){const actual=new Map(info.parameters.map(p=>[p.id,p]));if(actual.size!==nextProfile.parameters.length||nextProfile.parameters.some(p=>{const a=actual.get(p.id);return !a||['min','max','default'].some(k=>Math.abs(a[k]-p[k])>1e-5);}))throw Error('原版实际参数校验失败');}
   if(nextExpressionProfile){const actual=new Map(info.parameters.map(p=>[p.id,p]));if(actual.size!==nextExpressionProfile.parameters.length||nextExpressionProfile.parameters.some(p=>{const a=actual.get(p.id);return !a||['min','max','default'].some(k=>Math.abs(a[k]-p[k])>1e-5);}))throw Error('胸像实际参数校验失败');for(const pose of Object.values(nextExpressionProfile.poses))for(const[k,v]of Object.entries(pose)){const p=actual.get(k);if(!p||!Number.isFinite(v)||v<p.min||v>p.max)throw Error('胸像表情范围无效：'+k);}}
   if(token!==generation||disposed){next.destroy();nextCanvas.remove();return false;}
   viewer?.destroy();canvas?.remove();viewer=next;canvas=nextCanvas;inventory=info;activeId=id;profile=nextProfile;expressionProfile=nextExpressionProfile;loading=false;nextCanvas.style.opacity='1';submit();viewer.renderNow();if(paused)viewer.freezeCaptureParameters();onChange?.(item);return true;
  }catch(e){next?.destroy();nextCanvas.remove();if(token===generation)loading=false;throw e;}
 }
 const move=e=>{const r=container.getBoundingClientRect();gaze={x:clamp((e.clientX-r.left)/r.width*2-1,-1,1),y:clamp(1-(e.clientY-r.top)/r.height*2,-1,1)};},leave=()=>{gaze={x:0,y:0};};
 container.addEventListener('pointermove',move);container.addEventListener('pointerleave',leave);
 function loop(now){if(now-last<1000/30){if(!disposed)raf=requestAnimationFrame(loop);return;}const dt=clamp((now-last)/1000,0,.05);last=now;if(!paused){elapsed+=dt;visual.step(dt,now);motionPose=motion.step(dt);reactions=reactions.filter(r=>elapsed-r.start<r.attack+r.hold+r.release);for(const k of AXES){let desired=target[k];for(const r of reactions){const t=elapsed-r.start,e=t<r.attack?t/r.attack:t<r.attack+r.hold?1:1-(t-r.attack-r.hold)/r.release;desired=clamp(desired+(r.values[k]||0)*e,0,1);}const tau=desired>weights[k]?(expressionProfile?.transition.attack??.20):(expressionProfile?.transition.release??.65);weights[k]+=(desired-weights[k])*(1-Math.exp(-dt/tau));}for(const k of ['x','y'])smoothGaze[k]+= (gaze[k]-smoothGaze[k])*(1-Math.exp(-dt/.3));submit();}if(!disposed)raf=requestAnimationFrame(loop);}
 await select(catalog.defaultOutfit);raf=requestAnimationFrame(loop);
 return {ready:true,catalog,get inventory(){return inventory;},get sha256(){return catalog.outfits.find(x=>x.id===activeId).sha256;},
  setOutfit:select,setWardrobe:id=>select(id),
  setTone(values){checkWeights(values);target={...target,...values};manual=null;},
  calm(){target=Object.fromEntries(AXES.map(k=>[k,0]));reactions=[];manual=null;},
  react(values,{attack=.2,hold=.6,release=1.4}={}){checkWeights(values);if(![attack,hold,release].every(Number.isFinite)||attack<=0||hold<0||release<=0)throw Error('反应时长无效');reactions.push({values:{...values},attack,hold,release,start:elapsed});manual=null;},
  setVoice(level,playing){voice=Number.isFinite(level)?clamp(level,0,1):0;voicePlaying=Boolean(playing);},
  setAutomatic(value){automatic=Boolean(value);leave();smoothGaze={x:0,y:0};},
  setGaze(x,y){if(!Number.isFinite(x)||!Number.isFinite(y))throw Error('视线值无效');gaze={x:clamp(x,-1,1),y:clamp(y,-1,1)};},
  setVisualTarget(x,y,active){visual.target(x,y,active);},
  respondToObservation(event){visual.respond(event);const values=event==='LEFT'?{CURIOUS:.25}:event==='SHAKE'?{CURIOUS:.5}:event==='APPROACH'?{SHY:.35,AFFECTION:.35}:{JOY:.55,AFFECTION:.3};reactions.push({values,attack:.2,hold:.8,release:1.2,start:elapsed});manual=null;},
  setMotionEnabled(value,source='external'){motion.enable(value,source);},
  setMotionSensitivity(value){motion.setSensitivity(value);},
  setDeviceRotation(quaternion,screenDegrees=0){return motion.sample(quaternion,screenDegrees);},
  recenterMotion(){motion.recenter();},
  setPaused(value){paused=Boolean(value);last=performance.now();motionVisibility();if(paused){visual.reset();voice=0;voicePlaying=false;viewer.freezeCaptureParameters();}else submit();},
  applyParameters(values,{immediate=false}={}){const next={};for(const[k,v]of Object.entries(values)){const p=inventory.parameters.find(x=>x.id===k);if(!p||!Number.isFinite(v))throw Error('无效参数 '+k);next[k]=clamp(v,p.min,p.max);}manual=next;submit();if(immediate)viewer.renderNow();},
  clearParameters(){manual=null;submit();},
  getState(){return {outfit:activeId,loading,paused,automatic,voicePlaying,weights:{...weights},targets:{...target},motion:motion.state(),visual:visual.state(),parameters:viewer.getState().parameters};},
  getDrawables(){return viewer.getDrawableState();},getTopology(){return viewer.getDrawableTopology();},getCounts(){return viewer.getModelCounts();},capture(){viewer.renderNow();return viewer.capture();},
  destroy(){disposed=true;generation++;cancelAnimationFrame(raf);motion.enable(false);document.removeEventListener('visibilitychange',motionVisibility);container.removeEventListener('pointermove',move);container.removeEventListener('pointerleave',leave);viewer?.destroy();canvas?.remove();}
 };
}
