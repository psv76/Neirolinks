'use strict';
const assert=require('node:assert/strict'),{create}=require('./harness');
const h=create(),R=h.load('HHM3Runtime'),logs=[],messages=[];
const io=R.io({dev:{},now:()=>123456,trackMqtt:()=>{},publish:(...a)=>messages.push(a),
 log:{info:s=>logs.push(s),warning:s=>logs.push(s),error:s=>logs.push(s)}},'test',[]);
io.trace('502_output','OUTPUT_TRANSITION','','расчёт_клапана_проц=42; readback_Switch=ВКЛ');
assert.equal(logs.length,0,'technical trace не попадает в operator journal');
assert.equal(messages.length,1);
assert.equal(JSON.parse(messages[0][1]).severity,'trace');
io.event('502','PENDING_ON_READBACK','');
for(let i=0;i<20;i++)io.event('502','PENDING_ON_READBACK','');
assert.equal(logs.length,1);assert.equal(messages.length,2);
assert.match(logs[0],/СОСТОЯНИЕ=Ждём подтверждение включения зоны/);
io.event('502','PENDING_OFF_READBACK','');assert.equal(logs.length,2);
assert.match(logs[1],/СОСТОЯНИЕ=Ждём подтверждение выключения зоны/);
io.event('502','CLOSURE_UNCERTAIN','текст\n[подмена]; значение=1');
assert.doesNotMatch(logs[2],/[\r\n]/);assert.match(logs[2],/ОШИБКА=Закрытие смесителя не подтверждено/);
const broken=R.io({dev:{},now:()=>1,trackMqtt:()=>{},publish:()=>{throw Error('MQTT');},
 log:{info:()=>{throw Error('log');}}},'test',[]);
