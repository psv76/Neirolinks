/* Local HHM room thermostat tests. Offline, no physical WB writes. */
var assert=require('assert'),Module=require('../core/HHMRoomThermostat');
var passed=0;
function cfg(zone){
    return {zoneId:zone||'office',primarySensorId:(zone||'office')+'/air',
        backupSensorId:(zone||'office')+'/backup',
        minSetpointC:16,maxSetpointC:30,hysteresisC:0.6,
        minMeasuredC:-20,maxMeasuredC:60,sensorFreshMs:60000,
        recoveryStableMs:10000,recoverySamples:2,commandMaxAgeMs:30000};
}
function storage(init){
    var s=init===undefined?{mode:'HEAT',setpointC:22,revision:7,
        lastIntentId:null}:init;
    return {read:function(){return s;},commit:function(x){s=x;return true;},
        get:function(){return s;}};
}
function create(zone,st){
    return Module.create(cfg(zone),st||storage());
}
function frame(now,change,zone){
    var z=zone||'office',f={nowMs:now,
        primary:{id:z+'/air',temperatureC:19,ok:true,observedAtMs:now},
        backup:null,independentSafetyOk:true,hydraulicPathReady:true,
        fallbackAuthorized:true,fallbackHeatDemand:true};
    Object.keys(change||{}).forEach(function(k){f[k]=change[k];});
    return f;
}
function sensor(id,temp,now){return {id:id,temperatureC:temp,
    ok:true,observedAtMs:now};}
