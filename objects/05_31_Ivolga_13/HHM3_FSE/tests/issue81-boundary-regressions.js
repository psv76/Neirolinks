'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');
let passed=0;function test(n,f){f();passed++;console.log('PASS '+n);}
function setup(options){const h=create(options);h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(900000);return h;}
for(const delay of [120000,125000])test('READY через '+delay/1000+' с: предыдущий выбег завершён',()=>{
 const h=setup();h.set('boiler','NL_simple_thermostat_607/target_state',true);h.advance(5000);h.advance(175000-delay);
 h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);
 const n=h.writes.length;assert.equal(h.report()['502'].reason,'PUMP_POSTRUN');
 h.advance(delay);assert.equal(h.report()['502'].reason,'NORMAL');
 assert.ok(h.report()['502'].valve_pct<=10,'холодный запуск');
 if(delay>120000)assert.ok(h.writes.slice(n).some(w=>w.path==='A03/K2'&&w.value===false));
});
test('Неподтверждённое открытие не создаёт выбег и не включает насос из простоя',()=>{
 let drop=false;const h=create({dropReadback:p=>drop&&p==='A05/Channel 2 Switch'});
 h.samples();h.start();h.advance(10000);h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(180000);
 drop=true;h.advance(5000);assert.equal(h.report()['502'].output.ready,false);assert.equal(h.report()['502'].pump_command,false);
 h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);
 assert.notEqual(h.report()['502'].reason,'PUMP_POSTRUN');assert.equal(h.report()['502'].pump_command,false);
});
test('Неподтверждённое закрытие прерывает выбег, таймер очищается, новые READY запрещены',()=>{
 let drop=false;const h=setup({dropReadback:p=>drop&&p==='A05/Channel 2 Switch'});
 drop=true;h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);
 assert.equal(h.report()['502'].reason,'PUMP_POSTRUN');
 h.advance(10000);assert.equal(h.report()['502'].reason,'CLOSURE_UNCERTAIN');
 assert.equal(h.report()['502'].pump_command,false);assert.equal(h.report()['502'].demand,false);
 assert.equal(h.values.boiler['HHM3_FSE/pump_stop_remaining_502'],'—');
 h.advance(120000);assert.equal(h.report()['502'].pump_command,false);
});
test('Потеря датчика и откат часов не продлевают зональный выбег',()=>{
 for(const fault of ['sensor','clock']){
  const h=setup();h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);
  if(fault==='clock'){h.time(h.now()-10000);h.tick('620');h.tick('500');}
  else {for(const z of h.Z.filter(z=>z.circuit==='502')){h.health.boiler[h.C.m1w2Health[z.sensor]]=0;h.temperatures[z.sensor]=undefined;h.deliver('boiler',h.topic(z.sensor)+'/meta/error','fault',false);}h.temperatures[h.C.circuits['502'].supply]=undefined;h.deliver('boiler',h.topic(h.C.circuits['502'].supply)+'/meta/error','fault',false);h.advance(5000);}
  assert.notEqual(h.report()['502'].reason,'PUMP_POSTRUN');
  assert.equal(h.values.boiler['HHM3_FSE/pump_stop_remaining_502'],'—');
 }
});
test('Прямой зональный контур принимает объектный выбег без изменения алгоритма',()=>{
 const h=create({configure:C=>{C.circuits['503'].pumpPostrunMs=120000;}});
 h.samples();h.start();h.set('boiler','NL_simple_thermostat_005/target_state',true);h.advance(210000);
 assert.equal(h.report()['503'].pump_command,true);
 h.set('boiler','NL_simple_thermostat_005/target_state',false);h.advance(5000);
 assert.equal(h.report()['503'].reason,'PUMP_POSTRUN');assert.equal(h.report()['503'].demand,false);
 h.advance(115000);assert.equal(h.report()['503'].pump_command,true);
 h.advance(5000);assert.equal(h.report()['503'].pump_command,false);
});
console.log('RESULT: '+passed+' граничных групп PASS');