assert.doesNotThrow(()=>broken.event('502','NORMAL',''));
h.samples();h.start();h.set('boiler','NL_simple_thermostat_606/target_state',true);h.advance(210000);
const outputs=()=>h.messages.filter(m=>m.topic===h.C.eventTopic).map(m=>JSON.parse(m.payload)).filter(e=>e.circuit==='502_output');
const count=outputs().length;h.advance(20000);assert.equal(outputs().length,count,'стабильные выходы не журналируются каждый цикл');
assert.match(outputs().at(-1).detail,/расчёт_клапана_проц/);
assert.match(outputs().at(-1).detail,/readback_Level/);assert.match(outputs().at(-1).detail,/readback_Switch/);assert.match(outputs().at(-1).detail,/readback_насоса/);
assert.match(outputs().at(-1).detail,/сохранённый_Level/);
assert.doesNotMatch(outputs().at(-1).detail,/положение_штока=Не измеряется|вращение_насоса=Не измеряется|расход=Не измеряется/);
assert.doesNotMatch(outputs().at(-1).detail,/\{.*\"value\"/);
const operatorText=JSON.stringify(h.logs);
assert.doesNotMatch(operatorText,/OUTPUT_TRANSITION|положение_штока=Не измеряется|вращение_насоса=Не измеряется|расход=Не измеряется/);
assert.match(operatorText,/PUMP_COMMAND_ON|Команда насосу ВКЛ/);
assert.doesNotMatch(operatorText,/Автономия: HEAT/);

const src=create();src.enableAll();src.samples();src.start();src.advance(300000);
let sourceText=src.logs.map(x=>x.text).join('\n');
assert.match(sourceText,/КОМАНДА=Установить уставку котла/);
src.Z.forEach(z=>src.set('boiler','NL_simple_thermostat_'+z.id+'/target_state',false));
src.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;
src.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
src.advance(150000);
sourceText=src.logs.map(x=>x.text).join('\n');
assert.match(sourceText,/КОМАНДА=Перевести котёл в режим «Ожидание».*причина=Нет запроса тепла/);
assert.match(sourceText,/СОСТОЯНИЕ=Котёл переведён в режим «Ожидание».*readback=0/);
src.set('boiler','NL_simple_thermostat_505/target_state',true);src.advance(15000);
sourceText=src.logs.map(x=>x.text).join('\n');
assert.match(sourceText,/КОМАНДА=Перевести котёл в режим «Зима ЦО \+ ГВС».*причина=Появился запрос тепла/);
assert.match(sourceText,/СОСТОЯНИЕ=Котёл переведён в режим «Зима ЦО \+ ГВС».*readback=1/);
for(const x of src.logs.filter(x=>/BOILER_MODE_COMMAND|BOILER_MODE_CONFIRMED/.test(x.text)))assert.equal(x.level,'info');
assert.equal(src.logs.filter(x=>/BOILER_MODE_COMMAND_HEATING/.test(x.text)).length,1,
    'operator journal содержит одну команду перехода в Зима ЦО + ГВС до readback');
assert.equal(src.logs.filter(x=>/BOILER_MODE_COMMAND_STANDBY/.test(x.text)).length,1,
    'operator journal содержит одну команду перехода в Ожидание до readback');
assert.doesNotMatch(sourceText,/Master CH enable|DHW|Domestic/);

for(const x of src.logs.filter(x=>/PUMP_COMMAND_|HOT_PORT_COMMAND_/.test(x.text))){
    assert.equal((x.text.match(/причина=/g)||[]).length,1,'в строке команды должна быть одна причина: '+x.text);
}

const cold=create();cold.enableAll();cold.temperatures[cold.C.source.temperature]=20;
cold.samples();cold.start();cold.advance(300000);
const coldLogs=cold.logs.filter(x=>/SOURCE_WARMING|источник ещё холодный|код=NORMAL/.test(x.text));
assert.ok(coldLogs.some(x=>/SOURCE_WARMING/.test(x.text)&&x.level==='info'),'ожидание прогрева источника должно быть INFO');
assert.ok(coldLogs.every(x=>!(x.level==='warning'&&/код=NORMAL/.test(x.text))),
    'не должно быть WARNING с кодом NORMAL для штатного прогрева');
assert.doesNotMatch(coldLogs.map(x=>x.text).join('\n'),/причина=,\s*/);

// Live 3.5 export did not show zone-open completion lines. The runtime must emit
// them for every house circuit with 180 s actuator qualification; exporter/UI
// defects are investigated separately.
for(const id of ['501','502','503']){
    const timerLogs=src.logs.map(x=>x.text).filter(x=>x.includes('['+id+'_start_timer]')).join('\n');
    assert.match(timerLogs,/TIMER_ZONE_OPEN_STARTED/,id+' start timer start event');
    assert.match(timerLogs,/TIMER_ZONE_OPEN_FINISHED/,id+' start timer finish event');
}

// Operator log dedup must survive both the 30 s physical reassert interval and
// a wb-rules/script restart. Use only immediate-ready 505 so no legitimate
// intermediate setpoint changes can be confused with a duplicate.
const stable=create();stable.samples();stable.start();
stable.Z.forEach(z=>stable.set('boiler','NL_simple_thermostat_'+z.id+'/target_state',false));
stable.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;
stable.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
stable.advance(150000);
stable.set('boiler','NL_simple_thermostat_505/target_state',true);
stable.advance(15000);
const setpointPath=stable.C.source.setpoint;
const log45=()=>stable.logs.filter(x=>/BOILER_SETPOINT_COMMAND/.test(x.text)&&/значение_С=45/.test(x.text));
assert.equal(log45().length,1,'первое фактическое назначение 45 C должно попасть в operator journal');
const writes45Before=stable.physical().filter(w=>w.path===setpointPath&&w.value===45).length;
stable.advance(70000);
assert.ok(stable.physical().filter(w=>w.path===setpointPath&&w.value===45).length>writes45Before,
    'физическая reassert-запись 45 C должна существовать для проверки dedup');
assert.equal(log45().length,1,'30-секундные reassert-записи 45 C не должны создавать новые operator events');
assert.equal(stable.stores.hhm3_operator_log.lastSetpoint,45,'persistent operator setpoint before restart');

const restarted=create({stores:stable.stores,values:stable.values});
assert.equal(restarted.stores.hhm3_operator_log.lastSetpoint,45,'persistent operator setpoint after constructor');
restarted.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;
restarted.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
restarted.samples();restarted.advance(40000);
const restartSetpointLogs=restarted.logs.filter(x=>/BOILER_SETPOINT_COMMAND/.test(x.text));
assert.equal(restartSetpointLogs.filter(x=>/значение_С=45/.test(x.text)).length,0,
    'неизменная уставка 45 C после restart не должна повторяться; logs='+JSON.stringify(restartSetpointLogs.map(x=>x.text))+
    '; store='+JSON.stringify(restarted.stores.hhm3_operator_log));

console.log('PASS HHM 3.6 operator journal: persistent setpoint dedup, mode dedup, exact timers, source warming INFO');
