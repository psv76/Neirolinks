/* 05 16 Исеть. Единый HHM: комнаты, радиаторы, ГВС, ТП, OpenTherm.
 * Пишет: NO K1–K16, насосы wb-mr6cu_37/K1..K4,
 * wb-mao4_131/Channel 1, OT11 Heating Setpoint.
 * ВКЛЮЧАТЬ только вместо отключённых скриптов HM2 20–27.
 * Не запускать одновременно с 28_hhm_rooms_shadow.js (общие VD).
 */
var HHM_PHYSICAL_OUTPUTS=true; // release: install ONLY after HM2 writers retired
var HHM_ROOM_MAP=require("IsetRoomZones");
var HHM_SVC=require("IsetServiceConfig");
var HHM_STORE=require("IsetRoomSettingsStore");
var HHM_SIMPLE=require("IsetRoomSimpleThermostat");
var HHM_ROOMS=require("IsetRoomLocalRuntime");
var HHM_GATE=require("HHMRoomPathGate");
var HHM_ROOM_PLAN=require("IsetRoomOutputPlanner");
var HHM_DHW=require("IsetDhw");
var HHM_DEMAND=require("IsetDemand");
var HHM_SOURCE=require("IsetSource");
var HHM_COORD=require("IsetCoordinator");
var HHM_FLOOR=require("IsetFloorHydraulics");
var HHM_MIX=require("IsetFloorMixing");
var HHM_MIX_CORE=require("HHM3Mixing");
var HHM_RUN=require("IsetUnifiedRuntime");
var HHM_PERSIST=new PersistentStorage("iset_hhm_rooms_v1",{global:true});
function hhFloorStored(){
    try{
        var s=JSON.parse(HHM_PERSIST.iset_hhm_floor_cfg_v1||"null");
        return s&&s.version===1&&typeof s.enabled==="boolean"&&
            typeof s.targetC==="number"&&s.targetC>=20&&s.targetC<=40?
            s:null;
    }catch(e){return null;}
}
// Approved for Iset: initial floor supply 32 C, enabled on first setup.
var HHM_FLOOR_SETTINGS=hhFloorStored();
if(HHM_FLOOR_SETTINGS===null){
    var HHM_FLOOR_INITIAL={version:1,enabled:true,targetC:32};
    var HHM_FLOOR_RAW=JSON.stringify(HHM_FLOOR_INITIAL);
    HHM_PERSIST.iset_hhm_floor_cfg_v1=HHM_FLOOR_RAW;
    if(HHM_PERSIST.iset_hhm_floor_cfg_v1===HHM_FLOOR_RAW)
        HHM_FLOOR_SETTINGS=HHM_FLOOR_INITIAL;
    else log.warning("[отопление][29_hhm_iset][ТП]; ОШИБКА=Начальная уставка 32 не сохранена");
}
function hhBasementStored(){
    try{
        var n=Number(HHM_PERSIST.iset_hhm_basement_target_v1);
        return isFinite(n)&&n>=10&&n<=30?n:null;
    }catch(e){return null;}
}
var HHM_BASEMENT_TARGET=hhBasementStored();
if(HHM_BASEMENT_TARGET!==null)
    HHM_SVC.basement.targetC=HHM_BASEMENT_TARGET;
var HHM_BOOT="iset-hhm-"+String(Date.now());
var HHM_ERRORS={},HHM_PREV={},HHM_MIX_INTENTS=[],HHM_BUSY=false;
var HHM_LAST_WRITE={};
// Diagnostic-only state: failures here MUST NOT affect the control plan.
var HHM_TRACE_RING=[],HHM_TRACE_SEQ=0;
var HHM_SENSOR_OBS={},HHM_SENSOR_LAST_FAULT={};
var HHM_SENSOR_START_AT=Date.now();
var HHM_SENSOR_SPECS=[
    {id:"common",title:"Общая подача",path:HHM_SVC.channels.common},
    {id:"outdoor",title:"Улица",path:HHM_SVC.channels.outdoor},
    {id:"living",title:"Подача жилой зоны",path:HHM_SVC.channels.livingSupply},
    {id:"basement",title:"Подача цоколя",path:HHM_SVC.channels.basementSupply},
    {id:"floor",title:"Подача ТП",path:HHM_SVC.channels.floorSupply},
    {id:"dhw",title:"Бойлер ГВС",path:HHM_SVC.channels.dhwTank}
];
// Explicit user-approved initial settings: every room HEAT / 25 C.
// Existing valid WB settings always take precedence after restart.
for(var HHM_SEED=0;HHM_SEED<HHM_ROOM_MAP.zones.length;HHM_SEED++){
    var HHM_SEED_ZONE=HHM_ROOM_MAP.zones[HHM_SEED];
    var HHM_SEED_STORE=HHM_STORE.create(HHM_PERSIST,HHM_SEED_ZONE.id);
    if(HHM_SEED_STORE.read()===null){
        if(!HHM_SEED_STORE.provisionApproved("HEAT",25))
            log.warning("[отопление][29_hhm_iset]["+HHM_SEED_ZONE.id+
                "]; ОШИБКА=Начальная уставка 25 не сохранена");
    }
}
var HHM_ROOM=HHM_ROOMS.create({map:HHM_ROOM_MAP,Simple:HHM_SIMPLE,
    Settings:HHM_STORE,PathGate:HHM_GATE,storage:HHM_PERSIST,
    minSetpointC:16,maxSetpointC:30,hysteresisC:0.6,
    minMeasuredC:-20,maxMeasuredC:60});
