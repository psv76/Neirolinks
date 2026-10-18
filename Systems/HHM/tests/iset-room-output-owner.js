/* Iset room output owner: pure plan and explicitly gated physical commands.
 * All tests offline: no wb-rules and no controller is touched.
 */
var assert=require('assert');
var map=require('../../../Objects/05_16_Iset/HHM/room_zones');
var Planner=require('../../../Objects/05_16_Iset/HHM/room_output_planner');
var Writer=require('../../../Objects/05_16_Iset/HHM/room_output_executor');
var passed=0;
function check(n,f){f();passed++;console.log('PASS '+n);}
function create(){return Planner.create({map:map,openWaitMs:map.actuators.nominalOpenWaitMs});}
function frame(t){var d={};map.zones.forEach(function(z){d[z.id]=null;});
    return {nowMs:t,bootEpoch:'bootA',demands:d,readbacks:{},
        protectionActive:false};}
function action(s,p){return s.actions.filter(function(a){return a.path===p;})[0];}
function mock(mode,confirmed,commissioned){
    var written=[],logs=[],writer=Writer.create({
        map:Object.assign({},map,{commissioned:commissioned}),mode:mode,
        exclusiveOwnershipConfirmed:confirmed,commissioned:commissioned,
        write:function(path,value){written.push({path:path,value:value});return true;},
        log:{info:function(m){logs.push(m);},warning:function(m){logs.push(m);}}});
    return {writer:writer,written:written,logs:logs};
}
var PUMP=map.pump,OFFICE='wb-mio-gpio_195:2/K1',
    CORRIDOR='wb-mio-gpio_195:2/K4';
