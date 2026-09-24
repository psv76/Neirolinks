'use strict';
const assert=require('node:assert/strict');
const {create,epoch}=require('./harness');
let count=0;
function test(name,fn){fn();count++;console.log('PASS '+name);}
function unit(){
    const channels=[{value:25,error:''},{value:1,error:''}],W=create().load('HHM3Wire');
    const s=W.localM1w2(i=>channels[i]);
    const sample=(i,v,retained=false,t=epoch)=>{channels[i].value=v;s.sample(i,v,retained,t);};
    const error=(i,v,retained=false,t=epoch)=>{channels[i].error=v;s.error(i,v,retained,t);};
    return {s,channels,sample,error,read:(t=epoch)=>s.read(t,-20,110),arm:()=>{sample(0,25);sample(1,1);}};
}
function running(options){const h=create(options);h.enableAll();h.samples();h.start();h.advance(300000);return h;}
function freezeLocal(h){
    for(const p of Object.keys(h.C.m1w2Health)){
        if(p.startsWith('921.'))h.gazeboTemperatures[p]=undefined;
        else h.temperatures[p]=undefined;
    }
    for(const board of ['boiler','gazebo'])for(const p of Object.keys(h.health[board]))h.health[board][p]=undefined;
}
test('M1W2 stable numeric and OK without any republish for 24 hours remain valid',()=>{
    const u=unit();u.arm();assert.equal(u.read(epoch+86400000),25);
    assert.equal(u.s.timestamp(),epoch,'measurement timestamp is not fabricated');
});
test('retained-only startup, partial proofs and repeated local reads cannot qualify',()=>{
    const u=unit();u.sample(0,25,true);u.sample(1,1,true);
    for(let t=0;t<300000;t+=5000)assert.equal(u.read(epoch+t),null);
    u.sample(0,25,false,epoch+300000);assert.equal(u.read(epoch+300000),null);
    u.sample(1,1,false,epoch+300001);assert.equal(u.read(epoch+300001),25);
});
test('OK 1->0->1 and repeated flapping recover without new numeric publication',()=>{
    const u=unit();u.arm();
    for(let i=0;i<5;i++){u.sample(1,0);assert.equal(u.read(),null);u.sample(1,1);assert.equal(u.read(),25);}
    assert.equal(u.s.timestamp(),epoch);
});
test('empty error metadata cannot qualify retained-only startup; rare numeric changes remain usable',()=>{
    const u=unit();u.error(0,'');u.error(1,'');assert.equal(u.read(),null);
    u.arm();assert.equal(u.read(epoch+600000),25);
    u.sample(0,26,false,epoch+600001);assert.equal(u.read(epoch+1800000),26);
});
test('temperature and health errors block until live error clearance, including unchanged recovery',()=>{
    for(const channel of [0,1]){
        const u=unit();u.arm();u.error(channel,'r');assert.equal(u.read(),null);
        u.error(channel,'',true);assert.equal(u.read(),null,'retained clearance cannot erase a live fault');
        u.sample(channel,channel===0?25:1);assert.equal(u.read(),null,'value does not clear error');
        u.error(channel,'');assert.equal(u.read(),25,'driver successful read/error-clear qualifies unchanged control');
    }
});
test('missing controls, invalid values and out-of-range cannot become zero or valid',()=>{
    for(const v of [null,undefined,'', ' ', 'NaN',NaN,Infinity,true,[],{},-21,111]){
        const u=unit();u.arm();u.sample(0,v);assert.equal(u.read(),null,String(v));
        u.sample(0,0);assert.equal(u.read(),0,'actual numeric zero is valid');
    }
    for(const v of [null,undefined,'',false,0,2,'true','01',NaN]){
        const u=unit();u.arm();u.sample(1,v);assert.equal(u.read(),null,String(v));
    }
    const u=unit();u.arm();u.channels[0]=null;assert.equal(u.read(),null);
    u.channels[0]={value:25,error:''};assert.equal(u.read(),null,'control reappearance alone is no proof');
    u.sample(0,25);assert.equal(u.read(),25);
});
test('local #error is authoritative even without an MQTT error callback',()=>{
    const u=unit();u.arm();u.channels[0].error='r';assert.equal(u.read(),null);
    u.channels[0].error='';assert.equal(u.read(),null);
    u.error(0,'');assert.equal(u.read(),25);
});
test('late retained readings, clocks and new script instances require requalification',()=>{
    const u=unit();u.arm();u.sample(0,20,true);assert.equal(u.read(),null);
    u.sample(0,26);assert.equal(u.read(),26);
    assert.equal(u.read(epoch-1),null);u.sample(0,26);assert.equal(u.read(),null);
    u.sample(1,1);assert.equal(u.read(),26);
    const reboot=unit();assert.equal(reboot.read(),null);
});
test('unsupported MQTT metadata remains sticky for M1W2 as well as network data',()=>{
    for(const flag of [undefined,null,0,'false']){
        const u=unit();u.s.sample(0,25,flag,epoch);u.arm();assert.equal(u.read(),null);
        assert.equal(u.s.runtimeStatus(),'RUNTIME_UNSUPPORTED');
    }
});
test('MQTT callback and local control-cache ordering cannot validate the previous temperature',()=>{
    const u=unit();u.arm();u.s.sample(0,80,false,epoch);assert.equal(u.read(),null);
    u.channels[0].value=80;assert.equal(u.read(),80);
    u.channels[0].value=25;assert.equal(u.read(),null);
    u.s.sample(0,25,false,epoch);assert.equal(u.read(),25);
});
test('explicit inventory contains exactly 20 required sensors and excludes empty inputs/MSW',()=>{
    const h=create(),map=h.C.m1w2Health;
    assert.equal(Object.keys(map).length,20);
    assert.equal(h.Z.filter(z=>map[z.sensor]).length,9);
    for(const p of ['wb-m1w2_121/External Sensor 2','wb-m1w2_164/External Sensor 1','wb-m1w2_164/External Sensor 2','wb-m1w2_166/External Sensor 2'])assert.equal(map[p],undefined);
    for(const z of h.Z.filter(z=>z.kind!=='floor'))assert.equal(map[z.sensor],undefined);
});
test('500/620/624 remain healthy for 10 minutes with no M1W2 numeric or OK publications',()=>{
    const h=running();freezeLocal(h);
    for(let t=0;t<600000;t+=5000){
        h.advance(5000);
        for(const id of ['501','502','503','504','505'])assert.equal(h.report()[id].reason,'NORMAL',id);
        assert.equal(h.source().state,'ACTIVE');
        assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
        for(const z of h.Z.filter(z=>h.C.m1w2Health[z.sensor]))assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/valid'],true);
    }
    assert.equal(h.values.boiler['HHM3_FSE/sensor_health_contract'],'m1w2-health-v1');
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/sensor_health_contract'],'m1w2-health-v1');
});
test('genuine 504 OK/error faults and recovery work with unchanged floor temperature',()=>{
    const h=running(),p='921.10_TEMP_NONE/External Sensor 1',ok=h.C.m1w2Health[p];freezeLocal(h);
    for(const suffix of ['', '/meta/error']){
        const topic=h.topic(ok)+suffix;
        h.deliver('gazebo',topic,suffix?'r':0);h.advance(10000);
        assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
        assert.equal(h.report()['504'].reason,'AUTONOMOUS');
        assert.equal(h.report()['502'].reason,'NORMAL');
        h.deliver('gazebo',topic,suffix?'':1);h.advance(10000);
        assert.equal(h.report()['504'].reason,'NORMAL');
    }
});
test('floor fault remains local under existing 502 safety policy; neighbours keep operating',()=>{
    const h=running(),z=h.Z.find(z=>z.circuit==='502'&&h.C.m1w2Health[z.sensor]);freezeLocal(h);
    h.deliver('boiler',h.topic(h.C.m1w2Health[z.sensor]),0);h.advance(10000);
    assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/valid'],false);
    assert.equal(h.report()['504'].reason,'NORMAL');assert.equal(h.report()['505'].reason,'NORMAL');
    h.deliver('boiler',h.topic(h.C.m1w2Health[z.sensor]),1);h.advance(240000);
    assert.equal(h.report()['502'].reason,'NORMAL');
});
test('rules restart with retained-only values cannot reuse previously qualified M1W2 state',()=>{
    const old=running(),h=create({stores:old.stores,values:old.values});
    for(const [p,ok]of Object.entries(h.C.m1w2Health)){
        const board=p.startsWith('921.')?'gazebo':'boiler';
        h.deliver(board,h.topic(p),old.values[board][p],true);
        h.deliver(board,h.topic(ok),1,true);
    }
    h.advance(150000,false);
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],false);
    for(const z of h.Z.filter(z=>h.C.m1w2Health[z.sensor]))assert.equal(h.values.boiler['NL_simple_thermostat_'+z.id+'/valid'],false);
    h.samples();h.advance(300000);
    assert.equal(h.report()['504'].reason,'NORMAL');assert.equal(h.report()['502'].reason,'NORMAL');
});
test('MSW and house/gazebo frames still expire independently of local sensor health',()=>{
    const h=running();freezeLocal(h);
    h.gazeboTemperatures['921.09_MSW_TH/Temperature']=undefined;h.advance(125000);
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/air_valid'],false);
    assert.equal(h.values.gazebo['NL_combo_thermostat_504/floor_valid'],true);
    const msw=h.Z.find(z=>z.id==='505').sensor;h.temperatures[msw]=undefined;h.advance(125000);
    assert.equal(h.values.boiler['NL_simple_thermostat_505/valid'],false);
    h.bridge(false);h.advance(35000);assert.match(h.report()['504'].warning,/MQTT_STALE/);
    // Keep local inputs and outputs refreshed but stop both sending scripts.
    for(let i=0;i<8;i++){h.time(h.now()+5000);h.samples();h.tick('500');}
    assert.match(h.report()['502'].warning,/HOUSE_LINK_LOST/);
});
test('thermal stop and recovery use qualified local observations, not numeric republish',()=>{
    const h=running(),p=h.C.source.temperature,m=h.C.circuits['502'].supply;
    h.temperatures[p]=76;h.temperatures[m]=46;h.advance(5000);
    assert.equal(h.source().state,'SOURCE_OVERHEAT');assert.equal(h.report()['502'].reason,'OVERHEAT_STOP');
    h.temperatures[p]=50;h.temperatures[m]=25;h.advance(5000);freezeLocal(h);
    h.advance(100000);assert.equal(h.source().state,'SOURCE_OVERHEAT');
    h.advance(50000);assert.equal(h.source().state,'ACTIVE');
    assert.equal(h.report()['502'].reason,'NORMAL');
});
test('health failure interrupts cooling dwell and stale retained cache cannot release protection',()=>{
    const h=running(),p=h.C.source.temperature,ok=h.C.m1w2Health[p];
    h.temperatures[p]=76;h.advance(5000);h.temperatures[p]=50;h.advance(5000);freezeLocal(h);
    h.advance(100000);h.deliver('boiler',h.topic(ok),0);h.advance(5000);
    h.deliver('boiler',h.topic(ok),1,true);h.advance(150000);
    assert.equal(h.source().state,'SOURCE_OVERHEAT');
    h.deliver('boiler',h.topic(ok),1);h.advance(100000);assert.equal(h.source().state,'SOURCE_OVERHEAT');
    h.advance(30000);assert.equal(h.source().state,'ACTIVE');
});
test('411-420 diagnostics share the contract, including 412 without a new heating interlock',()=>{
    const h=running({startOrder:['500','620','624','600']});freezeLocal(h);h.advance(180000);h.tick('600');
    const pairs=h.contexts['600'].HD_PAIRS;
    for(const pair of pairs)assert.notEqual(h.values.boiler['heat_diagnostics/'+pair.id],'нет данных');
    for(const p of Object.values(h.contexts['600'].HD_SENSORS)){
        const ok=h.C.m1w2Health[p];h.deliver('boiler',h.topic(ok),0);h.tick('600');
        for(const pair of pairs.filter(pair=>pair.s===p||pair.r===p))assert.equal(h.values.boiler['heat_diagnostics/'+pair.id],'нет данных');
        h.deliver('boiler',h.topic(ok),1);h.tick('600');
        for(const pair of pairs.filter(pair=>pair.s===p||pair.r===p))assert.notEqual(h.values.boiler['heat_diagnostics/'+pair.id],'нет данных');
    }
    const p='wb-m1w2_170/External Sensor 2';h.deliver('boiler',h.topic(h.C.m1w2Health[p]),0);h.advance(5000);
    assert.equal(h.source().state,'ACTIVE');assert.equal(h.report()['504'].reason,'NORMAL');
    assert.equal(h.physical().some(w=>w.owner==='600'),false);
});
console.log('RESULT: '+count+' sensor-health groups PASS; simulated controls, no physical tests.');
