/* HHM 3.1 / Иволга: единственный writer зональных A08/A09/A13/A14.
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
function thermostatTitle(z){
    var t=z.title,p=t.indexOf(' ');
    if(p>=0&&p+1<t.length)t=t.substring(0,p+1)+t.charAt(p+1).toUpperCase()+t.substring(p+2);
    return z.id+' '+t;
}
function statusText(reason){
    var texts={
        STARTUP:'Запуск',
        OFF:'Выключен',
        NO_DEMAND:'Ожидание',
        HEAT:'Нагрев',
        SETTINGS_INVALID:'Ошибка уставки',
        SENSOR_FALLBACK:'Нагрев без датчика',
        FLOOR_SENSOR_UNAVAILABLE:'Нет датчика пола',
        FLOOR_HARD_MAX:'Перегрев пола',
        RUNTIME_UNSUPPORTED:'Ошибка среды',
        OUTPUT_WRITE_ERROR:'Ошибка выхода',
        WAIT_OUTPUT_READBACK:'Ждём подтверждение',
        FIRST_COMMISSIONING:'Первичный пуск'
    };
    return texts[reason]||'Неизвестно';
}
Config.zones.forEach(function(z){
    var saved=settings[z.id],state=saved&&saved.state===1?1:0,target=saved?W.number(saved.target):z.target;
    var targetTitle=z.kind==='floor'?'Уставка пола, °C':'Уставка воздуха, °C';
    var temperatureTitle=z.kind==='floor'?'Температура пола':'Температура воздуха';
    if(target===null)target=z.target;
    defineVirtualDevice('NL_simple_thermostat_'+z.id,{title:thermostatTitle(z),cells:{
        target_state:{title:'Логика термостата',type:'switch',value:state===1,forceDefault:false,order:1},
        target_temperature:{title:targetTitle,type:'range',value:target,min:z.min,max:z.max,forceDefault:false,order:2},
        temperature:{title:temperatureTitle,type:'temperature',value:0,readonly:true,forceDefault:true,order:3},
        status:{title:'Состояние',type:'text',value:'Запуск',readonly:true,forceDefault:true,order:4},
        valid:{title:'Показания достоверны',type:'switch',value:false,readonly:true,forceDefault:true,order:5},
        current_state:{title:'Запрос тепла',type:'switch',value:false,readonly:true,forceDefault:true,order:6}
    }});
    memory[z.id]=false;
    io.watchTemperature(z.sensor,-20,z.kind==='floor'?70:60);
});
function stateValue(v){if(v===true||v===1||v==='1')return 1;if(v===false||v===0||v==='0')return 0;return null;}
function evaluate(){
    io.begin();
    var now=Date.now(),groups={},pending={},unsafe={},blocked={};
    if(lastNow!==null&&(now<lastNow||now-lastNow>C.periodMs*3))opened={};
    lastNow=now;
    ['501','502','503','505'].forEach(function(id){
        groups[id]={valid:true,demand:false,ready:false,enabled:false,degraded:false,
            partial_ready:false,output_blocked:false,reason:'OFF',floor:null};
        pending[id]=false;unsafe[id]=false;blocked[id]=false;
    });
    Config.zones.forEach(function(z){
        var base='NL_simple_thermostat_'+z.id+'/',enabled=stateValue(dev[base+'target_state']);
        var target=W.number(dev[base+'target_temperature']),t=io.read(z.sensor);
        // wb-rules PersistentStorage rejects plain objects. Preserve existing VD settings;
        // persist only actual changes to avoid a database write every evaluation cycle.
        var previous=settings[z.id];
        if(enabled!==null&&target!==null&&target>=z.min&&target<=z.max&&
           (!previous||previous.state!==enabled||previous.target!==target)) {
            settings[z.id]=new StorableObject({state:enabled,target:target});
        }
        var sensorFresh=t!==null,valid=sensorFresh,on=false,reason='OFF',g=groups[z.circuit],error=false;
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
        if(!valid&&enabled!==0){g.degraded=true;g.reason=reason;unsafe[z.circuit]=true;}
        var sent=true;
        if(operation.inService===true)z.outputs.forEach(function(p){var w=io.write(p,on);error=error||!w.ok;sent=w.ok&&io.matches(p,on)&&sent;});
        if(!sent){
            reason=error?'OUTPUT_WRITE_ERROR':'WAIT_OUTPUT_READBACK';
            g.degraded=true;g.valid=false;
            // A clean thermostat transition may wait for MQTT readback while
            // another already-confirmed ready zone keeps the shared circuit heating.
            // The pending zone itself is never counted as an open/ready path.
            // Explicit disable, sensor/settings faults and write errors remain blocking.
            if(!error&&valid&&enabled===1)pending[z.circuit]=true;
            else unsafe[z.circuit]=true;
            if(error||(!on&&enabled!==1))blocked[z.circuit]=true;
        }
        if(on&&sent&&operation.inService===true){
            if(opened[z.id]===undefined||now<opened[z.id])opened[z.id]=now;
            g.demand=true;
            if(now-opened[z.id]>=C.circuits[z.circuit].zoneDelayMs)g.ready=true;
            if(!g.degraded)g.reason='HEAT';
        }else delete opened[z.id];
        if(enabled!==0&&!on&&!valid)g.valid=false;
        sc(z.id,'valid',sensorFresh);sc(z.id,'current_state',!!on);
        sc(z.id,'status',statusText(operation.inService===true?reason:'FIRST_COMMISSIONING'));
        io.event(z.id,reason,(!valid&&enabled!==0)||error?'Недостоверность датчика/настроек/команды; исправные зоны продолжают работу':'');
    });
    Object.keys(groups).forEach(function(id){
        var g=groups[id];
        if(g.demand)g.valid=true; // one confirmed ON is a real path, not proof of all zones
        g.partial_ready=g.demand&&g.ready&&pending[id]&&!unsafe[id];
        g.output_blocked=blocked[id];
        if(!g.enabled){g.valid=true;g.reason='OFF';}
        else if(g.partial_ready)g.reason='HEAT';
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
