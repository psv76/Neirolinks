/* HHM3 / Ivolga boiler: five circuits, arbiter and the only source writer.
 * 620 owns zone relays; 506/507/DHW are not heating outputs.
 */
var C=require('HHM3Config').config,Z=require('HHM3Config').zones;
var W=require('HHM3Wire'),R=require('HHM3Runtime'),Policy=require('HHM3Circuit'),Mix=require('HHM3Mixing');
var Outputs=require('HHM3Outputs'),outputSteps={},evaluating=false;
var operation=new PersistentStorage('hhm3_operation',{global:true});
var userSettings=new PersistentStorage('hhm3_thermostats',{global:true});
var VD='HHM3_FSE',initialized=false,engines={},thermal={},directCool={},lastNow=null,openSince={},valveHistory={};
var allowed=[C.source.setpoint,C.source.chEnable];
Object.keys(C.circuits).forEach(function(id){var c=C.circuits[id];allowed.push(c.pump);if(c.kind==='mixed')allowed.push(c.level,c.enable);});
var io=R.io({dev:dev,now:Date.now,trackMqtt:trackMqtt,publish:publish,log:log,
    onSample:function(){if(initialized)evaluate();}},'500_HHM3',allowed);
var house=W.receiver(Date.now(),R.houseValid),gazebo=W.receiver(Date.now());
trackMqtt(C.houseTopic,function(m){house.accept(m.value,m.retained,Date.now());if(initialized)evaluate();});
trackMqtt(W.TOPIC,function(m){gazebo.accept(m.value,m.retained,Date.now());if(initialized)evaluate();});
[C.source.temperature,C.source.connection,C.source.fault].forEach(function(p){io.watch(p,p===C.source.temperature?-20:0,p===C.source.temperature?110:1);});
Z.forEach(function(z){z.outputs.forEach(function(p){io.watch(p,0,1);});});
Object.keys(C.circuits).forEach(function(id){
    var c=C.circuits[id];io.watch(c.supply,-20,110);io.watch(c.ret,-20,110);
    thermal[id]=new PersistentStorage('hhm3_circuit_'+id,{global:true});
    if(c.kind==='mixed')engines[id]=Policy.create(c,thermal[id],Mix);
    if(c.kind==='mixed')outputSteps[id]=Outputs.create(c,io);
});
var sourceStep=R.source(C.source,new PersistentStorage('hhm3_source',{global:true}),io);
// Keep JSON channels for existing diagnostics, but exclude raw JSON from WB WebUI.
// Operator-facing controls report actions and measurements, not false proof of motion.
defineVirtualDevice(VD,{title:'HHM3 — Иволга | состояние отопления',cells:{
    in_service:{title:'Управление отоплением разрешено',type:'switch',value:false,readonly:true,forceDefault:true,order:1},
    operational_status:{title:'Состояние системы',type:'text',value:'Ожидает первого ввода',readonly:true,forceDefault:true,order:2},
    circuit_501:{title:'501 · ТП дом, паркет',type:'text',value:'—',readonly:true,forceDefault:true,order:10},
    circuit_502:{title:'502 · ГП дом, плитка',type:'text',value:'—',readonly:true,forceDefault:true,order:11},
    circuit_503:{title:'503 · Радиаторы дом',type:'text',value:'—',readonly:true,forceDefault:true,order:12},
    circuit_504:{title:'504 · ГП беседка',type:'text',value:'—',readonly:true,forceDefault:true,order:13},
    circuit_505:{title:'505 · Радиаторы хозблок',type:'text',value:'—',readonly:true,forceDefault:true,order:14},
    selected_consumer:{title:'Источник для контура',type:'text',value:'',readonly:true,forceDefault:true,order:20},
    requested_source_temperature:{title:'Требуется от источника',type:'value',value:0,units:'deg C',readonly:true,forceDefault:true,order:21},
    requested_heating_setpoint:{title:'Команда котлу',type:'value',value:0,units:'deg C',readonly:true,forceDefault:true,order:22},
    source_status:{title:'Котёл',type:'text',value:'Ожидает первого ввода',readonly:true,forceDefault:true,order:23},
    runtime_status:{title:'Связь HHM3',type:'text',value:'STARTUP',readonly:true,forceDefault:true,order:24},
    last_event:{title:'Последнее событие',type:'text',value:'—',readonly:true,forceDefault:true,order:25},
    start_heating:{title:'Первый ввод отопления',type:'pushbutton',value:false,forceDefault:true,order:90,hidden:operation.inService===true},
    circuits_json:{title:'Служебные данные контуров',type:'text',value:'{}',readonly:true,forceDefault:true,hidden:true},
    source_json:{title:'Служебные данные котла',type:'text',value:'{}',readonly:true,forceDefault:true,hidden:true},
    last_event_json:{title:'Служебные данные событий',type:'text',value:'{}',readonly:true,forceDefault:true,hidden:true}
}});
function sc(k,v){dev[VD+'/'+k]=v;}
function event(id,r){
    var e=io.event(id,r.reason||r.state,r.warning);
    if(e){
        sc('last_event_json',JSON.stringify(e));
        sc('last_event',String(id)+': '+String(e.state)+(e.warning?' · '+String(e.warning).slice(0,80):''));
    }
}
function operatorCircuit(id,r,out){
    if(operation.inService!==true)return 'Ожидает первого ввода';
    if(/ERROR|UNCERTAIN/.test(out.state)||out.fault)return 'Ошибка команды: '+out.state;
    if(/^OVERHEAT/.test(r.reason))return 'Защита по температуре · '+r.reason;
    if(r.reason==='NO_DEMAND'||r.reason==='OFF')return 'Нет запроса · насос '+(out.pump?'ВКЛ':'ВЫКЛ');
    if(r.reason==='CIRCULATION_CHECK')return 'Подготовка · клапан закрыт · насос '+(out.pump?'ВКЛ':'ВЫКЛ');
    if(r.reason==='FLOOR_SENSOR_UNAVAILABLE'||r.reason==='NO_FEEDBACK_UNCOVERED')return 'Нет датчика · '+r.reason;
    if(r.pump)return 'Команда насосу ВКЛ · клапан '+(r.valve>0?String(Math.round(r.valve))+'%':'ЗАКРЫТ')+' · '+r.reason;
    return 'Насос ВЫКЛ · '+r.reason;
}
function fallback(id){
    var enabled=false,open=false,ready=false,now=Date.now();
    Z.filter(function(z){return z.circuit===id;}).forEach(function(z){
        var s=userSettings[z.id];if(s&&s.state===1)enabled=true;
        if(s&&s.state===1)z.outputs.forEach(function(p){if(io.read(p)===1){
            open=true;if(openSince[p]!==undefined&&now-openSince[p]>=C.circuits[id].zoneDelayMs)ready=true;
        }});
    });
    if(id==='505'){open=enabled;ready=enabled;}
    return {enabled:enabled,valid:!enabled||open,demand:enabled&&open,ready:enabled&&ready,
        degraded:enabled,reason:enabled?'HOUSE_LINK_LOST':'OFF',floor:null};
}
function direct(id,c,g,now){
    var t=io.read(c.supply),s=thermal[id],stamp=io.at(c.supply);
    if(t!==null&&t>=c.hardMaxC)s.hot=true;
    if(s.hot){
        if(t===null||t>c.recoverC)delete directCool[id];
        else if(!directCool[id])directCool[id]={at:now,sample:stamp};
        var cool=directCool[id];
        if(cool&&now-cool.at>=120000&&stamp>cool.sample)s.hot=false;
    }
    var pump=!!(g&&g.demand&&g.ready&&!s.hot);
    return {pump:pump,valve:0,demand:pump,valid:!!g&&g.valid,write:true,
        target:pump?(g.degraded?c.fallbackC:c.targetC):0,
        reason:s.hot?'OVERHEAT_STOP':(pump?(g.degraded?'DEGRADED':'NORMAL'):(g?g.reason:'REQUEST_UNAVAILABLE')),
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
    if(lastNow!==null&&(now<lastNow||now-lastNow>C.periodMs*3)){directCool={};openSince={};}
    lastNow=now;
    Z.forEach(function(z){z.outputs.forEach(function(p){
        if(io.read(p)===1){if(openSince[p]===undefined)openSince[p]=now;}else delete openSince[p];
    });});
    Object.keys(C.circuits).forEach(function(id){
        var c=C.circuits[id],g=id==='504'?null:(hl.frame?hl.frame.groups[id]:fallback(id)),r;
        if(operation.inService!==true)r={reason:'FIRST_COMMISSIONING',warning:'',write:false,pump:false,valve:0,demand:false,valid:false,target:0};
        else if(!io.compatible())r={reason:'RUNTIME_UNSUPPORTED',warning:W.RUNTIME_ERROR_RU,write:true,pump:false,valve:0,demand:false,valid:false,target:0};
        else if(c.kind==='direct')r=direct(id,c,g,now);
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
            r=engines[id].step({now:now,supply:io.read(c.supply),supplyAt:io.at(c.supply),
                ret:io.read(c.ret),source:io.read(C.source.temperature),frame:f,linkReason:gl.reason});
            // A failed write or an unconfirmed OFF might leave an unsafe
            // zone energized; no shared hot water until its OFF/readback is known.
            if(id!=='504'&&g.output_blocked===true){
                r.pump=false;r.valve=0;r.demand=false;r.target=0;r.valid=false;
                if(r.reason!=='OVERHEAT_STOP'&&r.reason!=='OVERHEAT_CLOSE')
                    r.reason='ZONE_OUTPUT_UNCONFIRMED';
                r.warning+='; зональный выход: ошибка записи либо OFF не подтверждён';
                engines[id].reset();
            }
            if(id!=='504'&&g.partial_ready===true&&r.reason==='NORMAL')
                r.warning+='; другая зона ожидает readback, подтверждённый путь сохранён';
            if(id!=='504'&&g.output_blocked!==true&&(!g.ready||!g.demand)){
                r.pump=false;r.valve=0;r.demand=false;r.target=0;
                if(r.reason!=='OVERHEAT_STOP'&&r.reason!=='OVERHEAT_CLOSE')r.reason=g.reason;
                if(!g.enabled)r.valid=true;
                engines[id].reset();
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
        if(failed){r.warning+='; '+out.state+'; '+(out.fault||'')+'; повтор автоматически';r.reason=out.state;if(engines[id])engines[id].reset();}
        var temperature=r.demand&&ok?r.target+(c.kind==='mixed'?c.sourceMarginC:0):0;
        // A known idle circuit is valid even when its pump is intentionally OFF.
        // A write error remains invalid; never turn an output fault into known zero.
        requests[id]={at:now,valid:r.valid&&!failed&&(!r.demand||ok),
            demand:r.demand&&ok,ready:r.pump&&ok,temperature:temperature};
        // Report abrupt calculated drops as events; do not call a command a physical movement.
        // Ordinary mixing steps are bounded to 4 points, so >=8 merits a trace.
        if(c.kind==='mixed'){
            if(valveHistory[id]!==undefined&&valveHistory[id]-r.valve>=8)
                io.event(id+'_valve_transition','VALVE_COMMAND_DROP',
                    'расчёт '+valveHistory[id]+' -> '+r.valve+'%; причина='+r.reason+
                    '; выход='+out.state);
            valveHistory[id]=r.valve;
        }
        reports[id]={reason:r.reason,warning:r.warning,pump_command:out.pump,requested_pump:r.pump,valve_pct:r.valve,
            output:out,commands:commands,command_sent:commands.some(function(w){return w.sent;}),
            demand:requests[id].demand,requested_source_temperature:temperature,
            supply:io.read(c.supply),return_temperature:io.read(c.ret)};
        sc('circuit_'+id,operatorCircuit(id,r,out));
        event(id,r);
    });
    var selected=R.select(requests,now),source=sourceStep(selected.temperature,operation.inService===true&&io.compatible(),now,selected.demandKnown);
    if(operation.inService===true&&!io.compatible()){source.state='RUNTIME_UNSUPPORTED';source.warning=W.RUNTIME_ERROR_RU;}
    sc('in_service',operation.inService===true);sc('circuits_json',JSON.stringify(reports));
    sc('operational_status',operation.inService!==true?'Ожидает первого ввода':
        !io.compatible()?'Несовместимая версия wb-rules':
        faultCount?'Ошибки команд контуров: '+faultCount:
        'Команды отопления разрешены (без подтверждения работы оборудования)');
    sc('selected_consumer',selected.consumer||'Нет');sc('requested_source_temperature',selected.temperature);
    sc('requested_heating_setpoint',source.requested_heating_setpoint);sc('source_json',JSON.stringify(source));
    sc('source_status',source.state+(source.warning?' · '+source.warning.slice(0,80):''));
    sc('runtime_status',io.runtime()+'; house='+hl.reason+'; gazebo='+gl.reason);
    event('source',source);
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
