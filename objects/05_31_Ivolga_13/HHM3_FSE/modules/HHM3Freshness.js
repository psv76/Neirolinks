/* Иволга HHM3: адресное подтверждение температуры через read-only device/Load.
 * Только разрешённые температурные каналы; никогда не пишет /on или device/Set.
 * Один ожидающий RPC на экземпляр, ответ коррелируется по topic/id/revision.
 */
var W = require('HHM3Wire');
function finite(v) { return typeof v === 'number' && isFinite(v); }
exports.create = function (env, owner, onSample) {
    var entries = [], current = null, lastRequestAt = null, lastClock = null, id = 0;
    var stamp = Math.floor(env.now()), nonce = Math.floor(Math.random() * 1000000000);
    if (!/^[a-zA-Z0-9_-]+$/.test(owner)) throw new Error('Invalid HHM3 RPC owner');
    var topic = '/rpc/v1/wb-mqtt-serial/device/Load/hhm3-' + owner + '-' + stamp + '-' + nonce;
    function fail(reason) {
        if (!current) return;
        var e = current.entry, now = env.now();
        // A new non-retained measurement or error transition supersedes the RPC.
        if (e.sensor.revision() === current.revision) e.sensor.invalidate();
        e.errors = Math.min(4, e.errors + 1);
        e.next = now + Math.min(300000, 30000 * Math.pow(2, e.errors - 1)) +
            Math.floor(Math.random() * 3000);
        e.reason = reason;
        current = null;
        if (onSample) onSample();
    }
    env.trackMqtt(topic + '/reply', function (m) {
        if (!current || m.retained !== false || typeof m.value !== 'string' || m.value.length > 8192) return;
        var r, e = current.entry;
        try { r = JSON.parse(m.value); } catch (ex) { fail('INVALID_JSON'); return; }
        // Wrong-id / replay replies are ignored; only this request may be completed.
        if (!r || r.id !== current.id) return;
        if (env.now() < current.at || env.now() - current.at >= 12000) {fail('LATE_REPLY'); return;}
        if (r.error !== null || !r.result || !r.result.channels ||
            !Object.prototype.hasOwnProperty.call(r.result.channels, e.channel) ||
            !Array.isArray(r.result.readonly) || r.result.readonly.indexOf(e.channel) < 0 ||
            !finite(r.result.channels[e.channel]) || r.result.channels[e.channel] < e.min ||
            r.result.channels[e.channel] > e.max) { fail('INVALID_RESPONSE'); return; }
        if (e.sensor.revision() !== current.revision) {
            // The RPC is older than a later sensor sample or error transition.
            e.next = env.now() + 70000; current = null; return;
        }
        if (!e.sensor.rpcSample(r.result.channels[e.channel],env.now(),current.revision)) {
            fail('SENSOR_REJECTED'); return;
        }
        e.errors = 0; e.next = env.now() + 70000; e.reason = 'RPC_OK';
        current = null;
        if (onSample) onSample();
    });
    function add(path,sensor,min,max) {
        var slash=path.indexOf('/'), dev=path.slice(0,slash), channel=path.slice(slash+1);
        if (slash<1 || !/^[a-zA-Z0-9_.-]+$/.test(dev) ||
            !/^(External Sensor [12]|Temperature)$/.test(channel) ||
            !finite(min) || !finite(max) || min>=max || !sensor ||
            typeof sensor.rpcSample!=='function') throw new Error('Unsupported HHM3 temperature '+path);
        for (var i=0;i<entries.length;i++) if(entries[i].path===path)return;
        entries.push({path:path,device:dev,channel:channel,sensor:sensor,min:min,max:max,
            errors:0,next:env.now()+20000,reason:'WAIT_MQTT'});
    }
    function tick() {
        var now=env.now();
        if (lastClock!==null && now<lastClock) {
            if (current) fail('CLOCK_ROLLBACK');
            entries.forEach(function(e){e.sensor.invalidate();e.next=now+20000;});
            lastRequestAt=null;
        }
        lastClock=now;
        if (current) {
            if (now-current.at>=12000) fail('RPC_TIMEOUT');
            else return;
        }
        if (lastRequestAt!==null && now-lastRequestAt<2000) return;
        // Most overdue reading first: no starvation with many thermostats.
        var selected=null, earliest=Infinity;
        entries.forEach(function(e){
            var at=e.sensor.timestamp(), due=at===null?e.next:Math.max(e.next,at+70000);
            if (e.sensor.runtimeStatus()==='RUNTIME_UNSUPPORTED' || due>now) return;
            if (due<earliest) {earliest=due;selected=e;}
        });
        if (!selected) return;
        id+=1;
        current={id:id,at:now,revision:selected.sensor.revision(),entry:selected};
        lastRequestAt=now;
        selected.next=now+30000;
        try {
            env.publish(topic,JSON.stringify({id:id,params:{device_id:selected.device,
                channels:[selected.channel],total_timeout:10000}}),0,false);
        } catch(e) {fail('RPC_PUBLISH_ERROR');}
    }
    return {add:add,tick:tick,pending:function(){return current?current.entry.path:null;},
        status:function(path){for(var i=0;i<entries.length;i++)if(entries[i].path===path)return entries[i].reason;return 'NOT_MONITORED';},
        replyTopic:topic+'/reply'};
};
