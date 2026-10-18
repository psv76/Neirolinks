/* Iset HHM: autonomous DHW priority, K1 pump intent and timing.
 * Pure WB ES5 model. No HA, no physical commands.
 * Ported behavior from 24_heating_dhw_manager.js, 18.10.2026.
 */
function finite(n){return typeof n==='number'&&isFinite(n);}
function valid(t){return finite(t)&&t>=0&&t<=85;}
function priorityLimit(outdoor){
    if(!finite(outdoor)||outdoor<=-20)return 900;
    if(outdoor>=10)return 2700;
    return 900+(outdoor+20)*60;
}
exports.create=function(cfg){
    if(!cfg||!finite(cfg.targetC)||!finite(cfg.hysteresisC)||
       !finite(cfg.triggerC)||!finite(cfg.timeoutS)||!finite(cfg.reliefS)||
       !finite(cfg.overrunS)||!finite(cfg.marginC)||
       !finite(cfg.priorityMarginC)||!finite(cfg.recoveryS)||
       cfg.targetC<=cfg.hysteresisC||cfg.timeoutS<=0||
       cfg.recoveryS<0||cfg.policy!=='CONDITIONAL')
        throw new Error('Iset DHW: as-built policy required');
    var demand=false,start=null,startTemp=null,priorityAt=null,
        reliefUntil=0,overrunUntil=0,fault=false,boost=false,
        lastAt=null,recoveredAt=null,runObservedAt=null,prevPump=null;
    function clamp(v,lo,hi){return Math.max(lo,Math.min(hi,v));}
    return {
        boost:function(){boost=true;},
        reset:function(){
            if(fault){fault=false;start=null;startTemp=null;
                priorityAt=null;reliefUntil=0;overrunUntil=0;boost=false;
                recoveredAt=null;}
        },
        step:function(i){
            if(!i||!finite(i.nowS)||i.nowS<0)
                throw new Error('Iset DHW: time required');
            if(lastAt!==null&&i.nowS<lastAt){
                // Clock regression resets transient timing; NO automatic
                // reset of a latched total-timeout fault.
                demand=false;start=null;startTemp=null;priorityAt=null;
                reliefUntil=0;overrunUntil=0;recoveredAt=null;boost=false;
                runObservedAt=null;prevPump=null;
            }
            lastAt=i.nowS;
            if(i.pumpReadback===true){
                if(prevPump!==true)runObservedAt=i.nowS;
            }else runObservedAt=null;
            prevPump=i.pumpReadback;
            var tank=valid(i.tankC)?i.tankC:null;
            if(tank===null)recoveredAt=null;
            else if(recoveredAt===null)recoveredAt=i.nowS;
            var ready=tank!==null&&
                i.nowS-recoveredAt>=cfg.recoveryS;
            var was=demand,pause=false,mode='IDLE',reason='SENSOR_UNKNOWN';
            if(!ready||fault){
                // Local fault suppresses DHW K1 only; do NOT veto rooms.
                demand=false;start=null;startTemp=null;priorityAt=null;
                overrunUntil=0;reliefUntil=0;
                // A deliberate local BOOST pressed during sensor recovery
                // must not disappear before the tank is available.
                if(fault)boost=false;
                reason=fault?'DHW_TIMEOUT_LATCHED':'TANK_NOT_READY';
            }else{
                if(tank<=cfg.targetC-cfg.hysteresisC||
                   boost&&tank<cfg.targetC)demand=true;
                if(tank>=cfg.targetC)demand=false;
                if(demand&&start===null){start=i.nowS;startTemp=tank;}
                if(demand&&i.nowS-start>=cfg.timeoutS){
                    fault=true;demand=false;
                }
                if(!demand){
                    if(was&&!fault)overrunUntil=i.nowS+cfg.overrunS;
                    start=null;startTemp=null;priorityAt=null;boost=false;
                }
                reason=fault?'DHW_TIMEOUT_LATCHED':'TANK_THERMOSTAT';
            }
            var elapsed=start===null?0:i.nowS-start;
            var rise=tank===null||startTemp===null?0:tank-startTemp;
            var forecastSlow=elapsed>=900&&rise>0&&
                (cfg.targetC-tank)*elapsed/rise>2700;
            var priorityWanted=demand&&
                (tank<=cfg.triggerC||boost||forecastSlow);
            var remaining=null;
            if(priorityWanted&&i.nowS>=reliefUntil){
                if(priorityAt===null)priorityAt=i.nowS;
                var limit=priorityLimit(i.outdoorC);
                if(i.nowS-priorityAt>=limit){
                    priorityAt=null;reliefUntil=i.nowS+cfg.reliefS;
                }else{
                    pause=true;mode='ACCELERATED';
                    remaining=limit-(i.nowS-priorityAt);
                }
            }else priorityAt=null;
            if(demand&&!pause)mode='SUPPORT';
            var pumpWanted=demand;
            var overrunRemaining=null;
            if(!demand&&!fault&&ready&&i.nowS<overrunUntil&&
               finite(i.commonC)&&i.commonC>=5&&tank!==null&&
               i.commonC-tank>=7&&i.sourceAvailable===true){
                pumpWanted=true;mode='OVERRUN';
                overrunRemaining=overrunUntil-i.nowS;
            }
            // No pump source authorization is fabricated from missing link.
            // Pump intent is made here; source-authorized writer applies it.
            return {state:fault?'FAULT':!ready?'UNKNOWN':
                    demand?'ACTIVE':'INACTIVE',
                reason:reason,mode:mode,demand:demand,
                pauseSpaceHeating:pause,
                requestSupplyC:demand?
                    clamp(cfg.targetC+(pause?
                        cfg.priorityMarginC:cfg.marginC),55,80):null,
                pumpWanted:pumpWanted,
                priorityRemainingS:remaining,
                reliefRemainingS:i.nowS<reliefUntil?
                    reliefUntil-i.nowS:null,
                heatingElapsedS:elapsed,
                overrunRemainingS:overrunRemaining,
                pumpObservedRunS:runObservedAt===null?null:
                    i.nowS-runObservedAt,
                faultLatched:fault};
        }
    };
};
