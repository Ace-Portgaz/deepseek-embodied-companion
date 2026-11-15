import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../vendor/rem/RemBody/assets/rem-bust-v4/preview/visual-follow.js',import.meta.url),'utf8');
const {createVisualFollow}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const v=createVisualFollow();
const bounds=['ParamEyeBallX','ParamEyeBallY','ParamAngleX','ParamAngleY','ParamAngleZ'].map(id=>({id,min:id.includes('Eye')?-1:-30,max:id.includes('Eye')?1:30}));
for(let i=0;i<30;i++){v.target(1,-1,true,i*33);v.step(.033,i*33);}
let frame=v.apply({ParamMouthOpenY:.4,ParamEyeLOpen:.1},bounds);
assert(frame.ParamEyeBallX>.6&&frame.ParamEyeBallY<-.5);
assert.equal(frame.ParamMouthOpenY,.4);assert.equal(frame.ParamEyeLOpen,.1);
v.respond('NOD');v.step(.1,1000);frame=v.apply({ParamAngleY:-30},bounds);assert(frame.ParamAngleY>=-30);
assert.throws(()=>v.target(NaN,0,true));assert.throws(()=>v.respond('unknown'));
for(let i=0;i<80;i++)v.step(.05,3000+i*50);
assert(Math.abs(v.state().x)<.01);assert(v.state().mix<.01);
v.reset();assert.equal(v.state().enabled,false);
assert.deepEqual(v.apply({ParamMouthOpenY:.2},[]),{ParamMouthOpenY:.2});
console.log('PASS: visual parameter direction, bounds, expression preservation and stale-target release');
