'use strict';
const assert=require('node:assert/strict');
const harness=require('./harness'),epoch=harness.epoch;
const oldModules={};
function create(options={}){
    if(process.argv.includes('--baseline'))options.moduleTransform=(name,source)=>{
        if(!['HHM3Wire','HHM3Runtime'].includes(name))return source;
        if(!oldModules[name])oldModules[name]=require('node:child_process').execFileSync('git',[
            'show','14354bcf1e0033c51f02f0b242bea8aa7fa29e4e:objects/05_31_Ivolga_13/HHM3_FSE/modules/'+name+'.js'
        ],{cwd:harness.root,encoding:'utf8'});
        return oldModules[name];
    };
    return harness.create(options);
}
let passed=0,failed=0;
function test(name,fn){try{fn();passed++;console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+': '+e.message);}}
function unit(){
    const controls=[{value:23.7,error:''},{value:1,error:''}];
    const s=create().load('HHM3Wire').localM1w2(i=>controls[i]);
    const read=(t=epoch)=>s.read(t,-20,70);
    s.sample(0,23.7,false,epoch);s.sample(1,1,false,epoch);assert.equal(read(),23.7);
    return {s,controls,read};
}
test('qualified local cache absence recovers at unchanged value without either MQTT sample',()=>{
    for(const channel of [0,1]){
        const u=unit(),saved=u.controls[channel];u.controls[channel]=null;assert.equal(u.read(),null);
        u.controls[channel]=saved;assert.equal(u.read(),23.7);
        assert.equal(u.s.timestamp(),epoch);
    }
});
test('control getter exception invalidates this read, not the rules-instance admission',()=>{
    let fail=false;const W=create().load('HHM3Wire');
    const s=W.localM1w2(i=>{if(fail)throw new Error('cache unavailable');return {value:i?1:23.7,error:''};});
    s.sample(0,23.7,false,epoch);s.sample(1,1,false,epoch);assert.equal(s.read(epoch,-20,70),23.7);
    fail=true;assert.equal(s.read(epoch,-20,70),null);
    fail=false;assert.equal(s.read(epoch,-20,70),23.7);
});
test('local-only temperature/health error clear recovers without numeric or error MQTT republish',()=>{
    for(const channel of [0,1]){
        const u=unit();u.controls[channel].error='r';assert.equal(u.read(),null);
        u.controls[channel].error='';assert.equal(u.read(),23.7);
    }
});
test('local-only OK 1->0->1 recovers without re-arm or numeric republish',()=>{
    const u=unit();u.controls[1].value=0;assert.equal(u.read(),null);
    u.controls[1].value=1;assert.equal(u.read(),23.7);
});
test('invalid/out-of-range current values block and restoration recovers for qualified sensor',()=>{
    for(const value of [undefined,null,NaN,Infinity,'',true,-21,71]){
        const u=unit();u.controls[0].value=value;assert.equal(u.read(),null);
        u.controls[0].value=23.7;assert.equal(u.read(),23.7);
    }
});
test('live error callback before cache blocks; observed local error then clear recovers without numeric sample',()=>{
    for(const channel of [0,1]){
        const u=unit();u.s.error(channel,'r',false,epoch);assert.equal(u.read(),null);
        u.controls[channel].error='r';assert.equal(u.read(),null);
        u.controls[channel].error='';assert.equal(u.read(),23.7);
    }
});
test('new instance and retained revalidation cannot borrow runtime recovery admission',()=>{
    const u=unit(),W=create().load('HHM3Wire'),reboot=W.localM1w2(i=>u.controls[i]);
    reboot.sample(0,23.7,true,epoch);reboot.sample(1,1,true,epoch);
    for(let t=0;t<=600000;t+=5000)assert.equal(reboot.read(epoch+t,-20,70),null);
    u.s.sample(0,23.7,true,epoch);assert.equal(u.read(),null);
    u.s.sample(0,23.7,false,epoch);assert.equal(u.read(),23.7);
});
test('retained revalidation waits for actual local/live sample synchronization',()=>{
    const u=unit();u.s.sample(0,22,true,epoch);u.controls[0].value=22;assert.equal(u.read(),null);
    u.s.sample(0,23.7,false,epoch);assert.equal(u.read(),null);
    u.controls[0].value=23.7;assert.equal(u.read(),23.7);
});
test('invalid live callback blocks old healthy cache until model observes fault and then recovers',()=>{
    for(const [channel,bad]of [[0,100],[0,'NaN'],[1,0]]){
        const u=unit(),good=u.controls[channel].value;
        u.s.sample(channel,bad,false,epoch);assert.equal(u.read(),null);
        u.controls[channel].value=bad;assert.equal(u.read(),null);
        u.controls[channel].value=good;assert.equal(u.read(),23.7);
    }
});
test('simultaneous bad sample and control error recover together without an orphan pending latch',()=>{
    const u=unit();u.s.sample(0,100,false,epoch);u.s.sample(1,0,false,epoch);u.s.error(0,'r',false,epoch);
    u.controls[0]={value:100,error:'r'};u.controls[1].value=0;assert.equal(u.read(),null);
    u.controls[0]={value:23.7,error:''};u.controls[1].value=1;assert.equal(u.read(),23.7);
});
test('healthy local reads after startup fault do not manufacture initial admission',()=>{
    const W=create().load('HHM3Wire'),controls=[{value:23.7,error:''},{value:1,error:''}];
    const s=W.localM1w2(i=>controls[i]);
    s.sample(0,23.7,true,epoch);s.sample(1,1,true,epoch);
    controls[0].error='r';assert.equal(s.read(epoch,-20,70),null);
    controls[0].error='';assert.equal(s.read(epoch,-20,70),null);
    s.error(0,'',false,epoch);s.error(1,'',false,epoch);assert.equal(s.read(epoch,-20,70),null);
});
test('retained error clearance cannot release live fault in either callback/cache ordering',()=>{
    for(const cacheAfter of [false,true])for(const channel of [0,1]){
        const u=unit();u.s.error(channel,'r',false,epoch);u.controls[channel].error='r';assert.equal(u.read(),null);
        if(!cacheAfter)u.controls[channel].error='';
        u.s.error(channel,'',true,epoch);assert.equal(u.read(),null);
        u.controls[channel].error='';assert.equal(u.read(),null);
        u.s.error(channel,'',false,epoch);assert.equal(u.read(),23.7);
    }
});
function running(){const h=create({startOrder:['500','620','624','600']});h.enableAll();h.samples();h.start();h.advance(300000);return h;}
test('504 local cache transient: one invalid observation then immediate HOLD/normal recovery, no numeric publication',()=>{
    const h=running(),p='921.10_TEMP_NONE/External Sensor 1',before=h.messages.length;
    for(let i=0;i<3;i++){
        const value=h.values.gazebo[p];h.values.gazebo[p]=undefined;h.tick('624');
        assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
        h.values.gazebo[p]=value;h.time(h.now()+5000);h.tick('624');h.tick('500');
        assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
        assert.notEqual(h.report()['504'].reason,'AUTONOMOUS');
    }
    assert.equal(h.messages.slice(before).some(m=>m.topic===h.topic(p)),false);
});
test('qualified 504 remains valid for ten minutes after recovery with no further numeric publications',()=>{
    const h=running(),p='921.10_TEMP_NONE/External Sensor 1',v=h.values.gazebo[p];
    h.values.gazebo[p]=undefined;h.tick('624');h.values.gazebo[p]=v;
    for(let t=0;t<600000;t+=5000){
        h.time(h.now()+5000);
        h.deliver('gazebo',h.topic('921.09_MSW_TH/Temperature'),20,false);
        h.tick('624');h.tick('500');
        assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
        assert.notEqual(h.report()['504'].reason,'AUTONOMOUS');
    }
});
test('all mapped 501/502 and boiler 411-420 consumers recover current cache without republish',()=>{
    const h=running();
    for(const p of Object.keys(h.C.m1w2Health).filter(p=>!p.startsWith('921.'))){
        const value=h.values.boiler[p];h.values.boiler[p]=undefined;
        h.tick('620');h.tick('500');h.tick('600');
        h.values.boiler[p]=value;h.tick('620');h.tick('500');h.tick('600');
        for(const z of h.Z.filter(z=>z.sensor===p))assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/valid'],true,z.id);
        for(const pair of h.contexts['600'].HD_PAIRS.filter(pair=>pair.s===p||pair.r===p))
            assert.notEqual(h.values.boiler['heat_diagnostics/'+pair.id],'нет данных',pair.id);
        if(Object.values(h.C.circuits).some(c=>c.supply===p))assert.notEqual(h.contexts['500'].io.read(p),null,p);
    }
});
test('watchM1w2 logs transition cause and recovery once, with sensor identity',()=>{
    const h=running(),p='921.10_TEMP_NONE/External Sensor 1',v=h.values.gazebo[p],before=h.logs.length;
    h.values.gazebo[p]=undefined;h.tick('624');h.tick('624');
    h.values.gazebo[p]=v;h.tick('624');h.tick('624');
    const logs=h.logs.slice(before).filter(e=>e.text.includes('[M1W2 '+p+']'));
    assert.equal(logs.length,2);assert.match(logs[0].text,/LOCAL_TEMPERATURE_MISSING/);
    assert.match(logs[0].text,/"phase":"RUNTIME"/);assert.equal(logs[0].level,'warning');
    assert.match(logs[1].text,/"reason":"VALID"/);assert.equal(logs[1].level,'info');
});
console.log('RESULT: '+passed+' PASS, '+failed+' FAIL; Issue #75 offline recovery regressions.');
if(failed)process.exitCode=1;
