'use strict';
const assert=require('node:assert/strict');
const callback=require('./wb240-callback');
module.exports=function(test,create,epoch){
 test('2.40 exact callback: live and retained traces are observationally identical',()=>{
  const replay=callback('/devices/A05/controls/Channel 1 Switch','0',true,1);
  const live=callback('/devices/A05/controls/Channel 1 Switch','0',false,0);
  assert.deepEqual(replay,live);assert.deepEqual(Object.keys(live),['topic','value']);
  assert.equal(Object.hasOwn(live,'retained'),false);assert.equal(Object.hasOwn(live,'qos'),false);
 });
 test('2.40 unknown/nonboolean metadata never qualifies sensor or frame, even after later false',()=>{
  const h=create(),W=h.load('HHM3Wire');
  for(const flag of [undefined,null,0,1,'false','true',{},[]]){
   const s=W.sensor();s.sample('25',flag,epoch);assert.equal(s.read(epoch,-20,100),null);
   assert.equal(s.runtimeStatus(),'RUNTIME_UNSUPPORTED');
   s.sample('25',false,epoch+5000);assert.equal(s.read(epoch+5000,-20,100),null);
   const rx=W.receiver(epoch);assert.equal(rx.accept('{}',flag,epoch),'RUNTIME_UNSUPPORTED');
   assert.equal(rx.accept('{}',false,epoch+5000),'RUNTIME_UNSUPPORTED');assert.equal(rx.read(epoch+5000).fresh,false);
  }
 });
 test('error clearance requires explicit fresh metadata and a subsequent measurement',()=>{
  const W=create().load('HHM3Wire'),s=W.sensor();
  s.sample(25,false,epoch);s.error('r',false);s.error('',true);s.sample(26,false,epoch+1);
  assert.equal(s.read(epoch+1,0,100),null,'retained empty error cannot clear live fault');
  s.error('',false);assert.equal(s.read(epoch+2,0,100),null);
  s.sample(27,false,epoch+3);assert.equal(s.read(epoch+3,0,100),27);
  s.error('',undefined);s.sample(28,false,epoch+4);assert.equal(s.read(epoch+4,0,100),null);
 });
 test('2.40 both boards cold retained 40/ON, temperatures and frames do not qualify or energize',()=>{
  const baseline=create(),initial={};
  for(const c of Object.values(baseline.C.circuits)){
   initial[c.pump]=true;
   if(c.level){initial[c.level]=40;initial[c.enable]=true;}
  }
  const h=create({apiVersion:'2.40.0',values:{boiler:initial}});h.enableAll();
  for(const board of ['boiler','gazebo'])for(const topic of h.topics(board)){
   h.deliver(board,topic,topic.endsWith('/meta/error')?'':/ Switch$|\/K[1-5]$/.test(topic)?'1':'40',true);
  }
  h.samples();h.start();h.advance(300000);
  assert.equal(h.request(),0);assert.equal(h.source().state,'RUNTIME_UNSUPPORTED');
  assert.equal(h.values.gazebo['NL_combo_thermostat_504/demand_valid'],false);
  assert.match(h.values.boiler['HHM3_FSE/runtime_status'],/RUNTIME_UNSUPPORTED/);
  for(const w of h.physical())assert.equal(w.value,false,'no heating writes under unsupported API: '+w.path);
  for(const id of ['501','502','503','504','505']){
   assert.equal(h.report()[id].demand,false);assert.equal(h.report()[id].pump_command,false);
  }
  assert.ok(h.physical().length>0,'OFF attempts are allowed only after commissioned state');
 });
 test('2.40 startup with no messages cannot energize; real live payloads still cannot prove freshness',()=>{
  const h=create({apiVersion:'2.40.0'});h.enableAll();h.start();h.advance(30000,false);
  for(const w of h.physical())assert.equal(w.value,false);
  h.samples();h.advance(30000);assert.equal(h.request(),0);
  assert.equal(h.source().command_sent,false);
 });
 test('2.40 absent MQTT metadata still cannot grant heating through 500',()=>{
  const h=create({apiVersion:'2.40.0'});h.enableAll();h.samples();h.start();h.advance(30000);
  assert.equal(h.request(),0);assert.equal(h.source().state,'RUNTIME_UNSUPPORTED');
  assert.equal(h.physical().filter(w=>w.value===true||typeof w.value==='number'&&w.value>0).length,0);
 });
 test('2.40 restart/reordered subscriptions/delayed retained/reconnect/clocks never qualify old cache',()=>{
  for(const order of [['624','620','500'],['620','500','624']]){
   const first=create({apiVersion:'2.40.0'});first.enableAll();first.start();first.advance(10000);
   const h=create({apiVersion:'2.40.0',stores:first.stores,values:first.values,startOrder:order});
   h.advance(30000,false);
   for(const board of ['boiler','gazebo'])for(const topic of h.topics(board))h.deliver(board,topic,'0',true);
   h.bridge(false);h.advance(135000,false);h.bridge(true);
   h.time(epoch-20000);h.advance(20000);h.time(epoch+1000000);h.advance(15000);
   assert.equal(h.request(),0);assert.equal(h.source().command_sent,false);
   for(const w of h.physical())assert.equal(w.value,false);
  }
 });
 test('2.40 blocked transport preserves 18 settings, 505 first boot OFF and ownership exclusions',()=>{
  const h=create({apiVersion:'2.40.0'});
  assert.equal(h.values.boiler['NL_simple_thermostat_505/target_state'],false);
  for(const [i,z]of h.Z.filter(z=>z.id!=='505').entries()){
   h.values.boiler['NL_simple_thermostat_'+z.id+'/target_state']=i%2===0;
   h.values.boiler['NL_simple_thermostat_'+z.id+'/target_temperature']=z.min+1;
  }
  h.advance(10000);const saved=JSON.parse(JSON.stringify(h.stores.hhm3_thermostats));
  const restarted=create({apiVersion:'2.40.0',stores:h.stores,values:h.values});restarted.advance(10000);
  assert.deepEqual(JSON.parse(JSON.stringify(restarted.stores.hhm3_thermostats)),saved);
  assert.equal(h.Z.filter(z=>z.id!=='505').length,18);
  assert.equal(restarted.C.source.noDemandMode,'unconfirmed');assert.equal(restarted.C.circuits['504'].floorOnlyMaxPct,50);
  assert.equal(restarted.physical().length,0,'no writes before commissioning');
 });
};