var HHM_COORDINATOR=HHM_COORD.create({rooms:HHM_ROOM,
    dhw:HHM_DHW.create(HHM_SVC.dhw),
    demand:HHM_DEMAND.create(HHM_SVC),
    source:HHM_SOURCE.create(HHM_SVC.source),services:HHM_SVC});
var HHM_MIXER=HHM_MIX.create(HHM_MIX_CORE,{
    writePosition:function(v){
        if(HHM_PHYSICAL_OUTPUTS)
            return hhWrite({path:HHM_SVC.outputs.floorValveLevel,
                value:v,action:"MIX_VALVE_POS",reason:"FLOOR_MIXING"},
                Date.now());
        HHM_MIX_INTENTS.push({path:HHM_SVC.outputs.floorValveLevel,
            value:v,action:"MIX_VALVE_POS"});return true;
    },
    writeEnable:function(v){
        if(HHM_PHYSICAL_OUTPUTS)
            return hhWrite({path:HHM_SVC.outputs.floorValveEnable,
                value:v,action:"MIX_ENABLE",reason:"FLOOR_MIXING"},
                Date.now());
        HHM_MIX_INTENTS.push({path:HHM_SVC.outputs.floorValveEnable,
            value:v,action:"MIX_ENABLE"});return true;
    }
});
var HHM_ENGINE=HHM_RUN.create({
    map:HHM_ROOM_MAP,services:HHM_SVC,coordinator:HHM_COORDINATOR,
    roomsPlanner:HHM_ROOM_PLAN.create({map:HHM_ROOM_MAP,
        openWaitMs:120000}),
    floorHydraulics:HHM_FLOOR.create({outputs:HHM_SVC.outputs,
        actuatorOpenWaitMs:120000}),
    mixing:HHM_MIXER,mixerIntents:{
        drain:function(){var a=HHM_MIX_INTENTS;HHM_MIX_INTENTS=[];return a;}
    }
});
var HHM_ALLOWED={},HHM_WHITELIST=HHM_ENGINE.allowedTargets();
for(var HHM_A=0;HHM_A<HHM_WHITELIST.length;HHM_A++)
    HHM_ALLOWED[HHM_WHITELIST[HHM_A]]=true;
function hhBool(x){
    if(x===true||x===1||x==="1"||x==="true")return true;
    if(x===false||x===0||x==="0"||x==="false")return false;
    return null;
}
function hhNum(x){
    if(typeof x==="number"&&isFinite(x))return x;
    if(typeof x==="string"&&x.trim()!==""&&isFinite(Number(x)))
        return Number(x);
    return null;
}
function hhSec(ms){return ms===null||ms===undefined?"—":
    String(Math.ceil(ms/1000))+" с";}
