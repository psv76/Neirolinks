'use strict';
const assert=require('node:assert/strict');
const createOutputs=require('../modules/HHM3Outputs').create;
module.exports=function(test){
 function fixture(){
  const c={periodMs:5000,valveActiveMinLevel:1,valveActiveMaxLevel:100,valveOffCommand:false,
   pump:'A03/K4',level:'A05/Channel 3 Dimming Level',enable:'A05/Channel 3 Switch'};
  let now=100000;const values={},writes=[];let noEcho=false,fail='';
  const io={read:p=>noEcho?null:(values[p]===undefined?null:values[p]),
   matches:(p,v)=>io.read(p)===(typeof v==='boolean'?(v?1:0):v),
   readback:p=>({value:io.read(p)}),
   write:(p,v)=>{writes.push({p,v});if(p===fail)return {ok:false,sent:false};
    values[p]=typeof v==='boolean'?(v?1:0):v;
    if(p===c.level){assert.equal(v%1,0);values[c.enable]=v>0?1:0;}
    return {ok:true,sent:true};}};
  const step=createOutputs(c,io);
  return {c,values,writes,noEcho:v=>noEcho=v,fail:v=>fail=v,
   run:(valve,pump=true,dt=5000)=>step({valve,pump},now+=dt)};
 }
 test('integer MAO4 command 20% becomes 21, no explicit Switch ON',()=>{
  const f=fixture();f.run(0,false);const r=f.run(20);
  assert.equal(r.state,'HEAT_COMMANDED');assert.equal(r.ready,true);
  assert.equal(r.requested_level,21);assert.equal(f.values[f.c.enable],1);
  assert.equal(f.values[f.c.pump],1);assert.ok(!f.writes.some(w=>w.p===f.c.enable&&w.v===true));
 });
 test('missing readback never cancels an accepted Level and pump command',()=>{
  const f=fixture();f.run(0,false);f.noEcho(true);
  for(let i=0;i<8;i++){const r=f.run(20);assert.equal(r.ready,true);assert.equal(r.state,'HEAT_COMMANDED');}
  assert.equal(f.values[f.c.pump],1);assert.equal(f.values[f.c.enable],1);
  assert.equal(f.writes.filter(w=>w.p===f.c.level).length,1);
 });
 test('retarget preserves pump and does not send Switch ON',()=>{
  const f=fixture();f.run(0,false);f.run(20);const n=f.writes.length;
  const r=f.run(40);assert.equal(r.ready,true);assert.equal(r.requested_level,41);
  assert.equal(f.values[f.c.pump],1);
  assert.ok(!f.writes.slice(n).some(w=>w.p===f.c.pump&&w.v===false));
  assert.ok(!f.writes.slice(n).some(w=>w.p===f.c.enable&&w.v===true));
 });
 test('OFF preserves Level, uses Switch OFF and does not assert hydraulic closure',()=>{
  const f=fixture();f.run(0,false);f.run(20);const n=f.writes.length;
  const r=f.run(0,false);assert.equal(r.state,'OFF_COMMANDED');assert.equal(r.ready,false);
  assert.equal(r.saved_level,21);assert.equal(f.values[f.c.enable],0);
  assert.ok(!f.writes.slice(n).some(w=>w.p===f.c.level));
 });
 test('actual Level write error cancels request and attempts OFF',()=>{
  const f=fixture();f.run(0,false);f.fail(f.c.level);const r=f.run(30);
  assert.equal(r.ready,false);assert.equal(r.state,'LEVEL_WRITE_ERROR');
  assert.equal(f.values[f.c.pump],0);assert.equal(f.values[f.c.enable],0);
 });
 test('OFF write error prevents new heating until OFF command accepted',()=>{
  const f=fixture();f.fail(f.c.enable);let r=f.run(0,false);
  assert.equal(r.state,'OFF_WRITE_ERROR');f.run(40);const count=f.writes.filter(w=>w.p===f.c.level).length;
  assert.equal(count,0);f.fail('');r=f.run(40);assert.equal(r.state,'OFF_COMMANDED');
  r=f.run(40);assert.equal(r.state,'HEAT_COMMANDED');
 });
};
if(require.main===module){let passed=0;module.exports((n,fn)=>{fn();passed++;console.log('PASS '+n);});console.log('RESULT: '+passed+' integer MAO4 groups PASS');}
