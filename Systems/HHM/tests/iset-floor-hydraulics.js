/* As-built K12..K16 + K2 + MAO4 preflight. Offline only. */
var assert=require('assert');
var cfg=require('../../../Objects/05_16_Iset/HHM/isethhm_service_config');
var mod=require('../../../Objects/05_16_Iset/HHM/isethhm_floor_hydraulics');
var passed=0;
function check(n,fn){fn();passed++;console.log('PASS '+n);}
function c(){return mod.create({outputs:cfg.outputs,actuatorOpenWaitMs:120000});}
function f(ms){return {nowMs:ms,bootEpoch:'test_boot',enabled:true,
    localSetpointC:34,supplyC:30,
    readbacks:{},independentEquipmentProtection:false};}
function act(a,name){return a.actions.filter(function(x){return x.action===name;});}
check('all five independent NO loops are mapped exactly',function(){
    var r=c().step(f(1000));
    assert.strictEqual(r.loops.length,5);
    assert.strictEqual(act(r,'FLOOR_LOOP_OPEN').length,5);
    assert.strictEqual(r.physicalWriteAllowed,false);
});
check('readback state starts 120-second wait, not a mere command',function(){
    var x=c(),v=f(1000);v.readbacks[cfg.outputs.floorLoops[0]]=false;
    var r=x.step(v);
    assert.strictEqual(r.loops[0].remainingMs,120000);
    assert.strictEqual(r.remainingOpenMs,null);
    assert.strictEqual(r.pumpWanted,false);
});
check('all five open after 120 s allow K2 only with MAO4 preflight',function(){
    var x=c(),v=f(1000);
    cfg.outputs.floorLoops.forEach(function(k){v.readbacks[k]=false;});
    v.readbacks[cfg.outputs.floorPump]=false;
    v.readbacks[cfg.outputs.floorValveEnable]=true;
    v.readbacks[cfg.outputs.floorValveLevel]=1;
    assert.strictEqual(x.step(v).pumpWanted,false);
    v.nowMs=120999;assert.strictEqual(x.step(v).pumpWanted,false);
    v.nowMs=121000;var r=x.step(v);
    assert.strictEqual(r.pumpWanted,true);
    assert.strictEqual(r.state,'READY');
    assert.strictEqual(act(r,'FLOOR_PUMP_START').length,1);
});
check('MAO4 missing readback suggests preflight command even when loops ready',function(){
    var x=c(),v=f(1000);
    cfg.outputs.floorLoops.forEach(function(k){v.readbacks[k]=false;});
    x.step(v);v.nowMs=121000;
    var r=x.step(v);
    assert.strictEqual(r.allLoopsReady,true);
    assert.strictEqual(r.pumpWanted,false);
    assert.strictEqual(act(r,'FLOOR_VALVE_PREFLIGHT').length,1);
});
check('a running K2 is not stopped only because its valve rises above 1%',function(){
    var x=c(),v=f(1000);
    cfg.outputs.floorLoops.forEach(function(k){v.readbacks[k]=false;});
    v.readbacks[cfg.outputs.floorPump]=true;
    v.readbacks[cfg.outputs.floorValveEnable]=true;
    v.readbacks[cfg.outputs.floorValveLevel]=20;
    x.step(v);v.nowMs=121000;
    var r=x.step(v);
    assert.strictEqual(r.pumpWanted,true);
    assert.strictEqual(act(r,'FLOOR_PUMP_STOP_PROTECTION').length,0);
});
check('at 40C hot port closes but K2 need not stop if loops open',function(){
    var x=c(),v=f(1000);
    cfg.outputs.floorLoops.forEach(function(k){v.readbacks[k]=false;});
    v.readbacks[cfg.outputs.floorPump]=true;
    v.readbacks[cfg.outputs.floorValveEnable]=true;
    v.readbacks[cfg.outputs.floorValveLevel]=20;
    x.step(v);v.nowMs=121000;v.supplyC=40;
    var r=x.step(v);
    assert.strictEqual(r.state,'HOT_PORT_CLOSED_CIRCULATION_ALLOWED');
    assert.strictEqual(act(r,'FLOOR_HOT_PORT_CLOSE')[0].value,0);
    assert.strictEqual(act(r,'FLOOR_PUMP_STOP_PROTECTION').length,0);
});
check('at 45C separate physical thermal stop commands K2 OFF',function(){
    var x=c(),v=f(1000);v.supplyC=45;
    v.readbacks[cfg.outputs.floorPump]=true;
    var r=x.step(v);
    assert.strictEqual(r.state,'HARD_SUPPLY_STOP');
    assert.strictEqual(act(r,'FLOOR_HOT_PORT_CLOSE').length,1);
    assert.strictEqual(act(r,'FLOOR_PUMP_STOP_PROTECTION')[0].value,false);
});
check('explicit non-sensor equipment protection stops K2',function(){
    var x=c(),v=f(1000);v.independentEquipmentProtection=true;
    v.readbacks[cfg.outputs.floorPump]=true;
    assert.strictEqual(act(x.step(v),'FLOOR_PUMP_STOP_PROTECTION').length,1);
});
check('local OFF can stop K2 without HA heartbeat',function(){
    var x=c(),v=f(1000);v.enabled=false;
    v.readbacks[cfg.outputs.floorPump]=true;
    var r=x.step(v);
    assert.strictEqual(r.state,'OFF');
    assert.strictEqual(act(r,'FLOOR_PUMP_STOP_NO_DEMAND').length,1);
});
check('reboot forces new 120s loop opening observation',function(){
    var x=c(),v=f(1000);
    cfg.outputs.floorLoops.forEach(function(k){v.readbacks[k]=false;});
    x.step(v);v.nowMs=121000;
    assert.strictEqual(x.step(v).allLoopsReady,true);
    v.bootEpoch='next';
    assert.strictEqual(x.step(v).loops[0].remainingMs,120000);
});
console.log('TOTAL PASS '+passed);