function hhChanged(path,value){if(dev[path]!==value)dev[path]=value;}
// Machine-only bounded trace. Never affects heating if MQTT/serialization fails.
function hhTrace(event,context,detail,at){
    try{
        var item={schema:1,source:"29_hhm_iset",boot:HHM_BOOT,
            sequence:++HHM_TRACE_SEQ,
            timestamp_ms:at===undefined?Date.now():at,
            event:event,context:context,detail:detail};
        HHM_TRACE_RING.push(item);
        if(HHM_TRACE_RING.length>24)HHM_TRACE_RING.shift();
        hhChanged("iset_hhm/trace_seq",HHM_TRACE_SEQ);
        hhChanged("iset_hhm/trace_recent",JSON.stringify(HHM_TRACE_RING));
    }catch(ignore){}
}
// Observe numeric MQTT changes, never claim a physical measurement timestamp.
// Retained replay (including reconnect) and old APIs without retained metadata
// cannot prove a live update. Identical publications are not new measurements.
function hhObserveSensor(path,msg){
    try{
        if(!msg||msg.value===undefined||msg.value===null)return;
        var v=hhNum(msg.value),o=HHM_SENSOR_OBS[path];
        if(!o)o=HHM_SENSOR_OBS[path]={lastValue:null,lastChangeAt:null};
        if(v===null||msg.retained!==false){
            o.lastValue=v;o.lastChangeAt=null;return;
        }
        if(o.lastValue!==null&&o.lastValue!==v)
            o.lastChangeAt=Date.now();
        o.lastValue=v;
    }catch(ignore){}
}
function hhSensorPresencePath(path){
    var m=/^([^/]+)\/External Sensor ([12])$/.exec(path);
    return m?m[1]+"/ext_sens"+m[2]+"_presense":null;
}
// Observation only. Do not feed these classifications into physical interlocks.
function hhSensorMonitor(now){
    try{
        var problems=0,uncertain=0,items=[],i,s,v,presence,reported,
            o,status,bad,previous,proof;
        for(i=0;i<HHM_SENSOR_SPECS.length;i++){
            s=HHM_SENSOR_SPECS[i];
            v=hhNum(dev[s.path]);
            presence=hhBool(dev[hhSensorPresencePath(s.path)]);
            reported=hhBool(dev[s.path+" OK"]);
            o=HHM_SENSOR_OBS[s.path];
            proof=o&&o.lastChangeAt!==null&&
                now-o.lastChangeAt>=0&&now-o.lastChangeAt<300000;
            bad=v===null||presence===false||reported===false;
            if(bad){
                status=v===null?"Нет числового значения":
                    presence===false?"M1W2 сообщает отсутствие датчика":
                    "M1W2 сообщает ошибку датчика";
                problems++;
            }else if(!proof){
                status="Свежесть MQTT не подтверждена";
                uncertain++;
            }else status="Наблюдалось изменение MQTT (не возраст измерения)";
            items.push(s.title+": "+status);
            previous=HHM_SENSOR_LAST_FAULT[s.id];
            // Allow retained MQTT and Modbus devices to settle after
            // wb-rules restart; initial missing values are not a fault yet.
            if(now-HHM_SENSOR_START_AT<15000)continue;
            if(bad&&previous!==true){
                log.warning("[отопление][29_hhm_iset]["+s.title+
                    "]; ОШИБКА=Диагностика датчика; причина="+status);
                hhTrace("SENSOR_FAULT",s.id,
                    {channel:s.path,reason:status},now);
            }else if(!bad&&previous===true){
                log.info("[отопление][29_hhm_iset]["+s.title+
                    "]; СОСТОЯНИЕ=Показания датчика восстановились; "+
                    "свежесть MQTT="+(proof?"подтверждены изменения":"не доказана"));
                hhTrace("SENSOR_RECOVERED",s.id,
                    {channel:s.path,mqtt_change_observed:proof===true},now);
            }
            HHM_SENSOR_LAST_FAULT[s.id]=bad;
        }
        hhChanged("iset_hhm/sensor_issues",problems);
        hhChanged("iset_hhm/sensor_unverified",uncertain);
        hhChanged("iset_hhm/sensor_details",items.join("; "));
    }catch(e){
        // Never let diagnostics throw into the calculation/writer path.
    }
}
function hhHumanMode(id,code){
    var source={
        OT_LINK_INVALID:"Нет связи с котлом по OpenTherm",
        EQUIPMENT_PROTECTION:"Нагрев запрещён защитой оборудования",
        NO_DEMAND:"Нет запроса на нагрев",
        HEAT_REQUESTED:"Запрошен нагрев"
    },dhw={
        IDLE:"ГВС: ожидание",ACCELERATED:"ГВС: ускоренный нагрев",
        SUPPORT:"ГВС: совместный нагрев с отоплением",
        OVERRUN:"ГВС: выбег насоса",
        FAULT:"ГВС: авария",UNKNOWN:"ГВС: нет достоверных данных"
    },floor={
        OFF:"Тёплый пол отключён",
        HARD_SUPPLY_STOP:"Тёплый пол: останов К2 по пределу подачи",
        SUPPLY_SENSOR_UNAVAILABLE:"Тёплый пол: температура подачи недоступна",
        HOT_PORT_CLOSED_CIRCULATION_ALLOWED:
            "Тёплый пол: горячий порт закрыт, К2 может продолжать циркуляцию",
        CIRCULATING:"Тёплый пол: К2 включён по MQTT",
        WAIT_LOOPS:"Тёплый пол: ожидание открытия петель",
        WAIT_MAO4_PREFLIGHT:"Тёплый пол: проверка канала MAO4",
        WAIT_MAO4_STABLE:"Тёплый пол: ожидание подтверждения MAO4",
        READY:"Тёплый пол: готов к нагреву"
    };
    var table=id==="source_mode"?source:id==="dhw_mode"?dhw:floor;
    return table[code]||"Режим "+String(code);
}
function hhHumanReason(code){
    var reasons={
        OT_DISCONNECTED:"нет связи OpenTherm",
        EQUIPMENT_PROTECTION:"сработали условия защиты котла",
        TANK_NOT_READY:"температура бойлера недостоверна",
        DHW_TIMEOUT_LATCHED:"превышено время нагрева ГВС",
        TANK_THERMOSTAT:"управление по температуре бойлера",
        NO_DEMAND:"нет запроса тепла",SOURCE_REQUEST:"есть запрос тепла",
        SENSOR_UNKNOWN:"нет достоверных данных датчика",
        LOCAL_OFF:"локально отключено",FLOOR_MIXING:"регулирование ТП",
        ALL_ROOMS_OFF:"запросы комнат сняты",ROOM_HEAT_DEMAND:"комната запрашивает тепло",
        ROOM_NO_DEMAND:"нет запроса комнаты",
        REQUESTED_ZONE_OPEN_WAIT_COMPLETE:"выдержка открытия зоны завершена",
        INDEPENDENT_PLANT_PROTECTION:"источник недоступен или запрещён защитой",
        REQUESTED:"запрошен нагрев",NOT_REQUESTED:"нет запроса",
        DHW_PRIORITY:"приоритет ГВС",DHW_PRIORITY_PAUSE:"пауза по приоритету ГВС",
        NO_REQUEST:"нет запроса"
    };
    if(reasons[code])return reasons[code];
    var floor=hhHumanMode("floor_mode",code),dhw=hhHumanMode("dhw_mode",code);
    return floor.indexOf("Режим ")!==0?floor:
        dhw.indexOf("Режим ")!==0?dhw:String(code);
}
function hhHumanAction(code){
    var actions={PUMP_START:"Включить насос",PUMP_STOP:"Отключить насос",
        ZONE_OPEN:"Открыть NO-привод",ZONE_CLOSE:"Закрыть NO-привод",
        FLOOR_LOOP_OPEN:"Открыть петлю ТП",FLOOR_HOT_PORT_CLOSE:"Закрыть горячий порт ТП",
        FLOOR_VALVE_ENABLE:"Разрешить канал MAO4",FLOOR_VALVE_PREFLIGHT:"Проверка MAO4: 1%",
        FLOOR_PUMP_STOP_PROTECTION:"Отключить К2 по защите",
        FLOOR_PUMP_START:"Включить К2",FLOOR_PUMP_STOP_NO_DEMAND:"Отключить К2: нет запроса",
        MIX_ENABLE:"Переключить разрешение смесителя"};
    return actions[code]||String(code);
}
function hhOpTransition(id,context,state,reason){
    if(HHM_PREV[id]===state)return;
    var old=HHM_PREV[id];
    HHM_PREV[id]=state;
    hhTrace("MODE",context,{previous:old===undefined?null:old,
        state:state,reason:reason||null},Date.now());
    log.info("[отопление][29_hhm_iset]["+context+
        "]; СОСТОЯНИЕ="+hhHumanMode(id,state)+
        "; код="+state+"; ранее="+
        (old===undefined?"при запуске":hhHumanMode(id,old))+
        (reason?"; причина="+hhHumanReason(reason):""));
}
function hhControls(p){
    var o={},i;
    for(i=0;i<p.length;i++)o[p[i]]=dev[p[i]];
    return o;
}
function hhInput(){
    var channels=HHM_SVC.channels,outputs=HHM_SVC.outputs;
    var readPaths=HHM_WHITELIST.slice(0),o=hhControls(readPaths);
    var now=Date.now(),temperatures={},errors={};
    for(var i=0;i<HHM_ROOM_MAP.zones.length;i++){
        var z=HHM_ROOM_MAP.zones[i];
        temperatures[z.id]=dev[z.primarySensor];
        errors[z.id]=HHM_ERRORS[z.id]===true;
    }
    var tank=hhNum(dev[channels.dhwTank]);
    var boiler=hhNum(dev["wbe2-i-opentherm_11/Heating Temperature"]);
    var pressure=hhNum(dev["wbe2-i-opentherm_11/Water Pressure"]);
    var err=hhNum(dev["wbe2-i-opentherm_11/Error Code"]);
    var fault=hhBool(dev[channels.otBoilerFault]);
    var fire=hhBool(dev[channels.fire]);
    var link=hhBool(dev[channels.otConnectionInvalid]);
    // Existing HM2 equipment limits, not sensor freshness interlocks.
    // Fire is NC: IN1=0 means alarm (per existing 20_safety).
    var equipment=boiler!==null&&boiler<85&&
        pressure!==null&&pressure>=0.8&&fault===false&&
        err===0&&fire!==false;
    var basement=[];
    for(i=0;i<HHM_SVC.basement.sensors.length;i++)
        basement.push(hhNum(dev[HHM_SVC.basement.sensors[i]]));
    var fEnable=HHM_FLOOR_SETTINGS!==null&&
        HHM_FLOOR_SETTINGS.enabled===true;
    var floorTarget=HHM_FLOOR_SETTINGS===null?null:
        HHM_FLOOR_SETTINGS.targetC;
    return {nowMs:now,bootEpoch:HHM_BOOT,
        roomsFrame:{nowMs:now,bootEpoch:HHM_BOOT,
            temperatures:temperatures,sensorErrors:errors,
            outputReadbacks:o,protectionActive:false},
        plant:{outputs:o,otConnectionInvalid:link!==false,
            equipmentAllowsHeat:equipment,
            sourceAvailable:equipment&&link===false,
            offMethodCommissioned:true,
            flame:hhBool(dev["wbe2-i-opentherm_11/Boiler Flame Status"]),
            tankC:tank,commonC:hhNum(dev[channels.common]),
            outdoorC:hhNum(dev[channels.outdoor]),
            basementTemps:basement,
            floorSupplyC:hhNum(dev[channels.floorSupply])},
        floorControl:{enabled:fEnable,targetC:floorTarget===null?34:floorTarget,
            // The live HM2 requests floor setpoint + 8 C at startup.
            sourceRequestC:fEnable?Math.max(35,Math.min(60,floorTarget+8)):null}};
}
function hhWrite(cmd,at){
    if(!HHM_ALLOWED[cmd.path])
        throw new Error("Iset HHM output not in object whitelist: "+cmd.path);
    if(!HHM_PHYSICAL_OUTPUTS)return false;
    try{
        // Retry after 5s if the driver's readback remains unchanged.
        var prev=HHM_LAST_WRITE[cmd.path];
        var before=dev[cmd.path];
        // HHM3Mixing may request the SAME position every second while
        // holding a step. Accept already-confirmed MAO4 readback as a
        // successful idempotent no-op; do NOT write into /on or log.
        // If the readback differs or is invalid, retain retry/watchdog.
        if(cmd.action==="MIX_VALVE_POS"&&
           hhMatchesReadback(before,cmd.value))return true;
        // If a formerly unknown relay now reports an opposite state,
        // send STOP immediately. Retry throttling is only for identical,
        // unchanged readback conditions.
        if(prev&&prev.value===cmd.value&&at-prev.at<5000&&
           prev.observed===before)return true;
        dev[cmd.path]=cmd.value;
        HHM_LAST_WRITE[cmd.path]={
            value:cmd.value,at:at,observed:before,
            firstAt:prev&&prev.value===cmd.value?prev.firstAt:at,
            warned:prev&&prev.value===cmd.value&&prev.warned===true};
        // Normal MAO4 regulator steps and OT ramp are technical telemetry,
        // not operator events. Safety-related output commands still log.
        hhTrace("WRITE",cmd.path,{action:cmd.action,
            requested:cmd.value,readback_before:hhReadbackValue(before,cmd.value),
            reason:cmd.reason},at);
        if(cmd.action!=="MIX_VALVE_POS"&&cmd.action!=="OT_SETPOINT"&&
           (!prev||prev.value!==cmd.value))
            log.info("[отопление][29_hhm_iset]["+cmd.path+
                "]; КОМАНДА="+hhHumanAction(cmd.action)+"; значение="+cmd.value+
                "; причина="+hhHumanReason(cmd.reason));
        if(cmd.action==="OT_SETPOINT")
            HHM_COORDINATOR.acknowledgeOtWrite(at/1000,cmd.value);
        return true;
    }catch(e){
        log.warning("[отопление][29_hhm_iset]["+cmd.path+
            "]; ОШИБКА=Запись не принята; причина="+String(e));
        return false;
    }
}
// MQTT readback is not a flow/shaft sensor. Detect missing replies,
 // including the case where wb-mqtt-serial is active but ignoring /on.
