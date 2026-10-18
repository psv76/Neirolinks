/* Offline state-machine regressions: no MQTT, outputs, or live WB. */
var assert = require('assert');
var Policy = require('../core/HHM3SensorLossPolicy');
var passed = 0;
function newPolicy() { return Policy.create({holdMs:15000, recoveryStableMs:10000,
    recoverySamples:2, limitedValvePct:18}); }
function sample(now, valid, change) {
    var d={nowMs:now,sensorValid:valid,heatRequested:true,
        hydraulicPathReady:true,protectionActive:false,acceptedValvePct:37,
        acceptedValveConfirmed:valid,
        fallbackAuthorized:true,independentLimitOk:true};
    Object.keys(change||{}).forEach(function(k){d[k]=change[k];});
    return d;
}
function check(name,fn){fn();passed+=1;process.stdout.write('PASS '+name+'\n');}
check('normal position is observed without writing',function(){
    var p=newPolicy(),r=p.step(sample(0,true));
    assert.strictEqual(r.state,'NORMAL');assert.strictEqual(r.valvePct,37);
    assert.strictEqual(r.commandValve,false);
});
check('brief loss holds exact position and demand',function(){
    var p=newPolicy();p.step(sample(0,true));
    var r=p.step(sample(1000,false));
    assert.strictEqual(r.state,'HOLD_LAST_ACCEPTED');
    assert.strictEqual(r.valvePct,37);assert.strictEqual(r.commandValve,false);
    assert.strictEqual(r.heatDemand,true);
});
check('long loss allows only approved nonzero fallback',function(){
    var p=newPolicy();p.step(sample(0,true));p.step(sample(1000,false));
    var r=p.step(sample(16000,false));
    assert.strictEqual(r.state,'LIMITED_HEAT');
    assert.strictEqual(r.valvePct,18);assert.strictEqual(r.commandValve,true);
    assert.strictEqual(r.heatDemand,true);
    assert.strictEqual(r.lastAcceptedValvePct,37);
    var ack=p.step(sample(17000,false,{acceptedValveConfirmed:true,acceptedValvePct:18}));
    assert.strictEqual(ack.lastAcceptedValvePct,18);
});
check('independent safety not qualified: no arbitrary zero or ON',function(){
    var p=newPolicy();p.step(sample(0,true));p.step(sample(1000,false));
    var r=p.step(sample(16000,false,{independentLimitOk:false}));
    assert.strictEqual(r.state,'FALLBACK_NOT_VERIFIED');
    assert.strictEqual(r.valvePct,null);assert.strictEqual(r.commandValve,false);
    assert.strictEqual(r.heatDemand,null);
});
check('cold boot cannot HOLD a position it never saw',function(){
    var p=newPolicy(),r=p.step(sample(0,false));
    assert.strictEqual(r.state,'LIMITED_HEAT');
    assert.strictEqual(r.valvePct,18);
});
check('short recovery does not renew the original grace window',function(){
    var p=newPolicy();p.step(sample(0,true));
    p.step(sample(1000,false));
    assert.strictEqual(p.step(sample(2000,true)).state,'RECOVERY_HOLD');
    var r=p.step(sample(17000,false));
    assert.strictEqual(r.state,'LIMITED_HEAT');
    assert.strictEqual(r.sensorLostSinceMs,1000);
});
check('recovery needs sustained valid observations',function(){
    var p=newPolicy();p.step(sample(0,true));p.step(sample(1000,false));
    p.step(sample(20000,false));
    assert.strictEqual(p.step(sample(21000,true)).state,'RECOVERY_HOLD');
    assert.strictEqual(p.step(sample(28000,true)).state,'RECOVERY_HOLD');
    var r=p.step(sample(31001,true,{acceptedValvePct:60}));
    assert.strictEqual(r.state,'NORMAL');assert.strictEqual(r.valvePct,60);
    assert.strictEqual(r.sensorLostSinceMs,null);
});
check('real independent hazard overrides holding',function(){
    var p=newPolicy();p.step(sample(0,true));p.step(sample(1000,false));
    var r=p.step(sample(2000,false,{protectionActive:true}));
    assert.strictEqual(r.state,'PROTECTION_ACTIVE');
    assert.strictEqual(r.commandValve,false);assert.strictEqual(r.heatDemand,null);
});
check('no hydraulic path vetoes limited heating',function(){
    var p=newPolicy();p.step(sample(0,true));
    assert.strictEqual(p.step(sample(16000,false,{hydraulicPathReady:false})).state,
        'PATH_UNAVAILABLE');
});
check('user no-demand stays authoritative',function(){
    var p=newPolicy();p.step(sample(0,true));
    var r=p.step(sample(1000,false,{heatRequested:false}));
    assert.strictEqual(r.state,'NO_DEMAND');assert.strictEqual(r.heatDemand,false);
    assert.strictEqual(p.snapshot().lastAcceptedValvePct,null);
});
check('backward clock resets prior accepted position',function(){
    var p=newPolicy();p.step(sample(10000,true));
    var r=p.step(sample(9000,false,{independentLimitOk:false}));
    assert.strictEqual(r.state,'FALLBACK_NOT_VERIFIED');
    assert.strictEqual(r.valvePct,null);
});
check('invalid or zero fallback config forbidden',function(){
    assert.throws(function(){Policy.create({holdMs:15000,recoveryStableMs:10000,
        recoverySamples:2,limitedValvePct:0});},/requires reviewed/);
});
check('missing explicit safety input forbidden',function(){
    assert.throws(function(){newPolicy().step({nowMs:1,sensorValid:false});},
        /requires explicit/);
});
process.stdout.write('TOTAL PASS '+passed+'\n');
