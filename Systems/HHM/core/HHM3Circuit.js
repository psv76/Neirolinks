/* HHM3 mixed circuit: local temperature policy, independent of MQTT IO.
 * The caller owns channel writes. Temperature protections remain authoritative.
 */
function finite(v) {return typeof v==='number'&&isFinite(v);}
function valveConfig(c) {
    return finite(c.valveActiveMinLevel)&&finite(c.valveActiveMaxLevel)&&
        c.valveActiveMinLevel>0&&c.valveActiveMaxLevel<=100&&
        c.valveActiveMinLevel<c.valveActiveMaxLevel&&c.valveOffCommand===false;
}
exports.create=function(c,storage,Mixing,SensorLossPolicy){
    ['normalSupplyC','maxSupplyC','autonomousSupplyC','supplyCloseC','supplyStopC',
     'supplyImmediateStopC','floorCloseC','floorStopC','floorTargetMaxC',
     'supplyHysteresisC','floorHysteresisC','periodMs','closeObserveMs','coolStableMs',
     'circulationCheckMs','postrunMs','pumpPostrunMs','responseMs','responseRiseC','sourceMarginC',
     'floorStepPct','floorStepMs','requestTtlS'].forEach(function(k){
        if(!finite(c[k])||c[k]<0)throw new Error('504 invalid config: '+k);
    });
    if(!(c.normalSupplyC<=c.maxSupplyC&&c.autonomousSupplyC<=c.maxSupplyC&&
         c.maxSupplyC<c.supplyCloseC&&c.supplyCloseC<c.supplyStopC&&
         c.supplyStopC<c.supplyImmediateStopC&&c.floorTargetMaxC<c.floorCloseC&&
         c.floorCloseC<c.floorStopC&&c.periodMs>0&&c.requestTtlS>c.periodMs/1000&&
         c.requestTtlS<=15&&c.coolStableMs>=c.periodMs&&
         c.supplyHysteresisC>0&&c.floorHysteresisC>0&&
         c.floorStepMs>=c.periodMs&&c.floorStepPct>0&&c.floorStepPct<=100))
        throw new Error('504 inconsistent temperature/timing config');
    // Optional until the object supplies independent safety and valve evidence.
    // Existing approved circuits remain on their unchanged legacy path.
    if(c.sensorLossPolicy && (!SensorLossPolicy || typeof SensorLossPolicy.create!=='function'))
        throw new Error('Sensor loss policy module is required for opt-in circuit');
    var lossPolicy=c.sensorLossPolicy?SensorLossPolicy.create(c.sensorLossPolicy):null;
    var lossState='',lastMixing=null;
    var mix,mode='',position=0,lastNow=null;
    var closeAt=null,coolAt=null,coolSupplyAt=null,coolFloorAt=null;
    var closeFloorSession=0,closeFloorSeq=0;
    var idleAt=null,floorStepAt=null,responseAt=null,baseline=null,zonalRunning=false;
    function newMixer(){
        var t={},k;
        for(k in c.tuning)if(Object.prototype.hasOwnProperty.call(c.tuning,k))t[k]=c.tuning[k];
        t.hardMaxC=c.supplyCloseC;
        mix=Mixing.create({initialValvePositionPct:0,tuning:t},{
            writeValvePosition:function(pct){position=pct;return true;},
            writeValveEnable:function(){return true;}
        });
        position=0;
        lastMixing=mix.snapshot();
    }
    newMixer();
    function resetTiming(){
        closeAt=null;coolAt=null;idleAt=null;floorStepAt=null;
        responseAt=null;baseline=null;newMixer();
        if(lossPolicy){lossPolicy.reset();lossState='';}
        zonalRunning=false;
    }
    function result(reason,pump,demand,target,valve,warning){
        var r={reason:reason,pump:pump,demand:demand,target:target,
            valve:valve,warning:warning||'',write:valveConfig(c),
            valid:demand||reason==='NO_DEMAND'};
        // Output adapters may expose this snapshot in operator diagnostics.
        // A virtual mixer acceptance is NOT proof of physical valve travel.
        if(lastMixing)r.mixing=lastMixing;
        if(lossPolicy){r.sensorLossState=lossState;r.valveAction='APPLY';}
        return r;
    }
    return {
        reset:resetTiming,
        step:function(i){
            var now=i.now,f=i.frame,supply=i.supply,floor=f?f.floor:null;
            if(lastNow!==null&&(now<lastNow||now-lastNow>c.periodMs*3))resetTiming();
            lastNow=now;
            if(!valveConfig(c))return result('VALVE_CONFIG_MISSING',false,false,0,0);
            // A broken numeric sample is not proven thermal feedback.
            // Legacy circuits retain their original semantics unchanged.
            var supplyQualified=!lossPolicy||(i.sensorValid===true&&finite(supply)&&
                supply>=c.tuning.supplyValidMinC&&supply<=c.tuning.supplyValidMaxC);
            var guardSupply=supplyQualified?supply:null;
            var hotSupply=guardSupply!==null&&guardSupply>=c.supplyCloseC;
            var hotFloor=floor!==null&&floor>=c.floorCloseC;
            if(hotSupply)storage.supplyProtection=true;
            if(hotFloor)storage.floorProtection=true;
            var observed=closeAt!==null&&now-closeAt>=c.closeObserveMs;
            if((guardSupply!==null&&guardSupply>=c.supplyImmediateStopC)||
               (observed&&((guardSupply!==null&&guardSupply>=c.supplyStopC&&i.supplyAt>closeAt)||
               (floor!==null&&floor>=c.floorStopC&&(f.session_id>closeFloorSession||
               (f.session_id===closeFloorSession&&f.seq>closeFloorSeq))))))storage.thermalStop=true;
            if(storage.supplyProtection||storage.floorProtection||storage.thermalStop){
                if(closeAt===null){
                    closeAt=now;closeFloorSession=f?f.session_id:0;closeFloorSeq=f?f.seq:0;
                }
                var cooled=(!storage.supplyProtection||(guardSupply!==null&&guardSupply<=c.supplyCloseC-c.supplyHysteresisC))&&
                    (!storage.floorProtection||(floor!==null&&floor<=c.floorCloseC-c.floorHysteresisC));
                if(!cooled)coolAt=null;
                else if(coolAt===null){coolAt=now;coolSupplyAt=i.supplyAt;coolFloorAt=f?f.sent_ms:null;}
                var newSamples=(!storage.supplyProtection||i.supplyAt>coolSupplyAt)&&
                    (!storage.floorProtection||(f&&f.sent_ms>coolFloorAt));
                if(cooled&&newSamples&&now-coolAt>=c.coolStableMs){
                    storage.supplyProtection=false;storage.floorProtection=false;storage.thermalStop=false;
                    resetTiming();
                }else{
                    if(lossPolicy){lossPolicy.reset();lossState='PROTECTION';}
                    newMixer();
                    return result(storage.thermalStop?'OVERHEAT_STOP':'OVERHEAT_CLOSE',
                        !storage.thermalStop,false,0,0,'Перегрев: горячий подмес закрыт'+
                        (storage.thermalStop?', команда насосу ВЫКЛ':', команда насосу ВКЛ; расход не измеряется'));
                }
            }
            closeAt=null;
            if(!lossPolicy&&supply===null&&floor===null){
                if(typeof i.zoneReady==='boolean')resetTiming();
                newMixer();
                return result('NO_FEEDBACK_UNCOVERED',true,false,0,0,
                    'Нет подачи и пола: подмес закрыт, рециркуляция; защита от замерзания не обеспечена');
            }
            // Зональный выбег начинается только после реального рабочего цикла.
            // Ожидающий новый путь сам по себе не запускает насос из простоя.
            if(typeof i.zoneReady==='boolean'){
                if(!i.zoneReady&&i.zoneSafe===false){resetTiming();return result('ZONE_UNSAFE',false,false,0,0);}
                if(!i.zoneReady){
                    if(idleAt===null&&i.pumpWasOn!==true)zonalRunning=false;
                    if(zonalRunning&&idleAt===null)idleAt=now;
                    if(zonalRunning&&now-idleAt<c.pumpPostrunMs){
                        var post=result('PUMP_POSTRUN',true,false,0,0);
                        post.valid=true;post.stopRemainingMs=c.pumpPostrunMs-(now-idleAt);
                        return post;
                    }
                    if(zonalRunning)resetTiming();
                    return result('NO_DEMAND',false,false,0,0);
                }
                // READY в момент или после срока — уже следующий холодный пуск.
                if(idleAt!==null&&now-idleAt>=c.pumpPostrunMs)resetTiming();
                idleAt=null;zonalRunning=true;
            }
            var remoteValid=!!(f&&f.valid&&f.enabled===true);
            var demand=remoteValid?f.demand:true;
            var target=Math.min(c.maxSupplyC,remoteValid?c.normalSupplyC:c.autonomousSupplyC);
            var nextMode=lossPolicy?(remoteValid?'NORMAL':'AUTONOMOUS'):
                (supply===null?'FLOOR_ONLY':(remoteValid?'NORMAL':'AUTONOMOUS'));
            var warning=remoteValid?'':('Местное управление: внешний запрос недостоверен; код причины '+(f?f.reason:i.linkReason));
            var modeChanged=nextMode!==mode;
            if(modeChanged){if(!lossPolicy)newMixer();floorStepAt=null;mode=nextMode;}
            if(!demand){
                if(lossPolicy){lossPolicy.reset();lossState='';}
                if(idleAt===null){
                    idleAt=now;
                    if(lossPolicy||!modeChanged)newMixer(); // once on demand loss, not every idle tick
                }
                responseAt=null;
                var idle=result('NO_DEMAND',now-idleAt<c.postrunMs,false,0,0);
                if(idle.pump)idle.stopRemainingMs=c.postrunMs-(now-idleAt);
                return idle;
            }
            idleAt=null;
            if(lossPolicy){
                // Strict opt-in: no default "safe" permits inferred from missing
                // inputs. These booleans must be computed by the object adapter.
                if(i.valveActionSupported!==true)
                    throw new Error('Sensor loss requires HOLD-aware single output writer');
                if(typeof i.sensorValid!=='boolean' ||
                   typeof i.hydraulicPathReady!=='boolean' ||
                   typeof i.fallbackAuthorized!=='boolean' ||
                   typeof i.independentLimitOk!=='boolean')
                    throw new Error('Missing explicit sensor-loss safety/health input');
                var sensorQualifiedNow=i.sensorValid===true&&finite(supply)&&
                    supply>=c.tuning.supplyValidMinC&&
                    supply<=c.tuning.supplyValidMaxC;
                var previousLossState=lossState;
                var lp=lossPolicy.step({nowMs:now,sensorValid:sensorQualifiedNow,
                    heatRequested:demand,hydraulicPathReady:i.hydraulicPathReady,
                    protectionActive:i.protectionActive===true,
                    acceptedValveConfirmed:i.acceptedValveConfirmed===true,
                    acceptedValvePct:i.acceptedValvePct,
                    fallbackAuthorized:i.fallbackAuthorized,
                    independentLimitOk:i.independentLimitOk});
                lossState=lp.state;
                if(lp.state!=='NORMAL'){
                    var heat=lp.heatDemand===true;
                    // Uncertain fallback is not a fictitious source demand or
                    // an instruction to shut down an already circulating pump.
                    var keepPump=i.hydraulicPathReady===true &&
                        (heat || (lp.heatDemand===null&&i.pumpWasOn===true));
                    var degraded=result(lp.state,keepPump,heat,heat?target:0,
                        lp.valvePct,lp.reason);
                    degraded.valveAction=lp.commandValve?'APPLY':
                        (lp.valvePct===null?'NO_COMMAND':'HOLD');
                    degraded.sensorLossSinceMs=lp.sensorLostSinceMs;
                    if(lp.valvePct===null){degraded.valid=false;degraded.write=false;}
                    return degraded;
                }
                if(previousLossState&&previousLossState!=='NORMAL'){
                    // Resume the mixer without a cold-start reset. A verified
                    // accepted output is mandatory before reconciling position.
                    if(i.acceptedValveConfirmed!==true||!finite(lp.lastAcceptedValvePct))
                        throw new Error('Cannot resume mixer without accepted valve evidence');
                    lastMixing=mix.resumeAfterSensorGap(lp.lastAcceptedValvePct);
                    position=lp.lastAcceptedValvePct;
                }
            }
            // Do not run a minute-long pump-only phase against a commanded
            // closed hot port. Start temperature regulation as soon as demand
            // and sensors allow it; thermal protections above remain intact.
            if(nextMode==='FLOOR_ONLY'){
                if(!finite(c.floorOnlyMaxPct)||c.floorOnlyMaxPct<=0||c.floorOnlyMaxPct>100){
                    return result('FLOOR_CAP_UNMEASURED',true,false,0,0,
                        'Нет проверенного предела открытия клапана по полу');
                }
                var floorTarget=remoteValid?(f.mode==='HEAT'?f.heat:f.hold):c.floorTargetMaxC-1;
                if(floor>=floorTarget)position=0;
                else if(floorStepAt===null||now-floorStepAt>=c.floorStepMs){
                    position=Math.min(c.floorOnlyMaxPct,position+c.floorStepPct);floorStepAt=now;
                }
                warning='Отказ датчика подачи: ограничение по полу, температура подачи не измеряется';
            }else{
                lastMixing=mix.step({now:now/1000,enabled:true,pumpOn:true,
                    supplyTempC:supply,sourceTempC:i.source,targetC:target,sensorOffsetC:0,
                    valveEnableOn:true,phaseMode:'auto',freeze:false,manualValvePct:0});
                position=lastMixing.valvePositionPct;
            }
            if(i.source===null||i.ret===null)warning+='; нет свежего 411/419';
            if(i.source!==null&&i.source<target)warning+='; источник ещё холодный';
            var responseTemp=supply!==null?supply:floor;
            if(responseAt===null){responseAt=now;baseline=responseTemp;}
            if(responseTemp>=target-1||responseTemp>=baseline+c.responseRiseC){
                responseAt=now;baseline=responseTemp;
            }else if(now-responseAt>=c.responseMs)warning+='; NO_RESPONSE: нет роста температуры, расход не измерен';
            return result(nextMode,true,true,target,position,warning);
        }
    };
};
