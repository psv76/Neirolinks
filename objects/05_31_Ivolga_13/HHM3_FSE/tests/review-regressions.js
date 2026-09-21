'use strict';
const assert=require('node:assert/strict');
module.exports=function(test,create,epoch){
 function fixture(id='504'){
  const h=create(),c=h.C.circuits[id],handlers={},values={},writes=[],logs=[];
  let now=epoch,failure=()=>false,drop=()=>false,position=0;
  const R=h.load('HHM3Runtime');
  function emit(path,value,retained=false){for(const fn of handlers[R.topic(path)]||[])fn({value:String(typeof value==='boolean'?(value?1:0):value),retained});}
  const dev=new Proxy(values,{set(o,p,v){
   const w={path:p,value:v,at:now};writes.push(w);const e=failure(w);
   if(e&&e!=='after'){w.error=true;throw Error('before apply');}
   o[p]=v;
   // Ordinary Level does not energize the Switch; only explicit ON does.
   if(p===c.level||p===c.enable)position=o[c.enable]?(o[c.level]||0):0;
   w.position=position;
   if(!drop(p))emit(p,v);
   if(e==='after'){w.error=true;throw Error('after apply');}return true;
  }});
  const log={};for(const level of ['info','warning','error'])log[level]=s=>logs.push({level,s});
  const io=R.io({dev,now:()=>now,trackMqtt:(t,f)=>(handlers[t]||(handlers[t]=[])).push(f),publish:()=>{},log},'test',[c.level,c.enable,c.pump]);
  let step=h.load('HHM3Outputs').create(c,io);
  return {c,io,values,writes,logs,emit,position:()=>position,fail:f=>failure=f,drop:f=>drop=f,
   run:(valve=20,pump=true,dt=5000)=>{now+=dt;io.begin();return step({valve,pump},now);},
   restart:()=>step=h.load('HHM3Outputs').create(c,io),clock:dt=>now+=dt};
 }
 const ids=['501','502','504'];
 test('A05 config separates active range from OFF command for all three channels',()=>{
  const h=create();for(const id of ids){const c=h.C.circuits[id];
   assert.equal(c.valveOffCommand,false);assert.equal(c.valveActiveMinLevel,1);assert.equal(c.valveActiveMaxLevel,100);
   assert.equal(c.valveClosedLevel,undefined);assert.equal(c.valveClosedEnable,undefined);
  }assert.equal(h.C.circuits['504'].floorOnlyMaxPct,50);
 });
 test('ordinary A05 Level never changes Switch; explicit ON opens model',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;
   f.io.write(c.enable,false,true);
   f.io.write(c.level,20,true);assert.equal(f.values[c.enable],false);assert.equal(f.position(),0);
   f.io.write(c.enable,true,true);assert.equal(f.position(),20);
   f.io.write(c.level,30,true);assert.equal(f.values[c.enable],true);assert.equal(f.position(),30);
   f.io.write(c.enable,false,true);assert.equal(f.values[c.level],30);assert.equal(f.position(),0);
  }
 });
 test('A05 OFF preserves Level and restart issues OFF before opening',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.io.write(c.level,20,true);const n=f.writes.length;
   let r=f.run(0,false);assert.equal(r.state,'OFF_COMMANDED');assert.equal(r.ready,false);
   assert.equal(f.values[c.level],20);assert.equal(f.position(),0);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   r=f.run(40,true);assert.equal(r.state,'HEAT_COMMANDED');assert.equal(r.ready,true);
   assert.equal(f.position(),Math.round(1+99*.4));
   assert.ok(f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('known OFF with hot-port Level retained does not write Level on idle cycles',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.values[c.level]=73;f.emit(c.level,73);
   const n=f.writes.length;for(let i=0;i<5;i++)f.run(0,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.level],73);
  }
 });
 test('missing MQTT echo 120 seconds does not cancel accepted heat for 501/502/504',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.drop(()=>true);
   const n=f.writes.length;
   for(let i=0;i<24;i++){const r=f.run(40,true);assert.equal(r.state,'HEAT_COMMANDED');assert.equal(r.ready,true);}
   assert.equal(f.values[c.pump],true);assert.equal(f.position(),41);
   assert.ok(f.writes.slice(n).some(w=>w.path===c.level));
   assert.ok(f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('old retained MQTT OFF cannot veto explicit Switch ON command',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.emit(c.enable,0,true);f.drop(()=>true);
   for(let i=0;i<4;i++){const r=f.run(30,true);assert.equal(r.ready,true);}
   assert.equal(f.values[c.pump],true);assert.ok(f.writes.some(w=>w.path===c.level));
   assert.ok(f.writes.some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('A05 retarget writes integer Level without stopping operating pump',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.run(20,true);
   const n=f.writes.length,r=f.run(40,true);assert.equal(r.ready,true);
   assert.equal(r.state,'HEAT_COMMANDED');assert.equal(f.position(),41);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.pump&&w.value===false));
   assert.ok(f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('A05 OFF command error (before/after apply) cannot be reported as accepted',()=>{
  for(const id of ids)for(const error of [true,'after']){
   const f=fixture(id),c=f.c;f.run(0,false);f.run(20,true);f.fail(w=>w.path===c.enable&&w.value===false?error:false);
   let r=f.run(0,false);assert.equal(r.state,'OFF_WRITE_ERROR');assert.equal(r.ready,false);
   const n=f.writes.length;
   for(let i=0;i<3;i++){r=f.run(40,true);assert.equal(r.ready,false);}
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   f.fail(()=>false);r=f.run(40,true);assert.equal(r.state,'OFF_COMMANDED');
   r=f.run(40,true);assert.equal(r.state,'HEAT_COMMANDED');
  }
 });
 test('A05 Level write error aborts opening and attempts OFF',()=>{
  for(const id of ids)for(const error of [true,'after']){
   const f=fixture(id),c=f.c;f.run(0,false);f.fail(w=>w.path===c.level?error:false);
   const n=f.writes.length,r=f.run(40,true);assert.equal(r.ready,false);
   assert.equal(r.state,'LEVEL_WRITE_ERROR');assert.equal(f.values[c.pump],false);
   assert.ok(f.writes.slice(n).some(w=>w.path===c.enable&&w.value===false));
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
   f.fail(()=>false);assert.equal(f.run(40,true).ready,true);
  }
 });
 test('Switch ON write error aborts before pump ON and retries only after OFF',()=>{
  for(const id of ids)for(const error of [true,'after']){
   const f=fixture(id),c=f.c;f.run(0,false);
   f.fail(w=>w.path===c.enable&&w.value===true?error:false);
   const n=f.writes.length,r=f.run(40,true);
   assert.equal(r.state,'ENABLE_WRITE_ERROR');assert.equal(r.ready,false);
   assert.equal(f.values[c.pump],false);assert.equal(f.values[c.enable],false);
   const attempt=f.writes.slice(n),li=attempt.findIndex(w=>w.path===c.level);
   const on=attempt.findIndex(w=>w.path===c.enable&&w.value===true);
   assert.ok(li>=0&&on>li);assert.ok(!attempt.some(w=>w.path===c.pump&&w.value===true));
   assert.equal(f.run(40,true).state,'OFF_COMMANDED');
   f.fail(()=>false);assert.equal(f.run(40,true).state,'HEAT_COMMANDED');
  }
 });
 test('opening orders Level -> Switch ON -> pump ON, with Switch initially OFF',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);
   const n=f.writes.length,r=f.run(40,true);assert.equal(r.ready,true);
   const writes=f.writes.slice(n);
   const l=writes.findIndex(w=>w.path===c.level);
   const on=writes.findIndex(w=>w.path===c.enable&&w.value===true);
   const p=writes.findIndex(w=>w.path===c.pump&&w.value===true);
   assert.ok(l>=0&&l<on&&on<p);assert.equal(f.position(),41);
  }
 });
 test('failed OFF following Level error blocks further positive Level until recovered',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);
   f.fail(w=>w.path===c.level?'after':w.path===c.enable&&w.value===false);
   let r=f.run(40,true);assert.equal(r.state,'OFF_WRITE_ERROR');assert.equal(r.ready,false);
   const n=f.writes.length;
   for(let i=0;i<4;i++){r=f.run(40,true);assert.equal(r.ready,false);}
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   f.fail(()=>false);assert.equal(f.run(40,true).state,'OFF_COMMANDED');
   assert.equal(f.run(40,true).ready,true);
  }
 });
 test('pump OFF write error blocks first positive Level, but still attempts valve OFF',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.io.write(c.pump,true,true);
   f.fail(w=>w.path===c.pump&&w.value===false);
   const n=f.writes.length,r=f.run(40,true);
   assert.equal(r.ready,false);assert.equal(r.state,'PUMP_WRITE_ERROR');
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   assert.ok(f.writes.slice(n).some(w=>w.path===c.enable&&w.value===false));
   f.fail(()=>false);assert.equal(f.run(40,true).state,'OFF_COMMANDED');
   assert.equal(f.run(40,true).ready,true);
  }
 });
 test('pump ON write error attempts OFF and does not grant heat request',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);
   f.fail(w=>w.path===c.pump&&w.value===true);const r=f.run(40,true);
   assert.equal(r.ready,false);assert.equal(r.state,'PUMP_WRITE_ERROR');
   assert.equal(f.values[c.enable],false);
   f.fail(()=>false);assert.equal(f.run(40,true).state,'OFF_COMMANDED');
   assert.equal(f.run(40,true).ready,true);
  }
 });
 test('no-demand cancels hot-port opening with OFF only, may keep circulation',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.run(40,true);
   const n=f.writes.length,r=f.run(0,true);assert.equal(r.state,'OFF_COMMANDED');
   assert.equal(r.ready,true);assert.equal(f.values[c.enable],false);
   assert.equal(f.values[c.pump],true);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
  }
 });
 test('restart and clock rollback issue OFF; next tick may resume without MQTT echo',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.run(40,true);
   f.restart();f.drop(()=>true);const n=f.writes.length;
   let r=f.run(40,true);assert.equal(r.state,'OFF_COMMANDED');assert.equal(r.ready,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   assert.equal(f.run(40,true).state,'HEAT_COMMANDED');
   r=f.run(40,true,-20000);assert.equal(r.state,'OFF_COMMANDED');assert.equal(r.ready,false);
  }
 });
 test('I/O diagnostics: SENT/CACHE_SKIP/ERROR, fresh MQTT readback and external correction',()=>{
  const f=fixture(),p=f.c.pump;
  let r=f.io.write(p,true);assert.equal(r.status,'SENT');assert.equal(r.sent,true);
  r=f.io.write(p,true);assert.equal(r.status,'CACHE_SKIP');assert.equal(r.sent,false);assert.equal(r.readback.value,1);
  f.emit(p,0);r=f.io.write(p,true);assert.equal(r.status,'SENT');
  f.fail(w=>w.path===p);r=f.io.write(p,false);assert.equal(r.status,'ERROR');assert.equal(r.sent,false);
  f.fail(()=>false);f.drop(p2=>p2===p);r=f.io.write(p,false);assert.equal(r.status,'SENT');
  assert.equal(r.readback.value,1);assert.equal(f.io.matches(p,false),false);
 });
 test('WB log levels: warnings, closure/thermal alarms and recovery use named methods',()=>{
  const f=fixture();
  f.io.event('504','OUTPUT_WRITE_ERROR','write failed');assert.equal(f.logs.at(-1).level,'warning');
  f.io.event('504','CLOSURE_UNCERTAIN','not closed');assert.equal(f.logs.at(-1).level,'error');
  const e=f.io.event('504','NORMAL','');assert.equal(e.severity,'recovery');assert.equal(f.logs.at(-1).level,'info');
 });
 test('first start preserves 18 existing VD intents/targets with empty HHM3 storage; 505 OFF',()=>{
  const ref=create(),boiler={};
  const old=ref.Z.filter(z=>z.id!=='505');assert.equal(old.length,18);
  old.forEach((z,i)=>{boiler['NL_simple_thermostat_'+z.id+'/target_state']=i%2===0;boiler['NL_simple_thermostat_'+z.id+'/target_temperature']=z.min+1;});
  const h=create({values:{boiler}});
  for(const [i,z]of old.entries()){assert.equal(h.stores.hhm3_thermostats[z.id].state,i%2===0?1:0);assert.equal(h.stores.hhm3_thermostats[z.id].target,z.min+1);}
  assert.equal(h.stores.hhm3_thermostats['505'].state,0);assert.equal(h.stores.hhm3_thermostats['505'].target,20);
  for(const restored of [create({stores:h.stores,values:h.values}),create({stores:h.stores})]){
   for(const [i,z]of old.entries()){const p='NL_simple_thermostat_'+z.id+'/';
    assert.equal(restored.values.boiler[p+'target_state'],i%2===0);assert.equal(restored.values.boiler[p+'target_temperature'],z.min+1);}
   assert.equal(restored.values.boiler['NL_simple_thermostat_505/target_state'],false);
  }
 });
 test('clean first creation: all 18 defaults OFF, correct targets; subsequent explicit edits survive restart',()=>{
  const h=create();for(const z of h.Z){assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/target_state'],false);assert.equal(h.stores.hhm3_thermostats[z.id].target,z.target);}
  h.set('boiler','NL_simple_thermostat_601/target_state',true);h.set('boiler','NL_simple_thermostat_601/target_temperature',24);
  h.tick('620');h.set('boiler','NL_simple_thermostat_601/target_state',false);h.tick('620');
  const b=create({stores:h.stores});assert.equal(b.values.boiler['NL_simple_thermostat_601/target_state'],false);
  assert.equal(b.values.boiler['NL_simple_thermostat_601/target_temperature'],24);
 });
 test('integration: closure errors on each mixed circuit invalidate only its request, no Level writes',()=>{
  for(const id of ids){const h=create();h.enableAll();h.samples();h.start();h.advance(300000);const c=h.C.circuits[id];
   const n=h.writes.length;h.fail(w=>w.path===c.enable&&w.value===false);
   h.temperatures[c.supply]=c.supplyImmediateStopC;h.deliver('boiler',h.topic(c.supply),c.supplyImmediateStopC,false);h.advance(15000);
   assert.equal(h.report()[id].demand,false);assert.equal(h.report()[id].output.state,'OFF_WRITE_ERROR');
   assert.ok(!h.writes.slice(n).some(w=>w.path===c.level));
   for(const other of ['501','502','503','504','505'].filter(x=>x!==id))assert.equal(h.report()[other].demand,true,other);
   h.fail('');h.temperatures[c.supply]=25;h.advance(230000);assert.equal(h.report()[id].demand,true);
  }
 });
 test('integration: per-circuit Level failure excludes failing transactions; neighbours continue',()=>{
  for(const id of ids){const h=create();h.enableAll();h.samples();h.start();h.advance(300000);const c=h.C.circuits[id],n=h.writes.length;
   h.fail(w=>w.path===c.level);h.temperatures[c.supply]=18;h.advance(350000);
   const errors=h.writes.slice(n).filter(w=>w.path==='HHM3_FSE/circuits_json').map(w=>JSON.parse(w.value)[id]).filter(r=>r.output.fault);
   assert.ok(errors.length>0);errors.forEach(r=>assert.equal(r.demand,false));
   for(const other of ['501','502','503','504','505'].filter(x=>x!==id))assert.equal(h.report()[other].demand,true,other);
   h.fail('');h.advance(100000);assert.equal(h.report()[id].demand,true);
  }
 });
};
