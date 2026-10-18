/* HHM room sensor evidence from read-bound wb-mqtt-serial MQTT publication.
 * Pure ES5 evaluator; does not subscribe, publish, touch RS-485 or write outputs.
 * Valid ONLY after a trusted object adapter verifies exact running driver
 * version, effective max_unchanged_interval>0, disabled cached republish,
 * configuration SHA and current WB/service process epochs.
 * MQTT payloads alone do not prove a physical Modbus read or publisher identity.
 */
function whole(v){return typeof v==='number'&&isFinite(v)&&v>=0&&Math.floor(v)===v;}
function finite(v){return typeof v==='number'&&isFinite(v);}
function tag(v){return typeof v==='string'&&v.length>0&&v.length<=160;}
function sha(v){return typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);}
function decimal(v){
    if(typeof v==='number')return finite(v)?v:null;
    if(typeof v!=='string'||v.length>32||
       !/^-?(?:[0-9]+)(?:\.[0-9]+)?$/.test(v))return null;
    var n=Number(v);
    return finite(n)?n:null;
}
exports.create=function(c){
    if(!c||!tag(c.sensorId)||!tag(c.topic)||!tag(c.errorTopic)||
       !tag(c.driverVersion)||!sha(c.expectedConfigSHA256)||
       !whole(c.unchangedIntervalS)||c.unchangedIntervalS<5||
       !whole(c.freshMs)||c.freshMs<=1000*c.unchangedIntervalS||
       !finite(c.minC)||!finite(c.maxC)||c.minC>=c.maxC)
        throw new Error('Room MQTT evidence: approved read-bound publication contract required');
    var session=null,observedAt=null,temperature=null,
        lastTime=null,errorAt=null,clearAt=null,reason='POLICY_UNVERIFIED';
    function invalidate(why){
        observedAt=null;temperature=null;reason=why;
    }
    function checkTime(now){
        if(!whole(now))throw new Error('Room MQTT evidence: monotonic local time required');
        if(lastTime!==null&&now<lastTime){
            session=null;errorAt=null;clearAt=null;
            invalidate('CLOCK_REWIND');
            lastTime=now;
            return false;
        }
        lastTime=now;
        return true;
    }
    function matches(e){
        return !!(session&&e&&e.bootEpoch===session.bootEpoch&&
            e.driverEpoch===session.driverEpoch);
    }
    return {
        qualifyPolicy:function(p){
            if(!p){
                session=null;errorAt=null;clearAt=null;
                invalidate('POLICY_NOT_QUALIFIED');
                return {accepted:false,reason:'POLICY_NOT_QUALIFIED'};
            }
            if(!checkTime(p.observedAtMs))
                return {accepted:false,reason:'CLOCK_REWIND_OR_INVALID_POLICY'};
            if(p.source!=='LOCAL_SERVICE_AND_CONFIG_AUDIT'||
               p.confirmed!==true||!tag(p.bootEpoch)||!tag(p.driverEpoch)||
               p.driverVersion!==c.driverVersion||
               p.configSHA256!==c.expectedConfigSHA256||
               p.maxUnchangedIntervalS!==c.unchangedIntervalS||
               p.cachedRepublishEnabled!==false){
                session=null;errorAt=null;clearAt=null;
                invalidate('POLICY_NOT_QUALIFIED');
                return {accepted:false,reason:'POLICY_NOT_QUALIFIED'};
            }
            if(!session||session.bootEpoch!==p.bootEpoch||
               session.driverEpoch!==p.driverEpoch){
                session={bootEpoch:p.bootEpoch,driverEpoch:p.driverEpoch};
                errorAt=null;clearAt=null;
                invalidate('NEW_QUALIFIED_SESSION');
            }
            return {accepted:true,reason:'READ_BOUND_POLICY_QUALIFIED'};
        },
        observeError:function(e){
            if(!e||!checkTime(e.receivedAtMs))
                return {accepted:false,reason:'INVALID_ERROR_FRAME'};
            if(!matches(e)||e.topic!==c.errorTopic||
               (e.errorActive===false&&e.retained!==false)||
               typeof e.errorActive!=='boolean'||
               e.source!=='WB_MQTT_SERIAL_ERROR_TOPIC')
                return {accepted:false,reason:'UNTRUSTED_ERROR_FRAME'};
            if(e.errorActive){
                errorAt=e.receivedAtMs;clearAt=null;
                invalidate('DRIVER_REPORTED_ERROR');
            }else{
                clearAt=e.receivedAtMs;
                reason='AWAIT_FRESH_TEMPERATURE_AFTER_CLEAR';
            }
            return {accepted:true,reason:reason};
        },
        observeTemperature:function(e){
            if(!e||!checkTime(e.receivedAtMs))
                return {accepted:false,reason:'INVALID_TEMPERATURE_FRAME'};
            if(!matches(e)||e.topic!==c.topic||e.retained!==false||
               e.source!=='WB_MQTT_SERIAL_TEMPERATURE_PUBLISH'||
               e.qualifiedLocalTransport!==true)
                return {accepted:false,reason:'UNTRUSTED_TEMPERATURE_FRAME'};
            if(observedAt!==null&&e.receivedAtMs<=observedAt)
                return {accepted:false,reason:'DUPLICATE_OR_OLD_PUBLICATION'};
            // A driver error requires a subsequently observed clear and
            // a new Temperature publish. Retained clear may not authorise it.
            if(errorAt!==null&&(clearAt===null||clearAt<=errorAt||
               e.receivedAtMs<=clearAt))
                return {accepted:false,reason:'DRIVER_ERROR_NOT_RECOVERED'};
            var temp=decimal(e.payload);
            if(temp===null||temp<c.minC||temp>c.maxC){
                invalidate('INVALID_NUMERIC_TEMPERATURE');
                return {accepted:false,reason:'INVALID_NUMERIC_TEMPERATURE'};
            }
            temperature=temp;observedAt=e.receivedAtMs;
            errorAt=null;clearAt=null;reason='FRESH_READ_BOUND_PUBLICATION';
            return {accepted:true,reason:reason};
        },
        sample:function(now,bootEpoch,driverEpoch){
            if(!checkTime(now)||!session||session.bootEpoch!==bootEpoch||
               session.driverEpoch!==driverEpoch){
                session=null;errorAt=null;clearAt=null;
                invalidate('SESSION_NOT_QUALIFIED');
            }else if(observedAt!==null&&now-observedAt>c.freshMs)
                invalidate('PUBLICATION_STALE');
            var ok=!!(session&&observedAt!==null&&temperature!==null);
            return {id:c.sensorId,temperatureC:ok?temperature:null,
                ok:ok,observedAtMs:ok?observedAt:null,reason:reason};
        },
        snapshot:function(){
            return {qualified:!!session,bootEpoch:session?session.bootEpoch:null,
                driverEpoch:session?session.driverEpoch:null,
                lastPublicationMs:observedAt,reason:reason};
        }
    };
};
