'use strict';
const assert=require('node:assert/strict');
module.exports=function(test,create){
 function setup(dropReadback){
  const h=create({dropReadback});
  h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);
  h.advance(210000);
  assert.equal(h.report()['502'].reason,'NORMAL');
  assert.equal(h.report()['502'].demand,true);
  return h;
 }
 function latest(h){return JSON.parse(h.messages.filter(m=>m.topic===h.C.houseTopic).at(-1).payload).groups['502'];}
 function step(h){h.time(h.now()+5000);h.tick('620');h.tick('500');}
 test('502 pending ON from zone 607 retains already verified ready 606 and mixer position',()=>{
  let drop=false;const h=setup(p=>drop&&p==='A13/K2');const before=h.report()['502'].valve_pct;
  drop=true;h.set('boiler','NL_simple_thermostat_607/target_state',true);step(h);
  const g=latest(h),r=h.report()['502'];
  assert.equal(h.values.boiler['NL_simple_thermostat_607/status'],'WAIT_OUTPUT_READBACK');
  assert.equal(g.partial_ready,true);assert.equal(g.degraded,true);assert.equal(g.ready,true);
  assert.equal(r.reason,'NORMAL');assert.equal(r.demand,true);assert.equal(r.requested_source_temperature,37);
  assert.equal(r.output.pump,true);assert.ok(r.valve_pct>=before,'no fall to zero on pending zone');
  assert.match(r.warning,/ожидает readback/);
  // Even though its ON was commanded, pending 607 must never be used to make
  // a non-ready group ready; the ready grant here belongs to 606 only.
  assert.equal(h.values.boiler['NL_simple_thermostat_607/current_state'],1);
  drop=false;h.deliver('boiler',h.topic('A13/K2'),1,false);step(h);
  assert.equal(latest(h).partial_ready,false);assert.equal(h.report()['502'].reason,'NORMAL');
 });
 test('502 only pending ON cannot grant pump or requested source temperature',()=>{
  let drop=true;const h=create({dropReadback:p=>drop&&p==='A13/K2'});h.samples();h.start();
  h.set('boiler','NL_simple_thermostat_607/target_state',true);
  h.advance(190000);
  const g=latest(h),r=h.report()['502'];
  assert.equal(g.partial_ready,false);assert.equal(g.ready,false);
  assert.equal(r.demand,false);assert.equal(r.requested_source_temperature,0);
  assert.equal(h.values.boiler['A03/K2'],false);assert.equal(h.values.boiler['A05/Channel 2 Switch'],false);
 });
 test('502 sensor failure is unsafe even if another zone has a verified ready path',()=>{
  const h=setup(()=>false),z=h.Z.find(z=>z.id==='607');
  h.set('boiler','NL_simple_thermostat_607/target_state',true);step(h);
  h.temperatures[z.sensor]=undefined;
  h.deliver('boiler',h.topic(z.sensor)+'/meta/error','sensor fault',false);
  step(h);
  const g=latest(h);
  assert.equal(g.partial_ready,false);assert.equal(g.degraded,true);
  assert.equal(h.values.boiler[z.outputs[0]],false,'failed floor zone must be commanded OFF');
  assert.notEqual(h.report()['502'].reason,'NORMAL','genuine sensor fault must not use partial-ready bypass');
 });
 test('502 unconfirmed OFF cannot be bypassed by another ready ON zone',()=>{
  let drop=false;const h=setup(p=>drop&&p==='A13/K2');
  h.set('boiler','NL_simple_thermostat_607/target_state',true);h.advance(190000);
  assert.equal(h.values.boiler['A13/K2'],true);
  drop=true;h.set('boiler','NL_simple_thermostat_607/target_state',false);
  // Simulate loss of the OFF echo: previous confirmed ON is still visible.
  h.fail('');step(h);
  const g=latest(h);
  assert.equal(g.partial_ready,false);
  assert.equal(g.degraded,true);
  assert.equal(g.output_blocked,true);
  assert.equal(h.report()['502'].reason,'ZONE_OUTPUT_UNCONFIRMED');
  assert.equal(h.report()['502'].demand,false);
  assert.equal(h.report()['502'].pump_command,false);
  assert.equal(h.values.boiler['A05/Channel 2 Switch'],false);
 });
 test('502 failed zonal ON write blocks group despite independent verified path',()=>{
  const h=setup(()=>false);
  h.fail('A13/K2');h.set('boiler','NL_simple_thermostat_607/target_state',true);step(h);
  const g=latest(h),r=h.report()['502'];
  assert.equal(g.output_blocked,true);assert.equal(g.partial_ready,false);
  assert.equal(r.reason,'ZONE_OUTPUT_UNCONFIRMED');assert.equal(r.demand,false);
  assert.equal(r.pump_command,false);assert.equal(h.values.boiler['A05/Channel 2 Switch'],false);
  h.fail('');step(h);
  assert.equal(latest(h).output_blocked,false);
  assert.equal(h.report()['502'].reason,'NORMAL');
 });
 test('502 abrupt valve command drop produces diagnostic event without new writers',()=>{
  const h=setup(()=>false);
  h.advance(700000);const before=h.report()['502'].valve_pct;
  assert.ok(before>=8,'test must first build a meaningful opening');
  h.set('boiler','NL_simple_thermostat_606/target_state',false);step(h);
  const changes=h.messages.filter(m=>m.topic===h.C.eventTopic&&JSON.parse(m.payload).circuit==='502_valve_transition');
  assert.ok(changes.length>=1);
  assert.equal(JSON.parse(changes.at(-1).payload).state,'VALVE_COMMAND_DROP');
  assert.equal(h.report()['502'].valve_pct,0);
 });
 test('504 genuine FLOOR_SENSOR_INVALID remains bounded autonomous despite house partial-ready changes',()=>{
  const h=setup(()=>false);
  const floor='921.10_TEMP_NONE/External Sensor 1';h.gazeboTemperatures[floor]=undefined;
  h.deliver('gazebo',h.topic(floor)+'/meta/error','sensor fault',false);
  h.advance(40000);
  assert.equal(h.report()['504'].reason,'AUTONOMOUS');
  assert.match(h.report()['504'].warning,/FLOOR_SENSOR_INVALID/);
  assert.equal(h.report()['504'].requested_source_temperature,35);
 });
 test('house frame refuses forged partial_ready without confirmed heat, or malformed flag',()=>{
  const h=setup(()=>false),R=h.load('HHM3Runtime');
  const f=JSON.parse(h.messages.filter(m=>m.topic===h.C.houseTopic).at(-1).payload);
  assert.equal(R.houseValid(f),true);
  f.groups['502'].partial_ready=true;f.groups['502'].degraded=true;f.groups['502'].ready=false;
  assert.equal(R.houseValid(f),false);
  f.groups['502'].ready=true;f.groups['502'].partial_ready='true';
  assert.equal(R.houseValid(f),false);
 });
};
if(require.main===module){
 const {create}=require('./harness');let passed=0;
 module.exports((name,fn)=>{fn();passed++;console.log('PASS '+name);},create);
 console.log('RESULT: '+passed+' partial-ready groups PASS; Node model only.');
}
