'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');
let passed=0;
function test(name,fn){fn();passed++;console.log('PASS '+name);}
function setup(){const h=create();h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(900000);assert.ok(h.report()['502'].valve_pct>10);return h;}
function off(h){h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);}
for(const delay of [20000,50000,80000,10000,115000])test('Переход между зонами за '+delay/1000+' с без OFF и холодного старта',()=>{
 const h=setup();h.set('boiler','NL_simple_thermostat_607/target_state',true);h.advance(5000);
 h.advance(175000-delay);
 const before=h.report()['502'].valve_pct,index=h.writes.length;
 off(h);
 assert.equal(h.report()['502'].reason,'PUMP_POSTRUN');
 assert.equal(h.report()['502'].pump_command,true);
 assert.equal(h.values.boiler['A05/Channel 2 Switch'],false);
 h.advance(delay);
 assert.equal(h.report()['502'].reason,'NORMAL');
 assert.ok(h.report()['502'].valve_pct>10,'нет повторного ограничения 10%');
 assert.ok(h.report()['502'].valve_pct>=before-4,'память позиции сохранена');
 assert.equal(h.writes.slice(index).filter(w=>w.path==='A03/K2'&&w.value===false).length,0);
});
test('Последний запрос: 120 с, только Switch OFF, затем полный останов',()=>{
 const h=setup();
 off(h);const began=h.now(),level=h.values.boiler['A05/Channel 2 Dimming Level'],index=h.writes.length;
 assert.equal(h.report()['502'].stopRemainingMs,120000);
 h.advance(115000);assert.equal(h.report()['502'].pump_command,true);
 assert.equal(h.report()['502'].stopRemainingMs,5000);
 h.advance(5000);assert.equal(h.report()['502'].pump_command,false);
 assert.equal(h.now()-began,120000);
 assert.equal(h.values.boiler['A05/Channel 2 Dimming Level'],level);
 assert.equal(h.writes.slice(index).filter(w=>w.path==='A05/Channel 2 Dimming Level').length,0);
 h.set('boiler','NL_simple_thermostat_607/target_state',true);h.advance(190000);
 assert.equal(h.report()['502'].reason,'NORMAL');assert.ok(h.report()['502'].valve_pct<=10);
});
test('Первый пуск ждёт все 180 с после ON; из простоя выбега нет',()=>{
 const h=create();h.samples();h.start();h.advance(10000);
 assert.equal(h.report()['502'].pump_command,false);
 h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(5000);
 h.advance(175000);assert.equal(h.report()['502'].pump_command,false);
 h.advance(5000);assert.equal(h.report()['502'].pump_command,true);
});
test('501 и 503: после последнего зонального запроса насос остаётся включён ровно 120 с',()=>{
 for(const item of [{id:'501',zone:'601',pump:'A03/K1'},{id:'503',zone:'005',pump:'A03/K3'}]){
  const h=create();h.samples();h.start();
  h.set('boiler','NL_simple_thermostat_'+item.zone+'/target_state',true);
  h.advance(190000);
  assert.equal(h.report()[item.id].pump_command,true,item.id+' должен быть запущен после открытия зоны');
  h.set('boiler','NL_simple_thermostat_'+item.zone+'/target_state',false);
  h.advance(5000);
  assert.equal(h.report()[item.id].reason,'PUMP_POSTRUN',item.id);
  assert.equal(h.report()[item.id].pump_command,true,item.id);
  assert.equal(h.report()[item.id].stopRemainingMs,120000,item.id);
  h.advance(115000);
  assert.equal(h.report()[item.id].pump_command,true,item.id);
  assert.equal(h.report()[item.id].stopRemainingMs,5000,item.id);
  h.advance(5000);
  assert.equal(h.report()[item.id].pump_command,false,item.id);
 }
});
test('Перегрев и ошибка выхода прерывают выбег',()=>{
 for(const kind of ['heat','output']){
  const h=setup();off(h);
  if(kind==='heat'){h.temperatures[h.C.circuits['502'].supply]=50;h.samples();}
  else {h.fail('A03/K2');h.deliver('boiler',h.topic('A03/K2'),0,false);}
  h.advance(5000);
  assert.notEqual(h.report()['502'].reason,'PUMP_POSTRUN');
  assert.notEqual(h.report()['502'].pump_command,true);
 }
});
console.log('RESULT: '+passed+' групп выбега PASS; только модель Node');
