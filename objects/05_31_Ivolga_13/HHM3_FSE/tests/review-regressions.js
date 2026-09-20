'use strict';
const assert=require('node:assert/strict');
module.exports=function(test,create,epoch){
 function fixture(id='504'){
  const h=create(),c=h.C.circuits[id],handlers={},values={},writes=[],logs=[];
  let now=epoch,failure=()=>false,drop=()=>false;
  const R=h.load('HHM3Runtime');
  function emit(path,value,retained=false){for(const fn of handlers[R.topic(path)]||[])fn({value:String(typeof value==='boolean'?(value?1:0):value),retained});}
  const dev=new Proxy(values,{set(o,p,v){
   const w={path:p,value:v,at:now};writes.push(w);const e=failure(w);
   if(e&&e!=='after'){w.error=true;throw Error('before apply');}
   o[p]=v;
   if(p===c.level){o[c.enable]=v>0;if(!drop(c.enable))emit(c.enable,o[c.enable]);}
   if(!drop(p))emit(p,v);
   if(e==='after'){w.error=true;throw Error('after apply');}return true;
  }});
  const log={};for(const level of ['info','warning','error'])log[level]=s=>logs.push({level,s});
  const io=R.io({dev,now:()=>now,trackMqtt:(t,f)=>(handlers[t]||(handlers[t]=[])).push(f),publish:()=>{},log},'test',[c.level,c.enable,c.pump]);
  const step=h.load('HHM3Outputs').create(c,io);
  return {c,io,values,writes,logs,emit,fail:f=>failure=f,drop:f=>drop=f,
   run:(valve=20,pump=true,dt=5000)=>{now+=dt;io.begin();return step({valve,pump},now);},
   clock:dt=>now+=dt};
 }
 test('MAO4: independent closed tuples for 560/561/562; AUTO-ON then final switch readback',()=>{
  for(const id of ['501','502','504']){
   const f=fixture(id),c=f.c;assert.equal(c.valveClosedLevel,1);assert.equal(c.valveClosedEnable,id==='501');
   f.io.write(c.level,0,true);assert.equal(f.values[c.enable],false);
   const r=f.run(0,false);assert.equal(r.ready,true);assert.equal(r.closed_readback_match,true);
   assert.equal(f.values[c.enable],c.valveClosedEnable);assert.equal(f.values[c.level],1);
   assert.equal(c.level,'A05/Channel '+({'501':1,'502':2,'504':3}[id])+' Dimming Level');
  }
 });
 test('MAO4: no Switch ON without a new non-retained matching Level readback',()=>{
  const f=fixture();f.drop(p=>p===f.c.level);
  let r=f.run();assert.equal(r.state,'WAIT_LEVEL_READBACK');
  assert.equal(f.values[f.c.enable],true); // Level itself AUTO-ON, even before explicit ON.
  assert.equal(f.values[f.c.pump],false);
  assert.ok(!f.writes.some(w=>w.path===f.c.enable&&w.value===true));
  f.emit(f.c.level,f.values[f.c.level],true);r=f.run();assert.equal(r.state,'WAIT_LEVEL_READBACK');
  r=f.run();assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(f.values[f.c.enable],false);
  f.drop(()=>false);for(let i=0;i<5;i++)r=f.run();assert.equal(r.ready,true);
 });
 test('MAO4: pump stop error while awaiting readback immediately attempts Switch OFF',()=>{
  const f=fixture();f.drop(p=>p===f.c.level);f.fail(w=>w.path===f.c.pump&&w.value===false);
  const r=f.run();assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.ready,false);
  assert.ok(f.writes.some(w=>w.path===f.c.enable&&w.value===false));assert.equal(f.values[f.c.enable],false);
 });
 test('MAO4: separate Level/ON errors before and after application, startup and running',()=>{
  for(const running of [false,true])for(const channel of ['level','enable'])for(const when of [true,'after']){
   const f=fixture();if(running)assert.equal(f.run(10).ready,true);
   const n=f.writes.length;
   f.fail(w=>w.path===f.c[channel]&&(channel!=='enable'||w.value===true)?when:false);
   let r=f.run(40);assert.equal(r.ready,false);assert.equal(f.values[f.c.pump],false);
   assert.equal(f.values[f.c.enable],false);
   if(channel==='level')assert.ok(!f.writes.slice(n).some(w=>w.path===f.c.enable&&w.value===true));
   f.fail(()=>false);for(let i=0;i<6;i++)r=f.run(40);
   assert.equal(r.ready,true);assert.equal(f.values[f.c.enable],true);
  }
 });
 test('MAO4: failed OFF after 0-to-1 AUTO-ON never claims closure or repeatedly writes Level',()=>{
  const f=fixture();f.io.write(f.c.level,0,true);
  f.fail(w=>w.path===f.c.enable&&w.value===false);
  let r=f.run(0,true);assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.closed_readback_match,false);
  assert.equal(f.values[f.c.enable],true);assert.equal(f.values[f.c.pump],false);
  const n=f.writes.filter(w=>w.path===f.c.level).length;
  for(let i=0;i<10;i++)r=f.run(0,true);
  assert.equal(f.writes.filter(w=>w.path===f.c.level).length,n);
  assert.equal(r.ready,false);f.fail(()=>false);
  for(let i=0;i<5;i++)r=f.run(0,true);
  assert.equal(r.ready,true);assert.equal(r.closed_readback_match,true);assert.equal(f.values[f.c.pump],true);
 });
 test('MAO4: absent OFF readback, external Level change and retry preserve uncertainty',()=>{
  const f=fixture();assert.equal(f.run().ready,true);
  f.drop(p=>p===f.c.enable);
  let r=f.run(0,true);assert.equal(r.ready,false);assert.equal(r.state,'WAIT_SWITCH_READBACK');
  for(let i=0;i<3;i++)r=f.run(0,true);
  assert.equal(r.ready,false);assert.equal(f.values[f.c.pump],false);
  f.drop(()=>false);for(let i=0;i<6;i++)r=f.run(0,true);assert.equal(r.ready,true);
  f.values[f.c.level]=90;f.emit(f.c.level,90);r=f.run(0,true);
  assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.ready,false);
  for(let i=0;i<6;i++)r=f.run(0,true);assert.equal(r.ready,true);assert.equal(f.values[f.c.level],1);
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
 test('integration: MAO4 Level/ON failure removes only failed request; neighbours remain active',()=>{
  for(const channel of ['level','enable']){
   const h=create();h.enableAll();h.samples();h.start();h.advance(300000);const c=h.C.circuits['504'];
   h.fail(w=>w.path===c[channel]&&(channel==='level'?w.value>1:w.value===true));
   const begin=h.writes.length;h.advance(100000);
   const errors=h.writes.slice(begin).filter(w=>w.path==='HHM3_FSE/circuits_json').map(w=>JSON.parse(w.value)['504']).filter(r=>/UNCERTAIN|ERROR/.test(r.reason));
   assert.ok(errors.length>0);errors.forEach(r=>assert.equal(r.demand,false));
   for(const id of ['501','502','503','505'])assert.equal(h.report()[id].demand,true,id);
   assert.equal(h.request(),45);h.fail('');h.advance(100000);assert.equal(h.report()['504'].demand,true);
  }
 });
};
