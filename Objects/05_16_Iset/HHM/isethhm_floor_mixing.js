/* Iset HHM: physical-writer-injectable MAO4 floor mixing controller.
 * Reuses Systems/HHM/core/HHM3Mixing (approved generic algorithm).
 * Tuning is transcribed from WB 21_heating_floor_manager.js snapshot
 * 18.10.2026, NOT values from Ivolga. No default boiler ownership.
 * A caller must supply an actual write function and independently
 * qualify source protection and K2 hydraulic path.
 */
function finite(x){return typeof x==='number'&&isFinite(x);}
exports.tuning=function(){
    return {
        bandC:1,biasC:0,farErrorC:2.5,
        fastHoldColdS:60,fastHoldHotS:60,
        fastMinStepPct:2,fastMaxStepPct:5,
        trimHoldColdS:90,trimHoldHotS:90,
        trimMinStepPct:1,trimMaxStepPct:2,
        pctPerCCold:2,pctPerCHot:1.5,
        reverseLockS:60,trendOkCPerMin:0.35,
        trendSlowCPerMin:0.12,stagnationS:600,
        postMoveSettleS:30,
        minPosPct:0,maxPosPct:45,hardMaxC:45,
        supplyValidMinC:10,supplyValidMaxC:60,
        sensorBadLimit:3,sourceGuardEnabled:true,
        sourceMarginC:2,
        sourceValidMinC:5,sourceValidMaxC:95,
        startupCapEnabled:true,startupDurationS:2400,
        startupMaxPosPct:45,enableRetryS:60,
        safeCloseOnDisable:true
    };
};
exports.create=function(Mixing,io){
    if(!Mixing||typeof Mixing.create!=='function'||!io||
       typeof io.writePosition!=='function'||
       typeof io.writeEnable!=='function')
        throw new Error('Iset floor mixing: approved core + IO required');
    var mix=Mixing.create({
        tuning:exports.tuning(),initialValvePositionPct:0
    },{
        writeValvePosition:function(pct){
            return io.writePosition(pct)===true;
        },
        writeValveEnable:function(enabled){
            return io.writeEnable(enabled)===true;
        }
    });
    return {
        step:function(f){
            if(!f||!finite(f.nowS)||f.nowS<0||
               typeof f.enabled!=='boolean'||
               typeof f.pumpReadback!=='boolean')
                throw new Error('Iset floor mixing: explicit WB input');
            // This threshold was already adopted as the HM2 preventive
            // close stage. Do not turn 40C into a global K2 shutdown.
            var preventive=finite(f.supplyC)&&f.supplyC>=40;
            var state=mix.step({
                now:f.nowS,enabled:f.enabled&&!preventive,
                pumpOn:f.pumpReadback,
                supplyTempC:finite(f.supplyC)?f.supplyC:null,
                sourceTempC:finite(f.sourceC)?f.sourceC:null,
                targetC:finite(f.targetC)?f.targetC:null,
                sensorOffsetC:0,
                valveEnableOn:f.valveEnableReadback===true,
                phaseMode:'auto',freeze:false,manualValvePct:0
            });
            return {state:preventive?'HOT_PORT_PREVENTIVE_CLOSE':
                    state.status,
                targetC:finite(f.targetC)?f.targetC:null,
                valvePositionPct:state.valvePositionPct,
                phase:state.phase,sourceGuard:state.sourceGuardActive,
                startupRemainingS:state.startupRemainingS,
                preventiveClose:preventive,
                hardStopFromSupply:finite(f.supplyC)&&f.supplyC>=45,
                sensorAlarm:state.alarmActive};
        },
        reset:function(o){mix.reset(o||{});}
    };
};
