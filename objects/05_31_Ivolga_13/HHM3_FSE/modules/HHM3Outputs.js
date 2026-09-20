/* MAO4 Level may itself switch the channel ON/OFF.
 * MQTT readback is electrical state only, never mechanical/hydraulic proof.
 * On a failed transaction retry OFF only, then qualify the closed tuple anew.
 */
exports.create=function(c,io){
    if(!(c.commandTimeoutMs>0&&c.commandRetryMs>0))throw new Error('Invalid output retry timing');
    var key='',stage=0,pending=null,fault='',forceClose=false,retryAt=0,lastNow=null;
    function attempt(path,value,now){
        if(!pending){
            pending={path:path,value:value,seq:io.seq(path),at:now};
            var w=io.write(path,value,true);
            if(!w.ok){pending=null;return 'ERROR';}
        }
        if(io.seq(path)>pending.seq&&io.matches(path,value)){pending=null;return 'ACK';}
        if(now<pending.at||now-pending.at>=c.commandTimeoutMs){pending=null;return 'ERROR';}
        return 'WAIT';
    }
    function report(state,ready,pump){
        return {state:state,ready:ready,pump:pump,
            closed_readback_match:(state==='READBACK_MATCH'||state==='RECOVERED_CLOSED_READBACK')&&stage===2&&
                io.matches(c.level,c.valveClosedLevel)&&io.matches(c.enable,c.valveClosedEnable),
            readback:{level:io.readback(c.level),enable:io.readback(c.enable),pump:io.readback(c.pump)}};
    }
    function fail(now){
        fault='CLOSURE_UNCERTAIN';pending=null;stage=0;key='';forceClose=true;
        // No Level here: even a closing Level can AUTO-ON. Retry OFF alone.
        io.write(c.pump,false);
        var result=attempt(c.enable,false,now);
        if(result==='ACK'){fault='';pending=null;retryAt=now+c.commandRetryMs;}
        else if(result==='ERROR')retryAt=now+c.commandRetryMs;
        return report('CLOSURE_UNCERTAIN',false,false);
    }
    return function(r,now){
        if(lastNow!==null&&now<lastNow){pending=null;stage=0;key='';retryAt=0;}
        lastNow=now;
        if(!r.pump)io.write(c.pump,false);
        if(fault){
            io.write(c.pump,false);
            if(now<retryAt)return report('CLOSURE_UNCERTAIN',false,false);
            var off=attempt(c.enable,false,now);
            if(off==='ACK'){fault='';pending=null;retryAt=now+c.commandRetryMs;}
            else if(off==='ERROR')retryAt=now+c.commandRetryMs;
            return report('CLOSURE_UNCERTAIN',false,false);
        }
        if(now<retryAt){io.write(c.pump,false);return report('RECOVERY_WAIT',false,false);}
        var pct=forceClose?0:r.valve;
        var level=c.valveClosedLevel+(c.valveOpenLevel-c.valveClosedLevel)*pct/100;
        var enabled=pct>0?true:c.valveClosedEnable,newKey=String(level)+'/'+enabled;
        if(newKey!==key){key=newKey;stage=enabled?0:-1;pending=null;}
        // A changed external readback must invalidate completion, not the cache alone.
        if(stage===2&&(!io.matches(c.level,level)||!io.matches(c.enable,enabled))){
            return fail(now);
        }
        if(stage===-1){
            // OFF closes without erasing remembered Level. It takes priority over
            // any Level write, which could AUTO-ON even while trying to close.
            var offFirst=attempt(c.enable,false,now);
            if(offFirst==='ERROR')return fail(now);
            if(offFirst==='WAIT'){
                if(!io.write(c.pump,false).ok)return fail(now);
                return report('WAIT_PRIORITY_OFF_READBACK',false,false);
            }
            // Keep the accepted object scale. If already at closedLevel, do not
            // rewrite it and cause an unnecessary AUTO-ON. Otherwise Level must
            // be followed by a NEW OFF acknowledgment, never the preceding one.
            stage=io.matches(c.level,level)?2:0;
        }
        if(stage===0){
            var first=attempt(c.level,level,now);
            if(first==='ERROR')return fail(now);
            if(first==='WAIT'){
                if(!io.write(c.pump,false).ok)return fail(now);
                return report('WAIT_LEVEL_READBACK',false,false);
            }
            stage=1;
        }
        if(stage===1){
            // Never ON after a failed/missing/changed level acknowledgment.
            if(!io.matches(c.level,level))return fail(now);
            var second=attempt(c.enable,enabled,now);
            if(second==='ERROR')return fail(now);
            if(second==='WAIT'){
                if(!io.write(c.pump,false).ok)return fail(now);
                return report('WAIT_SWITCH_READBACK',false,false);
            }
            stage=2;
        }
        if(!io.matches(c.level,level)||!io.matches(c.enable,enabled))return fail(now);
        if(forceClose){
            forceClose=false;retryAt=now+c.commandRetryMs;
            // Recirculation only after the configured closed tuple was read back.
            var recirculate=r.pump&&r.valve===0;
            if(!io.write(c.pump,recirculate).ok)return fail(now);
            var recovered=report('RECOVERED_CLOSED_READBACK',false,recirculate);
            key='';stage=0;return recovered;
        }
        var pump=io.write(c.pump,r.pump);
        if(!pump.ok)return fail(now);
        var ready=io.matches(c.pump,r.pump);
        return report(ready?'READBACK_MATCH':'WAIT_PUMP_READBACK',ready,r.pump);
    };
};
