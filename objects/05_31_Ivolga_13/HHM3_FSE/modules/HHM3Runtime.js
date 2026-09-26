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
        if(why)env.log.warning('[отопление]['+owner+'][M1W2 '+p+']; POST_START_PROOF='+why);
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
                    var level=value===null?'warning':'info';
                    env.log[level]('[отопление]['+owner+'][M1W2 '+path+']; '+JSON.stringify(d));
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
        event:function(key,state,warning) {
            var signature=state+';'+warning, previous=lastEvents[key];
            if(previous && previous.signature===signature)return;
            var severity=warning?'warning':'state';
            if(/OVERHEAT|CLOSURE_UNCERTAIN/.test(state))severity='alarm';
            else if(previous && previous.warning && !warning)severity='recovery';
            var e={v:3,owner:owner,circuit:key,at:env.now(),state:state,warning:warning||'',severity:severity};
            lastEvents[key]={signature:signature,warning:warning};
            env.publish(C.eventTopic,JSON.stringify(e),0,false);
            var text='[отопление]['+owner+']['+key+']; STATE='+state+'; '+(warning||'');
            if(severity==='alarm')env.log.error(text);
            else if(severity==='warning')env.log.warning(text);
            else env.log.info(text);
            return e;
        }
    };
    allowed.forEach(function(path){api.watch(path,-100000,100000);});
    return api;
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
