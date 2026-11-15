// Cubism motion3 curves: linear, unrestricted cubic Bezier, stepped and inverse-stepped.
const lerp=(a,b,t)=>a+(b-a)*t;
const cubic=(a,b,c,d,t)=>lerp(lerp(lerp(a,b,t),lerp(b,c,t),t),lerp(lerp(b,c,t),lerp(c,d,t),t),t);
export function compileCurve(values){
 if(!Array.isArray(values)||values.length<2||!values.every(Number.isFinite))throw Error('Invalid motion curve');
 let start={t:values[0],v:values[1]},segments=[];
 for(let i=2;i<values.length;){
  const kind=values[i++],n=kind===1?6:2;
  if(![0,1,2,3].includes(kind)||i+n>values.length)throw Error('Invalid motion segment');
  const points=[];for(let j=0;j<n;j+=2)points.push({t:values[i+j],v:values[i+j+1]});i+=n;
  const end=points[points.length-1];if(end.t<start.t)throw Error('Nonmonotonic motion');
  segments.push({kind,start,points,end});start=end;
 }
 return time=>{
  if(time<=values[0])return values[1];
  const s=segments.find(s=>time<s.end.t);if(!s)return start.v;
  if(s.kind===2)return s.start.v;if(s.kind===3)return s.end.v;
  if(s.kind===0)return lerp(s.start.v,s.end.v,(time-s.start.t)/Math.max(1e-9,s.end.t-s.start.t));
  let lo=0,hi=1;for(let i=0;i<24;i++){const t=(lo+hi)/2;if(cubic(s.start.t,s.points[0].t,s.points[1].t,s.end.t,t)<time)lo=t;else hi=t;}
  return cubic(s.start.v,s.points[0].v,s.points[1].v,s.end.v,(lo+hi)/2);
 };
}
export function compileMotion(data){
 const duration=data.Meta?.Duration;if(!Number.isFinite(duration)||duration<=0)throw Error('Invalid motion duration');
 const curves=(data.Curves||[]).filter(c=>c.Target==='Parameter').map(c=>[c.Id,compileCurve(c.Segments)]);
 return {duration,sample(time,loop=false){const t=loop?Math.max(0,time)%duration:Math.max(0,Math.min(duration,time));return Object.fromEntries(curves.map(([id,evaluate])=>[id,evaluate(t)]));}};
}
