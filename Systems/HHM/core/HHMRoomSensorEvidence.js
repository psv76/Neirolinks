/* HHM room sensor evidence: ES5, no MQTT subscriptions or writes.
 * Object driver must attest a NEW successful local WB-Modbus poll with
 * independent pollSequence/bootEpoch. Retained MQTT snapshots are not proof.
 */
function finite(v){return typeof v==='number'&&isFinite(v);}
function whole(v){return finite(v)&&v>=0&&Math.floor(v)===v;}
function tag(s){return typeof s==='string'&&s.length>0&&s.length<=128;}
exports.create=function(c){
    if(!c||!tag(c.sensorId)||!tag(c.topic)||
       !finite(c.minC)||!finite(c.maxC)||c.minC>=c.maxC||
       !whole(c.freshMs)||c.freshMs===0)
        throw new Error('Room evidence: explicit local poll contract required');
    var epoch=null,sequence=null,seenAt=null,temp=null,healthy=false,
        lastNow=null,reason='NO_LOCAL_POLL';
    function invalidate(why){
        healthy=false;temp=null;seenAt=null;reason=why;
    }
    return {
        observePoll:function(p){
            if(!p||!whole(p.observedAtMs)||!tag(p.bootEpoch)||
               !whole(p.pollSequence)||!tag(p.source)||
               p.source!=='WB_LOCAL_MODBUS_POLL'||
               p.sensorId!==c.sensorId||p.topic!==c.topic||
               p.retained!==false||typeof p.pollSucceeded!=='boolean')
                return {accepted:false,reason:'UNTRUSTED_POLL_EVIDENCE'};
            if(lastNow!==null&&p.observedAtMs<lastNow){
                invalidate('CLOCK_REWIND');
                epoch=null;sequence=null;
                lastNow=p.observedAtMs;
                return {accepted:false,reason:'CLOCK_REWIND'};
            }
            lastNow=p.observedAtMs;
            if(epoch!==p.bootEpoch){
                epoch=p.bootEpoch;sequence=null;invalidate('NEW_BOOT_EPOCH');
            }
            if(sequence!==null&&p.pollSequence<=sequence)
                return {accepted:false,reason:'DUPLICATE_OR_OUT_OF_ORDER'};
            sequence=p.pollSequence;
            if(p.pollSucceeded!==true){
                invalidate('LOCAL_POLL_FAILED');
                return {accepted:true,reason:'LOCAL_POLL_FAILED'};
            }
            if(!finite(p.temperatureC)||p.temperatureC<c.minC||
               p.temperatureC>c.maxC){
                invalidate('INVALID_NUMERIC_TEMPERATURE');
                return {accepted:true,reason:'INVALID_NUMERIC_TEMPERATURE'};
            }
            temp=p.temperatureC;seenAt=p.observedAtMs;healthy=true;
            reason='FRESH_LOCAL_POLL';
            return {accepted:true,reason:'FRESH_LOCAL_POLL'};
        },
        sample:function(now,bootEpoch){
            if(!whole(now)||!tag(bootEpoch))
                throw new Error('Room evidence: boot/time required');
            if(lastNow!==null&&now<lastNow){
                invalidate('CLOCK_REWIND');epoch=null;sequence=null;
            }
            lastNow=now;
            if(epoch!==bootEpoch)invalidate('BOOT_NOT_QUALIFIED');
            else if(healthy&&seenAt!==null&&
                    (now<seenAt||now-seenAt>c.freshMs))
                invalidate('POLL_STALE');
            return {id:c.sensorId,temperatureC:healthy?temp:null,
                ok:healthy&&epoch===bootEpoch,observedAtMs:
                    healthy&&epoch===bootEpoch?seenAt:null,
                reason:reason};
        },
        snapshot:function(){
            return {sensorId:c.sensorId,bootEpoch:epoch,
                lastPollSequence:sequence,healthy:healthy,
                lastObservationMs:seenAt,reason:reason};
        }
    };
};
