'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const {create,epoch,root}=require('./harness');
let count=0;
function test(name,fn){fn();count++;console.log('PASS '+name);}
function running(options){const h=create(options);h.enableAll();h.samples();h.start();h.advance(300000);return h;}
test('all runtime files parse, ES5 syntax, no HM2 runtime imports',()=>{
    function walk(p){return fs.readdirSync(p,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(p,e.name)):[path.join(p,e.name)]);}
    for(const f of walk(root).filter(f=>f.endsWith('.js')&&!f.includes(path.sep+'tests'+path.sep))){
        cp.execFileSync(process.execPath,['--check',f]);const s=fs.readFileSync(f,'utf8');
        assert.doesNotMatch(s,/\b(?:const|let)\s+\w+\s*=|=>/);assert.doesNotMatch(s,/require\(['"](?:HM2|MixingController)/);
    }
});
test('fixed five-circuit map, 505 and living room are distinct; 562 has accepted values',()=>{
    const h=create(),c=h.C.circuits;
    assert.deepEqual(Object.keys(c),['501','502','503','504','505']);
    for(let n=1;n<=5;n++)assert.equal(c[String(500+n)].pump,'A03/K'+n);
    const z=h.Z.find(z=>z.id==='505');assert.equal(z.sensor,'901.01_MSW_TH/Temperature');assert.equal(z.target,20);
    assert.equal(z.hysteresis,1);assert.equal(z.min,15);assert.equal(z.max,28);assert.equal(z.outputs.length,0);
    assert.equal(h.Z.find(z=>z.id==='010').sensor,'902.01_MSW_TH/Temperature');
    assert.equal(c['504'].valveActiveMinLevel,1);assert.equal(c['504'].valveActiveMaxLevel,100);
    assert.equal(c['504'].valveOffCommand,false);assert.equal(c['504'].floorOnlyMaxPct,50);
    assert.equal(c['505'].zoneDelayMs,0);assert.equal(c['505'].kind,'direct');
    assert.equal(h.Z.flatMap(z=>z.outputs).includes('A14/K4'),false);
});
test('no physical writes before single initial commissioning; thermostat 505 initially OFF',()=>{
    const h=create();h.samples();h.advance(20000);
    assert.equal(h.physical().length,0);assert.equal(h.values.boiler['NL_simple_thermostat_505/target_state'],false);
    assert.equal(h.values.boiler['NL_simple_thermostat_505/target_temperature'],20);
});
test('legacy HHM3 retained-only JSON controls are recreated and removed through device API',()=>{
    const h=create({values:{boiler:{
        'HHM3_FSE/circuits_json':'{"legacy":1}',
        'HHM3_FSE/source_json':'{"legacy":2}',
        'HHM3_FSE/last_event_json':'{"legacy":3}'
    }}});
    for(const id of ['circuits_json','source_json','last_event_json']){
        assert.equal(h.values.boiler['HHM3_FSE/'+id],undefined,id);
        assert.equal(h.definitions.HHM3_FSE.cells[id],undefined,id);
    }
});
test('WebUI omits raw JSON and keeps short operator controls without claiming physical proof',()=>{
    const h=create(),cells=h.definitions.HHM3_FSE.cells;
    for(const id of ['circuits_json','source_json','last_event_json'])assert.equal(cells[id],undefined,id);
    for(const id of ['501','502','503','504','505'])assert.equal(cells['circuit_'+id].type,'text');
    h.enableAll();h.samples();h.start();h.advance(300000);
    assert.match(h.values.boiler['HHM3_FSE/circuit_501'],/Команда насосу/);
    assert.match(h.values.boiler['HHM3_FSE/operational_status'],/без подтверждения работы оборудования/);
    assert.doesNotMatch(h.values.boiler['HHM3_FSE/circuit_501'],/[{}\[\]]/);
    assert.equal(h.values.boiler['HHM3_FSE/circuits_json'],undefined);
    assert.equal(h.values.boiler['HHM3_FSE/source_json'],undefined);
    assert.equal(h.values.boiler['HHM3_FSE/last_event_json'],undefined);
    assert.ok(h.report()['501']);
    assert.ok(h.source().state);
    const after=create({stores:h.stores,values:h.values});
    assert.equal(after.definitions.HHM3_FSE.cells.start_heating.hidden,true);
});
test('simultaneous 501-505: pumps, paths, MAO4 target readbacks, arbiter MAX and source endpoint',()=>{
    const h=running(),r=h.report();for(const id of Object.keys(r)){assert.equal(r[id].demand,true,id);assert.equal(r[id].pump_command,true,id);}
    assert.equal(h.request(),45);assert.equal(h.values.boiler['HHM3_FSE/selected_consumer'],'503');
    assert.equal(h.values.boiler[h.C.source.setpoint],45);
    for(const id of ['501','502','504']){
        const c=h.C.circuits[id],writes=h.physical();
        assert.ok(writes.some(w=>w.path===c.enable&&w.value===true));
        assert.equal(r[id].output.state,'HEAT_COMMANDED');assert.equal(r[id].output.ready,true);
        assert.equal(r[id].output.saved_level,r[id].output.requested_level);
        assert.equal(h.values.boiler[c.enable],true);
        assert.ok(r[id].valve_pct>0,id);
    }
});
test('505 no actuator delay, hysteresis 1 C, explicit OFF persists; no other pump changes',()=>{
    const h=running();const p='NL_simple_thermostat_505/';
    h.temperatures['901.01_MSW_TH/Temperature']=20;h.advance(10000);assert.equal(h.values.boiler['A03/K5'],false);
    h.temperatures['901.01_MSW_TH/Temperature']=19.5;h.advance(10000);assert.equal(h.values.boiler['A03/K5'],false);
    h.temperatures['901.01_MSW_TH/Temperature']=19;h.advance(10000);assert.equal(h.values.boiler['A03/K5'],true);
    h.set('boiler',p+'target_state',false);h.advance(10000);assert.equal(h.values.boiler['A03/K5'],false);
    assert.equal(h.report()['503'].demand,true);assert.equal(h.request(),45);
    const b=create({stores:h.stores,values:h.values});b.samples();b.advance(240000);
    assert.equal(b.values.boiler[p+'target_state'],false);assert.equal(b.values.boiler['A03/K5'],false);
});
test('all no demand => numerical request 0; unknown physical OFF does not send 42 or guessed 0',()=>{
    const h=running();h.Z.forEach(z=>h.set('boiler','NL_simple_thermostat_'+z.id+'/target_state',false));
    h.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;h.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
    h.advance(10000);assert.equal(h.request(),0);
    const before=h.physical().filter(w=>w.path===h.C.source.setpoint).length;
    h.advance(140000);assert.equal(h.request(),0);assert.equal(h.source().requested_heating_setpoint,0);
    assert.equal(h.source().state,'NO_DEMAND_ACTION_UNCONFIRMED');
    assert.equal(h.physical().filter(w=>w.path===h.C.source.setpoint).length,before);
    h.set('boiler','NL_simple_thermostat_505/target_state',true);h.advance(10000);assert.equal(h.request(),45);
});
test('configured physical NO_DEMAND modes are explicit, CH-only and restore heat',()=>{
    for(const mode of ['setpoint_zero','ch_enable']){
        const h=running({configure:C=>C.source.noDemandMode=mode});
        h.Z.forEach(z=>h.set('boiler','NL_simple_thermostat_'+z.id+'/target_state',false));
        h.gazeboTemperatures['921.09_MSW_TH/Temperature']=25;h.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=30;
        h.advance(150000);assert.equal(h.request(),0);assert.equal(h.source().state,'NO_DEMAND');
        assert.ok(h.physical().some(w=>w.path===(mode==='setpoint_zero'?h.C.source.setpoint:h.C.source.chEnable)&&w.value===(mode==='setpoint_zero'?0:false)));
        assert.equal(h.values.boiler[mode==='setpoint_zero'?h.C.source.setpoint:h.C.source.chEnable],mode==='setpoint_zero'?0:false);
        h.set('boiler','NL_simple_thermostat_505/target_state',true);h.advance(10000);assert.equal(h.values.boiler[h.C.source.setpoint],45);
        if(mode==='ch_enable')assert.equal(h.values.boiler[h.C.source.chEnable],true);
    }
});
test('power return/rules restart: persistent service and intent, fresh sensors, no second click',()=>{
    const h=running(),b=create({stores:h.stores,values:h.values});
    assert.equal(b.report()['504'].valve_pct,0);
    b.samples();b.advance(240000);
    for(const r of Object.values(b.report()))assert.equal(r.demand,true);
    assert.equal(b.request(),45);assert.equal(b.stores.hhm3_operation.inService,true);
});
test('504 LAN/bridge outage >TTL uses local 30; neighbours survive; automatic reconnect',()=>{
    const h=running();h.bridge(false);h.advance(240000);
    assert.equal(h.report()['504'].reason,'AUTONOMOUS');assert.equal(h.report()['504'].requested_source_temperature,35);
    for(const id of ['501','502','503','505'])assert.equal(h.report()[id].demand,true);
    h.bridge(true);h.advance(15000);assert.equal(h.report()['504'].reason,'NORMAL');
});
test('504 invalid settings heartbeat stays diagnostic with bounded autonomy',()=>{
    const h=running();h.set('gazebo','NL_combo_thermostat_504/floor_max_temperature',35);h.advance(40000);
    assert.equal(h.report()['504'].reason,'AUTONOMOUS');assert.match(h.report()['504'].warning,/SETTINGS_INVALID/);
    h.set('gazebo','NL_combo_thermostat_504/floor_max_temperature',29);h.advance(10000);assert.equal(h.report()['504'].reason,'NORMAL');
});
test('504 418 lost -> floor-only cap 50 and Level 1..100 mapping -> recovery',()=>{
    const h=running();const p=h.C.circuits['504'].supply;h.temperatures[p]=undefined;
    h.deliver('boiler',h.topic(p)+'/meta/error','r');h.advance(900000);
    let r=h.report()['504'];assert.equal(r.reason,'FLOOR_ONLY');assert.ok(r.valve_pct>0&&r.valve_pct<=50);
    assert.equal(h.values.boiler[h.C.circuits['504'].level],Math.round(1+99*r.valve_pct/100));
    assert.equal(h.report()['503'].demand,true);
    h.deliver('boiler',h.topic(p)+'/meta/error','');h.temperatures[p]=25;h.advance(15000);
    assert.equal(h.report()['504'].reason,'NORMAL');
});
test('504 no 418 and no floor => explicit uncovered feedback, close hot input, neighbours active',()=>{
    const h=running();const p=h.C.circuits['504'].supply;h.temperatures[p]=undefined;h.deliver('boiler',h.topic(p)+'/meta/error','r');
    h.bridge(false);h.advance(45000);assert.equal(h.report()['504'].reason,'NO_FEEDBACK_UNCOVERED');
    assert.equal(h.report()['504'].valve_pct,0);assert.equal(h.values.boiler[h.C.circuits['504'].enable],false);
    assert.equal(h.values.boiler[h.C.circuits['504'].enable],false);assert.equal(h.report()['503'].demand,true);
});
test('504 thresholds raw 45/48/50, local stop only and controlled auto recovery',()=>{
    const h=running(),p=h.C.circuits['504'].supply;
    h.temperatures[p]=45;h.advance(5000);assert.equal(h.report()['504'].reason,'OVERHEAT_CLOSE');assert.equal(h.values.boiler['A03/K4'],true);
    h.temperatures[p]=48;h.advance(15000);assert.equal(h.values.boiler['A03/K4'],false);
    assert.equal(h.report()['503'].demand,true);h.temperatures[p]=40;h.advance(130000);
    assert.equal(h.report()['504'].reason,'NORMAL');assert.ok(h.report()['504'].valve_pct>=0);
    h.temperatures[p]=25;h.advance(70000);assert.equal(h.report()['504'].reason,'NORMAL');
    h.deliver('boiler',h.topic(p),50);assert.equal(h.values.boiler['A03/K4'],false);
});
test('floor 31 closes, fresh 33 after closure stops, persisted protection needs cooling',()=>{
    const h=running();h.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=31;h.advance(10000);
    assert.equal(h.report()['504'].reason,'OVERHEAT_CLOSE');
    h.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=33;h.advance(20000);assert.equal(h.values.boiler['A03/K4'],false);
    const b=create({stores:h.stores,values:h.values});b.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=33;
    b.samples();b.advance(60000);assert.equal(b.values.boiler['A03/K4'],false);
    b.gazeboTemperatures['921.10_TEMP_NONE/External Sensor 1']=28;b.advance(140000);assert.equal(b.values.boiler['A03/K4'],true);
});
test('house floor sensor failure closes only its zone; healthy simultaneous circuits survive',()=>{
    const h=running(),z=h.Z.find(z=>z.id==='601');h.temperatures[z.sensor]=undefined;h.deliver('boiler',h.topic(z.sensor)+'/meta/error','r');h.advance(10000);
    for(const p of z.outputs)assert.equal(h.values.boiler[p],false);
    assert.equal(h.values.boiler['A08/K2'],true);for(const id of ['501','502','503','504','505'])assert.equal(h.report()[id].demand,true,id);
    h.deliver('boiler',h.topic(z.sensor)+'/meta/error','');h.temperatures[z.sensor]=20;h.advance(190000);assert.equal(h.values.boiler['A08/K1'],true);
});
test('OT and 411 loss never cascade OFF pumps; recovery resumes source without grants',()=>{
    const h=running(),p=h.C.source.connection;h.temperatures[p]=1;h.advance(10000);
    assert.equal(h.source().state,'OT_UNAVAILABLE');for(const r of Object.values(h.report()))assert.equal(r.pump_command,true);
    const n=h.physical().filter(w=>w.path===h.C.source.setpoint).length;h.advance(65000);
    assert.equal(h.physical().filter(w=>w.path===h.C.source.setpoint).length,n);
    h.temperatures[p]=0;h.advance(10000);assert.equal(h.source().state,'ACTIVE');
    const t=h.C.source.temperature;h.temperatures[t]=undefined;h.deliver('boiler',h.topic(t)+'/meta/error','r');h.advance(10000);
    assert.equal(h.source().state,'SOURCE_SENSOR_UNAVAILABLE');assert.equal(h.report()['504'].pump_command,true);
    h.deliver('boiler',h.topic(t)+'/meta/error','');h.temperatures[t]=50;h.advance(10000);assert.equal(h.source().state,'ACTIVE');
});
test('cold source and NO_RESPONSE generate warning events, never permanent latch',()=>{
    const h=running();h.temperatures[h.C.source.temperature]=20;h.advance(1000000);
    assert.match(h.source().warning,/NO_RESPONSE/);
    for(const r of Object.values(h.report()))assert.equal(r.demand,true);
    h.temperatures[h.C.source.temperature]=50;h.advance(15000);assert.doesNotMatch(h.source().warning,/NO_RESPONSE/);
    assert.ok(h.messages.some(m=>m.topic===h.C.eventTopic&&JSON.parse(m.payload).severity==='recovery'));
});
test('output error on K4 does not suppress valve closure or healthy requests; retry automatic',()=>{
    const h=running();h.fail('A03/K4');h.temperatures[h.C.circuits['504'].supply]=50;h.advance(5000);
    assert.match(h.report()['504'].reason,/OFF_WRITE_ERROR|PUMP_WRITE_ERROR|LEVEL_WRITE_ERROR|OUTPUT_WRITE_ERROR|CLOSED/);assert.equal(h.values.boiler['A05/Channel 3 Switch'],false);
    assert.equal(h.report()['503'].demand,true);h.fail('');h.advance(35000);assert.equal(h.values.boiler['A03/K4'],false);
});
test('retained/invalid/null/stale sensors never become zero/fresh heat, recover with new samples',()=>{
    const h=create();const s=h.load('HHM3Wire').sensor();
    for(const v of [null,'',true,'nan']){s.sample(v,false,epoch);assert.equal(s.read(epoch,-20,110),null);}
    s.sample(20,true,epoch);assert.equal(s.read(epoch,-20,110),null);
    s.sample(20,false,epoch);assert.equal(s.read(epoch,-20,110),20);
    assert.equal(s.read(epoch+120000,-20,110),null);
    assert.equal(s.read(epoch+5000,-20,110),null);
    s.sample(21,false,epoch+10000);assert.equal(s.read(epoch+10000,-20,110),21);
});
test('wire v2 session/skew/TTL/replay/clock rollback plus unsupported retained',()=>{
    const h=create(),W=h.load('HHM3Wire');
    const f={v:2,source:W.SOURCE,session_id:1,seq:1,sent_ms:epoch+500,ttl_ms:30000,
        air:20,floor:23,target:22,hold:25,heat:29,enabled:true,valid:true,demand:true,mode:'HEAT',reason:'HEAT'};
    const r=W.receiver(epoch);assert.equal(r.accept(JSON.stringify(f),true,epoch),'RETAINED_REJECTED');
    r.accept(JSON.stringify(f),false,epoch);f.seq=2;f.sent_ms+=5000;r.accept(JSON.stringify(f),false,epoch+5000);
    assert.equal(r.read(epoch+5000).fresh,true);
    assert.equal(r.accept(JSON.stringify(f),false,epoch+10000),'DUPLICATE_OR_OLD');
    assert.equal(r.read(epoch+35000).fresh,false);
    assert.equal(r.read(epoch-10000).fresh,false);
    f.seq=3;f.sent_ms=epoch-10000;r.accept(JSON.stringify(f),false,epoch-10000);
    f.seq=4;f.sent_ms+=5000;r.accept(JSON.stringify(f),false,epoch-5000);assert.equal(r.read(epoch-5000).fresh,true);
    r.accept(JSON.stringify(f),undefined,epoch-5000);assert.equal(r.read(epoch).reason,'RUNTIME_UNSUPPORTED');
});
test('source arbiter independent TTL and deterministic five-way ties',()=>{
    const h=create(),select=h.load('HHM3Runtime').select,requests={};
    for(const id of h.C.priority)requests[id]={valid:true,demand:true,ready:true,at:epoch,temperature:45};
    assert.equal(select(requests,epoch).consumer,'503');
    requests['505'].temperature=55;assert.equal(select(requests,epoch).consumer,'505');
    requests['505'].at=epoch-15000;assert.equal(select(requests,epoch).consumer,'503');
    requests['503'].valid=false;assert.equal(select(requests,epoch).consumer,'502');
    for(const r of Object.values(requests))r.demand=false;assert.equal(select(requests,epoch).temperature,0);
});
test('506/507/GazeboPanel and DHW untouched; one owner per every output',()=>{
    const h=running({configure:C=>C.source.noDemandMode='ch_enable'});
    assert.ok(h.physical().length>0);
    for(const w of h.physical())assert.doesNotMatch(w.path,/A03\/K6|A04\/|905\.3|DHW|Domestic|GazeboPanel|A14\/K4/);
    const owners={};for(const w of h.physical()){(owners[w.path]||(owners[w.path]=new Set())).add(w.owner);}
    Object.values(owners).forEach(s=>assert.equal(s.size,1));
});
test('unknown requests are not physical OFF; known zero is distinct',()=>{
    const h=create(),R=h.load('HHM3Runtime'),writes=[];
    const io={read:p=>p===h.C.source.temperature?50:0,at:()=>epoch,commands:()=>[],readback:()=>({value:null}),write:(p,v)=>{writes.push([p,v]);return {ok:true,sent:true};}};
    h.C.source.noDemandMode='setpoint_zero';const step=R.source(h.C.source,{},io);
    const missing=R.select({},epoch);assert.equal(missing.demandKnown,false);
    assert.equal(step(0,true,epoch,missing.demandKnown).state,'REQUESTS_UNAVAILABLE');assert.equal(writes.length,0);
    assert.equal(step(0,true,epoch+5000,true).off_command_sent,true);assert.equal(writes[0][1],0);
});
test('house link fallback respects actuator delay and resumes without a grant',()=>{
    const h=create();h.enableAll();h.samples();h.start();h.tick('620');
    for(let i=0;i<40;i++){h.time(h.now()+5000);h.samples();
        for(const z of h.Z)for(const p of z.outputs)h.deliver('boiler',h.topic(p),h.values.boiler[p]?1:0,false);
        h.tick('624');h.tick('500');
        if(i===8){assert.equal(h.report()['503'].pump_command,false);assert.equal(h.report()['505'].pump_command,true);}
    }
    assert.equal(h.report()['503'].pump_command,true);assert.equal(h.report()['503'].reason,'DEGRADED');
    h.advance(200000);assert.equal(h.report()['503'].reason,'NORMAL');
});
test('clock jumps restart actuator qualification instead of skipping elapsed opening time',()=>{
    const h=running();h.time(h.now()+3600000);h.samples();h.tick('620');h.tick('500');
    assert.equal(h.report()['503'].pump_command,false);assert.equal(h.report()['505'].pump_command,true);
    h.advance(190000);assert.equal(h.report()['503'].pump_command,true);
});
test('501 and 502 immediate overheat stays local and automatically recovers',()=>{
    for(const id of ['501','502']){
        const h=running(),c=h.C.circuits[id];h.temperatures[c.supply]=c.supplyImmediateStopC;h.advance(5000);
        assert.equal(h.report()[id].pump_command,false);assert.equal(h.report()['504'].demand,true);assert.equal(h.report()['505'].demand,true);
        h.temperatures[c.supply]=25;h.advance(210000);assert.equal(h.report()[id].pump_command,true);
    }
});
test('source/direct thermal protection recovers on fresh stable cooling, mixed neighbours survive',()=>{
    const h=running();h.temperatures[h.C.source.temperature]=76;h.advance(5000);
    assert.equal(h.source().state,'SOURCE_OVERHEAT');assert.equal(h.report()['503'].pump_command,false);assert.equal(h.report()['505'].pump_command,false);
    assert.equal(h.report()['504'].pump_command,true);
    h.temperatures[h.C.source.temperature]=50;h.advance(135000);
    assert.equal(h.source().state,'ACTIVE');assert.equal(h.report()['503'].pump_command,true);assert.equal(h.report()['505'].pump_command,true);
});
test('house schema rejects impossible demand and unsafe counters; reference zone map preserved',()=>{
    const h=running(),R=h.load('HHM3Runtime');
    const m=h.messages.filter(m=>m.topic===h.C.houseTopic).pop(),f=JSON.parse(m.payload);assert.equal(R.houseValid(f),true);
    f.groups['505'].enabled=false;assert.equal(R.houseValid(f),false);f.groups['505'].enabled=true;
    f.seq=1e30;assert.equal(R.houseValid(f),false);
    const reference=JSON.parse(fs.readFileSync(path.join(root,'tests/zones-reference.json'),'utf8'));
    assert.deepEqual(JSON.parse(JSON.stringify(h.Z)),reference);
    assert.ok(h.messages.some(m=>m.board==='gazebo'&&m.topic===h.C.eventTopic));
});
require('./review-regressions')(test,create,epoch);
require('./level-integer-regressions')(test);
require('./wb240-regressions')(test,create,epoch);
console.log('RESULT: '+count+' groups PASS; simultaneous two-WB Node model. NOT physical tests.');
