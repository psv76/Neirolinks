/* HHM room temperature: read-only wb-mqtt-serial device/Load RPC evidence.
 * ES5 pure state machine; does NOT subscribe/publish MQTT or write hardware.
 * The trusted WB-local transport alone sends its returned request and hands
 * back the exact, non-retained reply with a monotonic local receive timestamp.
 * Unique per-request MQTT reply topics prevent old replies qualifying later
 * polls. Result from a successful driver Load is a LOCAL_POLL, not a cached
 * retained /devices/.../controls/Temperature MQTT sample.
 */
function whole(x){return typeof x==='number'&&isFinite(x)&&x>=0&&Math.floor(x)===x;}
function name(x){return typeof x==='string'&&x.length>0&&x.length<=128;}
function prefix(x){return typeof x==='string'&&/^[a-zA-Z0-9_-]{8,72}$/.test(x);}
function decode(payload){
    if(typeof payload==='string'){
        if(payload.length>4096)return null;
        try{return JSON.parse(payload);}catch(e){return null;}
    }
    return payload;
}
exports.create=function(c,Evidence){
    if(!Evidence||typeof Evidence.create!=='function')
        throw new Error('Serial Load evidence: injected evidence module required');
    if(!c||!name(c.sensorId)||!name(c.deviceType)||!name(c.temperatureTopic)||
       !whole(c.slaveId)||c.slaveId<1||c.slaveId>247||
       typeof c.portPath!=='string'||
       !/^\/dev\/[A-Za-z0-9_.-]+$/.test(c.portPath)||
       !whole(c.baudRate)||c.baudRate<300||c.baudRate>1000000||
       (c.parity!=='N'&&c.parity!=='E'&&c.parity!=='O')||
       c.dataBits!==8||(c.stopBits!==1&&c.stopBits!==2)||
       !name(c.channel)||!prefix(c.clientPrefix)||
       !whole(c.replyTimeoutMs)||c.replyTimeoutMs<1||
       !whole(c.minProbeGapMs)||c.minProbeGapMs<1||
       !whole(c.freshMs)||c.freshMs<=c.replyTimeoutMs||
       !whole(c.maxSequence)||c.maxSequence<1)
        throw new Error('Serial Load evidence: explicit verified RPC configuration required');
    var evidence=Evidence.create({sensorId:c.sensorId,topic:c.temperatureTopic,
        minC:c.minC,maxC:c.maxC,freshMs:c.freshMs});
    var boot=null,lastNow=null,nextSeq=0,pending=null,lastProbeAt=null,
        lastReason='NO_REQUEST';
    function context(now,epoch){
        if(!whole(now)||!name(epoch))throw new Error('Serial Load evidence: local time/boot required');
        if(lastNow!==null&&now<lastNow){
            pending=null;boot=epoch;lastProbeAt=null;lastNow=now;lastReason='CLOCK_REWIND';
            evidence.sample(now,epoch);return false;
        }
        lastNow=now;
        if(boot!==epoch){
            pending=null;boot=epoch;lastProbeAt=null;lastReason='NEW_BOOT';
            evidence.sample(now,epoch);
        }
        return true;
    }
    function fail(seq,now,why){
        evidence.observePoll({source:'WB_LOCAL_MODBUS_POLL',bootEpoch:boot,
            sensorId:c.sensorId,topic:c.temperatureTopic,pollSequence:seq,
            observedAtMs:now,retained:false,pollSucceeded:false});
        lastReason=why;
    }
    function timeout(now){
        if(pending&&now-pending.sentAtMs>c.replyTimeoutMs){
            var seq=pending.seq;pending=null;fail(seq,now,'RPC_TIMEOUT');
        }
    }
    return {
        request:function(now,bootEpoch,allowProbe){
            if(!context(now,bootEpoch))return {send:false,reason:'CLOCK_REWIND'};
            timeout(now);
            if(allowProbe!==true)return {send:false,reason:'PROBE_NOT_AUTHORIZED'};
            if(pending)return {send:false,reason:'REQUEST_PENDING'};
            if(lastProbeAt!==null&&now-lastProbeAt<c.minProbeGapMs)
                return {send:false,reason:'PROBE_RATE_LIMITED'};
            if(nextSeq>=c.maxSequence)return {send:false,reason:'SEQUENCE_EXHAUSTED'};
            nextSeq++;
            lastProbeAt=now;
            var requestTopic='wb-mqtt-serial/device/Load/'+c.clientPrefix+'_'+nextSeq;
            pending={seq:nextSeq,sentAtMs:now,replyTopic:requestTopic+'/reply'};
            lastReason='AWAIT_RPC_REPLY';
            return {send:true,topic:requestTopic,
                payload:{slave_id:c.slaveId,device_type:c.deviceType,
                    channels:[c.channel],path:c.portPath,baud_rate:c.baudRate,
                    parity:c.parity,data_bits:c.dataBits,stop_bits:c.stopBits},
                retained:false,replyTopic:pending.replyTopic};
        },
        reply:function(r){
            if(!r||!whole(r.nowMs)||!name(r.bootEpoch)||
               r.bootEpoch!==boot)
                return {accepted:false,reason:'CLOCK_OR_BOOT_INVALID'};
            if(!context(r.nowMs,r.bootEpoch))
                return {accepted:false,reason:'CLOCK_OR_BOOT_INVALID'};
            timeout(r.nowMs);
            if(!pending||r.topic!==pending.replyTopic||r.retained!==false)
                return {accepted:false,reason:'UNMATCHED_OR_RETAINED_REPLY'};
            var seq=pending.seq;
            pending=null; // one reply consumes the unique request; no replay
            var data=decode(r.payload);
            if(!data||typeof data!=='object'||!whole(data.id)||
               !Object.prototype.hasOwnProperty.call(data,'error')||
               data.error!==null||!data.result||
               typeof data.result!=='object'||!data.result.channels||
               typeof data.result.channels!=='object'||
               !Object.prototype.hasOwnProperty.call(data.result.channels,c.channel)){
                fail(seq,r.nowMs,'RPC_ERROR_OR_UNVERIFIED_CHANNEL');
                return {accepted:false,reason:'RPC_ERROR_OR_UNVERIFIED_CHANNEL'};
            }
            var temp=data.result.channels[c.channel];
            var applied=evidence.observePoll({source:'WB_LOCAL_MODBUS_POLL',
                bootEpoch:boot,sensorId:c.sensorId,topic:c.temperatureTopic,
                pollSequence:seq,observedAtMs:r.nowMs,temperatureC:temp,
                retained:false,pollSucceeded:true});
            lastReason=applied.reason;
            return {accepted:applied.accepted&&applied.reason==='FRESH_LOCAL_POLL',
                reason:applied.reason};
        },
        sample:function(now,bootEpoch){
            if(!context(now,bootEpoch))return evidence.sample(now,bootEpoch);
            timeout(now);
            return evidence.sample(now,bootEpoch);
        },
        snapshot:function(){return {bootEpoch:boot,pending:!!pending,
            pendingReplyTopic:pending?pending.replyTopic:null,
            nextSequence:nextSeq,lastProbeAtMs:lastProbeAt,
            minProbeGapMs:c.minProbeGapMs,lastReason:lastReason,
            sensor:evidence.snapshot()};}
    };
};
