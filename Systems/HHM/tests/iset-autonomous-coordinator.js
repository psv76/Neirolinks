/* Iset autonomous HHM service coordinator tests, no live I/O. */
var assert=require('assert');
var cfg=require('../../../Objects/05_16_Iset/HHM/isethhm_service_config');
var map=require('../../../Objects/05_16_Iset/HHM/room_zones');
var Simple=require('../../../Objects/05_16_Iset/HHM/simple_room_thermostat');
var Store=require('../../../Objects/05_16_Iset/HHM/room_settings_store');
var Gate=require('../core/HHMRoomPathGate');
var Rooms=require('../../../Objects/05_16_Iset/HHM/room_local_runtime');
var Dhw=require('../../../Objects/05_16_Iset/HHM/isethhm_dhw');
var Demand=require('../../../Objects/05_16_Iset/HHM/isethhm_demand');
var Source=require('../../../Objects/05_16_Iset/HHM/isethhm_source');
var Coordinator=require('../../../Objects/05_16_Iset/HHM/isethhm_coordinator');
var done=0;
function check(t,f){f();done++;console.log('PASS '+t);}
function coordinator(){
    var storage={},writer=Store.create(storage,'office');
    storage[writer.key]=writer.proposeInitial('HEAT',22);
    var room=Rooms.create({map:map,Simple:Simple,Settings:Store,
        PathGate:Gate,storage:storage,minSetpointC:16,maxSetpointC:30,
        hysteresisC:0.6,minMeasuredC:-20,maxMeasuredC:60});
    return Coordinator.create({rooms:room,dhw:Dhw.create(cfg.dhw),
        demand:Demand.create(cfg),source:Source.create(cfg.source),
        services:cfg});
}
function stepFrame(t){
    return {nowMs:t*1000,
        roomsFrame:{nowMs:t*1000,bootEpoch:'test-boot',
            temperatures:{office:19},sensorErrors:{},
            outputReadbacks:{},protectionActive:false},
        plant:{outputs:{},tankC:48,outdoorC:-10,commonC:65,
            basementTemps:[22,22,23,23],
            sourceAvailable:true,otConnectionInvalid:false,
            equipmentAllowsHeat:true,offMethodCommissioned:true,
            flame:false,floorCommissioned:false}};
}
check('autonomous coordinator does not need an HA field',function(){
    var x=coordinator(),f=stepFrame(100),r=x.step(f);
    assert.strictEqual(r.mode,'OFFLINE_PLAN_ONLY');
    assert.strictEqual(r.physicalWriteAllowed,false);
    assert.strictEqual(r.rooms.demands.office,true);
    assert.strictEqual(r.requests.livingHeatDemand,true);
    assert.strictEqual(r.livingPumpGranted,true);
    assert.strictEqual(r.source.state,'HEAT_REQUESTED');
});
check('individual room fault does not stop basement or DHW',function(){
    var x=coordinator(),f=stepFrame(100);x.step(f);
    f.nowMs=161000;f.roomsFrame.nowMs=161000;
    f.roomsFrame.sensorErrors.office=true;
    var r=x.step(f);
    assert.strictEqual(r.rooms.demands.office,false);
    assert.strictEqual(r.requests.basementHeatDemand,true);
    assert.strictEqual(r.dhw.demand,true);
    assert.strictEqual(r.source.state,'HEAT_REQUESTED');
});
check('normal DHW runs in parallel with room heating',function(){
    var x=coordinator(),f=stepFrame(100);x.step(f);
    f.nowMs=161000;f.roomsFrame.nowMs=161000;
    var r=x.step(f);
    assert.strictEqual(r.dhw.mode,'SUPPORT');
    assert.strictEqual(r.requests.grants.living,'REQUESTED');
    assert.strictEqual(r.requests.grants.dhw,'REQUESTED');
    assert.strictEqual(r.livingPumpGranted,true);
});
check('very cold DHW temporarily pauses K4 grant, not room demand',function(){
    var x=coordinator(),f=stepFrame(100);f.plant.tankC=44;x.step(f);
    f.nowMs=161000;f.roomsFrame.nowMs=161000;
    var r=x.step(f);
    assert.strictEqual(r.dhw.mode,'ACCELERATED');
    assert.strictEqual(r.rooms.demands.office,true);
    assert.strictEqual(r.requests.grants.living,'DHW_PRIORITY_PAUSE');
    assert.strictEqual(r.livingPumpGranted,false);
    assert.strictEqual(r.dhw.pumpWanted,true);
});
check('unavailable OT link prevents new K1/K3 requests, not room output closure',function(){
    var x=coordinator(),f=stepFrame(100);f.plant.otConnectionInvalid=true;
    var r=x.step(f);
    assert.strictEqual(r.source.desiredWrite,null);
    assert.strictEqual(r.intents[0].requested,false);
    assert.strictEqual(r.intents[1].requested,false);
    assert.strictEqual(r.rooms.demands.office,true);
    assert.strictEqual(r.livingPumpGranted,false);
});
check('AHU uncommissioned and floor uncommissioned have no physical intents',function(){
    var x=coordinator(),r=x.step(stepFrame(100));
    var targets=r.intents.map(function(x){return x.path;});
    assert.strictEqual(targets.indexOf(cfg.outputs.ahuPump),-1);
    assert.strictEqual(targets.indexOf(cfg.outputs.floorPump),-1);
    assert.strictEqual(r.requests.floorCommissioned,false);
});
check('coordinator cannot silently write physical channels',function(){
    var x=coordinator(),r=x.step(stepFrame(100));
    assert.strictEqual(x.writePump,undefined);
    assert.strictEqual(x.writeOT,undefined);
    assert.strictEqual(r.physicalWriteAllowed,false);
});
console.log('TOTAL PASS '+done);
