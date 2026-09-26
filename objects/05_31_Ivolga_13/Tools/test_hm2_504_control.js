/* Model/integration tests: simulated IO only, no network or controller access. */
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), cp=require('node:child_process');
const {harness,frame,H,Config,Control,Mixing,managerPath,senderPath,arbiterPath,root,epoch,sensorTopic,localSamples,incumbents,test}=require('./test_hm2_504.js');
const prefix='hm2_504_gp_besedka/';
const physical=['A03/K4','A05/Channel 3 Dimming Level','A05/Channel 3 Switch'];
// SYNTHETIC measured actuator. Never copied into deployed config.
function cfg(extra={}) { return Object.assign(JSON.parse(JSON.stringify(Config)),{
    valveClosedLevel:0,valveOpenLevel:100,valveClosedEnable:false,floorOnlyMaxPct:12
},extra); }
function rig(options={}) {
    const storage=options.storage||{inService:true}, config=cfg(options.config);
    let now=epoch;
    const control=Control.create(config,storage,Mixing);
    function step(extra={},advance=5000) {
        now+=advance;
        if (extra.frame) extra=Object.assign({},extra,{frame:Object.assign({},extra.frame,{sent_ms:now,seq:now})});
        return control.step(Object.assign({now,supply:25,supplyAt:now,source:50,ret:23,
            frame:frame({sent_ms:now}),linkReason:'NORMAL'},extra));
    }
    function run(ms,extra={}) {let r;for(let t=0;t<ms;t+=5000)r=step(extra);return r;}
    return {storage,config,control,step,run,now:()=>now};
}
function runtime(options={}) {
    return harness(managerPath,Object.assign({config:cfg(),stores:{ivolga_504_operation:{inService:true}},allowed:physical},options));
}
function remote(h,seq,now,overrides={}) {
    h.time(now);localSamples(h);h.emit(H.TOPIC,JSON.stringify(frame(Object.assign({seq,sent_ms:now},overrides))));h.tick();
}
test('first commissioning: no writes even OFF; one button, no restored legacy grants',()=>{
    const h=runtime({stores:{},values:Object.fromEntries(['enabled','commissioned','outputs_enabled','physical_write_grant'].map(k=>[prefix+k,true]))});
    localSamples(h);h.tick();assert.equal(h.writes.filter(([k])=>physical.includes(k)).length,0);
    for(const key of ['enabled','commissioned','outputs_enabled','physical_write_grant','reset_fault','fault_latched'])assert.equal(h.definitions[key],undefined);
    h.rules.hm2_504_first_start.then(false);assert.notEqual(h.stores.ivolga_504_operation.inService,true);
    h.rules.hm2_504_first_start.then(true);assert.equal(h.stores.ivolga_504_operation.inService,true);
    assert.equal(h.values[prefix+'request_reason'],'CIRCULATION_CHECK');
    assert.ok(h.writes.some(([k])=>physical.includes(k)));
});
test('unmeasured 562 config refuses initial start without touching outputs',()=>{
    const h=runtime({config:Config,stores:{}});h.rules.hm2_504_first_start.then(true);
    assert.notEqual(h.stores.ivolga_504_operation.inService,true);
    assert.equal(h.writes.filter(([k])=>physical.includes(k)).length,0);
    assert.match(h.values[prefix+'status'],/измерить/);
});
test('inconsistent limits or timing rejected; continued overheat requires post-close sample',()=>{
    for(const invalid of [{floorTargetMaxC:31},{maxSupplyC:46},{supplyStopC:45},{coolStableMs:0},{normalSupplyC:NaN}])
        assert.throws(()=>Control.create(cfg(invalid),{},Mixing),/504/);
    const storage={inService:true}, c=Control.create(cfg(),storage,Mixing);
    const input={now:epoch,supply:48,supplyAt:epoch,source:50,ret:23,frame:null};
    assert.equal(c.step(input).pump,true);
    input.now+=10000;assert.equal(c.step(input).pump,true);
    input.supplyAt=input.now;assert.equal(c.step(input).pump,false);
});
test('reboot / power return / rule reload preserves operation but resets measurement and ramp',()=>{
    for(const event of ['reboot','power','rules']){
        const stores={ivolga_504_operation:{inService:true}};
        const h=runtime({stores});assert.equal(h.values[prefix+'request_reason'],'NO_FEEDBACK_UNCOVERED',event);
        // Retained temperatures cannot arm heating.
        h.emit(sensorTopic('wb-m1w2_173/External Sensor 1'),25,true);h.tick();
        assert.equal(h.values[prefix+'valve_command_pct'],0);
        for(let n=0;n<16;n++)remote(h,n+1,epoch+n*5000);
        assert.equal(h.values[prefix+'request_reason'],'NORMAL');assert.ok(h.values[prefix+'valve_command_pct']>0);
        const reboot=runtime({stores,now:epoch+100000});
        assert.equal(reboot.values[prefix+'valve_command_pct'],0);
        localSamples(reboot);reboot.tick();assert.equal(reboot.values[prefix+'request_reason'],'CIRCULATION_CHECK');
    }
});
test('normal HEAT/HOLD/NO_DEMAND; postrun ends only this pump and closes hot input',()=>{
    const r=rig();let out=r.run(75000);assert.equal(out.reason,'NORMAL');assert.ok(out.valve>0);assert.equal(out.target,35);
    out=r.step({frame:frame({mode:'HOLD',reason:'HOLD'})});assert.equal(out.demand,true);
    const no={frame:frame({demand:false,reason:'NO_DEMAND'})};
    out=r.step(no);assert.equal(out.reason,'NO_DEMAND');assert.equal(out.valve,0);assert.equal(out.pump,true);
    out=r.run(125000,no);assert.equal(out.pump,false);assert.equal(out.demand,false);assert.equal(out.valid,true);
    out=r.step();assert.equal(out.reason,'CIRCULATION_CHECK');assert.equal(out.pump,true);
});
test('supply thresholds: 45 close and circulate; continuing 48 stop; 50 immediate; notification',()=>{
    const r=rig();r.run(75000);let out=r.step({supply:45});
    assert.equal(out.reason,'OVERHEAT_CLOSE');assert.equal(out.pump,true);assert.equal(out.valve,0);
    out=r.step({supply:48});assert.equal(out.pump,true);
    out=r.step({supply:48});assert.equal(out.reason,'OVERHEAT_STOP');assert.equal(out.pump,false);
    const immediate=rig().step({supply:50});assert.equal(immediate.pump,false);assert.equal(immediate.reason,'OVERHEAT_STOP');
    const h=runtime();localSamples(h,50);h.tick();
    assert.match(h.values[prefix+'notification_json'],/OVERHEAT_STOP/);
    assert.equal(h.values['A03/K4'],false);assert.equal(h.values['A05/Channel 3 Dimming Level'],0);
});
test('floor 31 closes, 33 after closing stops; simultaneous conditions choose hardest',()=>{
    const r=rig();let out=r.step({frame:frame({floor:31})});assert.equal(out.pump,true);assert.equal(out.valve,0);
    r.step({frame:frame({floor:33})});out=r.step({frame:frame({floor:33})});assert.equal(out.pump,false);
    out=rig().step({supply:50,frame:frame({floor:31})});assert.equal(out.reason,'OVERHEAT_STOP');
});
test('future-skewed floor snapshot is not a new post-close publication',()=>{
    const c=Control.create(cfg(),{inService:true},Mixing);
    const i={now:epoch,supply:null,supplyAt:null,source:50,ret:23,
        frame:frame({floor:33,sent_ms:epoch+2000})};
    assert.equal(c.step(i).pump,true);
    i.now+=10000;assert.equal(c.step(i).pump,true);
    i.frame=frame({floor:33,seq:2,sent_ms:i.now+2000});assert.equal(c.step(i).pump,false);
});
test('overheat auto recovery needs fresh cooled samples and stable duration, then closed circulation',()=>{
    const r=rig();r.step({supply:50});
    assert.equal(r.run(60000,{supply:43}).pump,false); // hysteresis not reached
    r.run(60000,{supply:40});assert.equal(r.step({supply:45}).pump,false); // resets cool interval
    assert.equal(r.run(120000,{supply:40}).pump,false);
    let out=r.step({supply:40});assert.equal(out.reason,'CIRCULATION_CHECK');assert.equal(out.pump,true);assert.equal(out.valve,0);
    out=r.run(60000,{supply:25});assert.equal(out.reason,'NORMAL');
    // Another episode recovers again, no reset/grant.
    r.step({supply:50});r.run(125000,{supply:40});assert.equal(r.storage.thermalStop,false);
});
test('thermal memory survives restart; missing sensor, old sample and clock steps cannot prove cooling',()=>{
    const storage={inService:true};const first=rig({storage});first.step({supply:50});
    const r=rig({storage});assert.equal(r.step({supply:null}).pump,false);
    r.run(130000,{supply:40,supplyAt:epoch});assert.equal(storage.thermalStop,true);
    // A future jump cannot stand in for observed stable cooling.
    assert.equal(r.step({supply:40},3600000).pump,false);
    assert.equal(r.step({supply:40},-86400000).pump,false);
    assert.equal(r.run(125000,{supply:40}).reason,'CIRCULATION_CHECK');
});
test('418 failure uses capped floor control, floor safety remains active and 418 restores automatically',()=>{
    const r=rig();r.run(75000);let out=r.run(180000,{supply:null});
    assert.equal(out.reason,'FLOOR_ONLY');assert.equal(out.demand,true);assert.ok(out.valve>0&&out.valve<=12);
    out=r.run(900000,{supply:null});assert.ok(out.valve<=12);
    out=r.step();assert.equal(out.reason,'NORMAL');
    out=r.step({supply:null,frame:frame({floor:31})});assert.equal(out.reason,'OVERHEAT_CLOSE');assert.equal(out.valve,0);
});
test('floor-only missing measured cap and both missing feedback are explicit uncovered cases',()=>{
    const cap=rig({config:{floorOnlyMaxPct:null}}).run(75000,{supply:null});
    assert.equal(cap.reason,'FLOOR_CAP_UNMEASURED');assert.equal(cap.valve,0);assert.match(cap.warning,/ПНР/);
    const r=rig();r.run(75000);const out=r.step({supply:null,frame:null});
    assert.equal(out.reason,'NO_FEEDBACK_UNCOVERED');assert.equal(out.pump,true);assert.equal(out.valve,0);
    assert.equal(out.demand,false);assert.match(out.warning,/не обеспечена/);
    assert.equal(r.run(75000).reason,'NORMAL');
});
test('remote outages longer than TTL autonomously regulate 30 C, fresh reconnect restores thermostat',()=>{
    const h=runtime();for(let n=0;n<16;n++)remote(h,n+1,epoch+n*5000);
    for(let n=16;n<120;n++){h.time(epoch+n*5000);localSamples(h);h.tick();}
    assert.equal(h.values[prefix+'request_reason'],'AUTONOMOUS');
    assert.equal(h.values[prefix+'requested_supply_c'],30);assert.equal(h.values['A03/K4'],true);
    remote(h,120,epoch+600000);assert.equal(h.values[prefix+'request_reason'],'AUTONOMOUS');
    remote(h,121,epoch+605000);assert.equal(h.values[prefix+'request_reason'],'NORMAL');
    remote(h,122,epoch+610000,{demand:false,reason:'NO_DEMAND'});
    assert.equal(h.values[prefix+'request_reason'],'NO_DEMAND');
});
test('air failure retains floor HOLD; invalid settings retain diagnosis and bounded autonomous target',()=>{
    assert.equal(H.combo({},null,22,{target:22,hold:25,heat:29,enabled:true}).demand,true);
    const r=rig();r.run(75000);
    const out=r.step({frame:frame({valid:false,demand:false,target:null,hold:null,heat:null,enabled:null,mode:'BLOCKED',reason:'SETTINGS_INVALID'})});
    assert.equal(out.reason,'AUTONOMOUS');assert.equal(out.target,30);assert.match(out.warning,/SETTINGS_INVALID/);
});
test('cold source / lost 411 or 419 / NO_RESPONSE warning never latch or disable demand',()=>{
    const r=rig();r.run(75000);
    let out=r.run(1000000,{supply:25,source:20,ret:null});
    assert.equal(out.pump,true);assert.equal(out.demand,true);assert.match(out.warning,/NO_RESPONSE/);
    out=r.step({source:null,ret:null});assert.equal(out.demand,true);
    out=r.step({supply:35,source:50,ret:30});assert.doesNotMatch(out.warning,/NO_RESPONSE/);
});
test('writer owns exactly 3 outputs; inverted scale works; Level always precedes enable independent of readback',()=>{
    const h=runtime({config:cfg({valveClosedLevel:100,valveOpenLevel:0,valveClosedEnable:true})});
    for(let n=0;n<16;n++)remote(h,n+1,epoch+n*5000);
    const writes=h.writes.filter(([k])=>physical.includes(k));assert.ok(writes.length>0);
    for(let n=0;n<writes.length;n++)if(writes[n][0]===physical[2])assert.equal(writes[n-1][0],physical[1]);
    assert.ok(h.values[physical[1]]<100);assert.equal(h.values[physical[2]],true);
});
test('IO errors retry automatically; failed pump write does not suppress close and cannot publish ready',()=>{
    let fail=true;const h=runtime({failWrite:k=>fail&&k==='A03/K4'});
    localSamples(h,50);h.tick();assert.equal(h.values[prefix+'path_ready'],false);
    assert.equal(h.values['A05/Channel 3 Dimming Level'],0);assert.match(h.values[prefix+'warning'],/ошибка записи/);
    fail=false;h.tick();assert.equal(h.values[prefix+'output_status'],'COMMANDS_SENT_NOT_FLOW_PROOF');
});
test('sender ignores legacy OFF and floor setpoints cannot reach 31; Sprut has no OFF/set binding',()=>{
    const h=harness(senderPath,{values:{'NL_combo_thermostat_504/target_state':0}});
    h.emit(sensorTopic('921.09_MSW_TH/Temperature'),20);h.emit(sensorTopic('921.10_TEMP_NONE/External Sensor 1'),23);h.tick();
    assert.equal(JSON.parse(h.published.at(-1)[1]).demand,true);assert.equal(h.definitions.target_state.readonly,true);
    h.values['NL_combo_thermostat_504/floor_max_temperature']=31;h.tick();
    assert.equal(JSON.parse(h.published.at(-1)[1]).reason,'SETTINGS_INVALID');
    const template=JSON.parse(fs.readFileSync(path.join(root,'Sprut/Templates/NL_combo_thermostat.json')));
    const state=template.services[0].characteristics.find(c=>c.type==='TargetHeatingCoolingState');
    assert.equal(state.validValues,'HEAT');assert.equal(state.link[0].topicSet,undefined);
    assert.equal(template.options.find(o=>o.name==='Пол при нагреве').maxValue,30);
});
const sourcePath=path.join(root,'Wirenboard/wb-rules/HM2_source_manager.js');
function source(values) {
    const h=harness(sourcePath,{values,allowed:['wbe2-i-opentherm_11/Heating Setpoint']});
    for(const k of ['source_commissioned','source_write_enabled','manual_source_grant','source_endpoint_confirmed','safe_off_commissioned'])
        h.values['hm2_source_manager/'+k]=true; // test fixture for existing #40 implementation, NOT live permission
    h.values['hm2_source_manager/safe_off_setpoint_c']=42; // baseline only, not approved OFF
    return h;
}
test('real 504 -> real arbiter -> real source accepts demand; OT drop/recovery leaves 504 circulating',()=>{
    const m=runtime();for(let n=0;n<16;n++)remote(m,n+1,epoch+n*5000);
    const now=epoch+75000, a=harness(arbiterPath,{values:m.values,now});a.tick();
    assert.equal(a.values['hm2_request_arbiter/selected_consumer'],'hm2_504_gp_besedka');
    const s=source(Object.assign({},a.values,{'wb-m1w2_170/External Sensor 1':50}));s.time(now);s.tick();
    assert.equal(s.values['hm2_source_manager/requested_heating_setpoint'],40);
    assert.equal(s.values['wbe2-i-opentherm_11/Heating Setpoint'],40);
    const writes=s.writes.filter(([k])=>k==='wbe2-i-opentherm_11/Heating Setpoint').length;
    s.values['wbe2-i-opentherm_11/Invalid Connection']=true;s.tick();
    assert.equal(s.writes.filter(([k])=>k==='wbe2-i-opentherm_11/Heating Setpoint').length,writes);
    m.tick();assert.equal(m.values['A03/K4'],true);
    s.values['wbe2-i-opentherm_11/Invalid Connection']=false;s.tick();
    assert.equal(s.values['hm2_source_manager/source_state'],'ACTIVE');
});
test('source changes only whitelist: 501-503/no-demand/DHW outputs match baseline in 80 scenarios',()=>{
    const original=cp.execFileSync('git',['show','c221f528b115341d79fc7d3a453463d53ec44cda:objects/05_31_Ivolga_13/Wirenboard/wb-rules/HM2_source_manager.js'],{cwd:path.resolve(root,'../..'),encoding:'utf8'});
    for(let i=0;i<80;i++){
        const values=incumbents(),a=harness(arbiterPath,{values});a.tick();
        if(i%4===0){a.values['hm2_request_arbiter/state']='INACTIVE';a.values['hm2_request_arbiter/no_demand_contract']=true;}
        a.values['wbe2-i-opentherm_11/Invalid Connection']=i%3===0;
        a.values['wb-m1w2_170/External Sensor 1']=25+i%30;
        const after=source(a.values),before=harness(sourcePath,{values:a.values,code:original,allowed:['wbe2-i-opentherm_11/Heating Setpoint']});
        Object.assign(before.values,after.values);before.tick();after.tick();
        assert.deepEqual(after.values,before.values);
        for(const h of [after,before])assert.ok(h.writes.every(([k])=>k.startsWith('hm2_source_manager/')||k==='wbe2-i-opentherm_11/Heating Setpoint'));
    }
});
test('no 504 demand or thermal stop cannot displace healthy incumbent or command DHW/other outputs',()=>{
    for(const supply of [25,50]){
        const m=runtime();remote(m,1,epoch,{demand:false,reason:'NO_DEMAND'});
        remote(m,2,epoch+5000,{demand:false,reason:'NO_DEMAND'});localSamples(m,supply);m.tick();
        const values=Object.assign({},m.values,incumbents()),a=harness(arbiterPath,{values,now:epoch+5000});a.tick();
        assert.equal(a.values['hm2_request_arbiter/selected_consumer'],'hm2_503_rad_dom');
        assert.ok(m.writes.every(([k])=>k.startsWith(prefix)||physical.includes(k)));
    }
});
