/* 05 16 Iset: deliberately simple WB-local room thermostat (offline).
 * One mapped WB-MSW temperature, one stored WB setpoint, hysteresis.
 * No poll sequence, MQTT freshness proof, fallback heat scheduling,
 * HA heartbeat, sensor timeout or remote availability dependencies.
 * Physical NO actuator and K4 pump owners remain separate.
 */
function finite(n){return typeof n==='number'&&isFinite(n);}
function str(s){return typeof s==='string'&&s.length>0&&s.length<=128;}
function integer(n){return finite(n)&&n>=0&&Math.floor(n)===n;}
function copy(s){return {mode:s.mode,setpointC:s.setpointC,revision:s.revision};}
function tempValue(x){
    if(finite(x))return x;
    if(typeof x==='string'&&x.length<32&&
       /^-?[0-9]+(?:\.[0-9]+)?$/.test(x)){
        var n=Number(x);return finite(n)?n:null;
    }
    return null;
}
exports.create=function(cfg,store){
    if(!cfg||!str(cfg.zoneId)||!str(cfg.sensorId)||
       !finite(cfg.minSetpointC)||!finite(cfg.maxSetpointC)||
       cfg.minSetpointC>=cfg.maxSetpointC||
       !finite(cfg.hysteresisC)||cfg.hysteresisC<=0||
       !finite(cfg.minMeasuredC)||!finite(cfg.maxMeasuredC)||
       cfg.minMeasuredC>=cfg.maxMeasuredC)
        throw new Error('Iset simple room: missing config');
    if(!store||typeof store.read!=='function'||
       typeof store.commit!=='function')
        throw new Error('Iset simple room: local durable store required');
    function valid(s){return !!(s&&(s.mode==='HEAT'||s.mode==='OFF')&&
        finite(s.setpointC)&&s.setpointC>=cfg.minSetpointC&&
        s.setpointC<=cfg.maxSetpointC&&integer(s.revision));}
    var settings=store.read();
    if(!valid(settings))
        throw new Error('Iset simple room: no approved stored settings');
    settings=copy(settings);
    var demand=null;
    function result(state,t,heat){
        return {zoneId:cfg.zoneId,state:state,
            measuredC:t,heatDemand:heat,mode:settings.mode,
            setpointC:settings.setpointC,revision:settings.revision};
    }
    return {
        settings:function(){return copy(settings);},
        applySettings:function(cmd){
            // Client authorization and MQTT transport are adapter duties.
            if(!cmd||!integer(cmd.expectedRevision)||
               cmd.expectedRevision!==settings.revision)
                return {accepted:false,reason:'REVISION_CONFLICT'};
            var next=copy(settings);
            if(cmd.mode!==undefined)next.mode=cmd.mode;
            if(cmd.setpointC!==undefined)next.setpointC=cmd.setpointC;
            if(!valid(next))return {accepted:false,reason:'INVALID_SETTINGS'};
            next.revision++;
            if(store.commit(copy(next))!==true)
                return {accepted:false,reason:'PERSISTENCE_FAILED'};
            settings=next;
            demand=null;
            return {accepted:true,reason:'APPLIED',settings:copy(settings)};
        },
        step:function(frame){
            if(!frame||typeof frame!=='object')
                throw new Error('Iset simple room: input frame required');
            if(settings.mode==='OFF'){
                demand=false;
                return result('USER_OFF',null,false);
            }
            // Explicit error of THIS sensor may switch off only THIS room.
            // A silent / unchanged MQTT temperature is NOT an error.
            if(frame.sensorError===true){
                demand=false;
                return result('SENSOR_ERROR',null,false);
            }
            var t=null;
            if(frame.reading&&frame.reading.id===cfg.sensorId)
                t=tempValue(frame.reading.temperatureC);
            if(t===null||t<cfg.minMeasuredC||t>cfg.maxMeasuredC){
                // No observation -> no new actuator decision. Do not make
                // global heat stop or synthesize a sensor failure timer.
                return result('NO_VALID_TEMPERATURE',null,null);
            }
            var half=cfg.hysteresisC/2;
            if(t<=settings.setpointC-half)demand=true;
            else if(t>=settings.setpointC+half)demand=false;
            else if(demand===null)demand=t<settings.setpointC;
            return result('NORMAL',t,demand);
        }
    };
};