function hhMatchesReadback(actual,wanted){
    if(typeof wanted==="boolean")return hhBool(actual)===wanted;
    var v=hhNum(actual);
    return v!==null&&Math.abs(v-wanted)<=0.5;
}
// Do not copy arbitrary MQTT payloads into the trace (size/privacy boundary).
function hhReadbackValue(actual,wanted){
    return typeof wanted==="boolean"?hhBool(actual):hhNum(actual);
}
function hhIOReadbackWatch(now){
    var pending=[],lost=[],path,record,elapsed,actual;
    for(path in HHM_LAST_WRITE){
        if(!HHM_LAST_WRITE.hasOwnProperty(path))continue;
        record=HHM_LAST_WRITE[path];
        actual=dev[path];
        if(hhMatchesReadback(actual,record.value)){
            if(record.warned)
                hhTrace("READBACK_RECOVERED",path,
                    {requested:record.value,actual:hhReadbackValue(actual,record.value)},now);
            if(record.warned)
                log.info("[отопление][29_hhm_iset]["+path+
                    "]; ВОССТАНОВЛЕНИЕ=MQTT readback совпал с командой");
            delete HHM_LAST_WRITE[path];
            continue;
        }
        elapsed=Math.max(0,now-record.firstAt);
        if(elapsed>=30000){
            lost.push(path+" ("+Math.floor(elapsed/1000)+" с)");
            if(!record.warned){
                record.warned=true;
                hhTrace("READBACK_TIMEOUT",path,
                    {requested:record.value,actual:hhReadbackValue(actual,record.value),
                    elapsed_ms:elapsed},now);
                log.warning("[отопление][29_hhm_iset]["+path+
                    "]; ОШИБКА=Нет подтверждения MQTT после команды "+
                    String(record.value)+" в течение 30 с; "+
                    "проверить wb-mqtt-serial и Modbus");
            }
        }else pending.push(path+" ("+Math.floor(elapsed/1000)+" с)");
    }
    hhChanged("iset_hhm/io_state",lost.length?"NO_READBACK":
        pending.length?"WAIT_READBACK":"READBACK_OK");
    hhChanged("iset_hhm/io_unconfirmed",lost.length);
    hhChanged("iset_hhm/io_waiting",pending.length);
    hhChanged("iset_hhm/io_details",lost.length?
        lost.join("; "):pending.length?pending.join("; "):
        "Все отправленные команды подтверждены каналами MQTT");
}
function hhRoomView(report){
    for(var i=0;i<HHM_ROOM_MAP.zones.length;i++){
        var z=HHM_ROOM_MAP.zones[i],name="iset_hhm_"+z.id;
        var state=report.rooms.roomStates[z.id],zplan=report.living.zones[z.id];
        hhChanged(name+"/state",state.state);
        hhChanged(name+"/demand",state.heatDemand===true?"HEAT":
            state.heatDemand===false?"OFF":"UNKNOWN");
        hhChanged(name+"/temp",state.measuredC===null?"—":
            String(state.measuredC));
        var settings=HHM_ROOM.settings(z.id);
        hhChanged(name+"/saved",settings?settings.mode+" / "+
            settings.setpointC+"°C":"Уставка не задана");
        hhChanged(name+"/wait",zplan.openRemainingMs===null?
            "Нет данных OPEN":hhSec(zplan.openRemainingMs));
        for(var j=0;j<zplan.actuators.length;j++){
            var a=zplan.actuators[j],k=a.path.split("/")[1].toLowerCase();
            hhChanged(name+"/servo_"+k,
                a.openingRemainingMs===null?a.state:
                    hhSec(a.openingRemainingMs));
        }
    }
}
function hhPumpView(report,path,vd){
    var t=report.pumpTimers[path];
    hhChanged(vd+"/relay",t.readback===true?"ON":
        t.readback===false?"OFF":"UNKNOWN");
    hhChanged(vd+"/run_timer",hhSec(t.observedRunMs));
    hhChanged(vd+"/stop_timer",hhSec(t.stopWaitMs));
    var start="По запросу";
    if(vd==="iset_hhm_k2"){
        start=t.readback===true?"Работает":
            !report.floor.allLoopsReady?
            (report.floor.remainingOpenMs===null?
                "Ожидание открытия NO":hhSec(report.floor.remainingOpenMs)):
            report.floor.valvePreflightRemainingMs===null?
                "Ожидание MAO4":hhSec(report.floor.valvePreflightRemainingMs);
    }else if(vd==="iset_hhm_k4")
        start=report.living.pumpStartRemainingMs===null?
            "Ожидание открытия NO":hhSec(report.living.pumpStartRemainingMs);
    hhChanged(vd+"/start_timer",start);
}
function hhTick(){
    if(HHM_BUSY)return;
    HHM_BUSY=true;
    try{
        var now=Date.now(),report=HHM_ENGINE.step(hhInput());
        hhSensorMonitor(now); // read-only diagnostics, isolated from control
        hhChanged("iset_hhm/status",
            HHM_PHYSICAL_OUTPUTS?"РАБОЧИЙ HHM":"РАСЧЁТ, КОМАНД НЕТ");
        hhChanged("iset_hhm/source",report.services.source.state+
            " / "+report.services.source.targetC+"°C");
        hhChanged("iset_hhm/dhw",report.services.dhw.mode+
            " / приоритет "+hhSec(report.services.dhw.priorityRemainingS===null?
                null:report.services.dhw.priorityRemainingS*1000));
        hhChanged("iset_hhm_dhw/mode",report.services.dhw.mode);
        hhOpTransition("dhw_mode","ГВС",report.services.dhw.mode,
            report.services.dhw.reason);
        hhOpTransition("source_mode","котёл",report.services.source.state,
            report.services.source.reason);
        hhOpTransition("floor_mode","ТП",report.floor.state,
            report.floor.state);
        hhChanged("iset_hhm_dhw/priority_timer",
            hhSec(report.services.dhw.priorityRemainingS===null?
                null:report.services.dhw.priorityRemainingS*1000));
        hhChanged("iset_hhm_dhw/overrun_timer",
            hhSec(report.services.dhw.overrunRemainingS===null?
                null:report.services.dhw.overrunRemainingS*1000));
        hhChanged("iset_hhm_dhw/tank",report.services.dhw.state+
            " / "+String(report.services.dhw.heatingElapsedS)+" с");
        hhChanged("iset_hhm_basement/target_saved",
            String(HHM_SVC.basement.targetC)+" °C");
        hhChanged("iset_hhm_basement/demand",
            String(report.services.requests.basementHeatDemand));
        hhChanged("iset_hhm/k4_start_timer",
            hhSec(report.living.pumpStartRemainingMs));
        hhChanged("iset_hhm/floor_timer",
            hhSec(report.floor.remainingOpenMs));
        hhChanged("iset_hhm/floor_state",report.floor.state);
        hhChanged("iset_hhm_floor/state",report.floor.state);
        hhChanged("iset_hhm_floor/preflight_timer",
            hhSec(report.floor.valvePreflightRemainingMs));
        hhChanged("iset_hhm/actions",report.commands.length?
            report.commands.map(function(x){return x.action+" "+x.path;})
                .join(", "):"Нет");
        hhRoomView(report);
        hhPumpView(report,HHM_SVC.outputs.dhwPump,"iset_hhm_k1");
        hhPumpView(report,HHM_SVC.outputs.floorPump,"iset_hhm_k2");
        hhPumpView(report,HHM_SVC.outputs.basementPump,"iset_hhm_k3");
        hhPumpView(report,HHM_SVC.outputs.livingPump,"iset_hhm_k4");
        for(var f=0;f<report.floor.loops.length;f++){
            var fl=report.floor.loops[f];
            var v="iset_hhm_floor/"+fl.path.split("/")[1].toLowerCase()+"_timer";
            hhChanged(v,hhSec(fl.remainingMs));
        }
        if(!HHM_PHYSICAL_OUTPUTS){
            hhChanged("iset_hhm/io_state","PREVIEW");
            return;
        }
        for(var c=0;c<report.commands.length;c++)
            hhWrite(report.commands[c],now);
        hhIOReadbackWatch(now);
    }catch(e){
        log.error("[отопление][29_hhm_iset][система]; АВАРИЯ=Ошибка расчёта; причина="+String(e));
    }finally{HHM_BUSY=false;}
}
for(var HHM_Z=0;HHM_Z<HHM_ROOM_MAP.zones.length;HHM_Z++){
    (function(z){
        var n="iset_hhm_"+z.id;
        var st=HHM_ROOM.settings(z.id);
        var cells={
            state:{type:"text",value:"START",readonly:true,title:"Состояние"},
            demand:{type:"text",value:"UNKNOWN",readonly:true,title:"Запрос тепла"},
            temp:{type:"text",value:"—",readonly:true,title:"Температура"},
            saved:{type:"text",value:"—",readonly:true,title:"Уставка сохранена"},
            setpoint_input:{type:"value",readonly:false,value:st?st.setpointC:0,
                title:"Уставка, °C"},
            heating_mode:{type:"switch",value:st?st.mode==="HEAT":true,
                title:"Отопление включено"},
            apply:{type:"pushbutton",title:"Применить уставку"},
            wait:{type:"text",value:"—",readonly:true,
                title:"Открытие всей зоны"}
        };
        for(var k=0;k<z.outputs.length;k++){
            var kname=z.outputs[k].split("/")[1].toLowerCase();
            cells["servo_"+kname]={type:"text",value:"—",
                readonly:true,title:"Привод "+kname+" — таймер"};
        }
        defineVirtualDevice(n,{title:"HHM Исеть / "+z.title,cells:cells});
        defineRule("iset_hhm_apply_"+z.id,{
            whenChanged:n+"/apply",then:function(){
                var target=hhNum(dev[n+"/setpoint_input"]);
                var mode=hhBool(dev[n+"/heating_mode"])===true?
                    "HEAT":"OFF";
                var existing=HHM_ROOM.settings(z.id),result;
                if(!existing)
                    result=HHM_ROOM.provisionApproved(z.id,mode,target);
                else result=HHM_ROOM.applySettings(z.id,{
                    expectedRevision:existing.revision,
                    mode:mode,setpointC:target});
                if(result.accepted)
                    log.info("[отопление][29_hhm_iset]["+z.title+
                        "]; НАСТРОЙКА=Сохранена; температура="+target+
                        "; режим="+mode);
                else log.warning("[отопление][29_hhm_iset]["+z.title+
                    "]; ОШИБКА=Уставка не сохранена; причина="+result.reason);
                hhTick();
            }
        });
    })(HHM_ROOM_MAP.zones[HHM_Z]);
}
function hhPumpVD(path,name,title){
    defineVirtualDevice(name,{title:title,cells:{
        relay:{type:"text",value:"UNKNOWN",readonly:true,title:"Реле"},
        run_timer:{type:"text",value:"—",readonly:true,title:"Работает, с"},
        stop_timer:{type:"text",value:"—",readonly:true,
            title:"Ожидание OFF, с"},
        start_timer:{type:"text",value:"—",readonly:true,
            title:"До разрешения пуска"}
    }});
}
hhPumpVD(HHM_SVC.outputs.dhwPump,"iset_hhm_k1","HHM ГВС / K1");
hhPumpVD(HHM_SVC.outputs.floorPump,"iset_hhm_k2","HHM ТП / K2");
hhPumpVD(HHM_SVC.outputs.basementPump,"iset_hhm_k3","HHM Цоколь / K3");
hhPumpVD(HHM_SVC.outputs.livingPump,"iset_hhm_k4","HHM Жилые / K4");
defineVirtualDevice("iset_hhm_dhw",{title:"HHM Исеть / Бойлер ГВС",
    cells:{
        mode:{type:"text",value:"IDLE",readonly:true,title:"Режим"},
        tank:{type:"text",value:"—",readonly:true,title:"Состояние / нагрев"},
        priority_timer:{type:"text",value:"—",readonly:true,
            title:"Приоритет — осталось"},
        overrun_timer:{type:"text",value:"—",readonly:true,
            title:"Выбег K1 — осталось"},
        boost:{type:"pushbutton",title:"Ускорить нагрев ГВС"},
        reset_fault:{type:"pushbutton",title:"Сброс ошибки ГВС"}
    }});
