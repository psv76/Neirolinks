/* 05 16 Iset: sole OpenTherm setpoint planner.
 * Pure ES5: computes one write intent, without touching boiler or MQTT.
 * As-built HM2 ramp/write policy; no HA dependency.
 */
function finite(v){return typeof v==='number'&&isFinite(v);}
function clamp(v,low,high){return Math.max(low,Math.min(high,v));}
exports.create=function(cfg){
    if(!cfg||!finite(cfg.offC)||!finite(cfg.minC)||!finite(cfg.maxC)||
       !finite(cfg.offsetC)||!finite(cfg.writeIntervalS)||
       !finite(cfg.epsilonC)||!finite(cfg.upCPerMin)||
       !finite(cfg.downCPerMin)||!finite(cfg.dhwUpCPerMin)||
       !finite(cfg.releaseHoldS)||cfg.minC>=cfg.maxC)
        throw new Error('Iset source: as-built OT policy required');
    var lastAt=null,ramp=null,lastWritten=null,writeAt=null,
        high=null,releaseAt=null,flamePreviously=null,flameStarts=[];
    return {
        step:function(f){
            if(!f||!finite(f.nowS)||f.nowS<0||
               typeof f.otConnectionInvalid!=='boolean'||
               typeof f.equipmentAllowsHeat!=='boolean')
                throw new Error('Iset source: explicit OT and protection state required');
            if(lastAt!==null&&f.nowS<lastAt){
                ramp=null;high=null;releaseAt=null;
                lastWritten=null;writeAt=null;flameStarts=[];
            }
            var dt=lastAt===null?0:clamp(f.nowS-lastAt,0,10);
            lastAt=f.nowS;
            if(flamePreviously===false&&f.flame===true)
                flameStarts.push(f.nowS);
            flamePreviously=f.flame===true?true:
                f.flame===false?false:null;
            while(flameStarts.length&&flameStarts[0]<f.nowS-3600)
                flameStarts.shift();
            var connected=f.otConnectionInvalid===false;
            var requested=finite(f.sourceRequestedC)&&
                f.sourceRequestedC>=35&&f.sourceRequestedC<=82?
                f.sourceRequestedC:null;
            var allow=connected&&f.equipmentAllowsHeat===true;
            var off=!allow||requested===null;
            var priority=f.dhwPriorityPause===true;
            var target=off?cfg.offC:
                clamp(requested+cfg.offsetC,cfg.minC,cfg.maxC);
            if(off){ramp=cfg.offC;high=null;releaseAt=null;}
            else{
                if(high===null||target>=high){
                    high=target;releaseAt=null;
                }else{
                    if(releaseAt===null)releaseAt=f.nowS;
                    if(f.nowS-releaseAt<cfg.releaseHoldS)target=high;
                    else{high=target;releaseAt=null;}
                }
                if(ramp===null||ramp<cfg.minC)ramp=cfg.minC;
                var up=priority?cfg.dhwUpCPerMin:cfg.upCPerMin;
                ramp=clamp(ramp+clamp(target-ramp,
                    -cfg.downCPerMin*dt/60,up*dt/60),
                    cfg.minC,cfg.maxC);
            }
            var command=Math.round(ramp*10)/10;
            var writeAllowed=connected&&
                (off?f.offMethodCommissioned===true:
                    f.equipmentAllowsHeat===true);
            var urgent=off||priority;
            var due=writeAt===null||
                f.nowS-writeAt>=cfg.writeIntervalS;
            var changed=lastWritten===null||
                Math.abs(command-lastWritten)>=cfg.epsilonC;
            var write=writeAllowed&&(urgent||due)&&changed;
            return {
                state:!connected?'OT_LINK_INVALID':
                    !f.equipmentAllowsHeat?'EQUIPMENT_PROTECTION':
                    requested===null?'NO_DEMAND':'HEAT_REQUESTED',
                targetC:command,
                desiredWrite:write?{path:'wbe2-i-opentherm_11/Heating Setpoint',
                    value:command}:null,
                offRequired:off,
                writeAllowed:writeAllowed,
                flameStartsHour:flameStarts.length,
                releaseRemainingS:releaseAt===null?null:
                    Math.max(0,cfg.releaseHoldS-(f.nowS-releaseAt)),
                reason:!connected?'OT_DISCONNECTED':
                    !allow?'EQUIPMENT_PROTECTION':
                    requested===null?'NO_DEMAND':'SOURCE_REQUEST'
            };
        },
        // Call only after real output adapter confirms write accepted.
        acknowledge:function(nowS,command){
            if(!finite(nowS)||!finite(command))return false;
            lastWritten=command;writeAt=nowS;return true;
        }
    };
};
