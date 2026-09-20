'use strict';
// Standalone regression for integer WB-MAO4 readback and omitted duplicate ON.
// Run: node tests/level-integer-regressions.js
const assert=require('node:assert/strict');
const createOutputs=require('../modules/HHM3Outputs').create;
module.exports=function(test){
function fixture(){
    const c={periodMs:5000,commandTimeoutMs:10000,commandRetryMs:5000,
        valveActiveMinLevel:1,valveActiveMaxLevel:100,valveOffCommand:false,
        pump:'A03/K4',level:'A05/Channel 3 Dimming Level',enable:'A05/Channel 3 Switch'};
    let now=100000,counts={},values={},attempts=[],writes=[];
    let omitSameOn=true,integerReadback=true,dropEnable=false,dropLevel=false;
    function record(path,value){
        if((path===c.enable&&dropEnable)||(path===c.level&&dropLevel))return;
        counts[path]=(counts[path]||0)+1;
        values[path]=typeof value==='boolean'?value?1:0:value;
    }
    const io={
        seq:path=>counts[path]||0,
        read:path=>Object.prototype.hasOwnProperty.call(values,path)?values[path]:null,
        readback:path=>({value:io.read(path),seq:io.seq(path),at:now}),
        matches:(path,value)=>io.read(path)===(typeof value==='boolean'?value?1:0:value),
        commands:paths=>attempts.filter(w=>paths.indexOf(w.path)>=0),
        write:(path,value)=>{
            const w={path,value,sent:true,ok:true};attempts.push(w);writes.push(w);
            if(path===c.level){
                assert.equal(value%1,0,'a level command must be integer');
                const before=io.read(c.enable);
                record(c.level,integerReadback?Math.round(value):value);
                const on=value>0?1:0;
                if(before!==on||!omitSameOn)record(c.enable,on);
            }else record(path,value);
            return w;
        }
    };
    const step=createOutputs(c,io);
    return {c,io,writes,values,dropSwitch:v=>dropEnable=v,dropLevel:v=>dropLevel=v,
        inject:(path,value)=>record(path,value),
        run:(valve,pump=true,dt=5000)=>{now+=dt;attempts=[];return step({valve,pump},now);}};
}
test('20% target sends integer 21 and qualifies readback 21',()=>{
    const f=fixture();f.run(0,false);
    const r=f.run(20,true);
    assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
    assert.equal(r.requested_level,21);assert.equal(r.saved_level,21);
    assert.equal(f.io.read(f.c.enable),1);
    assert.equal(f.io.read(f.c.pump),1);
});
test('live probe: retarget 20/ON to 40/ON needs new Level, no duplicate ON',()=>{
    const f=fixture();f.run(0,false);assert.equal(f.run(20,true).state,'OPEN');
    const oldSeq=f.io.seq(f.c.enable),r=f.run(40,true);
    assert.equal(f.io.seq(f.c.enable),oldSeq);assert.equal(r.state,'OPEN');assert.equal(r.ready,true);
    assert.equal(r.requested_level,41);assert.equal(f.io.read(f.c.pump),1);
});
test('retarget rejects absent Level acknowledgment and OFF invalidates prior ON',()=>{
    const f=fixture();f.run(0,false);assert.equal(f.run(20,true).state,'OPEN');
    f.dropLevel(true);let r=f.run(40,true);assert.equal(r.state,'OPENING');
    assert.equal(r.ready,false);assert.equal(f.io.read(f.c.pump),0);
    f.inject(f.c.enable,0);f.dropLevel(false);f.inject(f.c.level,41);
    r=f.run(40,true,1000);assert.equal(r.ready,false);assert.equal(r.state,'CLOSED');
    assert.equal(f.io.read(f.c.enable),0);assert.equal(f.io.read(f.c.pump),0);
});
test('first opening from OFF cannot reuse historical ON',()=>{
    const f=fixture();f.run(0,false);f.dropSwitch(true);
    let r=f.run(20,true);assert.equal(r.state,'OPENING');assert.equal(r.ready,false);
    assert.equal(f.io.read(f.c.pump),0);
    r=f.run(20,true,10000);assert.equal(r.ready,false);
    assert.equal(f.writes.filter(w=>w.path===f.c.enable&&w.value===true).length,0);
});
test('closing preserves remembered integer Level; no Level write on close',()=>{
    const f=fixture();f.run(0,false);f.run(20,true);
    const n=f.writes.length;
    const r=f.run(0,false);
    assert.equal(r.state,'CLOSED');assert.equal(r.closed_readback_match,true);
    assert.equal(r.saved_level,21);assert.equal(f.io.read(f.c.enable),0);
    assert.equal(f.writes.slice(n).filter(w=>w.path===f.c.level).length,0);
});
test('missing new OFF acknowledgment cannot claim safe closure',()=>{
    const f=fixture();f.run(0,false);f.run(20,true);f.dropSwitch(true);
    const r=f.run(0,false);
    assert.equal(r.ready,false);assert.equal(r.closed_readback_match,false);
    assert.equal(f.io.read(f.c.pump),0);
});
};
if(require.main===module){
    let passed=0;
    module.exports(function(name,fn){fn();passed++;console.log('PASS '+name);});
    console.log('PASS integer MAO4 regressions: '+passed+' groups');
}
