'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');

const h=create(),R=h.load('HHM3Runtime'),logs=[],messages=[];
const io=R.io({dev:{},now:()=>123456,trackMqtt:()=>{},publish:(...a)=>messages.push(a),
 log:{info:s=>logs.push(s),warning:s=>logs.push(s),error:s=>logs.push(s)}},'test',[]);

io.event('502','PENDING_ON_READBACK','');
for(let i=0;i<20;i++)io.event('502','PENDING_ON_READBACK','');
assert.equal(logs.length,1);
assert.equal(messages.filter(m=>m[0]===h.C.eventTopic).length,1);
assert.match(logs[0],/СОСТОЯНИЕ=Ждём подтверждение включения зоны/);

io.event('502','PENDING_OFF_READBACK','');
assert.equal(logs.length,2);
assert.match(logs[1],/СОСТОЯНИЕ=Ждём подтверждение выключения зоны/);

io.trace('502_output','OUTPUT_TRANSITION','',
    'readback_Level=10; readback_Switch=ВКЛ; сохранённый_Level=10');
io.trace('502_output','OUTPUT_TRANSITION','',
    'readback_Level=10; readback_Switch=ВКЛ; сохранённый_Level=10');
assert.equal(logs.length,2,'technical trace не попадает в operator journal');
const directTrace=messages.filter(m=>m[0]===h.C.traceTopic);
assert.equal(directTrace.length,1,'одинаковый trace подавляется');
assert.match(JSON.parse(directTrace[0][1]).detail,/readback_Level=10/);

io.event('502','CLOSURE_UNCERTAIN','текст\n[подмена]; значение=1');
assert.doesNotMatch(logs[2],/[\r\n]/);
assert.match(logs[2],/ОШИБКА=Закрытие смесителя не подтверждено/);

const broken=R.io({dev:{},now:()=>1,trackMqtt:()=>{},publish:()=>{throw Error('MQTT');},
 log:{info:()=>{throw Error('log');},warning:()=>{throw Error('log');},error:()=>{throw Error('log');}}},'test',[]);
assert.doesNotThrow(()=>broken.event('502','NORMAL',''));
assert.doesNotThrow(()=>broken.trace('502_output','OUTPUT_TRANSITION','','x=1'));

h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(210000);
const traces=()=>h.messages.filter(m=>m.topic===h.C.traceTopic).map(m=>JSON.parse(m.payload))
    .filter(e=>e.circuit==='502_output');
const count=traces().length;
h.advance(20000);
assert.equal(traces().length,count,'стабильный output trace не публикуется каждый цикл');
assert.ok(count>0,'output transition сохраняется в technical trace');
assert.match(traces().at(-1).detail,/расчёт_клапана_проц/);
assert.match(traces().at(-1).detail,/readback_Level/);
assert.match(traces().at(-1).detail,/readback_Switch/);
assert.match(traces().at(-1).detail,/readback_насоса/);
assert.match(traces().at(-1).detail,/сохранённый_Level/);
assert.doesNotMatch(traces().at(-1).detail,/положение_штока=Не измеряется|вращение_насоса=Не измеряется|расход=Не измеряется/);
assert.doesNotMatch(traces().at(-1).detail,/\{.*\"value\"/);

const operatorText=JSON.stringify(h.logs);
assert.doesNotMatch(operatorText,/502_output/);
assert.doesNotMatch(operatorText,/readback_Level|readback_Switch|readback_насоса|сохранённый_Level/);
assert.doesNotMatch(operatorText,/положение_штока=Не измеряется|вращение_насоса=Не измеряется|расход=Не измеряется/);
assert.match(operatorText,/КОМАНДА=Изменена команда насосу/);
assert.doesNotMatch(operatorText,/Автономия: HEAT/);

// Один краткий штатный провал готовности выхода не должен давать пару
// REQUESTS_UNAVAILABLE -> ACTIVE в операторском журнале.
let dropped=false;
const h2=create({dropReadback:p=>{
    if(!dropped&&p==='A05/Channel 2 Dimming Level'){dropped=true;return true;}
    return false;
}});
h2.gazeboTemperatures['921.09_MSW_TH/Temperature']=30;
h2.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=35;
h2.samples();h2.start();h2.set('boiler','NL_simple_thermostat_606/target_state',true);h2.advance(220000);
const sourceNoise=h2.logs.filter(x=>/\[source\]/.test(x.text)&&/REQUESTS_UNAVAILABLE/.test(x.text));
assert.equal(sourceNoise.length,0,'краткий output handshake не шумит source warning');

console.log('PASS operator journal отделён от technical trace; output/readback детали и transient source noise подавлены');
