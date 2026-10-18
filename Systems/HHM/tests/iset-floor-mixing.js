/* #204 real HHM3Mixing with Iset, fake IO only. */
var assert=require('assert');
var Mix=require('../core/HHM3Mixing');
var Is=require('../../../Objects/05_16_Iset/HHM/isethhm_floor_mixing');
var passed=0;
function check(n,fn){fn();passed++;console.log('PASS '+n);}
function mixer(){
    var writes=[];
    var x=Is.create(Mix,{
        writePosition:function(v){writes.push({kind:'LEVEL',value:v});return true;},
        writeEnable:function(v){writes.push({kind:'SWITCH',value:v});return true;}
    });
    return {x:x,writes:writes};
}
function frame(s,t){return {nowS:s,enabled:true,pumpReadback:true,
    supplyC:t===undefined?30:t,sourceC:65,targetC:34,
    valveEnableReadback:true};}
check('Iset MAO4 tuning matches on-object 45% max and 40/45 stages',function(){
    var t=Is.tuning();
    assert.strictEqual(t.maxPosPct,45);
    assert.strictEqual(t.hardMaxC,45);
    assert.strictEqual(t.reverseLockS,60);
    assert.strictEqual(t.postMoveSettleS,30);
    assert.strictEqual(t.trimMaxStepPct,2);
    assert.strictEqual(t.startupDurationS,2400);
});
check('pure mixer with stubbed relay adapter does not need HA',function(){
    var m=mixer(),r=m.x.step(frame(100,30));
    assert.strictEqual(typeof r.valvePositionPct,'number');
    assert.strictEqual(r.hardStopFromSupply,false);
});
check('40C preventive close never implies K2 stop',function(){
    var m=mixer();m.x.step(frame(100,30));
    var r=m.x.step(frame(115,40));
    assert.strictEqual(r.preventiveClose,true);
    assert.strictEqual(r.hardStopFromSupply,false);
    assert.strictEqual(r.valvePositionPct,0);
});
check('45C hard supply signal remains separate from 40C close',function(){
    var m=mixer(),r=m.x.step(frame(100,45));
    assert.strictEqual(r.preventiveClose,true);
    assert.strictEqual(r.hardStopFromSupply,true);
    assert.strictEqual(r.valvePositionPct,0);
});
check('no K2 pump writes are possible from mixing-only IO',function(){
    var m=mixer();m.x.step(frame(100,30));m.x.step(frame(115,40));
    m.writes.forEach(function(x){
        assert.ok(x.kind==='LEVEL'||x.kind==='SWITCH');
    });
});
console.log('TOTAL PASS '+passed);