defineRule("iset_hhm_dhw_boost",{whenChanged:"iset_hhm_dhw/boost",
    then:function(){
        HHM_COORDINATOR.boostDhw();
        log.info("[отопление][29_hhm_iset][ГВС]; КОМАНДА=Ускоренный нагрев");
        hhTick();
    }});
defineRule("iset_hhm_dhw_reset",{whenChanged:"iset_hhm_dhw/reset_fault",
    then:function(){
        var tank=hhNum(dev[HHM_SVC.channels.dhwTank]);
        if(tank===null||tank>=85||
            hhBool(dev[HHM_SVC.outputs.dhwPump])!==false){
            log.warning("[отопление][29_hhm_iset][ГВС]; ОШИБКА=Сброс не разрешён: K1 не OFF или бойлер не проверен");
            return;
        }
        HHM_COORDINATOR.resetDhwFault();
        log.info("[отопление][29_hhm_iset][ГВС]; КОМАНДА=Сброс ошибки");
        hhTick();
    }});
defineVirtualDevice("iset_hhm_basement",{title:"HHM Исеть / Цоколь",
    cells:{
        target_saved:{type:"text",value:String(HHM_SVC.basement.targetC)+" °C",
            readonly:true,title:"Сохранённая уставка"},
        target_input:{type:"value",readonly:false,value:HHM_SVC.basement.targetC,
            title:"Новая уставка, °C"},
        save:{type:"pushbutton",title:"Сохранить уставку"},
        demand:{type:"text",value:"—",readonly:true,title:"Запрос тепла"}
    }});
