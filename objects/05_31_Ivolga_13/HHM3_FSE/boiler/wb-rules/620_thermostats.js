/* HHM 3.0 FSE / Иволга: единственный writer зональных A08/A09/A13/A14.
 * 505 — только термостат, его насос принадлежит manager, задержки приводов нет.
 */
var Config=require('HHM3Config'),C=Config.config,W=require('HHM3Wire'),R=require('HHM3Runtime');
var operation=new PersistentStorage('hhm3_operation',{global:true});
var settings=new PersistentStorage('hhm3_thermostats',{global:true});
var session=W.nextSession(new PersistentStorage('hhm3_house_sender',{global:true})),seq=0;
var allowed=[],memory={},opened={},lastNow=null;
Config.zones.forEach(function(z){allowed=allowed.concat(z.outputs);});
var io=R.io({dev:dev,now:Date.now,trackMqtt:trackMqtt,publish:publish,log:log},'620',allowed);
function sc(id,k,v){dev['NL_simple_thermostat_'+id+'/'+k]=v;}
Config.zones.forEach(function(z){
    var saved=settings[z.id],state=saved&&saved.state===1?1:0,target=saved?W.number(saved.target):z.target;
    if(target===null)target=z.target;
    defineVirtualDevice('NL_simple_thermostat_'+z.id,{title:z.title,cells:{
        temperature:{title:'Температура, °C (см. достоверность)',type:'temperature',value:0,readonly:true,forceDefault:true},
        target_temperature:{title:'Уставка, °C',type:'range',value:target,min:z.min,max:z.max,forceDefault:false},
        target_state:{title:'Включено',type:'switch',value:state===1,forceDefault:false},
        current_state:{title:'Запрос тепла',type:'value',value:0,readonly:true,forceDefault:true},
        valid:{title:'Свежий датчик',type:'switch',value:false,readonly:true,forceDefault:true},
        status:{title:'Состояние',type:'text',value:'STARTUP',readonly:true,forceDefault:true},
        output_json:{title:'Команды и MQTT readback (не положение привода)',type:'text',value:'[]',readonly:true,forceDefault:true}
    }});
    memory[z.id]=false;
    io.watch(z.sensor,-20,z.kind==='floor'?70:60);
});
function stateValue(v){if(v===true||v===1||v==='1')return 1;if(v===false||v===0||v==='0')return 0;return null;}
function evaluate(){
    io.begin();
    var now=Date.now(),groups={};
    if(lastNow!==null&&(now<lastNow||now-lastNow>C.periodMs*3))opened={};
    lastNow=now;
    ['501','502','503','505'].forEach(function(id){groups[id]={valid:true,demand:false,ready:false,enabled:false,degraded:false,reason:'OFF',floor:null};});
    Config.zones.forEach(function(z){
        var base='NL_simple_thermostat_'+z.id+'/',enabled=stateValue(dev[base+'target_state']);
        var target=W.number(dev[base+'target_temperature']),t=io.read(z.sensor);
        if(enabled!==null&&target!==null&&target>=z.min&&target<=z.max)settings[z.id]={state:enabled,target:target};
        var valid=t!==null,on=false,reason='OFF',g=groups[z.circuit],error=false;
        if(t!==null){sc(z.id,'temperature',t);if(z.kind==='floor')g.floor=g.floor===null?t:Math.max(g.floor,t);}
        if(enabled!==0){
            g.enabled=true;
            if(enabled===null||target===null||target<z.min||target>z.max){reason='SETTINGS_INVALID';valid=false;}
            else if(t===null){
                // A floor without its limiting sensor cannot be silently heated.
                // Air-only radiators retain bounded water demand; warning is explicit.
                on=z.kind==='air';reason=on?'SENSOR_FALLBACK':'FLOOR_SENSOR_UNAVAILABLE';valid=false;
            } else if(z.hardMax>0&&t>=z.hardMax){reason='FLOOR_HARD_MAX';memory[z.id]=false;}
            else{
                if(t<=target-z.hysteresis)memory[z.id]=true;
                if(t>=target)memory[z.id]=false;
                on=memory[z.id];reason=on?'HEAT':'NO_DEMAND';
            }
        }else memory[z.id]=false;
        if(!io.compatible()){on=false;valid=false;reason='RUNTIME_UNSUPPORTED';memory[z.id]=false;}
        if(!valid&&enabled!==0){g.degraded=true;g.reason=reason;}
        var sent=true;
        if(operation.inService===true)z.outputs.forEach(function(p){var w=io.write(p,on);error=error||!w.ok;sent=w.ok&&io.matches(p,on)&&sent;});
        if(!sent){reason=error?'OUTPUT_WRITE_ERROR':'WAIT_OUTPUT_READBACK';g.degraded=true;g.valid=false;}
        sc(z.id,'output_json',JSON.stringify(io.commands(z.outputs)));
        if(on&&sent&&operation.inService===true){
            if(opened[z.id]===undefined||now<opened[z.id])opened[z.id]=now;
            g.demand=true;
            if(now-opened[z.id]>=C.circuits[z.circuit].zoneDelayMs)g.ready=true;
            if(!g.degraded)g.reason='HEAT';
        }else delete opened[z.id];
        if(enabled!==0&&!on&&!valid)g.valid=false;
        sc(z.id,'valid',valid);sc(z.id,'current_state',on?1:0);
        sc(z.id,'status',operation.inService===true?reason:'FIRST_COMMISSIONING');
        io.event(z.id,reason,(!valid&&enabled!==0)||error?'Недостоверность датчика/настроек/команды; исправные зоны продолжают работу':'');
    });
    Object.keys(groups).forEach(function(id){
        var g=groups[id];
        if(g.demand)g.valid=true; // independent healthy/open path survives another failed zone
        if(!g.enabled){g.valid=true;g.reason='OFF';}
        else if(!g.demand&&!g.degraded)g.reason='NO_DEMAND';
    });
    seq+=1;
    publish(C.houseTopic,JSON.stringify({v:3,source:C.houseSource,session_id:session,seq:seq,
        sent_ms:now,ttl_ms:W.TTL_MS,groups:groups}),0,false);
}
Config.zones.forEach(function(z){
    defineRule('hhm3_settings_'+z.id,{whenChanged:['NL_simple_thermostat_'+z.id+'/target_state',
        'NL_simple_thermostat_'+z.id+'/target_temperature'],then:evaluate});
});
evaluate();setInterval(evaluate,C.periodMs);
