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
function isError(value){
    if(value===true)return true;
    if(value===false||value===0)return false;
    var x=value===undefined||value===null?"":String(value);
    return x!==""&&x!=="0"&&x!=="false";
}
function isPath(z){return "iset_hhm_"+z.id+"_shadow";}
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
    var state=IS_RUN.step(isRead());
    for(var i=0;i<IS_MAP.zones.length;i++){
        var z=IS_MAP.zones[i],p=isPath(z);
        var room=state.roomStates[z.id];
        var demand=room.heatDemand===true?"ON":
            room.heatDemand===false?"OFF":"UNKNOWN";
        var last=IS_LAST[z.id];
        dev[p+"/state"]=room.state;
        dev[p+"/demand"]=demand;
        dev[p+"/temperature"]=room.measuredC===null?"—":
            String(room.measuredC);
        var settings=IS_RUN.settings(z.id);
        dev[p+"/settings"]=settings?
            (settings.mode+" / "+settings.setpointC+" °C"):
            "NOT_COMMISSIONED";
        if(last!==room.state+"/"+demand){
            IS_LAST[z.id]=room.state+"/"+demand;
            log.info("[отопление][28_hhm_rooms_shadow]["+z.title+
                "]; СОСТОЯНИЕ="+room.state+"; запрос="+demand+
                "; запись_выходов=ЗАПРЕЩЕНА");
        }
    }
    dev["iset_hhm_rooms_shadow/status"]="SHADOW_ONLY";
}
for(var IS_I=0;IS_I<IS_MAP.zones.length;IS_I++){
    (function(z){
        var d=isPath(z);
        defineVirtualDevice(d,{title:"HHM Исеть / "+z.title+" (теневой)",
            cells:{
                state:{title:"Состояние",type:"text",value:"NOT_COMMISSIONED",
                    readonly:true,order:1},
                demand:{title:"Запрос тепла",type:"text",value:"UNKNOWN",
                    readonly:true,order:2},
                temperature:{title:"Воздух",type:"text",value:"—",
                    readonly:true,order:3},
                settings:{title:"Режим / уставка",type:"text",
                    value:"NOT_COMMISSIONED",readonly:true,order:4}
            }});
    })(IS_MAP.zones[IS_I]);
}
defineVirtualDevice("iset_hhm_rooms_shadow",{title:"HHM Исеть (теневой)",
    cells:{status:{title:"Состояние",type:"text",value:"SHADOW_ONLY",
        readonly:true}}});
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
for(IS_I=0;IS_I<IS_MAP.zones.length;IS_I++)
    IS_TOPICS.push(IS_MAP.zones[IS_I].primarySensor);
defineRule("iset_hhm_room_shadow_temps",{
    whenChanged:IS_TOPICS,
    then:function(){isUpdate();}
});
isUpdate();
