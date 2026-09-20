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
   if(p===c.level){o[c.enable]=v>0;if(!drop(c.enable))emit(c.enable,o[c.enable]);}
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
 test('A05 model separates stored Level, Switch, position and AUTO transitions for each address',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;
   for(const [level,enabled,pos]of [[0,false,0],[1,true,1],[0,false,0],[20,true,20]]){
    f.io.write(c.level,level,true);assert.equal(f.values[c.enable],enabled);assert.equal(f.position(),pos);
   }
   f.io.write(c.enable,false,true);assert.equal(f.values[c.level],20);assert.equal(f.position(),0);
   f.io.write(c.enable,true,true);assert.equal(f.position(),20);
  }
 });
 test('A05 20/ON -> OFF only -> stored 20/OFF -> new target, no explicit ON',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.io.write(c.level,20,true);const begin=f.writes.length;
   let r=f.run(0,false);assert.equal(r.state,'CLOSED');assert.equal(r.closed_readback_match,true);
   assert.equal(r.saved_level,20);assert.equal(r.requested_level,null);assert.equal(r.requested_enable,false);
   assert.equal(f.values[c.level],20);assert.equal(f.position(),0);
   assert.ok(!f.writes.slice(begin).some(w=>w.path===c.level));
   r=f.run(40,true);assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
   assert.equal(f.position(),1+99*0.4);
   assert.ok(!f.writes.slice(begin).some(w=>w.path===c.enable&&w.value===true));
  }
 });
 test('A05 closed command accepts unknown/manual/stored Level without changing it',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;let r=f.run(0,true);
   assert.equal(r.ready,true);assert.equal(r.saved_level,null);assert.equal(r.closed_readback_match,true);
   f.values[c.level]=73;f.emit(c.level,73);const n=f.writes.length;r=f.run(0,true);
   assert.equal(r.ready,true);assert.equal(r.saved_level,73);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
  }
 });
 test('A05 OFF write errors before/after application never claim closed or ready',()=>{
  for(const id of ids)for(const error of [true,'after']){
   const f=fixture(id),c=f.c;f.io.write(c.level,20,true);const n=f.writes.length;
   f.fail(w=>w.path===c.enable&&w.value===false?error:false);
   for(let i=0;i<4;i++){const r=f.run(0,true);assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);assert.equal(r.pump,false);}
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.level],20);
   f.fail(()=>false);let r;for(let i=0;i<5;i++)r=f.run(0,true);
   assert.equal(r.ready,true);assert.equal(r.closed_readback_match,true);assert.equal(f.position(),0);
  }
 });
 test('A05 old/cached/retained OFF cannot qualify a new close, timeout retries OFF only',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.io.write(c.level,20,true);f.io.write(c.enable,false,true);
   const n=f.writes.length;f.drop(p=>p===c.enable);
   let r=f.run(0,true);assert.equal(r.state,'CLOSING');assert.equal(r.closed_readback_match,false);
   f.emit(c.enable,0,true);r=f.run(0,true);assert.equal(r.ready,false);
   r=f.run(0,true);assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.ready,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.level],20);
   f.drop(()=>false);for(let i=0;i<5;i++)r=f.run(0,true);assert.equal(r.ready,true);
  }
 });
 test('A05 opening needs new Level AND Switch readback after Level, never cached ON',()=>{
  for(const id of ids)for(const missing of ['level','enable']){
   const f=fixture(id),c=f.c;f.run(0,false);f.drop(p=>p===c[missing]);const n=f.writes.length;
   let r=f.run(40,true);assert.equal(r.state,'OPENING');assert.equal(r.ready,false);assert.equal(f.values[c.pump],false);
   f.emit(c[missing],missing==='level'?1+99*0.4:1,true);
   r=f.run(40,true);assert.equal(r.ready,false);
   r=f.run(40,true);assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.enable&&w.value===true));
   f.drop(()=>false);for(let i=0;i<7;i++)r=f.run(40,true);assert.equal(r.ready,true);
  }
 });
 test('A05 asynchronous Level then ON readback enables pump only after both fresh messages',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.drop(p=>p===c.level||p===c.enable);
   let r=f.run(40,true);assert.equal(r.ready,false);assert.equal(f.values[c.pump],false);
   f.emit(c.level,1+99*0.4);r=f.run(40,true);assert.equal(r.ready,false);assert.equal(f.values[c.pump],false);
   f.emit(c.enable,1);r=f.run(40,true,1000);assert.equal(r.ready,true);assert.equal(r.state,'OPEN');assert.equal(f.values[c.pump],true);
  }
 });
 test('A05 Level failure before/after application, startup/running, closes only with OFF',()=>{
  for(const id of ids)for(const error of [true,'after'])for(const running of [false,true]){
   const f=fixture(id),c=f.c;if(running)f.run(10,true);else f.run(0,false);
   const n=f.writes.length;f.fail(w=>w.path===c.level?error:false);
   const r=f.run(40,true);assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);
   const writes=f.writes.slice(n);assert.equal(writes.filter(w=>w.path===c.level).length,1);
   assert.ok(writes.some(w=>w.path===c.enable&&w.value===false));assert.equal(f.position(),0);
   assert.ok(!writes.some(w=>w.path===c.enable&&w.value===true));assert.equal(f.values[c.pump],false);
  }
 });
 test('A05 Level failure followed by failed OFF retries only OFF until closure succeeds',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);
   f.fail(w=>w.path===c.level?'after':w.path===c.enable&&w.value===false);
   let r=f.run(40,true);assert.equal(r.state,'CLOSURE_UNCERTAIN');const n=f.writes.length;
   for(let i=0;i<4;i++){r=f.run(40,true);assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);}
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));f.fail(()=>false);
   for(let i=0;i<6;i++)r=f.run(40,true);assert.equal(r.ready,true);
  }
 });
 test('A05 pump stop readback/error prevents Level write and opening',()=>{
  for(const id of ids)for(const error of [false,true]){
   const f=fixture(id),c=f.c;f.run(20,true);f.values[c.pump]=true;f.emit(c.pump,1);
   const n=f.writes.length;if(error)f.fail(w=>w.path===c.pump&&w.value===false);else f.drop(p=>p===c.pump);
   let r=f.run(40,true);assert.equal(r.ready,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
   for(let i=0;i<3;i++)r=f.run(40,true);assert.equal(r.ready,false);
  }
 });
 test('A05 manual Level change while OPEN triggers OFF, then new commanded Level',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(40,true);f.values[c.level]=80;f.emit(c.level,80);
   const n=f.writes.length;let r=f.run(40,true);assert.equal(r.ready,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.enable],false);
   for(let i=0;i<4;i++)r=f.run(40,true);assert.equal(r.ready,true);assert.equal(f.position(),1+99*0.4);
  }
 });
 test('A05 cancelled opening enters OFF closure without another Level',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(0,false);f.drop(p=>p===c.level);f.run(40,true);
   const n=f.writes.length;let r=f.run(0,true);assert.equal(r.ready,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.enable],false);
   r=f.run(0,true);assert.equal(r.ready,true);assert.equal(r.closed_readback_match,true);
  }
 });
 test('A05 restart requalifies OFF; old readback cannot restart pump',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(40,true);f.restart();f.drop(p=>p===c.enable);
   const n=f.writes.length;const r=f.run(40,true);
   assert.equal(r.ready,false);assert.equal(r.pump,false);assert.equal(r.closed_readback_match,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));assert.equal(f.values[c.pump],false);
  }
 });
 test('A05 clock rollback invalidates confirmations and requalifies through OFF only',()=>{
  for(const id of ids){const f=fixture(id),c=f.c;f.run(40,true);const n=f.writes.length;
   const r=f.run(40,true,-20000);assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);
   assert.ok(!f.writes.slice(n).some(w=>w.path===c.level));
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
   assert.equal(h.report()[id].demand,false);assert.equal(h.report()[id].output.closed_readback_match,false);
   assert.ok(!h.writes.slice(n).some(w=>w.path===c.level));
   for(const other of ['501','502','503','504','505'].filter(x=>x!==id))assert.equal(h.report()[other].demand,true,other);
   h.fail('');h.temperatures[c.supply]=25;h.advance(230000);assert.equal(h.report()[id].demand,true);
  }
 });
 test('integration: per-circuit Level failure excludes failing transactions; neighbours continue',()=>{
  for(const id of ids){const h=create();h.enableAll();h.samples();h.start();h.advance(300000);const c=h.C.circuits[id],n=h.writes.length;
   h.fail(w=>w.path===c.level);h.advance(100000);
   const errors=h.writes.slice(n).filter(w=>w.path==='HHM3_FSE/circuits_json').map(w=>JSON.parse(w.value)[id]).filter(r=>r.output.fault);
   assert.ok(errors.length>0);errors.forEach(r=>assert.equal(r.demand,false));
   for(const other of ['501','502','503','504','505'].filter(x=>x!==id))assert.equal(h.report()[other].demand,true,other);
   h.fail('');h.advance(100000);assert.equal(h.report()[id].demand,true);
  }
 });
};
