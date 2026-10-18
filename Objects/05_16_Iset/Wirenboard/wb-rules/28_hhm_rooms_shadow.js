/* 05 16 Iset: HHM simple room thermostats — read-only shadow panel.
 * Eight WB-MSW temperatures and their explicit device error events.
 * Writes ONLY local shadow virtual devices. NEVER writes K1..K11 or K4.
 * Requires staged modules in /etc/wb-rules-modules; NOT deployed.
 */
var IS_SIMPLE=require("IsetRoomSimpleThermostat");
var IS_STORE=require("IsetRoomSettingsStore");
var IS_RUNTIME=require("IsetRoomLocalRuntime");
var IS_MAP=require("IsetRoomZones");
var IS_GATE=require("HHMRoomPathGate");
var IS_PLAN=require("IsetRoomOutputPlanner");
var IS_STORAGE=new PersistentStorage("iset_hhm_rooms_v1",{global:true});
var IS_ROOM_ERROR={},IS_TEMPS={},IS_LAST={};
var IS_MIN_SETPOINT=16,IS_MAX_SETPOINT=30,IS_HYSTERESIS=0.6;
var IS_MIN_TEMP=-20,IS_MAX_TEMP=60;
var IS_BOOT="iset-shadow-"+String(Date.now());
var IS_RUN=IS_RUNTIME.create({map:IS_MAP,Simple:IS_SIMPLE,
    Settings:IS_STORE,PathGate:IS_GATE,storage:IS_STORAGE,
    minSetpointC:IS_MIN_SETPOINT,maxSetpointC:IS_MAX_SETPOINT,
    hysteresisC:IS_HYSTERESIS,minMeasuredC:IS_MIN_TEMP,
    maxMeasuredC:IS_MAX_TEMP});
var IS_PLANNER=IS_PLAN.create({map:IS_MAP,
    openWaitMs:IS_MAP.actuators.nominalOpenWaitMs});
