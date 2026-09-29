/* HHM3 common runtime: freshness, ownership and structured transition events. ES5. */
var W = require('HHM3Wire');
var C = require('HHM3Config').config;
exports.number = W.number;
exports.topic = function (path) { var p=path.indexOf('/'); return '/devices/'+path.slice(0,p)+'/controls/'+path.slice(p+1); };
exports.io = function (env, owner, allowed) {
    var sensors={}, lastCommands={}, lastEvents={}, attempts=[];
    // One outstanding serial read per rules instance; only startup/revalidation.
    // Three bounded attempts per sensor, no permanent polling/heartbeat loop.
    var proofBoot=env.proofStorage?W.nextSession(env.proofStorage):null, proofSeq=0, pending=null, proofNow=null, proofStart=env.now();
    var proofTopic='/rpc/v1/wb-mqtt-serial/port/Load/hhm31-'+owner+'-'+proofBoot;
    function proofClock(now){
        if(proofNow!==null&&now<proofNow){pending=null;proofStart=now;Object.keys(sensors).forEach(function(p){sensors[p].proofTries=0;sensors[p].proofAfter=0;});}
        proofNow=now;
    }
    function finishProof(why){
        if(!pending)return;
        var p=pending.path,s=sensors[p];pending=null;s.proofAfter=env.now()+60000;
        if(why)env.log.warning('[отопление]['+owner+'][M1W2 '+p+']; ДАТЧИК=Не удалось подтвердить датчик после запуска; код=POST_START_PROOF; причина='+proofReason(why)+'; действие=Датчик не считается пригодным до успешного подтверждения');
    }
    function requestProof(path,stage,temperature){
        var s=sensors[path],input=s.input,now=env.now();
        proofSeq++;
        pending={path:path,stage:stage,temperature:temperature,id:proofSeq,at:now,revision:s.sensor.revision()};
        var params={device_id:path.substring(0,path.indexOf('/')),function:stage===0?4:2,
            address:(stage===0?7:16)+input-1,count:1,format:'HEX',total_timeout:10000};
        try{env.publish(proofTopic,JSON.stringify({id:proofSeq,params:params}),0,false);}
        catch(e){finishProof('PUBLISH_FAILED');}
    }
    function pumpProof(){
        if(proofBoot===null)return;
        var now=env.now();proofClock(now);
        if(now-proofStart<1000)return; // Let initial tracker replay settle; never trust it as proof.
        if(pending&&(now-pending.at>=10000||sensors[pending.path].sensor.revision()!==pending.revision))finishProof('TIMEOUT_OR_STATE_CHANGED');
        if(pending)return;
        Object.keys(sensors).some(function(path){
            var s=sensors[path];
            if(!s.local||!s.sensor.needsProof()||(s.proofTries||0)>=3||now<(s.proofAfter||0))return false;
            s.proofTries=(s.proofTries||0)+1;requestProof(path,0,null);return true;
        });
    }
    if(proofBoot!==null)env.trackMqtt(proofTopic+'/reply',function(m){
        var now=env.now();proofClock(now);
        if(!pending||m.retained!==false||m.topic!==proofTopic+'/reply')return;
        var r;try{r=JSON.parse(m.value);}catch(e){return;}
        if(!r||r.id!==pending.id)return;
        var q=pending,s=sensors[q.path];
        if(now-q.at>=10000||s.sensor.revision()!==q.revision){finishProof('STALE_OR_STATE_CHANGED');return;}
        if(r.error!==null||!r.result||r.result.exception||typeof r.result.response!=='string'){
            finishProof('RPC_ERROR_OR_UNSUPPORTED');return;
        }
        var hex=r.result.response;
        if(q.stage===0){
            if(!/^[0-9a-fA-F]{4}$/.test(hex)){finishProof('BAD_TEMPERATURE_RESPONSE');return;}
            var raw=parseInt(hex,16),t=(raw>=32768?raw-65536:raw)*0.0625;
            if(raw===32767||t<s.min||t>s.max){finishProof('TEMPERATURE_INVALID');return;}
            // WB template uses s16/16, with optional round_to=0.05. Accept only
            // exact native or exact template-rounded local values, never epsilon.
            var local;try{local=W.number(env.dev[q.path]);}catch(e){local=null;}
            var rounded=Number(((t<0?-1:1)*Math.round(Math.abs(t)/0.05)*0.05).toFixed(2));
            if(local!==t&&local!==rounded){finishProof('LOCAL_VALUE_MISMATCH');return;}
            requestProof(q.path,1,local);return;
        }
        if(hex!=='01'){finishProof('HEALTH_NOT_OK');return;}
        var accepted=s.sensor.qualifyFromPoll(q.temperature,1,q.revision,now,s.min,s.max);
        finishProof(accepted?'':'LOCAL_STATE_NOT_HEALTHY');
        if(env.onSample)env.onSample();
        pumpProof();
    });
    function numeric(v){return typeof v==='boolean'?(v?1:0):v;}
    function ruOnOff(v){
        if(v===true||v===1||v==='1')return 'ВКЛ';
        if(v===false||v===0||v==='0')return 'ВЫКЛ';
        return 'Нет данных';
    }
    function errorText(v){
        return v===undefined||v===null||v===''||v===0||v===false?'Нет':'Есть: '+safeText(v);
    }
    function proofReason(code){
        var text={
            PUBLISH_FAILED:'Не удалось отправить запрос проверки датчика',
            TIMEOUT_OR_STATE_CHANGED:'Проверка не завершилась вовремя или состояние датчика изменилось',
            STALE_OR_STATE_CHANGED:'Ответ проверки устарел или состояние датчика изменилось',
            RPC_ERROR_OR_UNSUPPORTED:'Устройство не ответило корректно на проверочный запрос',
            BAD_TEMPERATURE_RESPONSE:'Получен некорректный ответ температуры',
            TEMPERATURE_INVALID:'Получена недопустимая температура',
            LOCAL_VALUE_MISMATCH:'Ответ устройства не совпал с текущим локальным значением',
            HEALTH_NOT_OK:'Устройство сообщает, что датчик неисправен',
            LOCAL_STATE_NOT_HEALTHY:'Текущее локальное состояние датчика не позволяет принять данные'
        };
        return text[code]||safeText(code);
    }
    function sensorReason(code){
        var text={
            VALID:'Данные пригодны',
            STARTUP_VALIDATION:'Ожидается подтверждение после запуска',
            RETAINED_REVALIDATION:'Ожидается подтверждение сохранённых данных',
            CONTROL_MISSING:'Нет обязательного значения температуры или Sensor OK',
            CONTROL_ERROR:'Канал датчика сообщает ошибку',
            VALUE_INVALID:'Температура вне допустимого диапазона или некорректна',
            SENSOR_NOT_OK:'Sensor OK сообщает неисправность',
            CONTROL_SYNC_WAIT:'Ожидается согласование текущих значений',
            RUNTIME_UNSUPPORTED:'Среда не поддерживает требуемый контракт контроля датчика'
        };
        return text[code]||safeText(code);
    }
    function sensorCause(code){
        var text={
            NEW_INSTANCE:'Новый запуск скрипта',
            CLOCK_ROLLBACK:'Обнаружен откат системного времени',
            RETAINED_TEMPERATURE:'Получена сохранённая температура',
            RETAINED_HEALTH:'Получено сохранённое состояние Sensor OK',
            MQTT_TEMPERATURE_ERROR:'Получено сообщение об ошибке канала температуры',
            MQTT_HEALTH_ERROR:'Получено сообщение об ошибке Sensor OK',
            POST_START_SERIAL_READ:'Датчик подтверждён прямым чтением после запуска',
            MQTT_METADATA_UNSUPPORTED:'Недостаточно данных MQTT для доказательства актуальности',
            LOCAL_TEMPERATURE_MISSING:'Нет локального значения температуры',
            LOCAL_HEALTH_MISSING:'Нет локального значения Sensor OK',
            TEMPERATURE_ERROR:'Ошибка канала температуры',
            HEALTH_ERROR:'Ошибка канала Sensor OK',
            LOCAL_TEMPERATURE_INVALID:'Локальная температура некорректна',
            LOCAL_HEALTH_NOT_OK:'Локальный Sensor OK не подтверждает исправность',
            LIVE_INVALID_SAMPLE:'Получено некорректное новое значение'
        };
        return text[code]||safeText(code);
    }
    function eventKind(code){
        if(/^TIMER_/.test(code))return 'ТАЙМЕР';
        if(/^PUMP_COMMAND_|^HOT_PORT_COMMAND_/.test(code))return 'КОМАНДА';
        if(code==='VALVE_COMMAND_DROP')return 'РЕШЕНИЕ';
        if(code==='OUTPUT_TRANSITION')return 'ВЫХОД';
        if(/OVERHEAT|SAFETY/.test(code))return 'ЗАЩИТА';
        if(/ERROR|UNCERTAIN/.test(code))return 'ОШИБКА';
        return 'СОСТОЯНИЕ';
    }
    var api={
        watch:function(path,min,max) {
            if(sensors[path])return;
            var s=W.sensor();sensors[path]={sensor:s,min:min,max:max,seq:0};
            env.trackMqtt(exports.topic(path),function(m){s.sample(m.value,m.retained,env.now());if(m.retained===false&&s.runtimeStatus()==='SUPPORTED')sensors[path].seq++;if(env.onSample)env.onSample();});
            env.trackMqtt(exports.topic(path)+'/meta/error',function(m){s.error(m.value,m.retained);if(env.onSample)env.onSample();});
        },
        watchM1w2:function(path,min,max) {
            var healthPath=C.m1w2Health[path];
            if(!healthPath)throw new Error('Missing explicit M1W2 health mapping: '+path);
            if(sensors[path])throw new Error('Duplicate sensor policy: '+path);
            var paths=[path,healthPath],s=W.localM1w2(function(channel){
                var p=paths[channel],value=env.dev[p];
                if(value===undefined||value===null)return null;
                return {value:value,error:env.dev[p+'#error']};
            });
            sensors[path]={sensor:s,min:min,max:max,seq:0,local:true};
            var channel=path.match(/\/External Sensor ([12])$/);
            if(!channel||healthPath!==path+' OK')throw new Error('Unsupported explicit M1W2 register mapping: '+path);
            sensors[path].input=Number(channel[1]);
            paths.forEach(function(p,channel){
                env.trackMqtt(exports.topic(p),function(m){
                    s.sample(channel,m.value,m.retained,env.now());
                    if(channel===0&&m.retained===false)sensors[path].seq++;
                    if(env.onSample)env.onSample();
                });
                env.trackMqtt(exports.topic(p)+'/meta/error',function(m){
                    s.error(channel,m.value,m.retained,env.now());
                    if(env.onSample)env.onSample();
                });
            });
        },
        watchTemperature:function(path,min,max) {
            if(sensors[path])return;
            if(C.m1w2Health[path])api.watchM1w2(path,min,max);
            else api.watch(path,min,max);
        },
        read:function(path) {
            var s=sensors[path];if(!s)return null;
            var value=s.sensor.read(env.now(),s.min,s.max);
            if(s.local){if(value!==null){s.proofTries=0;s.proofAfter=0;}pumpProof();}
            if(s.local){
                var d=s.sensor.diagnostics(),signature=d.phase+';'+d.reason+';'+d.cause;
                if(s.healthSignature!==signature){
                    s.healthSignature=signature;
                    var level=value===null?'warning':'info',healthPath=C.m1w2Health[path];
                    env.log[level]('[отопление]['+owner+'][M1W2 '+path+']; ДАТЧИК='+
                        (value===null?'Данные датчика не пригодны':'Датчик пригоден')+
                        '; код='+safeText(d.reason)+'; этап='+(d.phase==='STARTUP'?'Запуск':'Работа')+
                        '; причина='+sensorReason(d.reason)+'; источник='+sensorCause(d.cause)+
                        '; температура_С='+(value===null?'Нет достоверного значения':safeText(value))+
                        '; Sensor_OK='+ruOnOff(env.dev[healthPath])+
                        '; ошибка_температуры='+errorText(env.dev[path+'#error'])+
                        '; ошибка_Sensor_OK='+errorText(env.dev[healthPath+'#error'])+
                        '; действие='+(value===null?'Не использовать датчик в расчёте до восстановления':'Данные пригодны по контракту'));
                }
            }
            return value;
        },
        at:function(path) {var s=sensors[path];return s?s.sensor.timestamp():null;},
        // A health-qualified local observation is not a new numeric measurement.
        // Thermal dwell logic uses this; command/readback age still uses at().
        observedAt:function(path) {var s=sensors[path];return api.read(path)===null?null:(s.local?env.now():api.at(path));},
        seq:function(path) {return sensors[path]?sensors[path].seq:0;},
        matches:function(path,value) {return api.read(path)===numeric(value);},
        begin:function(){attempts=[];pumpProof();},
        commands:function(paths){return attempts.filter(function(a){return paths.indexOf(a.path)>=0;});},
        readback:function(path){return {value:api.read(path),at:api.at(path),seq:api.seq(path)};},
        runtime:function() {
            return Object.keys(sensors).some(function(k){return sensors[k].sensor.runtimeStatus()==='RUNTIME_UNSUPPORTED';})?
                'RUNTIME_UNSUPPORTED: '+W.RUNTIME_ERROR_RU:'OK_OR_WAITING';
        },
        compatible:function() {
            // Capability qualification, not a version-number or timeout bypass.
            // Missing metadata is sticky for this script instance. No samples
            // means UNVERIFIED, never permission to energize an output.
            var states=Object.keys(sensors).map(function(k){return sensors[k].sensor.runtimeStatus();});
            return states.indexOf('RUNTIME_UNSUPPORTED')<0&&states.indexOf('SUPPORTED')>=0;
        },
        write:function(path,value,force) {
            if(allowed.indexOf(path)<0)throw new Error(owner+' forbidden output '+path);
            if(value===null || value===undefined || (typeof value==='number' && !isFinite(value)))throw new Error('Invalid output');
            var last=lastCommands[path],now=env.now();
            var result={path:path,value:value,at:now,status:'SENT',ok:true,sent:false,attempted:true,delivery_unknown:false};
            if(!force && last && last.value===value && now>=last.at && now-last.at<30000 && api.matches(path,value)){result.status='CACHE_SKIP';result.attempted=false;}
            else try {env.dev[path]=value;lastCommands[path]={value:value,at:now};result.sent=true;}
            catch(e){delete lastCommands[path];result.status='ERROR';result.ok=false;result.delivery_unknown=true;}
            result.readback=api.readback(path);attempts.push(result);return result;
        },
        event:function(key,state,warning,detail) {
            var signature=state+';'+warning+';'+(detail||''), previous=lastEvents[key];
            if(previous && previous.signature===signature)return;
            var severity=warning?'warning':'state';
            if(/OVERHEAT|CLOSURE_UNCERTAIN/.test(state))severity='alarm';
            else if(previous && previous.warning && !warning)severity='recovery';
            var e={v:3,owner:owner,circuit:key,at:env.now(),state:state,warning:warning||'',detail:detail||'',severity:severity};
            lastEvents[key]={signature:signature,warning:warning};
            var text='[отопление]['+owner+']['+key+']; '+eventKind(state)+'='+exports.stateText(state)+
                '; код='+safeText(state)+'; причина='+safeText(warning||'Штатный переход')+
                (detail?'; '+safeDetail(detail):'');
            // Отказ диагностического канала не должен блокировать управление.
            try {env.publish(C.eventTopic,JSON.stringify(e),0,false);}catch(ignorePublish){}
            try {
                if(severity==='alarm')env.log.error(text);
                else if(severity==='warning')env.log.warning(text);
                else env.log.info(text);
            }catch(ignoreLog){}
            return e;
        },
        trace:function(key,state,warning,detail) {
            var e={v:3,owner:owner,circuit:key,at:env.now(),state:state,warning:warning||'',detail:detail||'',severity:'trace'};
            // Machine-readable technical trace: intentionally not written to operator journal.
            try {env.publish(C.eventTopic,JSON.stringify(e),0,false);}catch(ignorePublish){}
            return e;
        }
    };
    allowed.forEach(function(path){api.watch(path,-100000,100000);});
    return api;
};
function safeText(value){return String(value).replace(/[\r\n;\[\]]/g,', ');}
function safeDetail(value){return String(value).replace(/[\r\n\[\]]/g,', ');}
exports.stateText=function(code){
    var text={NORMAL:'Нагрев по запросу зон',HEAT:'Нагрев по запросу зон',
        OFF:'Отключено',NO_DEMAND:'Нет запроса тепла',PUMP_POSTRUN:'Выбег насоса',
        AUTONOMOUS:'Местное управление без достоверного внешнего запроса',DEGRADED:'Работа в резервном режиме',
        PENDING_ON_READBACK:'Ждём подтверждение включения зоны',PENDING_OFF_READBACK:'Ждём подтверждение выключения зоны',
        OFF_READBACK_TIMEOUT:'Выключение зоны не подтверждено',ZONE_OUTPUT_UNCONFIRMED:'Ошибка выхода зоны',
        OFF_COMMANDED:'Отправлена команда закрытия смесителя',HEAT_COMMANDED:'Команда нагрева подтверждена выходом',
        WAIT_OUTPUT_READBACK:'Ждём подтверждение команды выхода',CLOSURE_UNCERTAIN:'Закрытие смесителя не подтверждено',
        ENABLE_UNCERTAIN:'Включение смесителя не подтверждено',OFF_WRITE_ERROR:'Ошибка записи закрытия смесителя',
        LEVEL_WRITE_ERROR:'Ошибка записи уровня смесителя',ENABLE_WRITE_ERROR:'Ошибка включения смесителя',
        PUMP_WRITE_ERROR:'Ошибка записи команды насосу',OUTPUT_WRITE_ERROR:'Ошибка записи выхода',
        OVERHEAT_CLOSE:'Перегрев: команда закрыть горячий порт',OVERHEAT_STOP:'Перегрев: защитная остановка',
        FLOOR_SENSOR_UNAVAILABLE:'Датчик пола недоступен',NO_FEEDBACK_UNCOVERED:'Нет достоверной подачи и пола',
        FLOOR_ONLY:'Ограниченное регулирование по полу',FLOOR_CAP_UNMEASURED:'Не задан проверенный предел по полу',
        HOUSE_LINK_LOST:'Нет достоверного запроса дома',FIRST_COMMISSIONING:'Ожидает первого ввода',
        RUNTIME_UNSUPPORTED:'Несовместимая среда управления',TIMER_STARTED:'Начало ожидания',TIMER_FINISHED:'Окончание ожидания',
        VALVE_COMMAND_DROP:'Расчётное открытие уменьшено',OUTPUT_TRANSITION:'Изменилось состояние выхода',
        PUMP_COMMAND_ON:'Команда насосу ВКЛ',PUMP_COMMAND_OFF:'Команда насосу ВЫКЛ',
        HOT_PORT_COMMAND_ON:'Команда разрешить горячий порт',HOT_PORT_COMMAND_OFF:'Команда закрыть горячий порт',
        COMMAND_ACCEPTED:'Попытка записи без обнаруженной ошибки',NOT_SENT:'Команда не отправлялась',
        SETTINGS_INVALID:'Ошибка настроек',SENSOR_FALLBACK:'Резерв при недоступном датчике',FLOOR_HARD_MAX:'Перегрев пола'};
    return text[code]||'Состояние управления изменено';
};
exports.houseValid=function(f) {
    if(!f || f.v!==3 || f.source!==C.houseSource || f.ttl_ms!==W.TTL_MS ||
        typeof f.session_id!=='number' || !isFinite(f.session_id) || f.session_id<1 || f.session_id>9007199254740991 || Math.floor(f.session_id)!==f.session_id ||
        typeof f.seq!=='number' || !isFinite(f.seq) || f.seq<1 || f.seq>9007199254740991 || Math.floor(f.seq)!==f.seq ||
        typeof f.sent_ms!=='number' || !isFinite(f.sent_ms) || !f.groups)return false;
    return ['501','502','503','505'].every(function(id){
        var g=f.groups[id];return g && typeof g.demand==='boolean' && typeof g.valid==='boolean' &&
            typeof g.ready==='boolean' && typeof g.enabled==='boolean' && typeof g.degraded==='boolean' &&
            (!g.demand || (g.enabled && g.valid)) && (!g.ready || g.demand) &&
            typeof g.reason==='string' &&
            (g.partial_ready===undefined || typeof g.partial_ready==='boolean') &&
            (g.output_blocked===undefined || typeof g.output_blocked==='boolean') &&
            (g.pending_on===undefined || typeof g.pending_on==='boolean') &&
            (g.pending_off===undefined || typeof g.pending_off==='boolean') &&
            (g.transition_safe===undefined || typeof g.transition_safe==='boolean') &&
            (!g.transition_safe || !g.output_blocked) &&
            (g.startRemainingMs===undefined || g.startRemainingMs===null ||
                (typeof g.startRemainingMs==='number'&&isFinite(g.startRemainingMs)&&g.startRemainingMs>=0&&
                 g.startRemainingMs<=C.circuits[id].zoneActuatorOpenMs&&!g.ready)) &&
            (!g.output_blocked || g.degraded) &&
            (!g.output_blocked || !g.partial_ready) &&
            (!g.partial_ready || (g.demand&&g.ready&&g.degraded&&g.valid)) &&
            (g.floor===null || (typeof g.floor==='number'&&isFinite(g.floor)&&g.floor>=-20&&g.floor<=70));
    });
};
exports.select=function(requests,now) {
    var selected='',temperature=0,unknown=0;
    C.priority.forEach(function(id){var r=requests[id];
        if(!r || r.valid!==true || typeof r.at!=='number' || now<r.at || now-r.at>=C.requestTtlMs)unknown++;
        if(!r || r.valid!==true || r.demand!==true || r.ready!==true ||
            typeof r.at!=='number' || now<r.at || now-r.at>=C.requestTtlMs ||
            typeof r.temperature!=='number'||!isFinite(r.temperature)||r.temperature<=0||r.temperature>C.source.maxC)return;
        if(r.temperature>temperature){selected=id;temperature=r.temperature;}
    });
    return {consumer:selected,temperature:temperature,demandKnown:unknown===0,unavailable:unknown}; // Zero never means unknown = OFF.
};
exports.source=function(config,storage,io) {
    var coolAt=null,firstSample=null,lastNow=null,lastWritten=null,responseAt=null,baseline=null;
    return function(requested,inService,now,demandKnown) {
        var t=io.read(config.temperature),connection=io.read(config.connection),fault=io.read(config.fault);
        if(lastNow!==null&&(now<lastNow||now-lastNow>15000)){coolAt=null;responseAt=null;}
        lastNow=now;
        if(t!==null&&t>=config.hardMaxC)storage.hot=true;
        if(storage.hot) {
            if(t===null||t>config.recoverC)coolAt=null;
            else if(coolAt===null){coolAt=now;firstSample=io.observedAt(config.temperature);}
            if(coolAt!==null&&now-coolAt>=config.coolMs&&io.observedAt(config.temperature)>firstSample)storage.hot=false;
        }
        var state='ACTIVE',warning='',command=null,ok=true,sent=false;
        function write(path,value){var w=io.write(path,value);sent=w.sent||sent;return w.ok;}
        if(!inService)state='FIRST_COMMISSIONING';
        else if(storage.hot){state='SOURCE_OVERHEAT';warning='Аппаратные защиты котла обязательны; насосы соседей не выключаются';}
        else if(connection!==0||fault!==0){state='OT_UNAVAILABLE';warning='Нет свежей исправной связи OT; новые команды удержаны';}
        else if(t===null){state='SOURCE_SENSOR_UNAVAILABLE';warning='Нет достоверного 411; новые команды удержаны';}
        else if(requested===0&&demandKnown===false){state='REQUESTS_UNAVAILABLE';warning='Запрос 0, но отсутствие спроса не подтверждено: команду OFF не выдаём';}
        else if(requested===0){
            state='NO_DEMAND';
            if(config.noDemandMode==='setpoint_zero') {ok=write(config.setpoint,0);command=0;}
            else if(config.noDemandMode==='ch_enable') {ok=write(config.chEnable,false);command=false;}
            else {state='NO_DEMAND_ACTION_UNCONFIRMED';warning='Запрос 0; физический способ выключения CH с сохранением ГВС не подтверждён';}
        } else {
            command=Math.max(config.minC,Math.min(config.maxC,requested));
            ok=write(config.setpoint,command);
            if(config.noDemandMode==='ch_enable'&&ok)ok=write(config.chEnable,true);
        }
        if(!ok){state='OUTPUT_WRITE_ERROR';warning='Повтор записи автоматически';}
        if(command!==null&&ok&&sent)lastWritten=command;
        if(requested>0&&t!==null){
            if(responseAt===null){responseAt=now;baseline=t;}
            if(t>=requested-1||t>=baseline+1){responseAt=now;baseline=t;}
            else if(now-responseAt>=config.responseMs)warning+='; NO_RESPONSE — недостаточный отклик, не защёлка';
        }else{responseAt=null;baseline=null;}
        return {requested_heating_setpoint:requested,state:state,warning:warning,
            command:command,last_written:lastWritten,command_sent:sent,
            commands:io.commands([config.setpoint,config.chEnable]),
            readback:{setpoint:io.readback(config.setpoint),chEnable:io.readback(config.chEnable)},
            off_command_sent:requested===0&&command!==null&&ok&&sent};
    };
};