function check(name,fn){fn();passed++;console.log('PASS '+name);}
check('primary WB sensor drives heat without HA heartbeat',function(){
    var t=create(),r=t.step(frame(100000));
    assert.strictEqual(r.state,'NORMAL');assert.strictEqual(r.heatDemand,true);
    assert.strictEqual(r.source,'primary');assert.strictEqual(r.settingsRevision,7);
});
check('temperature above hysteresis turns heat OFF',function(){
    var t=create();t.step(frame(100000));
    var r=t.step(frame(105000,{primary:sensor('office/air',23,105000)}));
    assert.strictEqual(r.state,'NORMAL');assert.strictEqual(r.heatDemand,false);
});
check('hysteresis holds previously requested heat in dead band',function(){
    var t=create();t.step(frame(100000));
    var r=t.step(frame(105000,{primary:sensor('office/air',22.1,105000)}));
    assert.strictEqual(r.heatDemand,true);
});
check('first sample in hysteresis band makes deterministic demand',function(){
    var t=create(),r=t.step(frame(100000,{primary:sensor('office/air',22.1,100000)}));
    assert.strictEqual(r.heatDemand,false);
});
check('unchanged numeric temperature stays valid if local health is refreshed',function(){
    var t=create();t.step(frame(100000));
    var r=t.step(frame(170000,{primary:sensor('office/air',19,170000)}));
    assert.strictEqual(r.state,'NORMAL');assert.strictEqual(r.heatDemand,true);
});
check('stale observation is not treated as a current room reading',function(){
    var t=create(),r=t.step(frame(170001,{primary:sensor('office/air',19,100000),
        fallbackAuthorized:false}));
    assert.strictEqual(r.state,'UNVERIFIED_FALLBACK');
    assert.strictEqual(r.heatDemand,null);assert.strictEqual(r.valid,false);
});
check('primary error immediately selects independently validated backup',function(){
    var t=create();t.step(frame(100000));
    var r=t.step(frame(105000,{primary:{id:'office/air',ok:false,
        temperatureC:19,observedAtMs:105000},
        backup:sensor('office/backup',20,105000)}));
    assert.strictEqual(r.state,'BACKUP_SENSOR');
    assert.strictEqual(r.source,'backup');assert.strictEqual(r.heatDemand,true);
});
check('primary reconnect requires stable observations before reselecting',function(){
    var t=create();t.step(frame(100000));
    t.step(frame(105000,{primary:null,
        backup:sensor('office/backup',20,105000)}));
    var a=t.step(frame(110000,{backup:sensor('office/backup',20,110000)}));
    assert.strictEqual(a.source,'backup');
    a=t.step(frame(120000,{backup:sensor('office/backup',20,120000)}));
    assert.strictEqual(a.source,'primary');assert.strictEqual(a.state,'NORMAL');
});
check('primary recovery counts distinct health observations only',function(){
    var t=create();t.step(frame(100000));
    t.step(frame(105000,{primary:null,backup:sensor('office/backup',20,105000)}));
    var repeated=sensor('office/air',19,110000);
    assert.strictEqual(t.step(frame(110000,{primary:repeated,
        backup:sensor('office/backup',20,110000)})).source,'backup');
    assert.strictEqual(t.step(frame(120000,{primary:repeated,
        backup:sensor('office/backup',20,120000)})).source,'backup');
    assert.strictEqual(t.step(frame(125000,{primary:sensor('office/air',19,125000),
        backup:sensor('office/backup',20,125000)})).source,'primary');
});
check('primary flapping cannot reset fallback by a single healthy read',function(){
    var t=create();t.step(frame(100000));
    t.step(frame(105000,{primary:null,backup:null}));
    assert.strictEqual(t.step(frame(110000)).state,'FALLBACK_HEAT');
    assert.strictEqual(t.step(frame(111000,{primary:null})).state,'FALLBACK_HEAT');
    assert.strictEqual(t.step(frame(120000)).state,'FALLBACK_HEAT');
    assert.strictEqual(t.step(frame(131000)).state,'NORMAL');
});
check('both sensors unavailable use separate authorized bounded heating',function(){
    var t=create();t.step(frame(100000));
    var r=t.step(frame(105000,{primary:null,backup:null}));
    assert.strictEqual(r.state,'FALLBACK_HEAT');assert.strictEqual(r.heatDemand,true);
    assert.strictEqual(r.source,null);assert.strictEqual(r.measuredC,null);
});
check('fallback limited OFF remains visible as deliberate bounded policy',function(){
    var t=create(),r=t.step(frame(100000,{primary:null,backup:null,
        fallbackHeatDemand:false}));
    assert.strictEqual(r.state,'FALLBACK_LIMITED_OFF');
    assert.strictEqual(r.heatDemand,false);assert.strictEqual(r.degraded,true);
});
check('unverified independent safety does not manufacture a demand',function(){
    var t=create(),r=t.step(frame(100000,{primary:null,backup:null,
        independentSafetyOk:false}));
    assert.strictEqual(r.state,'INDEPENDENT_PROTECTION');
    assert.strictEqual(r.heatDemand,null);assert.strictEqual(r.valid,false);
});
check('independent danger overrides an otherwise healthy room sensor',function(){
    var t=create(),r=t.step(frame(100000,{independentSafetyOk:false}));
    assert.strictEqual(r.state,'INDEPENDENT_PROTECTION');
    assert.strictEqual(r.heatDemand,null);
    assert.strictEqual(r.valid,false);
});
check('no hydraulic path means no approved fallback',function(){
    var t=create(),r=t.step(frame(100000,{primary:null,backup:null,
        hydraulicPathReady:false}));
    assert.strictEqual(r.state,'UNVERIFIED_FALLBACK');
    assert.strictEqual(r.heatDemand,null);
});
check('unrelated sensor ID cannot be used as room backup',function(){
    var t=create(),r=t.step(frame(100000,{primary:null,
        backup:sensor('corridor/air',19,100000),fallbackAuthorized:false}));
    assert.strictEqual(r.state,'UNVERIFIED_FALLBACK');
});
check('healthy sensor with out-of-range number becomes invalid',function(){
    var t=create(),r=t.step(frame(100000,{primary:sensor('office/air',100,100000),
        fallbackAuthorized:false}));
    assert.strictEqual(r.state,'UNVERIFIED_FALLBACK');
});
check('future-dated sensor is not silently accepted',function(){
    var t=create(),r=t.step(frame(100000,{primary:sensor('office/air',19,100001),
        fallbackAuthorized:false}));
    assert.strictEqual(r.state,'UNVERIFIED_FALLBACK');
});
check('user OFF locally overrides room thermostat and retained demand',function(){
    var st=storage({mode:'OFF',setpointC:22,revision:3});
    var t=create('office',st),r=t.step(frame(100000));
    assert.strictEqual(r.state,'USER_OFF');assert.strictEqual(r.heatDemand,false);
});
check('local UI intent persists new setpoint and revision',function(){
    var st=storage(),t=create('office',st);
    var r=t.applyIntent({clientId:'wb',intentId:'command1',issuedAtMs:110000,
        expectedRevision:7,setpointC:24,retained:false},110000);
    assert.strictEqual(r.reason,'APPLIED');assert.strictEqual(r.revision,8);
    assert.strictEqual(st.get().setpointC,24);
    assert.strictEqual(t.step(frame(115000)).setpointC,24);
});
check('another UI uses canonical WB revision',function(){
    var st=storage(),t=create('office',st);
    t.applyIntent({clientId:'sprut',intentId:'s-1',issuedAtMs:110000,
        expectedRevision:7,setpointC:23,retained:false},110000);
    var r=t.applyIntent({clientId:'ha',intentId:'h-1',issuedAtMs:112000,
        expectedRevision:8,setpointC:25,retained:false},112000);
    assert.strictEqual(r.reason,'APPLIED');assert.strictEqual(r.revision,9);
    assert.strictEqual(t.settings().setpointC,25);
});
check('stale HA revision cannot overwrite accepted WB setpoint',function(){
    var t=create();
    t.applyIntent({clientId:'wb',intentId:'one',issuedAtMs:110000,
        expectedRevision:7,setpointC:25,retained:false},110000);
    var r=t.applyIntent({clientId:'ha',intentId:'old',issuedAtMs:110000,
        expectedRevision:7,setpointC:18,retained:false},115000);
    assert.strictEqual(r.reason,'REVISION_CONFLICT');assert.strictEqual(t.settings().setpointC,25);
});
check('retained user intent rejected even with matching revision',function(){
    var t=create(),r=t.applyIntent({clientId:'ha',intentId:'retained',
        issuedAtMs:110000,expectedRevision:7,setpointC:18,retained:true},110000);
    assert.strictEqual(r.reason,'STALE_OR_UNTRUSTED_INTENT');
});
check('expired request rejected even if stale client knows revision',function(){
    var t=create(),r=t.applyIntent({clientId:'alice',intentId:'old',
        issuedAtMs:100000,expectedRevision:7,setpointC:18,retained:false},150001);
    assert.strictEqual(r.reason,'STALE_OR_UNTRUSTED_INTENT');
});
check('future request rejected without trusted clock alignment',function(){
    var t=create(),r=t.applyIntent({clientId:'homekit',intentId:'fut',
        issuedAtMs:150001,expectedRevision:7,setpointC:18,retained:false},150000);
    assert.strictEqual(r.reason,'STALE_OR_UNTRUSTED_INTENT');
});
check('malformed or out-of-range setpoint cannot be accepted',function(){
    var t=create(),r=t.applyIntent({clientId:'wb',intentId:'bad',
        issuedAtMs:110000,expectedRevision:7,setpointC:50,retained:false},110000);
    assert.strictEqual(r.reason,'INVALID_SETTINGS');
});
check('duplicate command is idempotent and does not increment revision',function(){
    var t=create(),cmd={clientId:'sprut',intentId:'x1',issuedAtMs:110000,
        expectedRevision:7,setpointC:25,retained:false};
    assert.strictEqual(t.applyIntent(cmd,110000).reason,'APPLIED');
    assert.strictEqual(t.applyIntent(cmd,115000).reason,'ALREADY_APPLIED');
    assert.strictEqual(t.settings().revision,8);
});
check('durable store failure prevents partial state change',function(){
    var st=storage(),t=create('office',st);
    st.commit=function(){return false;};
    var r=t.applyIntent({clientId:'wb',intentId:'failed',
        issuedAtMs:110000,expectedRevision:7,mode:'OFF',retained:false},110000);
    assert.strictEqual(r.reason,'PERSISTENCE_FAILED');
    assert.strictEqual(t.settings().mode,'HEAT');assert.strictEqual(t.settings().revision,7);
});
check('reboot restores settings without pulling any UI state',function(){
    var st=storage(),t=create('office',st);
    t.applyIntent({clientId:'wb',intentId:'persist',issuedAtMs:110000,
        expectedRevision:7,setpointC:26,retained:false},110000);
    var afterRestart=create('office',st);
    assert.strictEqual(afterRestart.settings().setpointC,26);
    assert.strictEqual(afterRestart.settings().revision,8);
});
check('no approved stored settings means no commissioning',function(){
    assert.throws(function(){create('office',storage(null));},/approved local settings/);
});
check('clock going backwards invalidates ephemeral demand, not settings',function(){
    var t=create();t.step(frame(150000));
    var r=t.step(frame(149000));
    assert.strictEqual(r.state,'CLOCK_UNCERTAIN');assert.strictEqual(r.heatDemand,null);
    assert.strictEqual(t.settings().revision,7);
    assert.strictEqual(t.step(frame(150000)).state,'NORMAL');
});
check('two rooms are isolated: failed office cannot stop corridor',function(){
    var office=create('office'),corridor=create('corridor');
    var a=office.step(frame(100000,{primary:null,backup:null,
        fallbackAuthorized:false},'office'));
    var b=corridor.step(frame(100000,{},'corridor'));
    assert.strictEqual(a.heatDemand,null);assert.strictEqual(b.heatDemand,true);
    assert.strictEqual(b.state,'NORMAL');
});
check('no actuator or source writes are exposed from pure module',function(){
    var t=create(),s=t.step(frame(100000));
    assert.strictEqual(typeof t.writePump,'undefined');
    assert.strictEqual(typeof t.writeValve,'undefined');
    assert.strictEqual(typeof s.physicalWrite,'undefined');
});
check('safety booleans are mandatory even when UI offline',function(){
    var t=create();
    assert.throws(function(){t.step({nowMs:1,primary:null});},/explicit WB safety/);
});
console.log('TOTAL PASS '+passed);