function isVDset(path,value){if(dev[path]!==value)dev[path]=value;}
function isError(value){
    if(value===true)return true;
    if(value===false||value===0)return false;
    var x=value===undefined||value===null?"":String(value);
    return x!==""&&x!=="0"&&x!=="false";
}
function isPath(z){return "iset_hhm_"+z.id+"_shadow";}
function isSeconds(ms){return String(Math.ceil(ms/1000))+" с";}
function isElapsed(ms){return ms===null?"—":String(Math.floor(ms/1000))+" с";}
function isServoTimer(a,demand){
    if(demand!==true)return demand===false?"Не требуется":"Запрос неизвестен";
    if(a.openingRemainingMs!==null)
        return a.openingRemainingMs>0?isSeconds(a.openingRemainingMs):"Готово";
    return a.state==="WAIT_OPEN"?"Ожидание OPEN":"Нет данных выхода";
}
function isPumpStartTimer(plan){
    if(plan.pumpReadback===true)return "K4 уже работает";
    if(plan.pumpAction==="START")return "Готов к пуску";
    if(plan.pumpReadback===null)return "Нет readback K4";
    if(plan.pumpStartRemainingMs!==null)
        return isSeconds(plan.pumpStartRemainingMs);
    return plan.requestingZones>0?"Ожидание открытия NO":"Нет запроса";
}
function isRead(){
    var result={nowMs:Date.now(),bootEpoch:IS_BOOT,
        temperatures:{},sensorErrors:{},outputReadbacks:{},
        protectionActive:false};
    for(var i=0;i<IS_MAP.zones.length;i++){
        var z=IS_MAP.zones[i];
        var raw=dev[z.primarySensor];
        if(raw!==undefined&&raw!==null)IS_TEMPS[z.id]=raw;
        result.temperatures[z.id]=IS_TEMPS[z.id];
        result.sensorErrors[z.id]=IS_ROOM_ERROR[z.id]===true;
    }
    // No actual NO readback or proof of physical opening in shadow.
    // Pump START permission therefore remains unqualified.
    return result;
}
function isUpdate(){
    var input=isRead(),state=IS_RUN.step(input),rb={},i,j,z;
    for(i=0;i<IS_MAP.zones.length;i++){
        z=IS_MAP.zones[i];
        for(j=0;j<z.outputs.length;j++)rb[z.outputs[j]]=dev[z.outputs[j]];
    }
    rb[IS_MAP.pump]=dev[IS_MAP.pump];
    var plan=IS_PLANNER.plan({nowMs:input.nowMs,
        bootEpoch:input.bootEpoch,demands:state.demands,
        readbacks:rb,protectionActive:false});
    // Only a plan: never call writer.apply() or assign physical channels.
    isVDset("iset_hhm_rooms_shadow/pump_action",plan.pumpAction);
    isVDset("iset_hhm_rooms_shadow/pump_status",plan.pumpStatus);
    isVDset("iset_hhm_rooms_shadow/pump_readback",
        plan.pumpReadback===true?"ВКЛ":
        plan.pumpReadback===false?"ВЫКЛ":"Нет данных");
    isVDset("iset_hhm_rooms_shadow/pump_start_timer",
        isPumpStartTimer(plan));
    isVDset("iset_hhm_rooms_shadow/pump_run_timer",
        isElapsed(plan.pumpRunObservedMs));
    isVDset("iset_hhm_rooms_shadow/pump_stop_timer",
        isElapsed(plan.pumpStopPendingMs));
    isVDset("iset_hhm_rooms_shadow/ready_rooms",plan.readyZones);
    isVDset("iset_hhm_rooms_shadow/proposed_actions",
        plan.actions.length?plan.actions.map(function(a){
            return a.action+" "+a.path;}).join(", "):"Нет");
    for(var i=0;i<IS_MAP.zones.length;i++){
        var z=IS_MAP.zones[i],p=isPath(z);
        var room=state.roomStates[z.id];
        var demand=room.heatDemand===true?"ON":
            room.heatDemand===false?"OFF":"UNKNOWN";
        var last=IS_LAST[z.id],zp=plan.zones[z.id],ai;
        isVDset(p+"/state",room.state);
        isVDset(p+"/opening_timer",room.heatDemand!==true?
            (room.heatDemand===false?"Не требуется":"Запрос неизвестен"):
            zp.waitingForReadback?"Ожидание readback NO":
            isSeconds(zp.openRemainingMs));
        for(ai=0;ai<zp.actuators.length;ai++){
            var sa=zp.actuators[ai];
            var n=sa.path.split("/")[1].toLowerCase();
            isVDset(p+"/servo_"+n+"_timer",
                isServoTimer(sa,room.heatDemand));
        }
        isVDset(p+"/demand",demand);
        isVDset(p+"/temperature",room.measuredC===null?"—":
            String(room.measuredC));
        var settings=IS_RUN.settings(z.id);
        isVDset(p+"/settings",settings?
            (settings.mode+" / "+settings.setpointC+" °C"):
            "NOT_COMMISSIONED");
        if(last!==room.state+"/"+demand){
            IS_LAST[z.id]=room.state+"/"+demand;
            log.info("[отопление][28_hhm_rooms_shadow]["+z.title+
                "]; СОСТОЯНИЕ="+room.state+"; запрос="+demand+
                "; запись_выходов=ЗАПРЕЩЕНА");
        }
    }
    isVDset("iset_hhm_rooms_shadow/status","SHADOW_ONLY");
}
for(var IS_I=0;IS_I<IS_MAP.zones.length;IS_I++){
    (function(z){
        var d=isPath(z);
        var cells={
            state:{title:"Состояние",type:"text",value:"NOT_COMMISSIONED",
                readonly:true,order:1},
            demand:{title:"Запрос тепла",type:"text",value:"UNKNOWN",
                readonly:true,order:2},
            temperature:{title:"Воздух",type:"text",value:"—",
                readonly:true,order:3},
            settings:{title:"Режим / уставка",type:"text",
                value:"NOT_COMMISSIONED",readonly:true,order:4},
            opening_timer:{title:"Ожидание открытия зоны",type:"text",
                value:"Запрос неизвестен",readonly:true,order:5}
        };
        for(var k=0;k<z.outputs.length;k++){
            var label=z.outputs[k].split("/")[1];
            cells["servo_"+label.toLowerCase()+"_timer"]={
                title:"Сервопривод "+label+" — таймер",type:"text",
                value:"Запрос неизвестен",readonly:true,order:6+k};
        }
        defineVirtualDevice(d,{title:"HHM Исеть / "+z.title+" (теневой)",
            cells:cells});
    })(IS_MAP.zones[IS_I]);
}
defineVirtualDevice("iset_hhm_rooms_shadow",{title:"HHM Исеть (теневой)",
    cells:{status:{title:"Состояние",type:"text",value:"SHADOW_ONLY",
        readonly:true,order:1},
        pump_action:{title:"K4: расчёт",type:"text",value:"HOLD",
            readonly:true,order:2},
        pump_status:{title:"K4: причина/состояние",type:"text",
            value:"READBACK_UNKNOWN",readonly:true,order:3},
        pump_readback:{title:"K4: реле",type:"text",
            value:"Нет данных",readonly:true,order:4},
        pump_start_timer:{title:"K4: до возможного пуска",type:"text",
            value:"Нет запроса",readonly:true,order:5},
        pump_run_timer:{title:"K4: наблюдаемая работа",type:"text",
            value:"—",readonly:true,order:6},
        pump_stop_timer:{title:"K4: ожидание подтверждения STOP",type:"text",
            value:"—",readonly:true,order:7},
        ready_rooms:{title:"Готово комнат",type:"value",value:0,
            readonly:true,order:8},
        proposed_actions:{title:"Предполагаемые команды",type:"text",
            value:"Нет",readonly:true,order:9}}});
// Subscribe after defining ALL shadow devices: early retained error events
// must never reference an unregistered virtual control.
for(IS_I=0;IS_I<IS_MAP.zones.length;IS_I++){
    (function(z){
        var topic="/devices/"+z.primarySensor.split("/")[0]+"/meta/error";
        trackMqtt(topic,function(m){
            IS_ROOM_ERROR[z.id]=isError(m&&m.value);
            isUpdate();
        });
    })(IS_MAP.zones[IS_I]);
}
var IS_TOPICS=[];
for(IS_I=0;IS_I<IS_MAP.zones.length;IS_I++){
    IS_TOPICS.push(IS_MAP.zones[IS_I].primarySensor);
    for(var IS_J=0;IS_J<IS_MAP.zones[IS_I].outputs.length;IS_J++)
        IS_TOPICS.push(IS_MAP.zones[IS_I].outputs[IS_J]);
}
IS_TOPICS.push(IS_MAP.pump);
defineRule("iset_hhm_room_shadow_temps",{
    whenChanged:IS_TOPICS,
    then:function(){isUpdate();}
});
isUpdate();
setInterval(isUpdate,1000); // update countdowns; no log/write per tick