check('map has eleven distinct NO outputs and separate K4 pump',function(){
    var x=mock('SHADOW',false,false).writer.whitelist();
    assert.strictEqual(x.length,12);
    assert.ok(x.indexOf(PUMP)>=0);
    assert.ok(x.indexOf(CORRIDOR)>=0);
});
check('requested cold room first asks OPEN, never starts K4 prematurely',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=true;f.readbacks[PUMP]=false;
    var x=p.plan(f);
    assert.strictEqual(action(x,OFFICE).value,false);
    assert.strictEqual(action(x,PUMP),undefined);
    assert.strictEqual(x.pumpAction,'HOLD');
});
check('newly observed open output waits full 120 seconds before pump START',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=false;
    assert.strictEqual(p.plan(f).readyZones,0);
    f.nowMs=120999;assert.strictEqual(p.plan(f).pumpAction,'HOLD');
    f.nowMs=121000;
    assert.strictEqual(action(p.plan(f),PUMP).action,'PUMP_START');
});
check('pump already running and demanded zone open issues no repeat start',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=true;
    p.plan(f);f.nowMs=121000;
    var x=p.plan(f);
    assert.strictEqual(x.pumpAction,'HOLD');
    assert.strictEqual(action(x,PUMP),undefined);
});
check('single room explicit OFF stops pump BEFORE closing final valve',function(){
    var p=create(),f=frame(1000);
    map.zones.forEach(function(z){f.demands[z.id]=false;});
    f.readbacks[PUMP]=true;f.readbacks[OFFICE]=false;
    var x=p.plan(f);
    assert.strictEqual(x.actions[0].action,'PUMP_STOP');
    assert.strictEqual(action(x,OFFICE),undefined);
    assert.strictEqual(x.closureDeferred,true);
    f.nowMs=2000;f.readbacks[PUMP]=false;
    x=p.plan(f);
    assert.strictEqual(action(x,OFFICE).action,'ZONE_CLOSE');
    assert.strictEqual(action(x,PUMP),undefined);
});
check('switching rooms leaves old path open until new path qualifies',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=true;
    p.plan(f);f.nowMs=121001;p.plan(f);
    f.demands.office=false;f.demands.corridor=true;
    f.readbacks[CORRIDOR]=true;
    var x=p.plan(f);
    assert.strictEqual(action(x,CORRIDOR).action,'ZONE_OPEN');
    assert.strictEqual(action(x,OFFICE),undefined);
    f.nowMs=122000;f.readbacks[CORRIDOR]=false;p.plan(f);
    f.nowMs=242000;x=p.plan(f);
    assert.strictEqual(action(x,OFFICE).action,'ZONE_CLOSE');
});
check('unknown sensor value never closes its room or turns off K4',function(){
    var p=create(),f=frame(1000);
    f.demands.office=null;f.readbacks[PUMP]=true;
    var x=p.plan(f);
    assert.strictEqual(x.pumpAction,'HOLD');
    assert.strictEqual(action(x,OFFICE),undefined);
});
check('one errored room cannot veto another requested ready path',function(){
    var p=create(),f=frame(1000);
    f.demands.office=false;f.demands.corridor=true;
    f.readbacks[OFFICE]=false;f.readbacks[CORRIDOR]=false;
    f.readbacks[PUMP]=true;p.plan(f);
    f.nowMs=121000;var x=p.plan(f);
    assert.strictEqual(x.readyZones,1);
    assert.strictEqual(action(x,OFFICE).action,'ZONE_CLOSE');
    assert.strictEqual(x.pumpAction,'HOLD');
});
check('two-actuator room needs BOTH valves open for pump permission',function(){
    var p=create(),f=frame(1000);
    f.demands.summer_kitchen=true;
    f.readbacks['wb-mio-gpio_195:2/K2']=false;
    f.readbacks['wb-mio-gpio_195:2/K3']=true;
    f.readbacks[PUMP]=false;p.plan(f);
    f.nowMs=121000;assert.strictEqual(p.plan(f).pumpAction,'HOLD');
    f.readbacks['wb-mio-gpio_195:2/K3']=false;p.plan(f);
    f.nowMs=241000;assert.strictEqual(p.plan(f).pumpAction,'START');
});
check('independent equipment protection stops pump, without closing NO',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.protectionActive=true;
    f.readbacks[OFFICE]=false;f.readbacks[PUMP]=true;
    var x=p.plan(f);
    assert.strictEqual(x.actions.length,1);
    assert.strictEqual(x.actions[0].action,'PUMP_STOP');
});
check('restart/epoch change requires new open delay, not inherited proof',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=false;
    p.plan(f);f.nowMs=121000;assert.strictEqual(p.plan(f).pumpAction,'START');
    f.bootEpoch='bootB';assert.strictEqual(p.plan(f).pumpAction,'HOLD');
});
check('clock rollback resets open timer rather than starting pump early',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=false;
    p.plan(f);f.nowMs=121000;p.plan(f);
    f.nowMs=10;assert.strictEqual(p.plan(f).pumpAction,'HOLD');
});
check('invalid or missing demand cannot silently mean OFF',function(){
    var p=create(),f=frame(1000);delete f.demands.office;
    assert.throws(function(){p.plan(f);},/three-state/);
});
check('SHADOW executor never writes any physical output',function(){
    var m=mock('SHADOW',true,true);
    var p=create(),f=frame(1000);f.demands.office=true;
    f.readbacks[OFFICE]=true;
    var x=m.writer.apply(p.plan(f));
    assert.strictEqual(x.mode,'SHADOW');
    assert.strictEqual(m.written.length,0);
});
check('PHYSICAL without both commissioning and HM2 ownership stays off',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=true;
    var x=p.plan(f),m=mock('PHYSICAL',false,true);
    assert.strictEqual(m.writer.apply(x).written,0);
    assert.strictEqual(m.written.length,0);
    m=mock('PHYSICAL',true,false);
    assert.strictEqual(m.writer.apply(x).written,0);
    assert.strictEqual(m.written.length,0);
});
check('object-level uncommissioned Iset map blocks physical writing even with grants',function(){
    var written=[],writer=Writer.create({map:map,mode:'PHYSICAL',
        commissioned:true,exclusiveOwnershipConfirmed:true,
        write:function(p,v){written.push({p:p,v:v});return true;}});
    var result=writer.apply({state:'PLANNED_ONLY',actions:[
        {path:OFFICE,value:false,action:'ZONE_OPEN'}]});
    assert.strictEqual(result.written,0);
    assert.strictEqual(writer.ownership(),false);
    assert.strictEqual(written.length,0);
});
check('PHYSICAL mock writer emits only mapped boolean output',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=true;
    var m=mock('PHYSICAL',true,true),x=m.writer.apply(p.plan(f));
    assert.strictEqual(x.written,1);
    assert.deepStrictEqual(m.written,[{path:OFFICE,value:false}]);
    assert.ok(m.logs[0].indexOf('КОМАНДА=ZONE_OPEN')>=0);
});
check('malicious unexpected channel fails entire batch before any write',function(){
    var m=mock('PHYSICAL',true,true);
    var x=m.writer.apply({state:'PLANNED_ONLY',actions:[
        {path:OFFICE,value:false,action:'ZONE_OPEN'},
        {path:'wb-mr6cu_37/K5',value:true,action:'PUMP_START'}]});
    assert.strictEqual(x.mode,'REJECTED');
    assert.strictEqual(m.written.length,0);
});
check('duplicated output in a batch is rejected before physical writes',function(){
    var m=mock('PHYSICAL',true,true);
    var x=m.writer.apply({state:'PLANNED_ONLY',actions:[
        {path:OFFICE,value:false,action:'ZONE_OPEN'},
        {path:OFFICE,value:true,action:'ZONE_CLOSE'}]});
    assert.strictEqual(x.written,0);
    assert.strictEqual(m.written.length,0);
});
check('repeated failed write is reported without claiming physical success',function(){
    var logs=[];
    var writer=Writer.create({map:Object.assign({},map,{commissioned:true}),mode:'PHYSICAL',
        exclusiveOwnershipConfirmed:true,commissioned:true,
        write:function(){return false;},
        log:{info:function(x){logs.push(x);},
            warning:function(x){logs.push(x);}}});
    var r=writer.apply({state:'PLANNED_ONLY',actions:[
        {path:OFFICE,action:'ZONE_OPEN',value:false}]});
    assert.strictEqual(r.written,0);
    assert.strictEqual(r.failed.length,1);
    assert.ok(logs[0].indexOf('ОШИБКА=')>=0);
});
check('Iset 120s interval is single map source of truth',function(){
    assert.strictEqual(map.actuators.nominalOpenWaitMs,120000);
    assert.strictEqual(create().plan(frame(1000)).openWaitMs,120000);
});
check('one servo opening timer counts down 120, 119, 1, 0 seconds',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=false;
    var x=p.plan(f);
    assert.strictEqual(x.zones.office.actuators[0].openingRemainingMs,120000);
    assert.strictEqual(x.pumpStartRemainingMs,120000);
    f.nowMs=2000;x=p.plan(f);
    assert.strictEqual(x.zones.office.actuators[0].openingRemainingMs,119000);
    f.nowMs=120001;x=p.plan(f);
    assert.strictEqual(x.zones.office.openRemainingMs,999);
    assert.strictEqual(x.pumpAction,'HOLD');
    f.nowMs=121000;x=p.plan(f);
    assert.strictEqual(x.zones.office.openRemainingMs,0);
    assert.strictEqual(x.pumpStartRemainingMs,0);
    assert.strictEqual(x.pumpAction,'START');
});
check('unconfirmed OPEN never starts servo or pump countdown',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=true;f.readbacks[PUMP]=false;
    var x=p.plan(f);
    assert.strictEqual(x.zones.office.actuators[0].openingRemainingMs,null);
    assert.strictEqual(x.zones.office.actuators[0].state,'WAIT_OPEN');
    assert.strictEqual(x.pumpStartRemainingMs,null);
    assert.strictEqual(x.pumpStatus,'WAIT_ACTUATOR_READBACK');
});
check('unknown actuator readback never fabricates timer or OPEN',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[PUMP]=false;
    var x=p.plan(f);
    assert.strictEqual(x.zones.office.actuators[0].state,'READBACK_UNKNOWN');
    assert.strictEqual(x.zones.office.openRemainingMs,null);
    assert.strictEqual(x.pumpStartRemainingMs,null);
    assert.strictEqual(x.pumpAction,'HOLD');
});
check('multi-servo zone shows independent countdowns, waits for slowest',function(){
    var p=create(),f=frame(1000),a='wb-mio-gpio_195:2/K2',
        b='wb-mio-gpio_195:2/K3';
    f.demands.summer_kitchen=true;f.readbacks[PUMP]=false;
    f.readbacks[a]=false;f.readbacks[b]=true;
    p.plan(f);
    f.nowMs=61000;f.readbacks[b]=false;
    var x=p.plan(f);
    assert.strictEqual(x.zones.summer_kitchen.actuators[0].openingRemainingMs,60000);
    assert.strictEqual(x.zones.summer_kitchen.actuators[1].openingRemainingMs,120000);
    assert.strictEqual(x.zones.summer_kitchen.openRemainingMs,120000);
    f.nowMs=121000;x=p.plan(f);
    assert.strictEqual(x.zones.summer_kitchen.actuators[0].openingRemainingMs,0);
    assert.strictEqual(x.zones.summer_kitchen.actuators[1].openingRemainingMs,60000);
    assert.strictEqual(x.pumpAction,'HOLD');
    f.nowMs=181000;x=p.plan(f);
    assert.strictEqual(x.pumpAction,'START');
});
check('pump earliest requested ready zone governs start timer',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.demands.corridor=true;f.readbacks[PUMP]=false;
    f.readbacks[OFFICE]=false;f.readbacks[CORRIDOR]=true;
    p.plan(f);f.nowMs=31000;f.readbacks[CORRIDOR]=false;
    var x=p.plan(f);
    assert.strictEqual(x.pumpStartRemainingMs,90000);
    f.nowMs=121000;x=p.plan(f);
    assert.strictEqual(x.pumpAction,'START');
});
check('pump observed RUN duration is separate from start countdown',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;
    f.readbacks[PUMP]=false;p.plan(f);
    f.nowMs=121000;p.plan(f);
    f.nowMs=123000;f.readbacks[PUMP]=true;
    var x=p.plan(f);
    assert.strictEqual(x.pumpRunObservedMs,0);
    assert.strictEqual(x.pumpStartRemainingMs,null);
    assert.strictEqual(x.pumpStatus,'RUNNING');
    f.nowMs=128500;x=p.plan(f);
    assert.strictEqual(x.pumpRunObservedMs,5500);
});
check('pump STOP pending elapsed timer clears only after OFF readback',function(){
    var p=create(),f=frame(1000);
    map.zones.forEach(function(z){f.demands[z.id]=false;});
    f.readbacks[PUMP]=true;
    var x=p.plan(f);
    assert.strictEqual(x.pumpStopPendingMs,0);
    assert.strictEqual(x.pumpStatus,'STOP_PENDING');
    f.nowMs=4000;x=p.plan(f);
    assert.strictEqual(x.pumpStopPendingMs,3000);
    f.nowMs=4500;f.readbacks[PUMP]=false;x=p.plan(f);
    assert.strictEqual(x.pumpStopPendingMs,null);
    assert.strictEqual(x.pumpRunObservedMs,null);
    assert.strictEqual(x.pumpStatus,'OFF_ALL_ROOMS');
});
check('pump and servo diagnostic timers reset on WB epoch change',function(){
    var p=create(),f=frame(1000);
    f.demands.office=true;f.readbacks[OFFICE]=false;f.readbacks[PUMP]=true;
    p.plan(f);f.nowMs=111000;p.plan(f);
    f.bootEpoch='bootB';
    var x=p.plan(f);
    assert.strictEqual(x.zones.office.actuators[0].openingRemainingMs,120000);
    assert.strictEqual(x.pumpRunObservedMs,0);
});
console.log('TOTAL PASS '+passed);
