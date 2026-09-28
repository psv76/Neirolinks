'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');
const h=create(),R=h.load('HHM3Runtime'),logs=[],messages=[];
const io=R.io({dev:{},now:()=>123456,trackMqtt:()=>{},publish:(...a)=>messages.push(a),
 log:{info:s=>logs.push(s),warning:s=>logs.push(s),error:s=>logs.push(s)}},'test',[]);
io.event('502','PENDING_ON_READBACK','');
for(let i=0;i<20;i++)io.event('502','PENDING_ON_READBACK','');
assert.equal(logs.length,1);assert.equal(messages.length,1);
assert.match(logs[0],/Ждём подтверждение включения зоны/);
io.event('502','PENDING_OFF_READBACK','');assert.equal(logs.length,2);
assert.match(logs[1],/Ждём подтверждение выключения зоны/);
io.event('502','CLOSURE_UNCERTAIN','текст\n[подмена]; значение=1');
assert.doesNotMatch(logs[2],/[\r\n]/);assert.match(logs[2],/Закрытие смесителя не подтверждено/);
const broken=R.io({dev:{},now:()=>1,trackMqtt:()=>{},publish:()=>{throw Error('MQTT');},
 log:{info:()=>{throw Error('log');}}},'test',[]);
assert.doesNotThrow(()=>broken.event('502','NORMAL',''));
h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(210000);
const outputs=()=>h.messages.filter(m=>m.topic===h.C.eventTopic).map(m=>JSON.parse(m.payload)).filter(e=>e.circuit==='502_output');
const count=outputs().length;h.advance(20000);assert.equal(outputs().length,count,'стабильные выходы не журналируются каждый цикл');
assert.match(outputs().at(-1).detail,/расчёт клапана/);
assert.match(outputs().at(-1).detail,/прочитано/);
assert.match(outputs().at(-1).detail,/сохранённый Level/);
assert.match(outputs().at(-1).detail,/расход не измеряются/);
assert.doesNotMatch(JSON.stringify(h.logs),/Автономия: HEAT/);
console.log('PASS русские переходы ON/OFF, подавление повторов, границы readback, одна строка, отказ диагностики');
