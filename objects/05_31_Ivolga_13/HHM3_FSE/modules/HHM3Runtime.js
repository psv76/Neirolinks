/* HHM3 common runtime: freshness, ownership and structured transition events. ES5. */
var W = require('HHM3Wire');
var C = require('HHM3Config').config;
exports.number = W.number;
exports.topic = function (path) { var p=path.indexOf('/'); return '/devices/'+path.slice(0,p)+'/controls/'+path.slice(p+1); };
exports.io = function (env, owner, allowed) {
    var sensors={}, lastCommands={}, lastEvents={};
    return {
        watch:function(path,min,max) {
            if(sensors[path])return;
            var s=W.sensor();sensors[path]={sensor:s,min:min,max:max};
            env.trackMqtt(exports.topic(path),function(m){s.sample(m.value,m.retained,env.now());if(env.onSample)env.onSample();});
            env.trackMqtt(exports.topic(path)+'/meta/error',function(m){s.error(m.value);if(env.onSample)env.onSample();});
        },
        read:function(path) {var s=sensors[path];return s?s.sensor.read(env.now(),s.min,s.max):null;},
        at:function(path) {var s=sensors[path];return s?s.sensor.timestamp():null;},
        runtime:function() {
            return Object.keys(sensors).some(function(k){return sensors[k].sensor.runtimeStatus()==='RUNTIME_UNSUPPORTED';})?
                'RUNTIME_UNSUPPORTED: требуется wb-rules >= 2.42.0 и boolean retained':'OK_OR_WAITING';
        },
        write:function(path,value) {
            if(allowed.indexOf(path)<0)throw new Error(owner+' forbidden output '+path);
            if(value===null || value===undefined || (typeof value==='number' && !isFinite(value)))throw new Error('Invalid output');
            var last=lastCommands[path],now=env.now();
            if(last && last.value===value && now>=last.at && now-last.at<30000)return true;
            try {env.dev[path]=value;lastCommands[path]={value:value,at:now};return true;}
            catch(e){delete lastCommands[path];return false;}
        },
        event:function(key,state,warning) {
            var signature=state+';'+warning, previous=lastEvents[key];
            if(previous && previous.signature===signature)return;
            var severity=warning?'warning':'state';
            if(/OVERHEAT|OUTPUT_WRITE_ERROR/.test(state))severity='alarm';
            else if(previous && previous.warning && !warning)severity='recovery';
            var e={v:3,owner:owner,circuit:key,at:env.now(),state:state,warning:warning||'',severity:severity};
            lastEvents[key]={signature:signature,warning:warning};
            env.publish(C.eventTopic,JSON.stringify(e),0,false);
            env.log('[отопление]['+owner+']['+key+']; STATE='+state+'; '+(warning||''));
            return e;
        }
    };
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
            typeof g.reason==='string' && (g.floor===null || (typeof g.floor==='number'&&isFinite(g.floor)&&g.floor>=-20&&g.floor<=70));
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
            else if(coolAt===null){coolAt=now;firstSample=io.at(config.temperature);}
            if(coolAt!==null&&now-coolAt>=config.coolMs&&io.at(config.temperature)>firstSample)storage.hot=false;
        }
        var state='ACTIVE',warning='',command=null,ok=true;
        if(!inService)state='FIRST_COMMISSIONING';
        else if(storage.hot){state='SOURCE_OVERHEAT';warning='Аппаратные защиты котла обязательны; насосы соседей не выключаются';}
        else if(connection!==0||fault!==0){state='OT_UNAVAILABLE';warning='Нет свежей исправной связи OT; новые команды удержаны';}
        else if(t===null){state='SOURCE_SENSOR_UNAVAILABLE';warning='Нет свежего 411; новые команды удержаны';}
        else if(requested===0&&demandKnown===false){state='REQUESTS_UNAVAILABLE';warning='Запрос 0, но отсутствие спроса не подтверждено: команду OFF не выдаём';}
        else if(requested===0){
            state='NO_DEMAND';
            if(config.noDemandMode==='setpoint_zero') {ok=io.write(config.setpoint,0);command=0;}
            else if(config.noDemandMode==='ch_enable') {ok=io.write(config.chEnable,false);command=false;}
            else {state='NO_DEMAND_ACTION_UNCONFIRMED';warning='Запрос 0; физический способ выключения CH с сохранением ГВС не подтверждён';}
        } else {
            command=Math.max(config.minC,Math.min(config.maxC,requested));
            ok=io.write(config.setpoint,command);
            if(config.noDemandMode==='ch_enable'&&ok)ok=io.write(config.chEnable,true);
        }
        if(!ok){state='OUTPUT_WRITE_ERROR';warning='Повтор записи автоматически';}
        if(command!==null&&ok)lastWritten=command;
        if(requested>0&&t!==null){
            if(responseAt===null){responseAt=now;baseline=t;}
            if(t>=requested-1||t>=baseline+1){responseAt=now;baseline=t;}
            else if(now-responseAt>=config.responseMs)warning+='; NO_RESPONSE — недостаточный отклик, не защёлка';
        }else{responseAt=null;baseline=null;}
        return {requested_heating_setpoint:requested,state:state,warning:warning,
            command:command,last_written:lastWritten,off_command_sent:requested===0&&command!==null&&ok};
    };
};
