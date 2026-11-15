import {orientationQuaternion} from './device-motion.js';
// Permission is requested only by the explicit UI button, never on page load.
export function createBrowserMotion(renderer,{onChange=()=>{}}={}){
 let wanted=false,paused=false,listening=false,disposed=false,request=0,timer,health,hasSample=false,pageHidden=false,status='off';
 const tell=(value,message)=>{status=value;onChange({enabled:wanted,status,message});};
 function stop(){clearTimeout(timer);clearInterval(health);window.removeEventListener('deviceorientation',sample);listening=false;renderer.setMotionEnabled(false);}
 function sample(e){
  if(!listening||![e.alpha,e.beta,e.gamma].every(Number.isFinite))return;
  renderer.setDeviceRotation(orientationQuaternion(e.alpha,e.beta,e.gamma),screen.orientation?.angle??window.orientation??0);
  if(!hasSample||status==='stale'){hasSample=true;clearTimeout(timer);tell('active','手机倾斜已开启，可随时点“以当前姿势回正”。');}
 }
 function sync(){
  if(disposed)return;
  const canRun=wanted&&!paused&&!document.hidden&&!pageHidden;
  if(!canRun){stop();if(wanted)tell('paused','手机倾斜已暂停，返回后会重新回正。');return;}
  if(listening)return;
  hasSample=false;listening=true;renderer.setMotionEnabled(true,'browser-orientation');
  window.addEventListener('deviceorientation',sample);tell('waiting','正在等待手机姿态数据…');
  timer=setTimeout(()=>{if(!hasSample){wanted=false;stop();tell('unavailable','没有收到姿态数据；请在支持传感器的手机上使用。');}},5000);
  health=setInterval(()=>{if(hasSample&&renderer.getState().motion.status==='stale'&&status!=='stale')tell('stale','姿态数据暂时中断，角色正在回正。');},500);
 }
 const hide=()=>{pageHidden=true;sync();},show=()=>{pageHidden=false;sync();};
 document.addEventListener('visibilitychange',sync);window.addEventListener('pagehide',hide);window.addEventListener('pageshow',show);
 return {
  async enable(){
   const token=++request;
   if(disposed)return false;
   if(!window.isSecureContext){tell('insecure','手机浏览器需要 HTTPS 才能读取姿态；Android 组件不受此限制。');return false;}
   const api=window.DeviceOrientationEvent;if(!api){tell('unavailable','此设备或浏览器不支持姿态传感器。');return false;}
   try{if(typeof api.requestPermission==='function'&&await api.requestPermission()!=='granted'){if(token===request)tell('denied','姿态权限未开启，可再次点击重试。');return false;}}
   catch(e){if(token===request)tell('denied','无法读取姿态权限，请检查浏览器的传感器设置。');return false;}
   if(disposed||token!==request)return false;wanted=true;sync();return true;
  },
  disable(){request++;wanted=false;stop();tell('off','手机倾斜未开启。');},
  recenter(){renderer.recenterMotion();},
  setPaused(value){paused=Boolean(value);sync();},
  destroy(){disposed=true;request++;wanted=false;stop();document.removeEventListener('visibilitychange',sync);window.removeEventListener('pagehide',hide);window.removeEventListener('pageshow',show);}
 };
}
