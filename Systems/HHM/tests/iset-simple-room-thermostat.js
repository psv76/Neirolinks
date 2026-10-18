/* #204 Iset simple room model — no poll attestations or physical writes. */
var assert=require('assert'),M=require('../../../Objects/05_16_Iset/HHM/simple_room_thermostat'),
    map=require('../../../Objects/05_16_Iset/HHM/room_zones'),
    Gate=require('../core/HHMRoomPathGate');
var n=0;function test(name,fn){fn();n++;console.log('PASS '+name);}
function config(zone){return {zoneId:zone||'office',
    sensorId:map.zones.filter(function(x){return x.id===(zone||'office');})[0].primarySensor,
    minSetpointC:16,maxSetpointC:30,hysteresisC:0.6,minMeasuredC:-20,maxMeasuredC:60};}
function store(s){var v=s===undefined?{mode:'HEAT',setpointC:22,revision:1}:s;
    return {read:function(){return v;},commit:function(x){v=x;return true;},
    get:function(){return v;}};}
function create(zone,st){return M.create(config(zone),st||store());}
function frame(zone,temp,fault){var x=config(zone);
    return {reading:temp===null?null:{id:x.sensorId,temperatureC:temp},
        sensorError:fault===true};}
test('Iset explicitly selects simple model, experimental policies disabled',function(){
    assert.strictEqual(map.roomThermostatImplementation,'./simple_room_thermostat');
    assert.strictEqual(map.advancedSensorEvidenceEnabled,false);
    assert.strictEqual(map.commissioned,false);
});
test('ordinary WB-MSW temperature starts room heating below setpoint',function(){
    var t=create(),r=t.step(frame('office','19.2'));
    assert.strictEqual(r.heatDemand,true);assert.strictEqual(r.state,'NORMAL');
});
test('warm room stops demanding heat with hysteresis',function(){
    var t=create();t.step(frame('office',19));
    assert.strictEqual(t.step(frame('office',23)).heatDemand,false);
});
test('stable identical MQTT value never triggers a stale timeout',function(){
    var t=create(),i,r;for(i=0;i<1000;i++)r=t.step(frame('office','19.20'));
    assert.strictEqual(r.heatDemand,true);assert.strictEqual(r.state,'NORMAL');
});
test('no new message can use the existing cached room value',function(){
    var t=create(),cached=frame('office',19);
    t.step(cached);
    assert.strictEqual(t.step(cached).heatDemand,true);
});
test('band keeps previous heat ON',function(){
    var t=create();t.step(frame('office',19));
    assert.strictEqual(t.step(frame('office',22.1)).heatDemand,true);
});
test('band keeps previous heat OFF',function(){
    var t=create();t.step(frame('office',24));
    assert.strictEqual(t.step(frame('office',21.9)).heatDemand,false);
});
test('first temperature in band uses deterministic choice',function(){
    var t=create();
    assert.strictEqual(t.step(frame('office',22.1)).heatDemand,false);
});
test('explicit WB-MSW error switches OFF only the affected zone',function(){
    var t=create();t.step(frame('office',19));
    var r=t.step(frame('office',19,true));
    assert.strictEqual(r.state,'SENSOR_ERROR');assert.strictEqual(r.heatDemand,false);
});
test('driver error clear resumes regulation without poll evidence protocol',function(){
    var t=create();t.step(frame('office',19,true));
    assert.strictEqual(t.step(frame('office',19,false)).heatDemand,true);
});
test('absence of a reading is NOT equivalent to error or heat OFF',function(){
    var t=create(),r=t.step(frame('office',null,false));
    assert.strictEqual(r.heatDemand,null);assert.strictEqual(r.state,'NO_VALID_TEMPERATURE');
    t.step(frame('office',19));
    assert.strictEqual(t.step(frame('office',null,false)).heatDemand,null);
});
test('incorrect sensor id cannot commandeer room',function(){
    var t=create(),r=t.step({sensorError:false,reading:{
        id:'wb-msw-v4_53/Temperature',temperatureC:19}});
    assert.strictEqual(r.heatDemand,null);
});
test('nonnumeric and out-of-range sensor values ignored without global fault',function(){
    var t=create();['nan','','999','22,5',Infinity,-40].forEach(function(v){
        assert.strictEqual(t.step(frame('office',v)).heatDemand,null);});
});
test('explicit user OFF does not depend on sensor data',function(){
    var t=create('office',store({mode:'OFF',setpointC:22,revision:1}));
    assert.strictEqual(t.step(frame('office',19,true)).heatDemand,false);
});
test('WB settings persist and revision increments',function(){
    var s=store(),t=create('office',s);
    var a=t.applySettings({expectedRevision:1,setpointC:24});
    assert.strictEqual(a.accepted,true);assert.strictEqual(a.settings.revision,2);
    assert.strictEqual(create('office',s).settings().setpointC,24);
});
test('stale settings revision does not overwrite WB accepted setpoint',function(){
    var t=create();assert.strictEqual(t.applySettings({
        expectedRevision:0,setpointC:23}).accepted,false);
    assert.strictEqual(t.settings().setpointC,22);
});
test('durable store failure blocks settings changes',function(){
    var st=store();st.commit=function(){return false;};
    var t=create('office',st);
    assert.strictEqual(t.applySettings({expectedRevision:1,mode:'OFF'}).accepted,false);
    assert.strictEqual(t.settings().mode,'HEAT');
});
test('no persisted setpoint: commissioning denied',function(){
    assert.throws(function(){create('office',store(null));},/stored settings/);
});
test('missing error flag is not a required sensor heartbeat',function(){
    var t=create(),r=t.step({reading:{id:config('office').sensorId,
        temperatureC:19}});
    assert.strictEqual(r.heatDemand,true);
});
test('entirely missing frame is rejected',function(){
    assert.throws(function(){create().step(null);},/input frame/);
});
test('one faulty room never vetoes healthy second room or pump start permission',function(){
    var office=create('office'),corridor=create('corridor');
    var demand={};map.zones.forEach(function(z){demand[z.id]=null;});
    demand.office=office.step(frame('office',19,true)).heatDemand;
    demand.corridor=corridor.step(frame('corridor',19,false)).heatDemand;
    var r=Gate.create({zones:map.zones,openCommand:0,closeCommand:1,
        openWaitMs:180000}).step({nowMs:300000,bootEpoch:'boot-1',
        protectionActive:false,demands:demand,
        outputs:{'wb-mio-gpio_195:2/K4':{
            valid:true,value:0,bootEpoch:'boot-1',acceptedOpenAtMs:1000}}});
    assert.strictEqual(r.zones.office.action,'CLOSE');
    assert.strictEqual(r.zones.corridor.action,'OPEN');
    assert.strictEqual(r.pumpStartPermitted,true);
    assert.strictEqual(r.pumpWrite,undefined);
});
test('simple module does not write relay, pump, MQTT or Modbus',function(){
    var t=create(),r=t.step(frame('office',19));
    ['writePump','writeValve','publish','pollSensor'].forEach(function(k){
        assert.strictEqual(t[k],undefined);assert.strictEqual(r[k],undefined);});
});
console.log('TOTAL PASS '+n);
