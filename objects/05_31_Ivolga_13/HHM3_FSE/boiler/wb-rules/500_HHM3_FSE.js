/* HHM3 / Ivolga boiler: five circuits, arbiter and the only source writer.
 * 620 owns zone relays; 506/507/DHW are not heating outputs.
 */
var C=require('HHM3Config').config,Z=require('HHM3Config').zones;
var W=require('HHM3Wire'),R=require('HHM3Runtime'),Policy=require('HHM3Circuit'),Mix=require('HHM3Mixing');
var Outputs=require('HHM3Outputs'),outputSteps={},evaluating=false;
var operation=new PersistentStorage('hhm3_operation',{global:true});
var userSettings=new PersistentStorage('hhm3_thermostats',{global:true});
var operatorLog=new PersistentStorage('hhm3_operator_log',{global:true});
var VD='HHM3_FSE',initialized=false,engines={},thermal={},directCool={},lastNow=null,openSince={},valveHistory={},lastReports={},lastSource={};
var sourceUnavailableSince=null,sourceUnavailableLogged=false;
var pendingBoilerMode=null,lastObservedBoilerMode=null;
var lastLoggedSetpoint=(typeof operatorLog.lastSetpoint==='number'&&isFinite(operatorLog.lastSetpoint))?operatorLog.lastSetpoint:null;
var setpointLogArmed=false;
var allowed=[C.source.setpoint,C.source.boilerMode];
Object.keys(C.circuits).forEach(function(id){var c=C.circuits[id];allowed.push(c.pump);if(c.kind==='mixed')allowed.push(c.level,c.enable);});
var io=R.io({proofStorage:new PersistentStorage('hhm31_poll_500',{global:true}),dev:dev,now:Date.now,trackMqtt:trackMqtt,publish:publish,log:log,
    onSample:function(){if(initialized)evaluate();}},'500_HHM3',allowed);
