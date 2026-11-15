import {ExpressionLayer} from './expression-layer.js';
import {compileMotion} from './motion-clip.js';
const FACES=new Set(['＞＜','爱心眼','黑脸','加载','脸红','流泪','流冷汗','圈圈眼','屑屑眼']);
const PROTECTED=new Set(['AngleX','AngleY','AngleZ','JawOpen','ParamAngleX','ParamAngleY','ParamAngleZ','ParamEyeLOpen','ParamEyeROpen','ParamEyeBallX','ParamEyeBallY','ParamMouthOpenY','ParamMouthForm']);
const GESTURES={greet:['默认手切举手','举手切默认手'],point:['竖手指切出来动画','竖手指切回默认'],grass:['狗尾草切换出来','狗尾草切回默认手']};
export async function createAuthorInteraction(url,parameters){
 const read=async u=>{const r=await fetch(u);if(!r.ok)throw Error('作者动作资源读取失败');return r.json();};
 const config=await read(url),expressions=new Map(),clips=new Map(),bounds=new Map(parameters.map(p=>[p.id,p]));
 await Promise.all(config.expressions.map(async x=>expressions.set(x.name,await read(new URL(x.file,url)))));
 await Promise.all(config.motions.map(async x=>clips.set(x.name,compileMotion(await read(new URL(x.file,url))))));
 const overlay=new ExpressionLayer(),toggles=new Set();let clock=0,face='',faceUntil=0,expressionKey='',phase=null,queued=null,gesture=null;
 const start=(name,hold=0)=>{const clip=clips.get(name);if(clip)phase={name,clip,start:clock,hold};};
 function requestGesture(id,hold=3){
  if(!GESTURES[id])return;
  if(gesture){queued={id,hold};if(!phase?.returning){start(GESTURES[gesture][1]);if(phase)phase.returning=true;}return;}
  gesture=id;start(GESTURES[id][0],hold);
 }
 function updateGesture(){
  if(!phase||clock-phase.start<=phase.clip.duration+phase.hold)return;
  if(gesture&&!phase.returning){start(GESTURES[gesture][1]);if(phase)phase.returning=true;}
  else{phase=null;gesture=null;if(queued){const next=queued;queued=null;requestGesture(next.id,next.hold);}}
 }
 function setFace(name,seconds=5){face=name;faceUntil=clock+seconds;}
 const autoFace=w=>w.IRRITATED>.35?'屑屑眼':w.SAD>.5?'流泪':w.SHY>.22?'脸红':w.SURPRISED>.55?'流冷汗':w.JOY>.45?'＞＜':'';
 const api={config,
  apply(frame,weights,dt){
   clock+=dt;updateGesture();const next={...clips.get('IDLE')?.sample(clock,true),...frame};
   if(phase)for(const [id,v]of Object.entries(phase.clip.sample(clock-phase.start)))if(!PROTECTED.has(id))next[id]=v;
   const current=clock<faceUntil?face:autoFace(weights),names=[...toggles];if(current)names.push(current);
   const key=names.sort().join('|');if(key!==expressionKey){expressionKey=key;overlay.set(names.flatMap(n=>expressions.get(n)?.Parameters||[]),.22);}
   overlay.step(dt).apply(id=>next[id]??bounds.get(id)?.default,(id,v)=>{const p=bounds.get(id);if(p)next[id]=Math.max(p.min,Math.min(p.max,v));});
   return next;
  },
  choose(name){
   if(name==='自动表情'){face='';faceUntil=0;return true;}
   if(name==='全部恢复'){toggles.clear();face='';faceUntil=0;phase=null;gesture=null;queued=null;return true;}
   if(FACES.has(name)){setFace(name,8);return true;}
   if(expressions.has(name)){
    if(['默认体型','体型1','体型2'].includes(name)){for(const n of ['默认体型','体型1','体型2'])toggles.delete(n);if(name!=='默认体型')toggles.add(name);}
    else if(name==='竖食指开'){requestGesture('point',5);}else if(name==='竖食指关'){queued=null;if(gesture){start(GESTURES[gesture][1]);if(phase)phase.returning=true;}}
    else if(toggles.has(name))toggles.delete(name);else toggles.add(name);return true;
   }
   if(name==='抚胸手'){requestGesture('greet');return true;}if(name==='竖食指'){requestGesture('point');return true;}if(name==='狗尾草'){requestGesture('grass');return true;}
   if(name==='脱捕演出'){gesture=null;queued=null;start('脱捕');return true;}
   return false;
  },
  observed(event){if(event==='WAVE'){setFace('＞＜',2.5);requestGesture('greet',1.7);}else if(event==='APPROACH')setFace('脸红',3);else if(event==='SHAKE')setFace('屑屑眼',2.5);},
  touch(region){setFace(region==='head'||region==='face'?'脸红':region==='tail'?'流冷汗':'屑屑眼',5);requestGesture(region==='hand'?'greet':'point',2);},
  reply(text){if(/谢谢|开心|太好|喜欢/.test(text))setFace('＞＜',5);else if(/别闹|哼|笨|才没有|尾巴/.test(text))setFace('屑屑眼',5);else if(/害羞|脸红|头发|摸头/.test(text))setFace('脸红',5);},
  state(){return {face:clock<faceUntil?face:null,accessories:[...toggles],motion:phase?.name||'IDLE'};}
 };
 return api;
}
