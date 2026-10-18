/* 05 16 Iset — unified physical command planning, offline WB model. */
var assert=require('assert');
var S=require('../../../Objects/05_16_Iset/HHM/isethhm_service_config');
var M=require('../../../Objects/05_16_Iset/HHM/room_zones');
var Store=require('../../../Objects/05_16_Iset/HHM/room_settings_store');
var Simple=require('../../../Objects/05_16_Iset/HHM/simple_room_thermostat');
var Rooms=require('../../../Objects/05_16_Iset/HHM/room_local_runtime');
var Gate=require('../core/HHMRoomPathGate');
var RoomPlan=require('../../../Objects/05_16_Iset/HHM/room_output_planner');
var Hot=require('../../../Objects/05_16_Iset/HHM/isethhm_dhw');
var Demand=require('../../../Objects/05_16_Iset/HHM/isethhm_demand');
var Source=require('../../../Objects/05_16_Iset/HHM/isethhm_source');
var Coordinator=require('../../../Objects/05_16_Iset/HHM/isethhm_coordinator');
var Floor=require('../../../Objects/05_16_Iset/HHM/isethhm_floor_hydraulics');
var Runtime=require('../../../Objects/05_16_Iset/HHM/isethhm_runtime');
var n=0;
function test(name,fn){fn();n++;console.log('PASS '+name);}
function make(){
    var storage={},s=Store.create(storage,'office');
    storage[s.key]=s.proposeInitial('HEAT',22);
    var rooms=Rooms.create({map:M,Simple:Simple,Settings:Store,
        PathGate:Gate,storage:storage,minSetpointC:16,maxSetpointC:30,
        hysteresisC:0.6,minMeasuredC:-20,maxMeasuredC:60});
    var coordinator=Coordinator.create({rooms:rooms,
        dhw:Hot.create(S.dhw),demand:Demand.create(S),
        source:Source.create(S.source),services:S});
    return Runtime.create({map:M,services:S,coordinator:coordinator,
        roomsPlanner:RoomPlan.create({map:M,openWaitMs:120000}),
        floorHydraulics:Floor.create({outputs:S.outputs,
            actuatorOpenWaitMs:120000})});
}
function frame(t){
    var outputs={};
    outputs[S.outputs.dhwPump]=false;
    outputs[S.outputs.floorPump]=false;
    outputs[S.outputs.basementPump]=false;
    outputs[S.outputs.livingPump]=false;
    M.zones.forEach(function(z){
        z.outputs.forEach(function(p){outputs[p]=true;});
    });
    S.outputs.floorLoops.forEach(function(p){outputs[p]=true;});
    outputs[S.outputs.floorValveLevel]=0;
    outputs[S.outputs.floorValveEnable]=false;
    return {nowMs:t,bootEpoch:'test-boot',
        roomsFrame:{nowMs:t,bootEpoch:'test-boot',
            temperatures:{office:19},sensorErrors:{},
            outputReadbacks:outputs,protectionActive:false},
        plant:{outputs:outputs,otConnectionInvalid:false,
            equipmentAllowsHeat:true,sourceAvailable:true,
            offMethodCommissioned:true,flame:false,
            tankC:52,commonC:65,outdoorC:-10,
            floorSupplyC:29,basementTemps:[20,22,23,23]},
        floorControl:{enabled:false,targetC:34,sourceRequestC:null}};
}
function command(result,path){
    return result.commands.filter(function(a){return a.path===path;})[0];
}
test('every command must fit the as-built physical channel allowlist',function(){
    var x=make(),f=frame(100000),r=x.step(f),allowed=x.allowedTargets();
    assert.strictEqual(allowed.length,23); // 4 pumps + 16 NO + 2 MAO4 + OT11
    r.commands.forEach(function(c){
        assert.ok(allowed.indexOf(c.path)>=0,c.path);
    });
    assert.strictEqual(r.physicalWriteAllowed,false);
});
test('first run opens requested room and asks for K3; no K4 before 120s',function(){
    var x=make(),r=x.step(frame(100000));
    assert.strictEqual(command(r,'wb-mio-gpio_195:2/K1').value,false);
    assert.strictEqual(command(r,S.outputs.basementPump).value,true);
    assert.strictEqual(command(r,S.outputs.livingPump),undefined);
});
test('after room relay OPEN and 120s observation, K4 is requested',function(){
    var x=make(),f=frame(100000);
    f.plant.outputs['wb-mio-gpio_195:2/K1']=false;
    x.step(f);f.nowMs=219999;f.roomsFrame.nowMs=f.nowMs;
    assert.strictEqual(command(x.step(f),S.outputs.livingPump),undefined);
    f.nowMs=220000;f.roomsFrame.nowMs=f.nowMs;
    var cmd=command(x.step(f),S.outputs.livingPump);
    assert.strictEqual(cmd.value,true);
    assert.strictEqual(cmd.action,'PUMP_START');
});
test('DHW accelerated mode suppresses only K4 permission, not room OPEN',function(){
    var x=make(),f=frame(100000);f.plant.tankC=44;
    f.plant.outputs[S.outputs.livingPump]=true;
    x.step(f);f.nowMs=160000;f.roomsFrame.nowMs=f.nowMs;
    var r=x.step(f);
    assert.strictEqual(r.services.dhw.mode,'ACCELERATED');
    assert.strictEqual(r.services.rooms.demands.office,true);
    assert.strictEqual(command(r,S.outputs.livingPump).value,false);
    assert.strictEqual(command(r,'wb-mio-gpio_195:2/K1').value,false);
});
test('DHW when tank warm gives no redundant K1 pump ON command',function(){
    var x=make(),f=frame(100000);f.plant.tankC=52;
    assert.strictEqual(command(x.step(f),S.outputs.dhwPump),undefined);
});
test('relays reported as integers 0/1 do not cause command spam',function(){
    var x=make(),f=frame(100000);
    f.plant.outputs[S.outputs.basementPump]=1;
    f.plant.outputs['wb-mio-gpio_195:2/K1']=0;
    var r=x.step(f);
    assert.strictEqual(command(r,S.outputs.basementPump),undefined);
    assert.strictEqual(command(r,'wb-mio-gpio_195:2/K1'),undefined);
});
test('floor remains dormant when source request has not been configured',function(){
    var x=make(),f=frame(100000);
    f.floorControl.enabled=true;f.floorControl.sourceRequestC=null;
    var r=x.step(f);
    assert.strictEqual(r.floor.pumpWanted,false);
    assert.strictEqual(command(r,S.outputs.floorPump),undefined);
    assert.strictEqual(command(r,S.outputs.floorLoops[0]),undefined);
});
test('floor correctly asks all five loops OPEN on locally enabled circuit',function(){
    var x=make(),f=frame(100000);
    f.floorControl.enabled=true;f.floorControl.sourceRequestC=49;
    var r=x.step(f);
    S.outputs.floorLoops.forEach(function(p){
        assert.strictEqual(command(r,p).value,false);
    });
    assert.strictEqual(r.floor.requestSupplyC,34);
});
test('floor protection K2 OFF at 45C, while no overall room closure',function(){
    var x=make(),f=frame(100000);
    f.floorControl.enabled=true;f.floorControl.sourceRequestC=49;
    f.plant.floorSupplyC=45;f.plant.outputs[S.outputs.floorPump]=true;
    var r=x.step(f);
    assert.strictEqual(command(r,S.outputs.floorPump).value,false);
    assert.strictEqual(r.floor.state,'HARD_SUPPLY_STOP');
    assert.strictEqual(command(r,'wb-mio-gpio_195:2/K1').value,false);
});
test('OT invalid disables source write and pump demands, not room OPEN',function(){
    var x=make(),f=frame(100000);
    f.plant.otConnectionInvalid=true;
    var r=x.step(f);
    assert.strictEqual(command(r,S.channels.otSetpoint),undefined);
    assert.strictEqual(command(r,S.outputs.basementPump),undefined);
    assert.strictEqual(command(r,'wb-mio-gpio_195:2/K1').value,false);
});
test('pump run timers for all K1–K4 are visible in plan',function(){
    var x=make(),f=frame(100000);
    f.plant.outputs[S.outputs.dhwPump]=true;
    x.step(f);f.nowMs=105000;f.roomsFrame.nowMs=f.nowMs;
    var r=x.step(f);
    assert.strictEqual(Object.keys(r.pumpTimers).length,4);
    assert.strictEqual(r.pumpTimers[S.outputs.dhwPump].observedRunMs,5000);
    assert.strictEqual(r.pumpTimers[S.outputs.basementPump].observedRunMs,null);
});
test('restarting WB resets observed pump runtime, not total equipment runtime',function(){
    var x=make(),f=frame(100000);
    f.plant.outputs[S.outputs.dhwPump]=true;x.step(f);
    f.bootEpoch='next';f.roomsFrame.bootEpoch='next';
    f.nowMs=115000;f.roomsFrame.nowMs=f.nowMs;
    assert.strictEqual(x.step(f).pumpTimers[S.outputs.dhwPump].observedRunMs,0);
});
console.log('TOTAL PASS '+n);