var house=W.receiver(Date.now(),R.houseValid),gazebo=W.receiver(Date.now());
trackMqtt(C.houseTopic,function(m){house.accept(m.value,m.retained,Date.now());if(initialized)evaluate();});
trackMqtt(W.TOPIC,function(m){gazebo.accept(m.value,m.retained,Date.now());if(initialized)evaluate();});
io.watchTemperature(C.source.temperature,-20,110);
[C.source.connection,C.source.fault].forEach(function(p){io.watch(p,0,1);});
Z.forEach(function(z){z.outputs.forEach(function(p){io.watch(p,0,1);});});
Object.keys(C.circuits).forEach(function(id){
    var c=C.circuits[id];io.watchTemperature(c.supply,-20,110);io.watchTemperature(c.ret,-20,110);
    thermal[id]=new PersistentStorage('hhm3_circuit_'+id,{global:true});
    if(c.kind==='mixed')engines[id]=Policy.create(c,thermal[id],Mix);
    if(c.kind==='mixed')outputSteps[id]=Outputs.create(c,io);
});
var sourceStep=R.source(C.source,new PersistentStorage('hhm3_source',{global:true}),io);
// Operator-facing virtual controls only. Detailed per-cycle structures stay in memory
// for regression tests and are not published as large MQTT/WebUI JSON strings.
defineVirtualDevice(VD,{title:'HHM3 — Иволга | отопление',cells:{
    runtime_version:{title:'Версия HHM',type:'text',value:C.version,readonly:true,forceDefault:true,order:3},
    sensor_health_contract:{type:'text',value:C.healthContract,readonly:true,forceDefault:true,hidden:true},
    in_service:{title:'Отопление разрешено',type:'switch',value:false,readonly:true,forceDefault:true,order:1},
    operational_status:{title:'Общий статус',type:'text',value:'Ожидает первого ввода',readonly:true,forceDefault:true,order:2},
    circuit_501:{title:'501 · ТП дом, паркет',type:'text',value:'—',readonly:true,forceDefault:true,order:10},
    circuit_502:{title:'502 · ГП дом, плитка',type:'text',value:'—',readonly:true,forceDefault:true,order:11},
    circuit_503:{title:'503 · Радиаторы дом',type:'text',value:'—',readonly:true,forceDefault:true,order:12},
    circuit_504:{title:'504 · ГП беседка',type:'text',value:'—',readonly:true,forceDefault:true,order:13},
    circuit_505:{title:'505 · Радиаторы хозблок',type:'text',value:'—',readonly:true,forceDefault:true,order:14},
    selected_consumer:{title:'Ведущий контур',type:'text',value:'',readonly:true,forceDefault:true,order:20},
    requested_source_temperature:{title:'Требуемая температура котла',type:'value',value:0,units:'deg C',readonly:true,forceDefault:true,order:21},
    requested_heating_setpoint:{title:'Расчётная уставка котла',type:'value',value:0,units:'deg C',readonly:true,forceDefault:true,order:22},
    source_status:{title:'Котёл / источник',type:'text',value:'Ожидает первого ввода',readonly:true,forceDefault:true,order:23},
    runtime_status:{title:'Связь и данные',type:'text',value:'Запуск',readonly:true,forceDefault:true,order:24},
    last_event:{title:'Последнее событие',type:'text',value:'—',readonly:true,forceDefault:true,order:25},
    diag_request_501:{title:'501 diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    diag_request_502:{title:'502 diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    diag_request_503:{title:'503 diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    diag_request_504:{title:'504 diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    diag_request_505:{title:'505 diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    diag_request_boiler:{title:'Boiler diagnostic request',type:'value',value:-1,readonly:true,forceDefault:true,hidden:true},
    start_heating:{title:'Первый ввод отопления',type:'pushbutton',value:false,forceDefault:true,order:90,hidden:operation.inService===true}
}});
var hhm3Device=getDevice(VD);
Object.keys(C.circuits).forEach(function(id){
    ['start','stop'].forEach(function(kind){
        if(!hhm3Device.isControlExists('pump_'+kind+'_remaining_'+id))hhm3Device.addControl('pump_'+kind+'_remaining_'+id,{title:id+' · До '+(kind==='start'?'запуска':'остановки')+' насоса',
            type:'text',value:'—',readonly:true,forceDefault:true,order:30+Number(id-501)*2+(kind==='stop'?1:0)});
    });
});
var timerStates={},directPostrun={};
function timer(id,kind,ms,r,out,group){
    var key=kind+'_'+id,active=typeof ms==='number'&&isFinite(ms)&&ms>0,code,reason;
    var startStillRequested=group?!!group.demand:!!r.demand;
    sc('pump_'+kind+'_remaining_'+id,active?String(Math.ceil(ms/1000))+' с':'—');
    if(active&&timerStates[key]!==true){
        code=kind==='start'?'TIMER_ZONE_OPEN_STARTED':'TIMER_PUMP_POSTRUN_STARTED';
        reason=kind==='start'?'Есть запрос тепла, ждём открытия зоны':'Нет запроса тепла';
        io.event(id+'_'+kind+'_timer',code,'','',reason);
    }
    if(!active&&timerStates[key]===true){
        if(out.fault||/^OVERHEAT|ZONE_OUTPUT/.test(r.reason)){
            code='TIMER_INTERRUPTED';reason='Ошибка или защита';
        }else if(kind==='start'){
            // The actuator wait is complete when the demand still exists; pump output
            // may legitimately still be waiting for its own electrical confirmation.
            code=startStillRequested?'TIMER_ZONE_OPEN_FINISHED':'TIMER_ZONE_OPEN_CANCELLED';
            reason=startStillRequested?'Время открытия зоны истекло':'Запрос снят до готовности зоны';
        }else{
            code=r.demand?'TIMER_PUMP_POSTRUN_CANCELLED':'TIMER_PUMP_POSTRUN_FINISHED';
            reason=r.demand?'Появился новый готовый запрос':'Время выбега истекло';
        }
        io.event(id+'_'+kind+'_timer',code,'','',reason);
    }
    timerStates[key]=active;
}
['circuits_json','source_json','last_event_json'].forEach(function(id){
    if(!hhm3Device)return;
    // These controls existed in earlier releases and may survive only as retained
    // MQTT metadata while no longer belonging to the current virtual-device model.
    // Recreate them in the model first, then remove through the wb-rules API so the
    // broker receives proper retained tombstones.
    if(!hhm3Device.isControlExists(id))
        hhm3Device.addControl(id,{title:'Legacy cleanup',type:'text',value:'',readonly:true,hidden:true,forceDefault:true});
    hhm3Device.removeControl(id);
});
function sc(k,v){
    var p=VD+'/'+k;
    if(dev[p]!==v)dev[p]=v;
}
function linkState(r){return r&&r.reason?r.reason:'NORMAL';}
function cleanWarning(value){
    return String(value||'').replace(/^\s*;\s*/,'').replace(/\s*;\s*$/,'').trim();
}
function event(id,r,out){
    var state=r.reason||r.state,warning=cleanWarning(r.warning);
    // Normal zone ON/OFF confirmation while an already-ready path keeps the pump commanded ON
    // is technical handshake, not an operator event.
    if((state==='PENDING_ON_READBACK'||state==='PENDING_OFF_READBACK')&&out&&out.pump===true){
        io.trace(id,state,warning,'готовый путь сохранён; команда_насосу=ВКЛ');
        return;
    }
    // A source below requested temperature immediately after demand is a normal warm-up phase,
    // not a fault. Keep it visible to the operator without WARNING/NORMAL contradiction.
    if(state==='NORMAL'&&warning==='источник ещё холодный'){
        var warm=io.event(id,'SOURCE_WARMING','','','Температура источника ниже требуемой');
        if(warm)sc('last_event',String(id)+': '+R.stateText(warm.state));
        return;
    }
    var e=io.event(id,state,warning);
    if(e)sc('last_event',String(id)+': '+R.stateText(e.state)+(e.warning?' · '+String(e.warning).slice(0,80):''));
}
function boilerModeName(value){
    if(value===C.source.standbyMode)return '«Ожидание»';
    if(value===C.source.heatingMode)return '«Зима ЦО + ГВС»';
    return 'код '+String(value);
}
function sourceModeEvents(r){
    var rb=r.readback&&r.readback.boilerMode?r.readback.boilerMode.value:null;
    var modeCode,reason,confirmed=false,i,w;
    if(r.mode_command_sent){
        var commanded=r.boiler_mode_command;
        if(pendingBoilerMode!==commanded){
            pendingBoilerMode=commanded;
            modeCode=commanded===C.source.standbyMode?'BOILER_MODE_COMMAND_STANDBY':'BOILER_MODE_COMMAND_HEATING';
            reason=commanded===C.source.standbyMode?'Нет запроса тепла':
                (lastSource&&lastSource.requested_heating_setpoint===0?'Появился запрос тепла':'Есть запрос тепла');
            io.event('source_mode_command',modeCode,'',
                'канал='+C.source.boilerMode+'; значение='+String(commanded)+'; режим='+boilerModeName(commanded),
                reason);
        }
    }
    if(rb!==null&&rb!==undefined){
        if(pendingBoilerMode!==null&&rb===pendingBoilerMode){
            modeCode=rb===C.source.standbyMode?'BOILER_MODE_CONFIRMED_STANDBY':'BOILER_MODE_CONFIRMED_HEATING';
            reason=rb===C.source.standbyMode?'Нет запроса тепла':'Есть запрос тепла';
            io.event('source_mode_confirmed',modeCode,'',
                'канал='+C.source.boilerMode+'; readback='+String(rb)+'; режим='+boilerModeName(rb),reason);
            pendingBoilerMode=null;confirmed=true;
            if(rb===C.source.heatingMode)setpointLogArmed=true;
        }
        if(!confirmed&&pendingBoilerMode===null&&lastObservedBoilerMode!==null&&rb!==lastObservedBoilerMode){
            io.event('source_mode_external','BOILER_MODE_EXTERNAL_CHANGE','',
                'было='+boilerModeName(lastObservedBoilerMode)+' ('+String(lastObservedBoilerMode)+')'+
                '; стало='+boilerModeName(rb)+' ('+String(rb)+')','Получен новый readback режима котла');
        }
        lastObservedBoilerMode=rb;
    }
    for(i=0;i<(r.commands||[]).length;i++){
        w=r.commands[i];
        if(w.path===C.source.setpoint&&w.sent&&w.ok){
            var setpoint=Number(w.value);
            if(isFinite(setpoint)&&(setpointLogArmed||lastLoggedSetpoint===null||setpoint!==lastLoggedSetpoint)){
                io.event('source_setpoint','BOILER_SETPOINT_COMMAND','',
                    'канал='+C.source.setpoint+'; значение_С='+String(setpoint),'Есть запрос тепла');
                lastLoggedSetpoint=setpoint;
                operatorLog.lastSetpoint=setpoint;
                setpointLogArmed=false;
            }
        }
    }
}
function sourceEvent(r,now){
    if(r.state==='REQUESTS_UNAVAILABLE'){
        if(sourceUnavailableSince===null)sourceUnavailableSince=now;
        io.trace('source',r.state,r.warning,'краткая недоступность запросов');
        if(!sourceUnavailableLogged&&now-sourceUnavailableSince>=C.requestTtlMs){
            sourceUnavailableLogged=true;
            event('source',r);
        }
        return;
    }
    sourceUnavailableSince=null;
    if(sourceUnavailableLogged){
        sourceUnavailableLogged=false;
        event('source',r);
        return;
    }
    // Normal source mode switching is represented by explicit command/readback events.
    if(!r.warning&&(r.state==='NO_DEMAND_SWITCHING'||r.state==='SOURCE_MODE_STARTING'||
       r.state==='NO_DEMAND'||r.state==='ACTIVE'))return;
    event('source',r);
}
function onOff(value){
    if(value===true||value===1)return 'ВКЛ';
    if(value===false||value===0)return 'ВЫКЛ';
    return 'Нет данных';
}
function logValue(value){
    if(value===true||value===false||value===1||value===0)return onOff(value);
    if(value===null||value===undefined)return 'Нет достоверного подтверждения';
    return String(value);
}
function readbackText(readback){
    if(!readback||readback.value===null||readback.value===undefined)return 'Нет достоверного подтверждения';
    return logValue(readback.value)+(typeof readback.seq==='number'?', seq='+readback.seq:'');
}
function diagnosticCircuitRequest(id,r){
    var c=C.circuits[id],n,margin;
    if(!r || typeof r.demand!=='boolean' || !c)return -1;
    if(!r.demand)return 0;
    n=r.requested_source_temperature;
    if(typeof n!=='number' || !isFinite(n) || n<=0)return -1;
    margin=c.kind==='mixed'?c.sourceMarginC:0;
    if(typeof margin!=='number' || !isFinite(margin))return -1;
    n-=margin;
    return n>=0&&n<=100?Math.round(n*10)/10:-1;
}
function diagnosticBoilerRequest(source){
    var n;
    if(!source || source.state==='REQUESTS_UNAVAILABLE')return -1;
    n=source.requested_heating_setpoint;
    return typeof n==='number'&&isFinite(n)&&n>=0&&n<=100?Math.round(n*10)/10:-1;
}
function operatorCircuit(id,r,out){
    if(operation.inService!==true)return 'Ожидает первого ввода';
    if(/ERROR|UNCERTAIN/.test(out.state)||out.fault)return R.stateText(out.state);
    if(/^OVERHEAT/.test(r.reason))return R.stateText(r.reason);
    if(r.reason==='PUMP_POSTRUN')return 'Насос в выбеге · команда ВКЛ';
    if(r.startRemainingMs>0)return 'Ждём открытия зоны · готовность по времени';
    if(r.reason==='NO_DEMAND'||r.reason==='OFF')return 'Нет запроса · команда насосу '+(out.pump?'ВКЛ':'ВЫКЛ');
    if(r.reason==='CIRCULATION_CHECK')return 'Подготовка · клапан закрыт · насос '+(out.pump?'ВКЛ':'ВЫКЛ');
    if(r.reason==='FLOOR_SENSOR_UNAVAILABLE'||r.reason==='NO_FEEDBACK_UNCOVERED')return R.stateText(r.reason);
    if(out.state==='WAIT_OUTPUT_READBACK')return R.stateText(out.state);
    if(r.pump)return R.stateText(r.reason)+' · команда насосу '+(out.pump?'ВКЛ':'ВЫКЛ')+
        ' · расчёт клапана '+(r.valve>0?String(Math.round(r.valve))+'%':'0%');
    return 'Команда насосу ВЫКЛ · '+R.stateText(r.reason);
}
function fallback(id){
    var enabled=false,open=false,ready=false,now=Date.now(),remaining=null;
    Z.filter(function(z){return z.circuit===id;}).forEach(function(z){
        var s=userSettings[z.id];if(s&&s.state===1)enabled=true;
        if(s&&s.state===1)z.outputs.forEach(function(p){if(io.read(p)===1){
            open=true;if(openSince[p]!==undefined){
                var left=Math.max(0,C.circuits[id].zoneActuatorOpenMs-(now-openSince[p]));
                if(left===0)ready=true;
                if(remaining===null||left<remaining)remaining=left;
            }
        }});
    });
    if(id==='505'){open=enabled;ready=enabled;}
    return {enabled:enabled,valid:!enabled||open,demand:enabled&&open,ready:enabled&&ready,
        degraded:enabled,reason:enabled?'HOUSE_LINK_LOST':'OFF',floor:null,startRemainingMs:ready?null:remaining};
}
function direct(id,c,g,now){
    var t=io.read(c.supply),s=thermal[id],stamp=io.observedAt(c.supply);
    if(t!==null&&t>=c.hardMaxC)s.hot=true;
    if(s.hot){
        if(t===null||t>c.recoverC)delete directCool[id];
        else if(!directCool[id])directCool[id]={at:now,sample:stamp};
        var cool=directCool[id];
        if(cool&&now-cool.at>=120000&&stamp>cool.sample)s.hot=false;
    }
    var demand=!!(g&&g.demand&&g.ready&&!s.hot),pump=demand,remaining=null;
    if(demand)delete directPostrun[id];
    else if(s.hot||!g||g.output_blocked||(g.degraded&&g.transition_safe!==true))delete directPostrun[id];
    else if(c.zoneActuatorOpenMs>0&&c.pumpPostrunMs>0){
        if(directPostrun[id]===undefined&&lastReports[id]&&lastReports[id].pump_command===true)
            directPostrun[id]=now;
        if(directPostrun[id]!==undefined&&now-directPostrun[id]<c.pumpPostrunMs){
            pump=true;remaining=c.pumpPostrunMs-(now-directPostrun[id]);
        }
    }
    return {pump:pump,valve:0,demand:demand,valid:!!g&&g.valid,write:true,stopRemainingMs:remaining,
        target:demand?(g.degraded?c.fallbackC:c.targetC):0,
        reason:s.hot?'OVERHEAT_STOP':(remaining!==null?'PUMP_POSTRUN':(demand?(g.degraded?'DEGRADED':'NORMAL'):(g?g.reason:'REQUEST_UNAVAILABLE'))),
        warning:s.hot?'Перегрев локальной подачи':(g&&g.degraded?'Нет свежего комнатного спроса; ограниченный резерв':'')};
}
function evaluate(){
    if(evaluating)return;
    evaluating=true;
    try {evaluateOnce();} finally {evaluating=false;}
}
function evaluateOnce(){
    io.begin();
    var now=Date.now(),hl=house.read(now),gl=gazebo.read(now),requests={},reports={},faultCount=0;
    if(lastNow!==null&&(now<lastNow||now-lastNow>C.periodMs*3)){directCool={};openSince={};directPostrun={};lastReports={};}
    lastNow=now;
    Z.forEach(function(z){z.outputs.forEach(function(p){
        if(io.read(p)===1){if(openSince[p]===undefined)openSince[p]=now;}else delete openSince[p];
    });});
    Object.keys(C.circuits).forEach(function(id){
        var c=C.circuits[id],g=id==='504'?null:(hl.frame?hl.frame.groups[id]:fallback(id)),r;
        if(operation.inService!==true)r={reason:'FIRST_COMMISSIONING',warning:'',write:false,pump:false,valve:0,demand:false,valid:false,target:0};
        else if(!io.compatible())r={reason:'RUNTIME_UNSUPPORTED',warning:W.RUNTIME_ERROR_RU,write:true,pump:false,valve:0,demand:false,valid:false,target:0};
        else if(c.kind==='direct'){
            r=direct(id,c,g,now);
            if(g&&g.output_blocked===true){
                r.pump=false;r.demand=false;r.valid=false;r.target=0;
                r.reason='ZONE_OUTPUT_UNCONFIRMED';
                r.warning='Ошибка зонального выхода либо OFF не подтверждён; насос остановлен';
            }
        }
        else {
            var f=id==='504'?gl.frame:{
                // Only an authenticated partial-ready group (pending ON with
                // another confirmed ready path, no sensor/command fault) may
                // retain NORMAL. Never treat the pending zone as open.
                valid:g.valid&&(!g.degraded||(g.partial_ready===true&&g.ready&&g.demand)),
                enabled:true,demand:g.demand,floor:g.floor,
                mode:'HEAT',heat:c.floorTargetMaxC,hold:c.floorTargetMaxC,reason:g.reason,
                sent_ms:hl.frame?hl.frame.sent_ms:now,session_id:hl.frame?hl.frame.session_id:0,seq:hl.frame?hl.frame.seq:0};
            if(id!=='504'&&!g.enabled)f.valid=true;
            r=engines[id].step({now:now,supply:io.read(c.supply),supplyAt:io.observedAt(c.supply),
                ret:io.read(c.ret),source:io.read(C.source.temperature),frame:f,linkReason:gl.reason,
                zoneReady:id==='504'?undefined:!!(g.ready&&g.demand),
                pumpWasOn:!!(lastReports[id]&&lastReports[id].pump_command===true),
                zoneSafe:id==='504'?undefined:!g.output_blocked&&(!g.degraded||g.transition_safe===true)});
            // A failed write or an unconfirmed OFF might leave an unsafe
            // zone energized; no shared hot water until its OFF/readback is known.
            if(id!=='504'&&g.output_blocked===true){
                r.pump=false;r.valve=0;r.demand=false;r.target=0;r.valid=false;
                if(r.reason!=='OVERHEAT_STOP'&&r.reason!=='OVERHEAT_CLOSE')
                    r.reason='ZONE_OUTPUT_UNCONFIRMED';
                if(r.reason==='OVERHEAT_CLOSE')
                    r.warning='Перегрев: подмес закрыт; рециркуляция запрещена из-за неподтверждённого OFF зоны';
                else r.warning+='; зональный выход: ошибка записи либо OFF не подтверждён';
                engines[id].reset();
            }
            if(id!=='504'&&g.partial_ready===true&&r.reason==='NORMAL')
                r.warning+='; '+(g.pending_off?'ждём подтверждение выключения зоны':'ждём подтверждение включения зоны')+
                    (g.pending_off&&g.pending_on?'; ждём подтверждение включения другой зоны':'')+'; готовый путь сохранён';
            if(id!=='504'&&g.output_blocked!==true&&(!g.ready||!g.demand)&&r.reason!=='PUMP_POSTRUN'){
                r.pump=false;r.valve=0;r.demand=false;r.target=0;
                if(r.reason!=='OVERHEAT_STOP'&&r.reason!=='OVERHEAT_CLOSE')r.reason=g.reason;
                if(!g.enabled)r.valid=true;
            }
        }
        var out={state:'NOT_SENT',ready:false,pump:false},writeResult;
        if(r.write&&c.kind==='mixed')out=outputSteps[id](r,now);
        else if(r.write){
            writeResult=io.write(c.pump,r.pump);
            // Command acceptance is not physical pump feedback. Do not block
            // direct circuits on an unrelated delayed MQTT publication.
            out={state:writeResult.ok?'COMMAND_ACCEPTED':'OUTPUT_WRITE_ERROR',
                ready:writeResult.ok,pump:r.pump,readback:{pump:io.readback(c.pump)}};
        }
        var commands=io.commands([c.pump,c.level,c.enable]);
        if(commands.some(function(w){return !w.ok;})&&!/ERROR|UNCERTAIN/.test(out.state))out.state='OUTPUT_WRITE_ERROR';
        var failed=/ERROR|UNCERTAIN/.test(out.state)||!!out.fault,ok=out.ready&&!failed;
        if(failed)faultCount++;
        if(failed){r.warning+='; '+R.stateText(out.state)+'; восстановление по подтверждению выхода';r.reason=out.state;if(engines[id])engines[id].reset();delete directPostrun[id];}
        r.startRemainingMs=null;
        if(operation.inService===true&&!failed&&!r.pump&&g&&g.startRemainingMs>0&&!g.output_blocked&&
           !/^OVERHEAT|RUNTIME_UNSUPPORTED/.test(r.reason))
            r.startRemainingMs=Math.max(0,g.startRemainingMs-(hl.frame?now-hl.frame.sent_ms:0));
        if(failed||out.pump!==true)r.stopRemainingMs=null;
        timer(id,'start',r.startRemainingMs,r,out,g);timer(id,'stop',r.stopRemainingMs,r,out,g);
        var temperature=r.demand&&ok?r.target+(c.kind==='mixed'?c.sourceMarginC:0):0;
        // A known idle circuit is valid even when its pump is intentionally OFF.
        // A write error remains invalid; never turn an output fault into known zero.
        requests[id]={at:now,valid:r.valid&&!failed&&(!r.demand||ok),
            demand:r.demand&&ok,ready:r.pump&&ok,temperature:temperature};
        // Report abrupt calculated drops as events; do not call a command a physical movement.
        // Ordinary mixing steps are bounded to 4 points, so >=8 merits a trace.
        if(c.kind==='mixed'){
            if(valveHistory[id]!==undefined&&valveHistory[id]-r.valve>=8)
                io.trace(id+'_valve_transition','VALVE_COMMAND_DROP','',
                    'расчёт_было_проц='+valveHistory[id]+'; расчёт_стало_проц='+r.valve+
                    '; основание='+R.stateText(r.reason)+'; код_основания='+r.reason+
                    '; состояние_выхода='+R.stateText(out.state));
            valveHistory[id]=r.valve;
        }
        reports[id]={reason:r.reason,warning:r.warning,pump_command:out.pump,requested_pump:r.pump,valve_pct:r.valve,
            stopRemainingMs:r.stopRemainingMs,
            output:out,commands:commands,command_sent:commands.some(function(w){return w.sent;}),
            demand:requests[id].demand,requested_source_temperature:temperature,
            supply:io.read(c.supply),return_temperature:io.read(c.ret)};
        var previous=lastReports[id],prior=previous?previous.output:null;
        if(!prior||prior.state!==out.state||prior.ready!==out.ready||prior.pump!==out.pump||
           prior.closed_readback_match!==out.closed_readback_match){
            // Full output handshake belongs to machine trace, not the operator journal.
            io.trace(id+'_output','OUTPUT_TRANSITION','',
                'состояние='+R.stateText(out.state)+'; решение='+R.stateText(r.reason)+
                '; расчёт_клапана_проц='+r.valve+'; команда_насосу='+onOff(out.pump)+
                '; записи='+commands.filter(function(w){return w.attempted;}).map(function(w){
                    return w.path+'='+logValue(w.value)+' ('+(w.ok?'попытка без обнаруженной ошибки':'ошибка записи')+')';
                }).join(', ')+
                '; readback_Level='+readbackText(out.readback&&out.readback.level)+
                '; readback_Switch='+readbackText(out.readback&&out.readback.enable)+
                '; readback_насоса='+readbackText(out.readback&&out.readback.pump)+
                '; сохранённый_Level='+logValue(out.saved_level)+
                '; готовность='+(out.ready?'Подтверждена':'Не подтверждена'));
        }
        if(!prior||prior.pump!==out.pump){
            io.event(id+'_pump_command',out.pump?'PUMP_COMMAND_ON':'PUMP_COMMAND_OFF','',
                'канал='+c.pump+'; значение='+onOff(out.pump),R.stateText(r.reason));
        }
        if(c.kind==='mixed'){
            var enableWrite=commands.filter(function(w){return w.attempted&&w.path===c.enable;}).slice(-1)[0];
            if(enableWrite){
                io.event(id+'_hot_port_command',enableWrite.value?'HOT_PORT_COMMAND_ON':'HOT_PORT_COMMAND_OFF','',
                    'канал='+c.enable+'; значение='+onOff(enableWrite.value),R.stateText(r.reason));
            }
        }
        sc('diag_request_'+id,diagnosticCircuitRequest(id,reports[id]));
        sc('circuit_'+id,operatorCircuit(id,r,out));
        event(id,r,out);
    });
    var selected=R.select(requests,now),source=sourceStep(selected.temperature,operation.inService===true&&io.compatible(),now,selected.demandKnown);
    if(operation.inService===true&&!io.compatible()){source.state='RUNTIME_UNSUPPORTED';source.warning=W.RUNTIME_ERROR_RU;}
    lastReports=reports;
    sc('in_service',operation.inService===true);
    sc('operational_status',operation.inService!==true?'Ожидает первого ввода':
        !io.compatible()?'Несовместимая версия wb-rules':
        faultCount?'Ошибки команд контуров: '+faultCount:
        'Команды отопления разрешены (без подтверждения работы оборудования)');
    sc('selected_consumer',selected.consumer||'Нет');sc('requested_source_temperature',selected.temperature);
    sc('requested_heating_setpoint',source.requested_heating_setpoint);
    sc('diag_request_boiler',diagnosticBoilerRequest(source));
    sc('source_status',R.stateText(source.state)+(source.warning?' · '+source.warning.slice(0,80):''));
    sc('runtime_status',io.runtime()+' · дом '+linkState(hl)+' · беседка '+linkState(gl));
    sourceModeEvents(source);
    sourceEvent(source,now);
    lastSource=source;
}
defineRule('hhm3_first_start',{whenChanged:VD+'/start_heating',then:function(value){
    if(value!==true&&value!==1&&value!=='1')return;
    if(operation.inService!==true){
        operation.inService=true;
        dev[VD+'/start_heating#hidden']=true;
    }
    evaluate();
}});
initialized=true;evaluate();setInterval(evaluate,C.periodMs);
