/* 05 16 Iset: independent heating requests & simple source arbitration.
 * Pure ES5. HA is not a runtime dependency. No physical writes.
 * Floor request MUST be supplied by commissioned independent mixer.
 */
function finite(n){return typeof n==='number'&&isFinite(n);}
function clamp(v,a,b){return Math.max(a,Math.min(v,b));}
function outdoorBase(t){
    if(!finite(t))return null;
    return t>=0?48-clamp(t,0,10):
        t>=-10?48-t:58+clamp(-t-10,0,15)*10/15;
}
exports.create=function(cfg){
    if(!cfg||!cfg.basement||!finite(cfg.basement.targetC)||
       !finite(cfg.basement.hysteresisC))
        throw new Error('Iset demand: basement policy required');
    var basementHeat=null,lastOutdoor=null,lastBasementMin=null;
    return {
        step:function(f){
            if(!f||!f.livingDemands||!f.dhw||
               typeof f.floorCommissioned!=='boolean')
                throw new Error('Iset demand: service request frame required');
            var living=false,knownLiving=0,k;
            for(k in f.livingDemands){
                if(!Object.prototype.hasOwnProperty.call(f.livingDemands,k))continue;
                if(f.livingDemands[k]===true)living=true;
                if(f.livingDemands[k]===true||f.livingDemands[k]===false)
                    knownLiving++;
            }
            if(finite(f.outdoorC)&&f.outdoorC>=-60&&f.outdoorC<=60)
                lastOutdoor=f.outdoorC;
            var base=outdoorBase(lastOutdoor);
            var bs=f.basementTemps||[],bmin=null,validCount=0;
            for(var i=0;i<bs.length;i++){
                if(finite(bs[i])&&bs[i]>=-10&&bs[i]<=50){
                    bmin=bmin===null?bs[i]:Math.min(bmin,bs[i]);
                    validCount++;
                }
            }
            if(bmin!==null){
                lastBasementMin=bmin;
                if(bmin<cfg.basement.targetC-cfg.basement.hysteresisC)
                    basementHeat=true;
                else if(validCount===bs.length&&
                        bmin>cfg.basement.targetC+cfg.basement.hysteresisC)
                    basementHeat=false;
            }
            var floor=!!(f.floorCommissioned===true&&f.floor&&
                f.floor.demand===true);
            var requests={
                living:living&&base!==null?clamp(base,35,75):null,
                basement:basementHeat===true&&base!==null&&lastBasementMin!==null?
                    clamp(base+clamp(2*(cfg.basement.targetC-lastBasementMin),0,6),35,75):null,
                floor:floor&&finite(f.floor.requestC)?
                    clamp(f.floor.requestC,35,60):null,
                dhw:f.dhw.demand===true&&finite(f.dhw.requestSupplyC)?
                    f.dhw.requestSupplyC:null
            };
            var pause=f.dhw.pauseSpaceHeating===true;
            var grants={living:'NO_DEMAND',basement:'NO_DEMAND',
                floor:'NOT_COMMISSIONED',dhw:'NO_DEMAND'};
            var highest=null,winner='NONE';
            for(var id in requests){
                if(!Object.prototype.hasOwnProperty.call(requests,id))continue;
                if(id==='floor'&&f.floorCommissioned!==true)continue;
                if(id==='living'&&!living&&knownLiving===0)
                    grants[id]='UNKNOWN'; 
                if(id==='basement'&&lastBasementMin===null)
                    grants[id]='UNKNOWN';
                if(requests[id]===null)continue;
                if(pause&&id!=='dhw'){
                    grants[id]='DHW_PRIORITY_PAUSE';
                    continue;
                }
                grants[id]='REQUESTED';
                if(highest===null||requests[id]>highest){
                    highest=requests[id];winner=id;
                }
            }
            return {sourceRequestedC:highest,winner:winner,
                grants:grants,dhwPriorityPause:pause,
                livingHeatDemand:living,
                basementHeatDemand:basementHeat,
                basementMinimumC:bmin,basementValidSensors:validCount,
                basementLastObservedMinC:lastBasementMin,
                basementLastValueHeld:bmin===null&&lastBasementMin!==null,
                floorCommissioned:f.floorCommissioned,
                reason:highest===null?'NO_SOURCE_REQUEST':pause?
                    'DHW_CONDITIONAL_PRIORITY':'PARALLEL_HEATING',
                // Room actuator decisions are still independent of
                // source temperature and DHW authorization.
                livingDemands:f.livingDemands};
        }
    };
};
