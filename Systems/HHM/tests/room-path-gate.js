/* Offline logical actuator path qualification; no physical writes. */
var assert=require('assert');
var data=require('../../../Objects/05_16_Iset/HHM/room_zones');
var Gate=require('../core/HHMRoomPathGate'),count=0;
function create(){return Gate.create({zones:data.zones,
    openCommand:data.actuators.openCommand,
    closeCommand:data.actuators.closeCommand,
    openWaitMs:data.actuators.nominalOpenWaitMs});}
function frame(now){
    var d={},i;
    for(i=0;i<data.zones.length;i++)d[data.zones[i].id]=null;
    return {nowMs:now,bootEpoch:'sim_boot_1',demands:d,outputs:{},protectionActive:false};
}
function pass(name,fn){fn();count++;console.log('PASS '+name);}
pass('unverified rooms do not authorize K4 start',function(){
    var f=frame(300000),r=create().step(f);
    assert.strictEqual(r.pumpStartPermitted,false);
    assert.strictEqual(r.pumpState,'UNKNOWN_DEMAND_NO_START');
    assert.strictEqual(r.anyDemandUnknown,true);
    assert.strictEqual(r.actuatorActions.length,11);
    r.actuatorActions.forEach(function(a){assert.strictEqual(a.action,'HOLD');
        assert.strictEqual(a.desiredOutput,null);});
});
pass('known heat demand alone is not a verified open path',function(){
    var f=frame(300000);f.demands.office=true;
    var r=create().step(f);
    assert.strictEqual(r.pumpStartPermitted,false);
    assert.strictEqual(r.pumpState,'WAIT_READY_PATH');
    assert.strictEqual(r.zones.office.action,'OPEN');
    assert.strictEqual(r.zones.office.pathReady,false);
});
pass('correct NO readback but 119 sec old cannot start pump',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:181000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
});
pass('readback and 120 sec accepted opening allow a pump start',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:180000};
    var r=create().step(f);
    assert.strictEqual(r.pumpStartPermitted,true);
    assert.strictEqual(r.zones.office.pathReady,true);
    assert.strictEqual(r.pumpState,'START_PERMITTED');
});
pass('readback close 1 makes NO actuator not ready',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:1,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
});
pass('invalid readback never qualifies a route',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:false,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
});
pass('future acceptedAt cannot prove a hydraulic path',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:400000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
});
pass('reboot cannot reuse prior-epoch actuator opening evidence',function(){
    var f=frame(300000);f.demands.office=true;f.bootEpoch='sim_boot_2';
    f.outputs['wb-mio-gpio_195:2/K1']={valid:true,value:0,
        bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
});
pass('two-actuator room requires BOTH open outputs',function(){
    var f=frame(300000);f.demands.summer_kitchen=true;
    f.outputs['wb-mio-gpio_195:2/K2']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    assert.strictEqual(create().step(f).pumpStartPermitted,false);
    f.outputs['wb-mio-gpio_195:2/K3']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    assert.strictEqual(create().step(f).pumpStartPermitted,true);
});
pass('missing one room cannot veto other valid open room',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    f.demands.corridor=null;
    var r=create().step(f);
    assert.strictEqual(r.pumpStartPermitted,true);
    assert.strictEqual(r.zones.corridor.action,'HOLD');
});
pass('all explicit OFF proposes close but never commands pump OFF',function(){
    var f=frame(300000),keys=Object.keys(f.demands);
    keys.forEach(function(k){f.demands[k]=false;});
    var r=create().step(f);
    assert.strictEqual(r.pumpState,'ALL_OFF');
    assert.strictEqual(r.allExplicitlyOff,true);
    assert.strictEqual(r.pumpStartPermitted,false);
    r.actuatorActions.forEach(function(a){
        assert.strictEqual(a.action,'CLOSE');
        assert.strictEqual(a.desiredOutput,1);
    });
    assert.strictEqual(r.pumpWrite,undefined);
});
pass('independent physical protection denies START regardless of readback',function(){
    var f=frame(300000);f.demands.office=true;
    f.outputs['wb-mio-gpio_195:2/K1']={
        valid:true,value:0,bootEpoch:'sim_boot_1',acceptedOpenAtMs:1000};
    f.protectionActive=true;
    var r=create().step(f);
    assert.strictEqual(r.pumpState,'PROTECTION');
    assert.strictEqual(r.pumpStartPermitted,false);
    assert.strictEqual(r.zones.office.action,'HOLD');
    assert.strictEqual(r.actuatorActions[0].desiredOutput,null);
});
pass('unknown demand MUST NOT become a CLOSE proposal',function(){
    var f=frame(300000);
    f.demands.office=null;
    var r=create().step(f);
    assert.strictEqual(r.zones.office.action,'HOLD');
    var office=r.actuatorActions.filter(function(a){return a.zoneId==='office';});
    assert.strictEqual(office[0].desiredOutput,null);
});
pass('unverified demand type is rejected, not guessed false',function(){
    var f=frame(300000);
    f.demands.office=undefined;
    assert.throws(function(){create().step(f);},/three-state demand/);
});
pass('duplicate actuator physical ownership is rejected',function(){
    assert.throws(function(){Gate.create({zones:[
        {id:'x',outputs:['a']},{id:'y',outputs:['a']}],
        openWaitMs:100,openCommand:0,closeCommand:1});},/duplicate/);
});
console.log('TOTAL PASS '+count);
