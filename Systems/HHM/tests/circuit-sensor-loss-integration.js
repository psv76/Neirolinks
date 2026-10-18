/* Offline integration checks for HHM3Circuit + HHM3Mixing + loss policy.
 * Numerical settings here are test fixtures only, not site commissioning.
 */
var assert=require('assert');
var Circuit=require('../core/HHM3Circuit');
var Mixing=require('../core/HHM3Mixing');
var Loss=require('../core/HHM3SensorLossPolicy');
var passed=0;
function fixture(optIn){
    var c={periodMs:5000,requestTtlS:15,normalSupplyC:32,
        maxSupplyC:35,autonomousSupplyC:28,supplyCloseC:40,
        supplyStopC:43,supplyImmediateStopC:46,floorCloseC:38,
        floorStopC:40,floorTargetMaxC:35,supplyHysteresisC:3,
        floorHysteresisC:2,closeObserveMs:10000,coolStableMs:120000,
        circulationCheckMs:60000,postrunMs:120000,pumpPostrunMs:120000,
        responseMs:900000,responseRiseC:1,sourceMarginC:5,
        floorStepPct:1,floorStepMs:60000,floorOnlyMaxPct:0,
        valveActiveMinLevel:1,valveActiveMaxLevel:100,
        valveOffCommand:false,
        tuning:{bandC:0.5,biasC:0,farErrorC:4,
            fastHoldColdS:60,fastHoldHotS:30,fastMinStepPct:1,
            fastMaxStepPct:4,trimHoldColdS:90,trimHoldHotS:30,
            trimMinStepPct:1,trimMaxStepPct:2,pctPerCCold:1,
            pctPerCHot:2,reverseLockS:60,trendOkCPerMin:0.3,
            trendSlowCPerMin:0.05,stagnationS:600,postMoveSettleS:30,
            minPosPct:0,maxPosPct:100,hardMaxC:45,
            supplyValidMinC:-20,supplyValidMaxC:110,
            sensorBadLimit:1,sourceGuardEnabled:false,sourceMarginC:0,
            sourceValidMinC:-20,sourceValidMaxC:110,
            startupCapEnabled:true,startupDurationS:300,
            startupMaxPosPct:10,enableRetryS:30,safeCloseOnDisable:true}
    };
    if(optIn)c.sensorLossPolicy={holdMs:15000,recoveryStableMs:10000,
        recoverySamples:2,limitedValvePct:18};
    return c;
}
function env(optIn){
    return Circuit.create(fixture(optIn),{},Mixing,Loss);
}
function frame(now){return {floor:24,valid:true,enabled:true,demand:true,
    mode:'HEAT',heat:30,hold:25,sent_ms:now,session_id:1,seq:1};}
