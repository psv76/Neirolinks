/* Offline WB-MSW poll provenance tests, no MQTT/physical IO. */
var assert=require('assert'),E=require('../core/HHMRoomSensorEvidence'),
    T=require('../core/HHMRoomThermostat');
var count=0;
function check(n,fn){fn();count++;console.log('PASS '+n);}
function src(){return E.create({sensorId:'wb-msw-v4_22/Temperature',
    topic:'/devices/wb-msw-v4_22/controls/Temperature',
    minC:-20,maxC:60,freshMs:30000});}
function poll(seq,at,t,opts){
    var x={source:'WB_LOCAL_MODBUS_POLL',bootEpoch:'wb-boot-A',
        sensorId:'wb-msw-v4_22/Temperature',
        topic:'/devices/wb-msw-v4_22/controls/Temperature',
        pollSequence:seq,observedAtMs:at,temperatureC:t,
        retained:false,pollSucceeded:true};
    Object.keys(opts||{}).forEach(function(k){x[k]=opts[k];});
    return x;
}
check('no local Modbus poll is not a valid sample',function(){
    var e=src(),r=e.sample(1000,'wb-boot-A');
    assert.strictEqual(r.ok,false);assert.strictEqual(r.temperatureC,null);
});
check('fresh WB poll qualifies the exact room channel',function(){
    var e=src();
    assert.strictEqual(e.observePoll(poll(1,1000,24)).accepted,true);
    var r=e.sample(1100,'wb-boot-A');
    assert.strictEqual(r.ok,true);assert.strictEqual(r.temperatureC,24);
    assert.strictEqual(r.id,'wb-msw-v4_22/Temperature');
});
check('constant temperature stays healthy with new poll IDs',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    e.observePoll(poll(2,20000,24));
    assert.strictEqual(e.sample(41000,'wb-boot-A').ok,true);
});
check('unchanged poll expires even if a retained numeric MQTT value exists',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    assert.strictEqual(e.sample(31001,'wb-boot-A').ok,false);
    assert.strictEqual(e.sample(31001,'wb-boot-A').reason,'POLL_STALE');
});
check('retained MQTT value cannot update healthy evidence',function(){
    var e=src();var r=e.observePoll(poll(1,1000,24,{retained:true}));
    assert.strictEqual(r.accepted,false);
    assert.strictEqual(e.sample(1100,'wb-boot-A').ok,false);
});
check('wrong WB-MSW channel rejected',function(){
    var e=src();var r=e.observePoll(poll(1,1000,24,{
        topic:'/devices/wb-msw-v4_52/controls/Temperature'}));
    assert.strictEqual(r.accepted,false);
});
check('local source attestation is mandatory',function(){
    var e=src(),r=e.observePoll(poll(1,1000,24,{
        source:'MQTT_RETAINED_CACHE'}));
    assert.strictEqual(r.accepted,false);
});
check('duplicate or older poll IDs cannot extend freshness',function(){
    var e=src();e.observePoll(poll(3,1000,24));
    assert.strictEqual(e.observePoll(poll(3,2000,24)).accepted,false);
    assert.strictEqual(e.observePoll(poll(2,3000,24)).accepted,false);
    assert.strictEqual(e.sample(31001,'wb-boot-A').ok,false);
});
check('new boot ID revokes previous temperature immediately',function(){
    var e=src();e.observePoll(poll(3,1000,24));
    assert.strictEqual(e.sample(2000,'wb-boot-B').ok,false);
    e.observePoll(poll(1,3000,25,{bootEpoch:'wb-boot-B'}));
    assert.strictEqual(e.sample(3100,'wb-boot-B').temperatureC,25);
});
check('negative poll status invalidates prior healthy reading',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    var r=e.observePoll(poll(2,2000,24,{pollSucceeded:false}));
    assert.strictEqual(r.reason,'LOCAL_POLL_FAILED');
    assert.strictEqual(e.sample(2100,'wb-boot-A').ok,false);
});
check('physically implausible number is not a valid sensor reading',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    assert.strictEqual(e.observePoll(poll(2,2000,100)).reason,
        'INVALID_NUMERIC_TEMPERATURE');
    assert.strictEqual(e.sample(2100,'wb-boot-A').ok,false);
});
check('clock rollback invalidates previous boot evidence',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    assert.strictEqual(e.sample(900,'wb-boot-A').ok,false);
    assert.strictEqual(e.observePoll(poll(2,1001,24)).accepted,true);
});
check('out-of-order poll timestamp fails closed',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    var r=e.observePoll(poll(2,999,24));
    assert.strictEqual(r.accepted,false);
    assert.strictEqual(e.sample(1001,'wb-boot-A').ok,false);
});
check('old valid sample cannot revive itself without new successful poll',function(){
    var e=src();e.observePoll(poll(1,1000,24));
    e.sample(31001,'wb-boot-A');
    assert.strictEqual(e.sample(31002,'wb-boot-A').ok,false);
    e.observePoll(poll(2,32000,24));
    assert.strictEqual(e.sample(32001,'wb-boot-A').ok,true);
});
check('strict object contract rejects missing source channel',function(){
    assert.throws(function(){E.create({sensorId:'test',minC:-20,maxC:60,freshMs:100});},
        /poll contract/);
});
check('real sensor evidence feeds pure WB-local thermostat without HA',function(){
    var e=src();
    var store={read:function(){return {mode:'HEAT',setpointC:22,revision:1};},
        commit:function(){return true;}};
    var t=T.create({zoneId:'office',primarySensorId:'wb-msw-v4_22/Temperature',
        backupSensorId:null,minSetpointC:16,maxSetpointC:30,
        hysteresisC:0.6,minMeasuredC:-20,maxMeasuredC:60,
        sensorFreshMs:30000,recoveryStableMs:10000,
        recoverySamples:2,commandMaxAgeMs:20000,
        sensorLossHoldMs:15000},store);
    function frame(now){
        return {nowMs:now,primary:e.sample(now,'wb-boot-A'),
            backup:null,independentSafetyOk:true,hydraulicPathReady:true,
            fallbackAuthorized:true,fallbackHeatDemand:true};
    }
    e.observePoll(poll(1,1000,19));
    assert.strictEqual(t.step(frame(1100)).heatDemand,true);
    e.observePoll(poll(2,3000,19,{pollSucceeded:false}));
    assert.strictEqual(t.step(frame(3500)).state,'SENSOR_HOLD');
    assert.strictEqual(t.step(frame(3500)).heatDemand,true);
    assert.strictEqual(t.step(frame(19000)).state,'FALLBACK_HEAT');
});
check('sensor outage holds room demand and never proposes NO actuator CLOSE',function(){
    var Gate=require('../core/HHMRoomPathGate'),
        map=require('../../../Objects/05_16_Iset/HHM/room_zones'),
        e=src();
    var store={read:function(){return {mode:'HEAT',setpointC:22,revision:1};},
        commit:function(){return true;}};
    var t=T.create({zoneId:'office',primarySensorId:'wb-msw-v4_22/Temperature',
        backupSensorId:null,minSetpointC:16,maxSetpointC:30,hysteresisC:0.6,
        minMeasuredC:-20,maxMeasuredC:60,sensorFreshMs:30000,
        recoveryStableMs:10000,recoverySamples:2,commandMaxAgeMs:20000,
        sensorLossHoldMs:15000},store);
    var gate=Gate.create({zones:map.zones,openCommand:0,
        closeCommand:1,openWaitMs:180000});
    var demands={},i;
    for(i=0;i<map.zones.length;i++)demands[map.zones[i].id]=null;
    var outputs={};
    outputs['wb-mio-gpio_195:2/K1']={valid:true,value:0,
        bootEpoch:'wb-boot-A',acceptedOpenAtMs:1000};
    function evalAt(now){
        var room=t.step({nowMs:now,primary:e.sample(now,'wb-boot-A'),
            backup:null,independentSafetyOk:true,hydraulicPathReady:true,
            fallbackAuthorized:false,fallbackHeatDemand:true});
        demands.office=room.heatDemand;
        var path=gate.step({nowMs:now,demands:demands,outputs:outputs,
            bootEpoch:'wb-boot-A',protectionActive:false});
        return {room:room,path:path};
    }
    e.observePoll(poll(1,180000,19));
    var normal=evalAt(181000);
    assert.strictEqual(normal.room.heatDemand,true);
    assert.strictEqual(normal.path.pumpStartPermitted,true);
    e.observePoll(poll(2,182000,19,{pollSucceeded:false}));
    var held=evalAt(183000);
    assert.strictEqual(held.room.state,'SENSOR_HOLD');
    assert.strictEqual(held.path.pumpStartPermitted,true);
    assert.strictEqual(held.path.zones.office.action,'OPEN');
    var later=evalAt(200000);
    assert.strictEqual(later.room.heatDemand,null);
    assert.strictEqual(later.path.zones.office.action,'HOLD');
    assert.strictEqual(later.path.actuatorActions[0].desiredOutput,null);
    // No pump OFF instruction exists in this planner.
    assert.strictEqual(later.path.pumpWrite,undefined);
});
console.log('TOTAL PASS '+count);