defineRule("iset_hhm_basement_save",{whenChanged:"iset_hhm_basement/save",
    then:function(){
        var n=hhNum(dev["iset_hhm_basement/target_input"]);
        if(n===null||n<10||n>30){
            log.warning("[отопление][29_hhm_iset][цоколь]; ОШИБКА=Уставка вне 10..30 °C");
            return;
        }
        var raw=String(n);
        try{
            HHM_PERSIST.iset_hhm_basement_target_v1=raw;
            if(HHM_PERSIST.iset_hhm_basement_target_v1!==raw)
                throw new Error("PersistentStorage readback");
            HHM_SVC.basement.targetC=n;
            log.info("[отопление][29_hhm_iset][цоколь]; НАСТРОЙКА=Уставка; значение="+raw);
            hhTick();
        }catch(e){log.warning("[отопление][29_hhm_iset][цоколь]; ОШИБКА=Запись уставки");}
    }});
var HHM_FLOOR_CELLS={
    enable:{type:"switch",value:HHM_FLOOR_SETTINGS!==null&&
        HHM_FLOOR_SETTINGS.enabled===true,title:"ТП: локально включить"},
    target:{type:"value",readonly:false,value:HHM_FLOOR_SETTINGS===null?
        34:HHM_FLOOR_SETTINGS.targetC,title:"ТП: целевая подача, °C"},
    save:{type:"pushbutton",title:"Сохранить настройки ТП"},
    state:{type:"text",value:"OFF",readonly:true,title:"Состояние"},
    timer:{type:"text",value:"—",readonly:true,title:"Все петли"},
    preflight_timer:{type:"text",value:"—",readonly:true,
        title:"MAO4 1%: подтверждение 10 с"},
};
for(var HHM_F=0;HHM_F<HHM_SVC.outputs.floorLoops.length;HHM_F++){
    var label=HHM_SVC.outputs.floorLoops[HHM_F].split("/")[1].toLowerCase();
    HHM_FLOOR_CELLS[label+"_timer"]={type:"text",value:"—",
        readonly:true,title:"Привод "+label+" — таймер"};
}
defineVirtualDevice("iset_hhm_floor",{title:"HHM Исеть / Тёплый пол",
    cells:HHM_FLOOR_CELLS});
