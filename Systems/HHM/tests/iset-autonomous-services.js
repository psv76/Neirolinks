/* #204 autonomous Iset services; offline only, no live WB writes. */
var assert=require('assert');
var cfg=require('../../../Objects/05_16_Iset/HHM/isethhm_service_config');
var DHW=require('../../../Objects/05_16_Iset/HHM/isethhm_dhw');
var Demand=require('../../../Objects/05_16_Iset/HHM/isethhm_demand');
var Source=require('../../../Objects/05_16_Iset/HHM/isethhm_source');
var done=0;
function check(s,f){f();done++;console.log('PASS '+s);}
function dhw(){return DHW.create(cfg.dhw);}
function dframe(t,temp){
    return {nowS:t,tankC:temp,commonC:65,outdoorC:-10,
        sourceAvailable:true,pumpReadback:false};}
function demand(){return Demand.create(cfg);}
function demandFrame(){return {livingDemands:{office:true,corridor:null},
    basementTemps:[22,23,23,23],outdoorC:-10,
    floorCommissioned:false,floor:null,
    dhw:{demand:false,pauseSpaceHeating:false,requestSupplyC:null}};}
function source(){return Source.create(cfg.source);}
function sframe(t,target){return {nowS:t,sourceRequestedC:target,
    otConnectionInvalid:false,equipmentAllowsHeat:true,
    offMethodCommissioned:true,dhwPriorityPause:false,flame:false};}
