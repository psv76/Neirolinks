'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {create,root,epoch}=require('./harness');
const baseline=process.argv.includes('--baseline'),sources={};
let passed=0,failed=0;
function test(name,fn){try{fn();passed++;console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+': '+e.stack);}}
function cold(order=['500','620','624','600'],extra={}){
    const seed=create(),values={boiler:{},gazebo:{}},retained={boiler:{},gazebo:{}};
    for(const board of ['boiler','gazebo'])for(const [p,v]of Object.entries({... (board==='boiler'?seed.temperatures:seed.gazeboTemperatures),...seed.health[board]})){
        values[board][p]=v;values[board][p+'#error']='';retained[board][seed.topic(p)]=v;
    }
    for(const z of seed.Z)values.boiler['NL_simple_thermostat_'+z.id+'/target_state']=true;
    const h=create({values,retained,wb2465Replay:true,startOrder:order,...extra,moduleTransform:(name,text)=>{
        if(!baseline||!['HHM3Wire','HHM3Runtime'].includes(name))return text;
        return sources[name]||(sources[name]=cp.execFileSync('git',['show','c35ddbdb99874111699d29116b03381f12daef08:objects/05_31_Ivolga_13/HHM3_FSE/modules/'+name+'.js'],{cwd:root,encoding:'utf8'}));
    }});
    // Separate hardware state: response generation never republishes control data.
    const hardware=JSON.parse(JSON.stringify(values));let cursor=0;
    function respond(edit){
        let n=0;
        while(cursor<h.messages.length){
            assert.ok(n++<1000,'bounded RPC work');
            const m=h.messages[cursor++];if(!m.topic.startsWith('/rpc/v1/wb-mqtt-serial/port/Load/'))continue;
            const q=JSON.parse(m.payload),p=q.params;
            assert.equal(m.retained,false);assert.ok([2,4].includes(p.function));assert.equal(p.count,1);
            assert.equal(p.format,'HEX');assert.equal(p.total_timeout,10000);
            assert.equal(p.path,undefined);assert.equal(p.slave_id,undefined);assert.equal(p.msg,undefined);
            const input=p.address-(p.function===4?7:16)+1;assert.ok([1,2].includes(input));
            const path=p.device_id+'/External Sensor '+input+(p.function===2?' OK':'');
            let v=hardware[m.board][path],raw=p.function===4?(Math.round(v*16)&65535):v;
            let r={id:q.id,error:null,result:{response:raw.toString(16).padStart(p.function===4?4:2,'0')}};
            let flags={retained:false};
            if(edit){const out=edit({q,m,r,flags,path});if(out===false)continue;}
            h.deliver(m.board,m.topic+'/reply',JSON.stringify(r),flags.retained);
        }
    }
    function tick(){for(const id of order)h.tick(id);}
    function step(edit){h.time(h.now()+5000);tick();respond(edit);}
    return {h,hardware,respond,tick,step};
}
function allHealthy(h){
    for(const z of h.Z.filter(z=>h.C.m1w2Health[z.sensor]))assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/valid'],true,z.id);
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
    for(const p of Object.keys(h.C.m1w2Health).filter(p=>!p.startsWith('921.'))){
        const v=h.contexts['500'].io.read(p);
        if(p===h.C.source.temperature||Object.values(h.C.circuits).some(c=>c.supply===p||c.ret===p))assert.notEqual(v,null,p);
    }
    for(const pair of h.contexts['600'].HD_PAIRS)assert.notEqual(h.values.boiler['heat_diagnostics/'+pair.id],'нет данных',pair.id);
}
test('retained unchanged hardware qualifies all consumers via fresh FC04 + FC02 in both restart orders',()=>{
    for(const order of [['500','620','624','600'],['620','500','600','624']]){
        const {h,step}=cold(order);for(let i=0;i<3;i++)step();allHealthy(h);
        assert.equal(h.contexts['500'].house.read(h.now()).fresh,true);
        assert.match(h.values.boiler['HHM3_FSE/runtime_status'],/дом NORMAL/);
        assert.equal(h.values.boiler['HHM3_FSE/sensor_health_contract'],'m1w2-health-v1');
        assert.equal(h.callbacks.some(c=>/^\/devices\//.test(c.topic)&&c.retained===false&&!/^(\/devices\/A|\/devices\/wbe2-i-opentherm)/.test(c.topic)),false,'no sensor numeric republish');
        const n=h.messages.filter(m=>m.topic.startsWith('/rpc/')).length;
        for(let i=0;i<30;i++)step();assert.equal(h.messages.filter(m=>m.topic.startsWith('/rpc/')).length,n,'no post-qualification polling');
    }
});
test('dead retained-only hardware never qualifies; retries bounded, no writes or synthetic publish',()=>{
    const {h,step}=cold();for(let i=0;i<80;i++)step(()=>false);
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    assert.ok(h.Z.filter(z=>h.C.m1w2Health[z.sensor]).every(z=>h.values.boiler['NL_simple_thermostat_'+z.id+'/valid']===false));
    const counts={};for(const m of h.messages.filter(m=>m.topic.startsWith('/rpc/'))){const q=JSON.parse(m.payload);const k=m.owner+q.params.device_id+q.params.address;counts[k]=(counts[k]||0)+1;}
    assert.ok(Object.values(counts).every(n=>n<=3));
});
test('retained, wrong-id, malformed, exception and error replies never qualify',()=>{
    for(const kind of ['retained','id','badhex','exception','error']){
        const {h,step}=cold();for(let i=0;i<4;i++)step(({r,flags})=>{
            if(kind==='retained')flags.retained=true;
            if(kind==='id')r.id+=100;
            if(kind==='badhex')r.result.response='01junk';
            if(kind==='exception')r.result.exception={code:2};
            if(kind==='error')r.error={code:-32601};
        });assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false,kind);
    }
});
test('fresh RPC cannot override OK=0, active local errors, hardware sentinel/range or stale local value',()=>{
    for(const kind of ['ok','local_ok','temp_error','health_error','sentinel','range','mismatch','missing_temp','missing_health']){
        const f=cold(),h=f.h,p='921.10_TEMP_NONE/External Sensor 1',ok=h.C.m1w2Health[p];
        if(kind==='ok')f.hardware.gazebo[ok]=0;
        if(kind==='local_ok')h.values.gazebo[ok]=0;
        if(kind==='missing_temp')h.values.gazebo[p]=undefined;
        if(kind==='missing_health')h.values.gazebo[ok]=undefined;
        if(kind==='temp_error')h.values.gazebo[p+'#error']='r';
        if(kind==='health_error')h.values.gazebo[ok+'#error']='r';
        if(kind==='sentinel')f.hardware.gazebo[p]=32767/16;
        if(kind==='range'){f.hardware.gazebo[p]=80;h.values.gazebo[p]=80;}
        if(kind==='mismatch')f.hardware.gazebo[p]=26;
        for(let i=0;i<3;i++)f.step();assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false,kind);
    }
});
test('unsupported callback metadata cannot use RPC to bypass the runtime safety gate',()=>{
    const f=cold(undefined,{apiVersion:'2.40.0'});for(let i=0;i<3;i++)f.step();
    assert.equal(f.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    assert.equal(f.h.values.boiler['NL_simple_thermostat_601/valid'],false);
});
test('template native/rounded temperatures match; absent controls and late state changes stay blocked',()=>{
    for(const value of [23.7,-0.05,-0.15,0]){
        const f=cold(),p='921.10_TEMP_NONE/External Sensor 1';f.hardware.gazebo[p]=value;f.h.values.gazebo[p]=value;
        for(let i=0;i<3;i++)f.step();assert.equal(f.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true,String(value));
    }
    const f=cold(),p='921.10_TEMP_NONE/External Sensor 1';
    f.step(({m,q})=>{if(m.board==='gazebo'&&q.params.function===2)f.h.deliver('gazebo',f.h.topic(p)+'/meta/error','r',false);});
    assert.equal(f.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
});
test('late response, reboot reply and clock rollback cannot supply current-start proof',()=>{
    const f=cold();f.h.time(epoch+5000);f.tick();
    const old=f.h.messages.find(m=>m.board==='gazebo'&&m.topic.startsWith('/rpc/'));assert.ok(old);
    f.h.time(epoch+20000);f.respond();f.tick();assert.equal(f.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    const newer=cold(undefined,{stores:f.h.stores});newer.h.time(epoch+5000);newer.tick();
    const fresh=newer.h.messages.find(m=>m.board==='gazebo'&&m.topic.startsWith('/rpc/'));assert.ok(fresh);assert.notEqual(fresh.topic,old.topic);
    newer.h.deliver('gazebo',old.topic+'/reply',JSON.stringify({id:1,error:null,result:{response:'0170'}}),false);
    assert.equal(newer.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    newer.h.time(epoch-1000);newer.respond();newer.tick();assert.equal(newer.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    for(let i=0;i<3;i++)newer.step();assert.equal(newer.h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
});
console.log('RESULT: '+passed+' PASS / '+failed+' FAIL; cold-start hardware-proof regression, simulated RPC only.');
if(failed)process.exitCode=1;
