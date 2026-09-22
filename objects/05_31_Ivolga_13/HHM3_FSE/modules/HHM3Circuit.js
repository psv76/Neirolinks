/* HHM3 mixed circuit: local temperature policy, independent of MQTT IO.
 * The caller owns channel writes. Temperature protections remain authoritative.
 */
function finite(v) {return typeof v==='number'&&isFinite(v);}
function valveConfig(c) {
    return finite(c.valveActiveMinLevel)&&finite(c.valveActiveMaxLevel)&&
        c.valveActiveMinLevel>0&&c.valveActiveMaxLevel<=100&&
        c.valveActiveMinLevel<c.valveActiveMaxLevel&&c.valveOffCommand===false;
}
exports.create=function(c,storage,Mixing){
    ['normalSupplyC','maxSupplyC','autonomousSupplyC','supplyCloseC','supplyStopC',
     'supplyImmediateStopC','floorCloseC','floorStopC','floorTargetMaxC',
     'supplyHysteresisC','floorHysteresisC','periodMs','closeObserveMs','coolStableMs',
     'circulationCheckMs','postrunMs','responseMs','responseRiseC','sourceMarginC',
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
    var mix,mode='',position=0,lastNow=null;
    var closeAt=null,coolAt=null,coolSupplyAt=null,coolFloorAt=null;
    var closeFloorSession=0,closeFloorSeq=0;
    var idleAt=null,floorStepAt=null,responseAt=null,baseline=null;
    function newMixer(){
        var t={},k;
        for(k in c.tuning)if(Object.prototype.hasOwnProperty.call(c.tuning,k))t[k]=c.tuning[k];
        t.hardMaxC=c.supplyCloseC;
        mix=Mixing.create({initialValvePositionPct:0,tuning:t},{
            writeValvePosition:function(pct){position=pct;return true;},
            writeValveEnable:function(){return true;}
        });
        position=0;
    }
    newMixer();
    function resetTiming(){
        closeAt=null;coolAt=null;idleAt=null;floorStepAt=null;
        responseAt=null;baseline=null;newMixer();
    }
    function result(reason,pump,demand,target,valve,warning){
        return {reason:reason,pump:pump,demand:demand,target:target,
            valve:valve,warning:warning||'',write:valveConfig(c),
            valid:demand||reason==='NO_DEMAND'};
    }
    return {
        reset:resetTiming,
        step:function(i){
            var now=i.now,f=i.frame,supply=i.supply,floor=f?f.floor:null;
            if(lastNow!==null&&(now<lastNow||now-lastNow>c.periodMs*3))resetTiming();
            lastNow=now;
            if(!valveConfig(c))return result('VALVE_CONFIG_MISSING',false,false,0,0);
            var hotSupply=supply!==null&&supply>=c.supplyCloseC;
            var hotFloor=floor!==null&&floor>=c.floorCloseC;
            if(hotSupply)storage.supplyProtection=true;
            if(hotFloor)storage.floorProtection=true;
            var observed=closeAt!==null&&now-closeAt>=c.closeObserveMs;
            if((supply!==null&&supply>=c.supplyImmediateStopC)||
               (observed&&((supply!==null&&supply>=c.supplyStopC&&i.supplyAt>closeAt)||
               (floor!==null&&floor>=c.floorStopC&&(f.session_id>closeFloorSession||
               (f.session_id===closeFloorSession&&f.seq>closeFloorSeq))))))storage.thermalStop=true;
            if(storage.supplyProtection||storage.floorProtection||storage.thermalStop){
                if(closeAt===null){
                    closeAt=now;closeFloorSession=f?f.session_id:0;closeFloorSeq=f?f.seq:0;
                }
                var cooled=(!storage.supplyProtection||(supply!==null&&supply<=c.supplyCloseC-c.supplyHysteresisC))&&
                    (!storage.floorProtection||(floor!==null&&floor<=c.floorCloseC-c.floorHysteresisC));
                if(!cooled)coolAt=null;
                else if(coolAt===null){coolAt=now;coolSupplyAt=i.supplyAt;coolFloorAt=f?f.sent_ms:null;}
                var newSamples=(!storage.supplyProtection||i.supplyAt>coolSupplyAt)&&
                    (!storage.floorProtection||(f&&f.sent_ms>coolFloorAt));
                if(cooled&&newSamples&&now-coolAt>=c.coolStableMs){
                    storage.supplyProtection=false;storage.floorProtection=false;storage.thermalStop=false;
                    resetTiming();
                }else{
                    newMixer();
                    return result(storage.thermalStop?'OVERHEAT_STOP':'OVERHEAT_CLOSE',
                        !storage.thermalStop,false,0,0,'Перегрев: горячий подмес закрыт'+
                        (storage.thermalStop?', насос остановлен':', насос циркулирует'));
                }
            }
            closeAt=null;
            if(supply===null&&floor===null){
                newMixer();
                return result('NO_FEEDBACK_UNCOVERED',true,false,0,0,
                    'Нет подачи и пола: подмес закрыт, рециркуляция; защита от замерзания не обеспечена');
            }
            var remoteValid=!!(f&&f.valid&&f.enabled===true);
            var demand=remoteValid?f.demand:true;
            var target=Math.min(c.maxSupplyC,remoteValid?c.normalSupplyC:c.autonomousSupplyC);
            var nextMode=supply===null?'FLOOR_ONLY':(remoteValid?'NORMAL':'AUTONOMOUS');
            var warning=remoteValid?'':('Автономия: '+(f?f.reason:i.linkReason));
            var modeChanged=nextMode!==mode;
            if(modeChanged){newMixer();floorStepAt=null;mode=nextMode;}
            if(!demand){
                if(idleAt===null){
                    idleAt=now;
                    if(!modeChanged)newMixer(); // once on demand loss, not every idle tick
                }
                responseAt=null;
                return result('NO_DEMAND',now-idleAt<c.postrunMs,false,0,0);
            }
            idleAt=null;
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
                position=mix.step({now:now/1000,enabled:true,pumpOn:true,
                    supplyTempC:supply,sourceTempC:i.source,targetC:target,sensorOffsetC:0,
                    valveEnableOn:true,phaseMode:'auto',freeze:false,manualValvePct:0}).valvePositionPct;
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