check('physical as-built sensor ownership does not use old wb-w1',function(){
    assert.strictEqual(cfg.channels.dhwTank,'wb-m1w2_67/External Sensor 2');
    assert.strictEqual(cfg.channels.otSetpoint,
        'wbe2-i-opentherm_11/Heating Setpoint');
    assert.strictEqual(cfg.outputs.dhwPump,'wb-mr6cu_37/K1');
    assert.strictEqual(cfg.outputs.floorPump,'wb-mr6cu_37/K2');
    assert.strictEqual(cfg.outputs.basementPump,'wb-mr6cu_37/K3');
    assert.strictEqual(cfg.outputs.livingPump,'wb-mr6cu_37/K4');
    assert.strictEqual(cfg.ahu.commissioned,false);
    assert.strictEqual(cfg.floor.commissioned,false);
});
check('DHW cold-start delay uses verified tank, not HA demand',function(){
    var x=dhw(),a=x.step(dframe(100,45));
    assert.strictEqual(a.state,'UNKNOWN');
    a=x.step(dframe(160,45));
    assert.strictEqual(a.state,'ACTIVE');
    assert.strictEqual(a.demand,true);
    assert.strictEqual(a.pumpWanted,true);
    assert.strictEqual(a.requestSupplyC,72); // 52 + priorityMargin 20
    assert.strictEqual(a.mode,'ACCELERATED');
    assert.strictEqual(a.priorityRemainingS,1500);
});
check('DHW conditional priority at low tank temperature is bounded by outdoor',function(){
    var x=dhw();x.step(dframe(100,44));
    var a=x.step(dframe(160,44));
    assert.strictEqual(a.priorityRemainingS,1500); // at -10 C: 900 + 10*60
});
check('DHW target reached transitions to overrun only with warm common',function(){
    var x=dhw();x.step(dframe(100,48));
    x.step(dframe(160,48));
    var f=dframe(200,52),r=x.step(f);
    assert.strictEqual(r.demand,false);
    assert.strictEqual(r.mode,'OVERRUN');
    assert.strictEqual(r.overrunRemainingS,180);
    assert.strictEqual(r.pumpWanted,true);
    f.nowS=381;r=x.step(f);
    assert.strictEqual(r.pumpWanted,false);
});
check('DHW no heat transfer never blocks living by itself',function(){
    var x=dhw();x.step(dframe(100,null));
    var a=x.step(dframe(200,null));
    assert.strictEqual(a.state,'UNKNOWN');
    assert.strictEqual(a.pauseSpaceHeating,false);
    assert.strictEqual(a.pumpWanted,false);
});
check('DHW timeout is local latched fault; independent requests unaffected',function(){
    var x=dhw();x.step(dframe(100,48));x.step(dframe(160,48));
    var a=x.step(dframe(7370,48));
    assert.strictEqual(a.state,'FAULT');
    assert.strictEqual(a.demand,false);
    assert.strictEqual(a.pauseSpaceHeating,false);
    var f=demandFrame();f.dhw=a;
    assert.strictEqual(demand().step(f).livingHeatDemand,true);
});
check('DHW priority relief expires and can resume',function(){
    var x=dhw();x.step(dframe(100,44));x.step(dframe(160,44));
    var a=x.step(dframe(1660,44));
    assert.strictEqual(a.pauseSpaceHeating,false);
    assert.strictEqual(a.reliefRemainingS,900);
    a=x.step(dframe(2561,44));
    assert.strictEqual(a.pauseSpaceHeating,true);
});
check('DHW boost is local command, no HA heartbeat',function(){
    var x=dhw();x.step(dframe(100,51));x.boost();
    var a=x.step(dframe(160,51));
    assert.strictEqual(a.demand,true);
    assert.strictEqual(a.mode,'ACCELERATED');
});
check('basement minimum drives K3 request even with another missing sensor',function(){
    var x=demand(),f=demandFrame();
    f.basementTemps=[22,null,25,24];
    var a=x.step(f);
    assert.strictEqual(a.basementHeatDemand,true);
    assert.strictEqual(a.basementValidSensors,3);
    assert.ok(a.sourceRequestedC>=55);
});
check('one missing basement sensor cannot vote for premature heat OFF',function(){
    var x=demand(),f=demandFrame();
    f.basementTemps=[20,21,22,23];x.step(f);
    f.basementTemps=[24,25,null,26];
    assert.strictEqual(x.step(f).basementHeatDemand,true);
});
check('basement remains heating after all sensor reads temporarily disappear',function(){
    var x=demand(),f=demandFrame();
    f.basementTemps=[20,21,22,23];x.step(f);
    f.basementTemps=[null,null,null,null];
    var r=x.step(f);
    assert.strictEqual(r.basementHeatDemand,true);
    assert.strictEqual(r.basementLastValueHeld,true);
    assert.strictEqual(r.grants.basement,'REQUESTED');
    assert.ok(r.sourceRequestedC!==null);
});
check('DHW priority pauses source grants but not room controller demand',function(){
    var x=demand(),f=demandFrame();
    f.dhw={demand:true,requestSupplyC:72,pauseSpaceHeating:true};
    var a=x.step(f);
    assert.strictEqual(a.grants.living,'DHW_PRIORITY_PAUSE');
    assert.strictEqual(a.grants.basement,'DHW_PRIORITY_PAUSE');
    assert.strictEqual(a.sourceRequestedC,72);
    assert.strictEqual(a.livingHeatDemand,true);
});
check('DHW normally operates in parallel and source picks maximum',function(){
    var x=demand(),f=demandFrame();
    f.dhw={demand:true,requestSupplyC:67,pauseSpaceHeating:false};
    var a=x.step(f);
    assert.strictEqual(a.winner,'dhw');
    assert.strictEqual(a.grants.living,'REQUESTED');
    assert.strictEqual(a.grants.basement,'REQUESTED');
    assert.strictEqual(a.sourceRequestedC,67);
});
check('AHU not commissioned and floor not proven do not fabricate heat',function(){
    var x=demand(),f=demandFrame();
    f.floor={demand:true,requestC:40};
    var a=x.step(f);
    assert.strictEqual(a.grants.floor,'NOT_COMMISSIONED');
});
check('one invalid room reading does not veto another zone request',function(){
    var x=demand(),f=demandFrame();
    f.livingDemands={office:null,corridor:true};
    var a=x.step(f);
    assert.strictEqual(a.livingHeatDemand,true);
    assert.strictEqual(a.grants.living,'REQUESTED');
});
check('source below 35 request means no demand rather than guessed heating',function(){
    var x=source(),r=x.step(sframe(0,25));
    assert.strictEqual(r.offRequired,true);
    assert.strictEqual(r.targetC,15);
});
check('OT link fault never generates a hazardous physical write',function(){
    var x=source(),f=sframe(0,65);
    f.otConnectionInvalid=true;
    var r=x.step(f);
    assert.strictEqual(r.desiredWrite,null);
    assert.strictEqual(r.state,'OT_LINK_INVALID');
});
check('source physical independent equipment protection requires OFF method',function(){
    var x=source(),f=sframe(0,65);
    f.equipmentAllowsHeat=false;
    f.offMethodCommissioned=false;
    var a=x.step(f);
    assert.strictEqual(a.desiredWrite,null);
    assert.strictEqual(a.targetC,15);
});
check('source on valid active request starts at confirmed minimum',function(){
    var x=source(),r=x.step(sframe(100,70));
    assert.strictEqual(r.offRequired,false);
    assert.strictEqual(r.targetC,40);
    assert.deepStrictEqual(r.desiredWrite,
        {path:'wbe2-i-opentherm_11/Heating Setpoint',value:40});
});
check('source does not treat calculated command as acknowledged physical write',function(){
    var x=source(),r=x.step(sframe(100,70));
    assert.ok(r.desiredWrite);
    r=x.step(sframe(105,70));
    assert.ok(r.desiredWrite); // still pending before actual write accepted
});
check('source ramps upward only after elapsed time and tracks confirmed writes',function(){
    var x=source(),f=sframe(100,70);
    var r=x.step(f);
    assert.strictEqual(x.acknowledge(100,r.targetC),true);
    f.nowS=110;r=x.step(f);
    assert.strictEqual(r.targetC,40.5);
    f.nowS=120;r=x.step(f);
    assert.strictEqual(r.targetC,41);
});
check('source does not require HA to select living and DHW heat',function(){
    var x=demand(),f=demandFrame();
    var a=x.step(f),s=source().step(sframe(100,a.sourceRequestedC));
    assert.strictEqual(s.state,'HEAT_REQUESTED');
    assert.ok(s.desiredWrite);
});
check('outdoor sensor absent at startup does NOT stop cold room heat',function(){
    var x=demand(),f=demandFrame();
    f.outdoorC=null;
    f.livingDemands={office:true,corridor:null};
    var r=x.step(f);
    assert.strictEqual(r.outdoorFallback,true);
    assert.strictEqual(r.outdoorUsedC,0);
    assert.strictEqual(r.grants.living,'REQUESTED');
    assert.ok(r.sourceRequestedC!==null);
});
check('actual outdoor observation supersedes startup fallback',function(){
    var x=demand(),f=demandFrame();
    f.outdoorC=null;x.step(f);
    f.outdoorC=-17;var r=x.step(f);
    assert.strictEqual(r.outdoorFallback,false);
    assert.strictEqual(r.outdoorUsedC,-17);
    f.outdoorC=null;r=x.step(f);
    assert.strictEqual(r.outdoorUsedC,-17);
    assert.strictEqual(r.outdoorFallback,false);
});
check('live 23.21C basement with 23C setpoint starts K3 inside hysteresis band',function(){
    var x=demand(),f=demandFrame();
    f.basementTemps=[23.21,23.44,26.19,24.4];
    f.outdoorC=12.4;
    var r=x.step(f);
    assert.strictEqual(r.basementHeatDemand,true);
    assert.strictEqual(r.grants.basement,'REQUESTED');
    assert.ok(r.sourceRequestedC!==null);
    f.basementTemps=[23.8,24.1,26.19,24.4];
    r=x.step(f);
    assert.strictEqual(r.basementHeatDemand,false);
});
console.log('TOTAL PASS '+done);
