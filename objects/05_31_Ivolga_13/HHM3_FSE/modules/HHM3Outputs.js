/* A05 contract: OFF preserves Level; positive Level may AUTO-ON.
 * No ON writes. Closing never writes Level. Readback is not hydraulic proof.
 * Active Level commands are integer percentages; compare MQTT against the value sent.
 */
exports.create=function(c,io){
    if(!(c.commandTimeoutMs>0&&c.commandRetryMs>0&&c.valveActiveMinLevel>0&&
        c.valveActiveMinLevel<c.valveActiveMaxLevel&&c.valveActiveMaxLevel<=100&&
        c.valveActiveMinLevel%1===0&&c.valveActiveMaxLevel%1===0&&c.valveOffCommand===false))
        throw new Error('Invalid MAO4 command contract');
    var state='UNINITIALIZED',transaction=null,confirmedOffSeq=-1,activeLevel=null;
    var fault='',retryAt=0,lastNow=null,desiredLevel=null,wantOpen=false,pumpCommand=false;
    function freshOff(){return confirmedOffSeq>=0&&io.seq(c.enable)>confirmedOffSeq&&io.matches(c.enable,false);}
    function report(ready){
        return {state:state,ready:ready,pump:pumpCommand,fault:fault,
            saved_level:io.read(c.level),requested_level:desiredLevel,
            requested_enable:wantOpen,closed_command:!wantOpen,
            closed_readback_match:state==='CLOSED'&&!fault&&freshOff(),
            readback:{level:io.readback(c.level),enable:io.readback(c.enable),pump:io.readback(c.pump)}};
    }
    function pump(value){
        pumpCommand=value;
        var w=io.write(c.pump,value);
        return w.ok&&io.matches(c.pump,value);
    }
    function closedAck(){
        if(transaction&&io.seq(c.enable)>transaction.switchSeq&&io.matches(c.enable,false)){
            confirmedOffSeq=transaction.switchSeq;transaction=null;state='CLOSED';return true;
        }
        return false;
    }
    function beginClose(now,reason){
        // Both ordinary closure and all recovery paths use this ONE operation.
        state='CLOSING';activeLevel=null;confirmedOffSeq=-1;
        if(reason){fault=reason;retryAt=now+c.commandRetryMs;}
        pump(false);
        transaction={at:now,switchSeq:io.seq(c.enable)};
        var w=io.write(c.enable,false,true);
        if(!w.ok){state='CLOSURE_UNCERTAIN';fault='OFF_WRITE_ERROR';transaction=null;retryAt=now+c.commandRetryMs;return;}
        closedAck();
    }
    function fail(now,reason){beginClose(now,reason);return report(false);}
    function startOpen(now){
        // Only an already qualified OPEN may reuse its fresh, unchanged ON.
        var provedOnSeq=state==='OPEN'&&io.matches(c.enable,true)?io.seq(c.enable):-1;
        state='OPENING';confirmedOffSeq=-1;
        transaction={at:now,level:desiredLevel,sent:false,provedOnSeq:provedOnSeq,reuseOn:false};
    }
    return function(r,now){
        pumpCommand=false;
        wantOpen=r.pump===true&&typeof r.valve==='number'&&isFinite(r.valve)&&r.valve>0&&r.valve<=100;
        // The MAO4 level is an integer percentage. Normalize BEFORE writing and
        // use the same normalized value for readback, caching and change detection.
        desiredLevel=wantOpen?Math.max(c.valveActiveMinLevel,Math.min(c.valveActiveMaxLevel,
            Math.round(c.valveActiveMinLevel+(c.valveActiveMaxLevel-c.valveActiveMinLevel)*r.valve/100))):null;
        if(lastNow!==null&&(now<lastNow||now-lastNow>c.periodMs*3)){
            beginClose(now,'CLOCK_REQUALIFICATION');lastNow=now;return report(false);
        }
        lastNow=now;
        if(state==='UNINITIALIZED')beginClose(now,'');
        if(state==='CLOSURE_UNCERTAIN'){
            pump(false);
            if(now>=retryAt)beginClose(now,fault);
            return report(false);
        }
        if(state==='CLOSING'){
            pump(false);
            if(now-transaction.at>=c.commandTimeoutMs){
                state='CLOSURE_UNCERTAIN';fault='OFF_READBACK_TIMEOUT';transaction=null;
                retryAt=now+c.commandRetryMs;return report(false);
            }
            if(!closedAck())return report(false);
        }
        if(state==='CLOSED'){
            // Remembered Level is irrelevant to OFF confirmation.
            if(!freshOff())return fail(now,'OFF_READBACK_LOST');
            if(now<retryAt){pump(false);return report(false);}
            if(!wantOpen){
                fault='';
                var circulating=pump(r.pump===true);
                if(!circulating&&io.commands([c.pump]).some(function(w){return !w.ok;}))
                    return fail(now,'PUMP_WRITE_ERROR');
                return report(circulating);
            }
            startOpen(now);
        }
        if(state==='OPEN'&&(!io.matches(c.level,activeLevel)||!io.matches(c.enable,true)))
            return fail(now,'OPEN_READBACK_CHANGED');
        if(state==='OPEN'&&!wantOpen){
            beginClose(now,'');
            if(state!=='CLOSED')return report(false);
            fault='';return report(pump(r.pump===true));
        }
        if(state==='OPEN'&&desiredLevel!==activeLevel)startOpen(now);
        if(state==='OPENING'){
            // Cancel a superseded in-flight opening through OFF, never through ON.
            if(!wantOpen||desiredLevel!==transaction.level){
                beginClose(now,'OPEN_CANCELLED');return report(false);
            }
            if(now-transaction.at>=c.commandTimeoutMs)return fail(now,'OPEN_READBACK_TIMEOUT');
            if(!pump(false)){
                if(io.commands([c.pump]).some(function(w){return !w.ok;}))return fail(now,'PUMP_WRITE_ERROR');
                return report(false);
            }
            if(!transaction.sent){
                // If Switch changed while pump stopped, old ON cannot be reused.
                transaction.reuseOn=transaction.provedOnSeq>=0&&
                    io.seq(c.enable)===transaction.provedOnSeq&&io.matches(c.enable,true);
                transaction.levelSeq=io.seq(c.level);transaction.switchSeq=io.seq(c.enable);
                transaction.sent=true;
                if(!io.write(c.level,transaction.level,true).ok)return fail(now,'LEVEL_WRITE_ERROR');
            }
            // An observed OFF invalidates former ON immediately.
            if(io.seq(c.enable)>transaction.switchSeq&&io.matches(c.enable,false))
                return fail(now,'OPEN_SWITCH_OFF');
            // New Level is required for EVERY target. A new ON is required from
            // CLOSED; only retargeting an already-qualified OPEN may preserve ON.
            var onNow=io.matches(c.enable,true);
            var freshOn=io.seq(c.enable)>transaction.switchSeq&&onNow;
            var preservedOn=transaction.reuseOn&&io.seq(c.enable)===transaction.switchSeq&&onNow;
            if(io.seq(c.level)<=transaction.levelSeq||!io.matches(c.level,transaction.level)||
                !(freshOn||preservedOn))return report(false);
            activeLevel=transaction.level;transaction=null;state='OPEN';fault='';
        }
        if(state==='OPEN'){
            var running=pump(true);
            if(!running&&io.commands([c.pump]).some(function(w){return !w.ok;}))return fail(now,'PUMP_WRITE_ERROR');
            return report(running);
        }
        return report(false);
    };
};
