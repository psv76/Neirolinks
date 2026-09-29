'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');
let passed=0;
function test(name,fn){fn();passed++;console.log('PASS '+name);}
function setup(){const h=create();h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(900000);assert.ok(h.report()['502'].valve_pct>10);return h;}
function off(h){h.set('boiler','NL_simple_thermostat_606/target_state',false);h.advance(5000);}
function stopCircuitDemand(h,id){
 if(id==='504'){
  h.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;
  h.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
 }else{
  h.Z.filter(z=>z.circuit===id).forEach(z=>h.set('boiler','NL_simple_thermostat_'+z.id+'/target_state',false));
 }
 h.advance(5000);
}
test('501–505: каждый насос имеет штатный выбег 120 с после последнего запроса',()=>{
 for(const id of ['501','502','503','504','505']){
  const h=create();h.enableAll();h.samples();h.start();h.advance(300000);
  assert.equal(h.report()[id].pump_command,true,id+' должен работать до снятия demand');
  stopCircuitDemand(h,id);
  assert.equal(h.report()[id].reason,'PUMP_POSTRUN',id+' должен перейти в выбег');
  assert.equal(h.report()[id].pump_command,true,id+' насос остаётся включён в начале выбега');
  assert.equal(h.report()[id].stopRemainingMs,120000,id+' старт выбега');
  h.advance(115000);
  assert.equal(h.report()[id].pump_command,true,id+' насос ещё включён на 115 с');
  assert.equal(h.report()[id].stopRemainingMs,5000,id+' осталось 5 с');
  h.advance(5000);
  assert.equal(h.report()[id].pump_command,false,id+' насос выключается через 120 с');
  assert.equal(h.report()[id].stopRemainingMs,null,id+' таймер очищен');
 }
});
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
