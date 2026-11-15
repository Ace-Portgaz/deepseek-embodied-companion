// Shared by the native Android bridge and the browser sensor adapter.
// Quaternions use [x,y,z,w], device -> reference frame. Angles are degrees.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const zero=()=>({x:0,y:0,z:0});
export function multiply(a,b){return [a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1],a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0],a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3],a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2]];}
function normalized(q){if(!Array.isArray(q)||q.length!==4||!q.every(Number.isFinite))throw Error('手机姿态数据无效');const n=Math.hypot(...q);if(n<.01)throw Error('手机姿态四元数无效');return q.map(v=>v/n);}
export function orientationQuaternion(alpha,beta,gamma){
 if(![alpha,beta,gamma].every(Number.isFinite))throw Error('手机姿态角度无效');
 const a=alpha*Math.PI/360,b=beta*Math.PI/360,g=gamma*Math.PI/360;
 // W3C intrinsic Z-X-Y order; same device axes as Android.
 return multiply(multiply([0,0,Math.sin(a),Math.cos(a)],[Math.sin(b),0,0,Math.cos(b)]),[0,Math.sin(g),0,Math.cos(g)]);
}
export function relativeTilt(neutral,current,screenDegrees){
 let q=multiply([-neutral[0],-neutral[1],-neutral[2],neutral[3]],current);
 if(q[3]<0)q=q.map(v=>-v); // q and -q are identical; use the shortest arc.
 const n=Math.hypot(q[0],q[1],q[2]),scale=n<1e-8?0:2*Math.atan2(n,clamp(q[3],-1,1))*180/Math.PI/n;
 const x=q[0]*scale,y=q[1]*scale,z=q[2]*scale,r=screenDegrees*Math.PI/180;
 const screenX=Math.cos(r)*x+Math.sin(r)*y,screenY=-Math.sin(r)*x+Math.cos(r)*y;
 // A 1-degree dead zone suppresses hand tremor; 26 degrees reaches full motion.
 const axis=v=>Math.sign(v)*clamp((Math.abs(v)-1)/25,0,1);
 return {x:axis(screenY),y:axis(-screenX),z:axis(-z)};
}
export function createDeviceMotion({clock=()=>performance.now()}={}){
 let enabled=false,suspended=false,source='none',neutral=null,latest=null,screen=0,lastSample=-Infinity,sensitivity=1,current=zero(),target=zero();
 function recenter(){neutral=latest?.slice()??null;target=zero();}
 function invalidate(){neutral=null;latest=null;lastSample=-Infinity;target=zero();}
 return {
  enable(value,nextSource='external'){
   const next=Boolean(value);if(next!==enabled||source!==nextSource)invalidate();enabled=next;source=next?String(nextSource):'none';
  },
  // Keep the last visible pose while frozen, then ease out on the first resumed frames.
  suspend(value){if(suspended!==Boolean(value)){suspended=Boolean(value);invalidate();}},
  setSensitivity(value){if(!Number.isFinite(value)||value<.25||value>2)throw Error('倾斜灵敏度应为 0.25–2');sensitivity=value;},
  sample(value,screenDegrees=0){
   if(!enabled||suspended)return false;
   const q=normalized(value);if(!Number.isFinite(screenDegrees)||screenDegrees%90!==0)throw Error('屏幕旋转角度无效');
   const nextScreen=((screenDegrees%360)+360)%360,now=clock();
   if(nextScreen!==screen||now-lastSample>1200)neutral=null;
   screen=nextScreen;latest=q;lastSample=now;neutral??=q.slice();target=relativeTilt(neutral,q,screen);return true;
  },
  recenter,
  step(dt){
   const active=enabled&&!suspended&&clock()-lastSample<=1200;
   const desired=active?target:zero(),a=1-Math.exp(-clamp(dt,0,.1)/.16);
   for(const k of ['x','y','z'])current[k]+=(clamp(desired[k]*sensitivity,-1,1)-current[k])*a;
   return {...current};
  },
  state(){return {enabled,suspended,source,sensitivity,status:!enabled?'off':suspended?'paused':!latest?'waiting':clock()-lastSample>1200?'stale':'active',pose:{...current}};}
 };
}
export function applyDeviceMotion(frame,pose,parameters){
 // Only add input parameters. In particular, never overwrite LPK hair physics outputs.
 const result={...frame},offsets={ParamAngleX:pose.x*10,ParamAngleY:pose.y*8,ParamAngleZ:pose.z*6,ParamBodyAngleZ:pose.z*1.2,ParamEyeBallX:pose.x*.35,ParamEyeBallY:pose.y*.25};
 for(const [id,delta]of Object.entries(offsets)){const p=parameters.find(p=>p.id===id);if(p&&Math.abs(delta)>1e-8)result[id]=clamp((result[id]??p.default)+delta,p.min,p.max);}
 return result;
}
