/* HHM local room thermostat: WB-authoritative settings and demand.
 * Pure ES5 decision module. Physical sensors, source and actuators belong to
 * the object adapter. Never use upper-level UI availability as heat demand.
 */
function finite(v) {return typeof v==='number'&&isFinite(v);}
function id(v) {return typeof v==='string'&&v.length>0&&v.length<=100;}
function integer(v) {return finite(v)&&Math.floor(v)===v&&v>=0;}
function copy(s) {return {mode:s.mode,setpointC:s.setpointC,revision:s.revision,
    lastIntentId:s.lastIntentId||null};}
function settingsValid(s,c) {
    return s&&(s.mode==='HEAT'||s.mode==='OFF')&&
        finite(s.setpointC)&&s.setpointC>=c.minSetpointC&&
        s.setpointC<=c.maxSetpointC&&integer(s.revision)&&
        (s.lastIntentId===null||s.lastIntentId===undefined||id(s.lastIntentId));
}

exports.create=function(c,store){
    if(!c||!id(c.zoneId)||!id(c.primarySensorId)||
       (c.backupSensorId!==null&&c.backupSensorId!==undefined&&
        (!id(c.backupSensorId)||c.backupSensorId===c.primarySensorId))||
       !finite(c.minSetpointC)||!finite(c.maxSetpointC)||
       c.maxSetpointC<=c.minSetpointC||
       !finite(c.hysteresisC)||c.hysteresisC<=0||
       !finite(c.minMeasuredC)||!finite(c.maxMeasuredC)||
       c.maxMeasuredC<=c.minMeasuredC||
       !finite(c.sensorFreshMs)||c.sensorFreshMs<=0||
       !finite(c.recoveryStableMs)||c.recoveryStableMs<0||
       !integer(c.recoverySamples)||c.recoverySamples<2||
       !finite(c.commandMaxAgeMs)||c.commandMaxAgeMs<=0||
       (c.sensorLossHoldMs!==undefined&&
        (!finite(c.sensorLossHoldMs)||c.sensorLossHoldMs<0)))
        throw new Error('Room thermostat: unqualified configuration');
    if(!store||typeof store.read!=='function'||typeof store.commit!=='function')
        throw new Error('Room thermostat: durable WB settings store required');
    var initial=store.read();
    if(!settingsValid(initial,c))
        throw new Error('Room thermostat: approved local settings required before commissioning');
    var settings=copy(initial);
    var selected=null,lastDemand=null,prevNow=null,lastState='STARTUP';
    var sensorLostAt=null;
    var primaryRecoverSince=null,primaryRecoverCount=0;
    var primaryRecoveryObservation=null;
    function readingOK(r,expected,now) {
        return !!(r&&r.id===expected&&r.ok===true&&
            finite(r.temperatureC)&&r.temperatureC>=c.minMeasuredC&&
            r.temperatureC<=c.maxMeasuredC&&finite(r.observedAtMs)&&
            r.observedAtMs<=now&&now-r.observedAtMs<=c.sensorFreshMs);
    }
    function calculateDemand(temp) {
        var half=c.hysteresisC/2;
        if(temp<=settings.setpointC-half)lastDemand=true;
        else if(temp>=settings.setpointC+half)lastDemand=false;
        else if(lastDemand===null)lastDemand=temp<settings.setpointC;
        return lastDemand;
    }
    function response(state,source,temp,demand,reason) {
        lastState=state;
        return {zoneId:c.zoneId,mode:settings.mode,setpointC:settings.setpointC,
            settingsRevision:settings.revision,state:state,source:source,
            measuredC:temp,heatDemand:demand,valid:typeof demand==='boolean',
            degraded:state==='SENSOR_HOLD'||state==='BACKUP_SENSOR'||state==='FALLBACK_HEAT'||
                state==='FALLBACK_LIMITED_OFF'||state==='UNVERIFIED_FALLBACK',
            reason:reason||''};
    }
    return {
        settings:function(){return copy(settings);},
        applyIntent:function(cmd,now){
            if(!cmd||!finite(now)||!integer(cmd.issuedAtMs)||!id(cmd.intentId)||
               !id(cmd.clientId)||cmd.retained!==false||
               now<cmd.issuedAtMs||now-cmd.issuedAtMs>c.commandMaxAgeMs)
                return {accepted:false,reason:'STALE_OR_UNTRUSTED_INTENT',
                    revision:settings.revision};
            if(cmd.intentId===settings.lastIntentId)
                return {accepted:true,reason:'ALREADY_APPLIED',
                    revision:settings.revision,settings:copy(settings)};
            if(!integer(cmd.expectedRevision)||cmd.expectedRevision!==settings.revision)
                return {accepted:false,reason:'REVISION_CONFLICT',
                    revision:settings.revision};
            var next=copy(settings);
            if(cmd.mode!==undefined)next.mode=cmd.mode;
            if(cmd.setpointC!==undefined)next.setpointC=cmd.setpointC;
            if(!settingsValid(next,c))
                return {accepted:false,reason:'INVALID_SETTINGS',
                    revision:settings.revision};
            next.revision+=1;
            next.lastIntentId=cmd.intentId;
            // The object adapter must commit to persistent local WB storage,
            // not just a volatile virtual device / UI retained value.
            if(store.commit(copy(next))!==true)
                return {accepted:false,reason:'PERSISTENCE_FAILED',
                    revision:settings.revision};
            settings=next;
            lastDemand=null;sensorLostAt=null;
            return {accepted:true,reason:'APPLIED',
                revision:settings.revision,settings:copy(settings)};
        },
        step:function(i){
            if(!i||!finite(i.nowMs)||typeof i.independentSafetyOk!=='boolean'||
               typeof i.hydraulicPathReady!=='boolean'||
               typeof i.fallbackAuthorized!=='boolean'||
               typeof i.fallbackHeatDemand!=='boolean')
                throw new Error('Room thermostat: missing explicit WB safety frame');
            var now=i.nowMs;
            if(prevNow!==null&&now<prevNow){
                selected=null;lastDemand=null;sensorLostAt=null;
                primaryRecoverSince=null;primaryRecoverCount=0;
                primaryRecoveryObservation=null;
                prevNow=now;
                return response('CLOCK_UNCERTAIN',null,null,null,
                    'Clock moved backwards; requalification required');
            }
            prevNow=now;
            if(settings.mode==='OFF'){
                lastDemand=false;selected=null;sensorLostAt=null;
                primaryRecoverSince=null;primaryRecoverCount=0;
                primaryRecoveryObservation=null;
                return response('USER_OFF',null,null,false,'Locally accepted OFF');
            }
            // An independent hardware/thermal interlock remains authoritative
            // even when the local room sensor itself looks healthy.
            if(!i.independentSafetyOk){
                lastDemand=null;sensorLostAt=null;
                return response('INDEPENDENT_PROTECTION',null,null,null,
                    'Physical safety interlock denies normal heat request');
            }
            var primary=readingOK(i.primary,c.primarySensorId,now);
            var backup=!!c.backupSensorId&&
                readingOK(i.backup,c.backupSensorId,now);
            if(!primary){primaryRecoverSince=null;primaryRecoverCount=0;
                primaryRecoveryObservation=null;}
            // First valid sensor at boot may run without upper-level UI.
            // After switching away from primary, require stable recovery
            // before returning, so a flapping sensor cannot seize control.
            var primaryReady=false;
            if(primary){
                if(selected===null||selected==='primary')primaryReady=true;
                else {
                    if(primaryRecoverSince===null){
                        primaryRecoverSince=now;primaryRecoverCount=0;
                        primaryRecoveryObservation=null;
                    }
                    // Distinct, locally health-qualified observations count;
                    // repeating a retained MQTT value every tick does not.
                    if(primaryRecoveryObservation===null||
                       i.primary.observedAtMs>primaryRecoveryObservation){
                        primaryRecoveryObservation=i.primary.observedAtMs;
                        primaryRecoverCount++;
                    }
                    primaryReady=primaryRecoverCount>=c.recoverySamples&&
                        now-primaryRecoverSince>=c.recoveryStableMs;
                }
            }
            var source=null,temp=null;
            if(primaryReady){source='primary';temp=i.primary.temperatureC;}
            else if(backup){source='backup';temp=i.backup.temperatureC;}
            if(source!==null){
                sensorLostAt=null;selected=source;
                if(source==='primary'){
                    primaryRecoverSince=null;primaryRecoverCount=0;
                    primaryRecoveryObservation=null;
                }
                var request=calculateDemand(temp);
                return response(source==='primary'?'NORMAL':'BACKUP_SENSOR',
                    source,temp,request,source==='primary'?'Local primary measurement':
                    'Approved local backup measurement');
            }
            if(sensorLostAt===null)sensorLostAt=now;
            if(c.sensorLossHoldMs>0 && lastDemand!==null &&
               now-sensorLostAt<c.sensorLossHoldMs){
                selected='fallback';
                return response('SENSOR_HOLD',null,null,lastDemand,
                    'Short sensor outage: preserve accepted local heat request');
            }
            selected='fallback';
            lastDemand=null; // never use stale room temperature indefinitely
            if(i.fallbackAuthorized&&i.independentSafetyOk&&i.hydraulicPathReady){
                return response(i.fallbackHeatDemand?'FALLBACK_HEAT':'FALLBACK_LIMITED_OFF',
                    null,null,i.fallbackHeatDemand,
                    'Separate object-approved bounded local fallback');
            }
            return response('UNVERIFIED_FALLBACK',null,null,null,
                'No valid sensor or validated bounded-heating contract');
        },
        snapshot:function(){
            return {settings:copy(settings),state:lastState,
                selectedSource:selected,lastDemand:lastDemand};
        }
    };
};