defineVirtualDevice("iset_hhm",{title:"HHM Исеть / Общее",cells:{
    status:{type:"text",value:"START",readonly:true,title:"Режим"},
    source:{type:"text",value:"—",readonly:true,title:"Котёл"},
    dhw:{type:"text",value:"—",readonly:true,title:"ГВС / приоритет"},
    k4_start_timer:{type:"text",value:"—",readonly:true,
        title:"K4: осталось до пуска"},
    floor_timer:{type:"text",value:"—",readonly:true,
        title:"ТП: открытие приводов"},
    floor_state:{type:"text",value:"OFF",readonly:true,title:"ТП"},
    actions:{type:"text",value:"—",readonly:true,title:"Расчёт команд"},
    io_state:{type:"text",value:"START",readonly:true,
        title:"Контроль MQTT-команд"},
    io_unconfirmed:{type:"value",value:0,readonly:true,
        title:"Нет подтверждения более 30 с"},
    io_waiting:{type:"value",value:0,readonly:true,
        title:"Ожидают подтверждения менее 30 с"},
    io_details:{type:"text",value:"—",readonly:true,
        title:"Каналы без подтверждения MQTT"},
    sensor_issues:{type:"value",value:0,readonly:true,
        title:"M1W2: ошибка/нет числового значения"},
    sensor_unverified:{type:"value",value:6,readonly:true,
        title:"M1W2: свежесть MQTT не подтверждена"},
    sensor_details:{type:"text",value:"—",readonly:true,
        title:"Диагностика шести температур M1W2"},
    trace_seq:{type:"value",value:0,readonly:true,
        title:"Машинная трасса: номер события"},
    trace_recent:{type:"text",value:"[]",readonly:true,
        title:"Машинная трасса (JSON, последние 24 события)"}
}});
defineRule("iset_hhm_floor_save",{
    whenChanged:"iset_hhm_floor/save",then:function(){
        var t=hhNum(dev["iset_hhm_floor/target"]);
        var enabled=hhBool(dev["iset_hhm_floor/enable"])===true;
        if(t===null||t<20||t>40){
            log.warning("[отопление][29_hhm_iset][ТП]; ОШИБКА=Недопустимая уставка");
            return;
        }
        var next={version:1,enabled:enabled,targetC:t};
        try{
            var raw=JSON.stringify(next);
            HHM_PERSIST.iset_hhm_floor_cfg_v1=raw;
            if(HHM_PERSIST.iset_hhm_floor_cfg_v1!==raw)
                throw new Error("PersistentStorage readback");
            HHM_FLOOR_SETTINGS=next;
            log.info("[отопление][29_hhm_iset][ТП]; НАСТРОЙКА=Сохранена; режим="+
                enabled+"; уставка="+t);
            hhTick();
        }catch(e){
            log.warning("[отопление][29_hhm_iset][ТП]; ОШИБКА=Уставка не сохранена");
        }
    }
});
for(var HHM_SI=0;HHM_SI<HHM_SENSOR_SPECS.length;HHM_SI++){
    (function(sensor){
        trackMqtt("/devices/"+sensor.path.replace("/","/controls/"),
            function(message){hhObserveSensor(sensor.path,message);});
    })(HHM_SENSOR_SPECS[HHM_SI]);
}
for(HHM_Z=0;HHM_Z<HHM_ROOM_MAP.zones.length;HHM_Z++){
    (function(z){
        var topic="/devices/"+z.primarySensor.split("/")[0]+"/meta/error";
        trackMqtt(topic,function(msg){
            var v=msg&&msg.value;
            HHM_ERRORS[z.id]=!(v===null||v===undefined||v===""||
                v===0||v===false||v==="0"||v==="false");
        });
    })(HHM_ROOM_MAP.zones[HHM_Z]);
}
hhTick();
setInterval(hhTick,1000); // visible timers; log commands only when attempted
