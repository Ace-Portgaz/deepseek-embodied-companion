import assert from 'node:assert/strict';
import {compileCurve,compileMotion} from '../vendor/rem/RemBody/assets/rem-bust-v4/preview/motion-clip.js';
import {hitMeshes,triangleContains} from '../vendor/rem/RemBody/assets/rem-bust-v4/preview/body-hit-test.js';
import {createAuthorInteraction} from '../vendor/rem/RemBody/assets/rem-bust-v4/preview/author-interaction.js';
assert.equal(compileCurve([0,0,0,2,4])(1),2);
assert.equal(compileCurve([0,0,2,2,4])(1),0);
assert.equal(compileCurve([0,0,3,2,4])(1),4);
assert.ok(Math.abs(compileCurve([0,0,1,.1,0,.9,1,1,1])(.5)-.5)<1e-5);
assert.throws(()=>compileCurve([0,0,7,1,1]));
assert.ok(triangleContains(.2,.2,[0,0,1,0,0,1],0,1,2));
assert.ok(!triangleContains(.9,.9,[0,0,1,0,0,1],0,1,2));
const d={ids:['back','front'],renderOrders:[0,1],opacities:[1,1],vertexPositions:[[0,0,1,0,0,1],[0,0,1,0,0,1]],indices:[[0,1,2],[0,1,2]]};
assert.equal(hitMeshes(.2,.2,d,{back:'body',front:'hand'}),'hand');
d.opacities[1]=0;assert.equal(hitMeshes(.2,.2,d,{back:'body',front:'hand'}),'body');
assert.equal(hitMeshes(2,2,d,{back:'body',front:'hand'}),null);
// Synthetic fixtures exercise control logic without redistributing any artist asset.
const root=new URL('https://fixtures.invalid/');
const faceIds={'脸红':'key7','爱心眼':'key4','黑框眼镜':'key11','流冷汗':'key13','＞＜':'key1','屑屑眼':'key2'};
const fixtures=new Map();
const config={expressions:Object.entries(faceIds).map(([name,id],i)=>{
 const file=`expression-${i}.json`;fixtures.set(file,{Parameters:[{Id:id,Value:1,Blend:'Overwrite'}]});return {name,file};
}),motions:[]};
for(const [i,name] of ['IDLE','默认手切举手','举手切默认手','竖手指切出来动画','竖手指切回默认','狗尾草切换出来','狗尾草切回默认手','脱捕'].entries()){
 const returning=name.includes('切回')||name==='举手切默认手',idle=name==='IDLE';
 const file=`motion-${i}.json`,clip={Meta:{Duration:1},Curves:[{Target:'Parameter',Id:'Movement2',Segments:[0,returning?1:0,0,1,idle||returning?0:1]},{Target:'Parameter',Id:'JawOpen',Segments:[0,0,0,1,0]}]};
 fixtures.set(file,clip);config.motions.push({name,file});
 for(let t=0;t<=1;t+=.05)assert.ok(Object.values(compileMotion(clip).sample(t)).every(Number.isFinite));
}
fixtures.set('interaction.json',config);
const previousFetch=globalThis.fetch;
globalThis.fetch=async url=>{const value=fixtures.get(new URL(url).pathname.slice(1));return {ok:!!value,json:async()=>structuredClone(value)};};
const parameters=[...Object.values(faceIds),'Movement2'].map(id=>({id,min:0,max:1,default:0}));
const a=await createAuthorInteraction(new URL('interaction.json',root),parameters);
globalThis.fetch=previousFetch;
const base={ParamEyeBallX:.4,JawOpen:.6,AngleX:5},w={};
a.choose('脸红');let f;for(let i=0;i<8;i++)f=a.apply(base,w,.05);
assert.ok(f.key7>.99);assert.equal(f.JawOpen,.6);assert.equal(f.ParamEyeBallX,.4);
a.choose('黑框眼镜');a.choose('爱心眼');for(let i=0;i<8;i++)f=a.apply(base,w,.05);
assert.ok(f.key11>.99&&f.key4>.99);assert.ok((f.key7||0)<.01);
a.choose('抚胸手');for(let i=0;i<35;i++)f=a.apply(base,w,.05);
assert.ok(f.Movement2>.9);assert.equal(f.JawOpen,.6);assert.equal(f.AngleX,5);
for(let i=0;i<150;i++)f=a.apply(base,w,.05);
assert.equal(a.state().motion,'IDLE');assert.ok((f.Movement2||0)<.01);
a.choose('全部恢复');for(let i=0;i<8;i++)f=a.apply(base,w,.05);assert.ok((f.key11||0)<.01);
a.touch('tail');for(let i=0;i<8;i++)f=a.apply(base,w,.05);assert.ok(f.key13>.99);
a.observed('WAVE');for(let i=0;i<200;i++)f=a.apply(base,w,.05);assert.equal(a.state().motion,'IDLE');
console.log('PASS: synthetic curves, mesh hit ordering/background, expressions/accessory reset, camera/lip preservation and gesture return.');
