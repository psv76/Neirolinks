/* Offline Iset WB settings and simple eight-room shadow integration. */
var assert=require('assert');
var Map=require('../../../Objects/05_16_Iset/HHM/room_zones');
var Store=require('../../../Objects/05_16_Iset/HHM/room_settings_store');
var Simple=require('../../../Objects/05_16_Iset/HHM/simple_room_thermostat');
var Runtime=require('../../../Objects/05_16_Iset/HHM/room_local_runtime');
var Gate=require('../core/HHMRoomPathGate');
var tests=0;
function check(n,fn){fn();tests++;console.log('PASS '+n);}
function create(storage){return Runtime.create({
    map:Map,Simple:Simple,Settings:Store,PathGate:Gate,storage:storage,
    minSetpointC:16,maxSetpointC:30,hysteresisC:0.6,
    minMeasuredC:-20,maxMeasuredC:60});}
function seed(storage,id,t){
    var s=Store.create(storage,id);
    storage[s.key]=s.proposeInitial('HEAT',t===undefined?22:t);
}
function f(){
    return {nowMs:300000,bootEpoch:'sim-boot-1',temperatures:{},
        sensorErrors:{},outputReadbacks:{},protectionActive:false};}
function ready(r,path){
    r.outputReadbacks[path]={valid:true,value:0,bootEpoch:'sim-boot-1',
        acceptedOpenAtMs:110000};
}
check('missing approved WB storage never seeds room from guesses',function(){
    var raw={},r=create(raw),s=r.step(f());
    assert.strictEqual(s.mode,'SHADOW_ONLY');
    assert.strictEqual(s.roomStates.office.state,'NOT_COMMISSIONED');
    assert.strictEqual(s.demands.office,null);
    assert.strictEqual(s.physicalWriteAllowed,false);
    assert.strictEqual(Object.keys(raw).length,0);
});
check('commissioning candidate does not itself change PersistentStorage',function(){
    var raw={},r=create(raw);
    var blob=r.provisionCandidate('office','HEAT',22);
    assert.strictEqual(typeof blob,'string');
    assert.strictEqual(Object.keys(raw).length,0);
    assert.strictEqual(r.provisionCandidate('non_room','HEAT',22),null);
});
check('approved record restores after independent runtime restart',function(){
    var raw={};seed(raw,'office',22);
    assert.strictEqual(create(raw).settings('office').setpointC,22);
    assert.strictEqual(create(raw).settings('office').revision,0);
});
check('invalid and foreign stored record cannot commission room',function(){
    var raw={};seed(raw,'office');raw.iset_hhm_room_v1_office='{broken';
    assert.strictEqual(create(raw).settings('office'),null);
    raw.iset_hhm_room_v1_office=JSON.stringify({
        version:1,zoneId:'corridor',mode:'HEAT',setpointC:22,revision:0});
    assert.strictEqual(create(raw).settings('office'),null);
});
check('simple heat demand for only configured rooms',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;
    var s=r.step(x);
    assert.strictEqual(s.demands.office,true);
    assert.strictEqual(s.demands.corridor,null);
    assert.strictEqual(s.pathPlan.zones.office.action,'OPEN');
    assert.strictEqual(s.pathPlan.zones.corridor.action,'HOLD');
    assert.strictEqual(s.physicalWriteAllowed,false);
});
check('unchanged sample continues heating with no freshness timeout',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;
    r.step(x);x.nowMs+=3600000;
    assert.strictEqual(r.step(x).demands.office,true);
});
check('one explicit sensor error closes only its own room',function(){
    var raw={};seed(raw,'office');seed(raw,'corridor');
    var r=create(raw),x=f();
    x.temperatures.office=19;x.temperatures.corridor=19;
    x.sensorErrors.office=true;ready(x,'wb-mio-gpio_195:2/K4');
    var s=r.step(x);
    assert.strictEqual(s.demands.office,false);
    assert.strictEqual(s.demands.corridor,true);
    assert.strictEqual(s.pathPlan.zones.office.action,'CLOSE');
    assert.strictEqual(s.pathPlan.zones.corridor.action,'OPEN');
    assert.strictEqual(s.pathPlan.pumpStartPermitted,true);
    assert.strictEqual(s.physicalWriteAllowed,false);
});
check('missing error flag is not a heartbeat',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;delete x.sensorErrors.office;
    assert.strictEqual(r.step(x).demands.office,true);
});
check('sensor error recovered permits room again',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;x.sensorErrors.office=true;
    assert.strictEqual(r.step(x).demands.office,false);
    x.sensorErrors.office=false;
    assert.strictEqual(r.step(x).demands.office,true);
});
check('corrupt numeric sample proposes HOLD, not CLOSE',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;r.step(x);
    x.temperatures.office='error';var s=r.step(x);
    assert.strictEqual(s.demands.office,null);
    assert.strictEqual(s.pathPlan.zones.office.action,'HOLD');
});
check('settings change persists in a single room JSON blob',function(){
    var raw={};seed(raw,'office');var r=create(raw);
    var x=r.applySettings('office',{expectedRevision:0,setpointC:24});
    assert.strictEqual(x.accepted,true);
    assert.strictEqual(JSON.parse(raw.iset_hhm_room_v1_office).setpointC,24);
    assert.strictEqual(create(raw).settings('office').setpointC,24);
});
check('conflicting revision cannot overwrite accepted settings',function(){
    var raw={};seed(raw,'office');var r=create(raw);
    assert.strictEqual(r.applySettings('office',
        {expectedRevision:0,setpointC:24}).accepted,true);
    assert.strictEqual(r.applySettings('office',
        {expectedRevision:0,setpointC:17}).accepted,false);
    assert.strictEqual(r.settings('office').setpointC,24);
});
check('not commissioned room cannot receive changes implicitly',function(){
    var raw={},r=create(raw);
    assert.strictEqual(r.applySettings('office',
        {expectedRevision:0,setpointC:24}).reason,'ROOM_NOT_COMMISSIONED');
});
check('store rejects partial record and unpersisted write',function(){
    var raw={};seed(raw,'office');
    var s=Store.create(raw,'office');
    assert.strictEqual(s.commit({mode:'HEAT',setpointC:NaN,revision:1}),false);
    assert.strictEqual(s.read().setpointC,22);
});
check('source fault is not inferred from missing temperature publication',function(){
    var raw={};seed(raw,'office');var r=create(raw),x=f();
    x.temperatures.office=19;
    assert.strictEqual(r.step(x).demands.office,true);
    assert.strictEqual(r.step(x).roomStates.office.state,'NORMAL');
});
check('eight room mapping remains one-to-one with 11 NO outputs',function(){
    var raw={},i,outputs={};Map.zones.forEach(function(z){
        seed(raw,z.id);
        z.outputs.forEach(function(p){assert.strictEqual(outputs[p],undefined);
            outputs[p]=true;});
    });
    var r=create(raw),x=f();
    Map.zones.forEach(function(z){x.temperatures[z.id]=19;});
    var y=r.step(x);
    assert.strictEqual(Object.keys(outputs).length,11);
    assert.strictEqual(Object.keys(y.demands).length,8);
    assert.strictEqual(y.pathPlan.actuatorActions.length,11);
    assert.strictEqual(y.physicalWriteAllowed,false);
});
console.log('TOTAL PASS '+tests);