function sample(now, options){
    var x={now:now,frame:frame(now),supply:28,supplyAt:now,
        source:60,ret:26,zoneReady:true,zoneSafe:true,pumpWasOn:true,
        sensorValid:true,valveActionSupported:true,hydraulicPathReady:true,
        fallbackAuthorized:true,independentLimitOk:true,
        acceptedValveConfirmed:true,acceptedValvePct:22};
    Object.keys(options||{}).forEach(function(k){x[k]=options[k];});
    return x;
}
function check(label,fn){fn();passed++;console.log('PASS '+label);}
check('no opt-in preserves original missing supply behavior',function(){
    var e=env(false);
    var r=e.step(sample(5000,{supply:null}));
    assert.strictEqual(r.reason,'FLOOR_CAP_UNMEASURED');
    assert.strictEqual(r.valve,0);assert.strictEqual(r.demand,false);
    assert.strictEqual(r.sensorLossState,undefined);
});
check('no opt-in preserves no-feedback stop of source request',function(){
    var e=env(false);
    var r=e.step(sample(5000,{supply:null,frame:null}));
    assert.strictEqual(r.reason,'NO_FEEDBACK_UNCOVERED');
});
check('missing pump postrun fails independent config validation',function(){
    var c=fixture(false);delete c.pumpPostrunMs;
    assert.throws(function(){Circuit.create(c,{},Mixing);},
        /invalid config/);
});
check('normal produces current mixer diagnostics',function(){
    var e=env(true),r=e.step(sample(5000));
    assert.strictEqual(r.reason,'NORMAL');
    assert.ok(r.mixing&&typeof r.mixing.status==='string');
    assert.strictEqual(r.sensorLossState,'NORMAL');
    assert.strictEqual(r.valveAction,'APPLY');
});
check('brief sensor loss is HOLD and retains valid heat request',function(){
    var e=env(true);e.step(sample(5000));
    var r=e.step(sample(10000,{supply:null,sensorValid:false,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'HOLD_LAST_ACCEPTED');
    assert.strictEqual(r.valve,22);
    assert.strictEqual(r.valveAction,'HOLD');
    assert.strictEqual(r.demand,true);
    assert.strictEqual(r.pump,true);
    assert.strictEqual(r.valid,true);
});
check('only independent certified fallback enables nonzero heat',function(){
    var e=env(true);e.step(sample(5000));
    e.step(sample(10000,{supply:null,sensorValid:false,acceptedValveConfirmed:false}));
    var r=e.step(sample(25000,{supply:null,sensorValid:false,acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'LIMITED_HEAT');
    assert.strictEqual(r.valve,18);
    assert.strictEqual(r.valveAction,'APPLY');
    assert.strictEqual(r.demand,true);
});
check('unknown fallback never emits a zero-setpoint or invented grant',function(){
    var e=env(true);e.step(sample(5000));
    e.step(sample(10000,{supply:null,sensorValid:false,acceptedValveConfirmed:false}));
    var r=e.step(sample(25000,{supply:null,sensorValid:false,
        independentLimitOk:false,acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'FALLBACK_NOT_VERIFIED');
    assert.strictEqual(r.valve,null);
    assert.strictEqual(r.valveAction,'NO_COMMAND');
    assert.strictEqual(r.write,false);
    assert.strictEqual(r.valid,false);
    assert.strictEqual(r.demand,false);
    assert.strictEqual(r.pump,true);
});
check('no hydraulic path cannot run heating fallback',function(){
    var e=env(true);e.step(sample(5000));
    var r=e.step(sample(10000,{supply:null,sensorValid:false,
        hydraulicPathReady:false,acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'PATH_UNAVAILABLE');
    assert.strictEqual(r.pump,false);
    assert.strictEqual(r.write,false);
});
check('stable sensor recovery resumes from confirmed level',function(){
    var e=env(true);e.step(sample(5000));
    e.step(sample(10000,{supply:null,sensorValid:false,acceptedValveConfirmed:false}));
    e.step(sample(25000,{supply:null,sensorValid:false,acceptedValveConfirmed:false}));
    var r=e.step(sample(30000,{acceptedValvePct:18,acceptedValveConfirmed:true}));
    assert.strictEqual(r.reason,'RECOVERY_HOLD');
    assert.strictEqual(r.valve,18);
    r=e.step(sample(35000,{acceptedValvePct:18,acceptedValveConfirmed:true}));
    assert.strictEqual(r.reason,'RECOVERY_HOLD');
    r=e.step(sample(41000,{acceptedValvePct:18,acceptedValveConfirmed:true}));
    assert.strictEqual(r.reason,'NORMAL');
    assert.ok(r.mixing&&typeof r.mixing.status==='string');
    assert.strictEqual(r.valveAction,'APPLY');
});
check('real overheat guard has priority over new sensor policy',function(){
    var e=env(true);e.step(sample(5000));
    var r=e.step(sample(10000,{supply:44,sensorValid:true}));
    assert.strictEqual(r.reason,'OVERHEAT_CLOSE');
    assert.strictEqual(r.valve,0);
});
check('explicit no-demand still cancels normal heating',function(){
    var e=env(true);e.step(sample(5000));
    var r=e.step(sample(10000,{frame:{
        floor:24,valid:true,enabled:true,demand:false,mode:'HEAT',
        heat:30,hold:25,sent_ms:10000,session_id:1,seq:2}}));
    assert.strictEqual(r.reason,'NO_DEMAND');
    assert.strictEqual(r.demand,false);
});
check('opt-in refuses missing sensor-health or hydraulic permits',function(){
    var e=env(true);
    assert.throws(function(){e.step(sample(5000,{sensorValid:null}));},/safety\/health/);
});
check('opt-in requires dedicated helper module',function(){
    var c=fixture(true);
    assert.throws(function(){Circuit.create(c,{},Mixing);},/module is required/);
});
check('legacy mixer sensor fault is now visible to circuit consumers',function(){
    var e=env(false);
    var r=e.step(sample(5000,{supply:-25}));
    assert.strictEqual(r.reason,'NORMAL');
    assert.strictEqual(r.mixing.sensorFault,true);
    assert.strictEqual(r.mixing.status,'SUPPLY_SENSOR_FAILSAFE_CLOSE');
});
check('a bad numeric sample cannot bypass explicit health signal',function(){
    var e=env(true);e.step(sample(300000));
    var r=e.step(sample(305000,{supply:-25,sensorValid:true,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'HOLD_LAST_ACCEPTED');
    assert.strictEqual(r.valve,22);
    assert.strictEqual(r.mixing.status,'STEP_OPEN');
});
check('real hard temperature stop overrides a contradictory health flag',function(){
    var e=env(true);e.step(sample(300000));
    var r=e.step(sample(305000,{supply:46,sensorValid:true}));
    assert.strictEqual(r.reason,'OVERHEAT_STOP');
    assert.strictEqual(r.pump,false);
    assert.strictEqual(r.valve,0);
});
check('recovering sensor never authorizes unconfirmed mixer resumption',function(){
    var e=env(true);e.step(sample(300000));
    e.step(sample(305000,{supply:null,sensorValid:false,
        acceptedValveConfirmed:false}));
    e.step(sample(310000,{acceptedValveConfirmed:false}));
    var r=e.step(sample(321000,{acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'RECOVERY_HOLD');
    assert.strictEqual(r.valveAction,'HOLD');
    r=e.step(sample(326000,{acceptedValveConfirmed:true,acceptedValvePct:22}));
    assert.strictEqual(r.reason,'NORMAL');
});
check('two short glitches preserve one original accepted valve position',function(){
    var e=env(true);e.step(sample(300000));
    var r=e.step(sample(301000,{supply:null,sensorValid:false,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'HOLD_LAST_ACCEPTED');
    e.step(sample(302000,{acceptedValveConfirmed:true}));
    r=e.step(sample(305000,{supply:null,sensorValid:false,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'HOLD_LAST_ACCEPTED');
    assert.strictEqual(r.valve,22);
    assert.strictEqual(r.sensorLossSinceMs,301000);
    r=e.step(sample(316000,{supply:null,sensorValid:false,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'LIMITED_HEAT');
});
check('opt-in rejects an old output adapter without HOLD support',function(){
    var e=env(true);
    assert.throws(function(){e.step(sample(5000,{valveActionSupported:false}));},
        /HOLD-aware single output writer/);
});
check('true health with missing numeric value becomes sensor-loss HOLD',function(){
    var e=env(true);e.step(sample(300000));
    var r=e.step(sample(305000,{supply:null,sensorValid:true,
        acceptedValveConfirmed:false}));
    assert.strictEqual(r.reason,'HOLD_LAST_ACCEPTED');
    assert.strictEqual(r.valve,22);
});
check('loss of upper-level frame does not reset mixer position',function(){
    var e=env(true);
    var first=e.step(sample(300000));
    assert.ok(first.valve>0);
    var r=e.step(sample(305000,{frame:{floor:24,valid:false,
        enabled:true,demand:false,reason:'HA_OFFLINE',sent_ms:305000}}));
    assert.strictEqual(r.reason,'AUTONOMOUS');
    assert.strictEqual(r.valve,first.valve);
});
check('missing safe path does not issue valve writes',function(){
    var e=env(true);e.step(sample(300000));
    var r=e.step(sample(305000,{supply:null,sensorValid:false,
        hydraulicPathReady:false,acceptedValveConfirmed:false}));
    assert.strictEqual(r.valveAction,'NO_COMMAND');
    assert.strictEqual(r.write,false);
});
console.log('TOTAL PASS '+passed);
