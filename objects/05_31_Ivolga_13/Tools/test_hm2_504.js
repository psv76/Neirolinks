/* Offline contract tests. No network, SSH, MQTT connection or physical outputs. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const cp = require('node:child_process');
const root = path.resolve(__dirname, '..');
const repo = path.resolve(root, '../..');
const modulePath = path.join(root, 'Wirenboard/wb-rules-modules/HM2504.js');
const H = require(modulePath);
const mixingPath = path.join(repo, 'Templates/WB-rules/Heating/HM2/MixingController/MixingController.js');
const Mixing = require(mixingPath);
const managerPath = path.join(root, 'Wirenboard/wb-rules/504_gp_besedka_manager.js');
const senderPath = path.join(root, 'Besedka/wb-rules/624_combo_besedka.js');
const arbiterPath = path.join(root, 'Wirenboard/wb-rules/HM2_arbiter_request.js');
const epoch = 1800000000000;
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS ' + name); }
function frame(overrides = {}) {
    return Object.assign({ v: 1, source: H.SOURCE, boot_ms: epoch, seq: 1, sent_ms: epoch,
        ttl_ms: H.TTL_MS, air: 20, floor: 22, target: 22, hold: 25, heat: 29,
        enabled: true, valid: true, demand: true, mode: 'HEAT', reason: 'HEAT' }, overrides);
}
function receive(r, overrides, now = epoch, retained = false) {
    return r.accept(JSON.stringify(frame(overrides)), retained, now);
}
function harness(file, options = {}) {
    let now = options.now || epoch;
    const values = Object.assign({}, options.values), writes = [], published = [], tracks = {}, rules = {};
    const stores = options.stores || {};
    const definitions = {};
    const prefix = file === senderPath ? 'NL_combo_thermostat_504/' :
        (file === managerPath ? 'hm2_504_gp_besedka/' : 'hm2_request_arbiter/');
    const dev = new Proxy(values, { set(o, k, v) {
        assert.ok(k.startsWith(prefix), 'Forbidden write: ' + k);
        assert.notEqual(v, undefined); assert.notEqual(v, null);
        if (typeof v === 'number') assert.ok(Number.isFinite(v));
        writes.push([k, v]); o[k] = v; return true;
    }});
    class Clock extends Date { constructor(...args) { super(...(args.length ? args : [now])); } static now() { return now; } }
    const logger = () => {}; logger.info = logger.warning = logger.error = logger;
    const context = vm.createContext({ dev, Date: Clock, log: logger,
        require: n => n === 'HM2504' ? H : (n === 'MixingController' ? Mixing : assert.fail(n)),
        PersistentStorage: function (name) { return stores[name] || (stores[name] = {}); },
        defineVirtualDevice: (id, d) => Object.entries(d.cells).forEach(([k, c]) => {
            definitions[k] = c;
            if (c.forceDefault || values[id + '/' + k] === undefined) values[id + '/' + k] = c.value;
        }),
        defineRule: (name, r) => { rules[name] = r; },
        trackMqtt: (topic, callback) => { tracks[topic] = callback; },
        publish: (...args) => published.push(args),
        setTimeout: () => 1, setInterval: () => 2 });
    vm.runInContext(options.code || fs.readFileSync(file, 'utf8'), context, { filename: file });
    return { context, values, stores, writes, published, definitions, rules,
        time: t => { now = t; }, tick: () => context.evaluate(),
        emit: (topic, value, retained = false) => {
            assert.ok(tracks[topic], topic); tracks[topic]({ topic, value: String(value), retained, qos: 0 });
        } };
}
const settings = { target: 22, hold: 25, heat: 29, enabled: true };
test('ES5-style runtime files parse with node --check', () => {
    for (const f of [modulePath, managerPath, senderPath, arbiterPath]) {
        cp.execFileSync(process.execPath, ['--check', f]);
        assert.ok(!/\b(?:const|let)\s+\w+\s*=|=>/.test(fs.readFileSync(f, 'utf8')));
    }
});
test('combo heat / hysteresis / hold demand / no demand / OFF', () => {
    const m = {};
    assert.equal(H.combo(m, 20, 27, settings).demand, true);
    assert.equal(H.combo(m, 22, 28.5, settings).demand, true);
    assert.equal(H.combo(m, 22, 29, settings).demand, false);
    assert.equal(H.combo(m, 23, 23, settings).demand, true);
    assert.equal(H.combo(m, 23, 25, settings).demand, false);
    assert.equal(H.combo(m, 20, 20, { ...settings, enabled: false }).reason, 'OFF');
});
test('one/both sensors offline, floor required, auto-recovery', () => {
    const m = {};
    assert.equal(H.combo(m, null, 23, settings).reason, 'AIR_SENSOR_INVALID_HOLD');
    assert.equal(H.combo(m, null, 23, settings).demand, true);
    assert.equal(H.combo(m, 20, null, settings).valid, false);
    assert.equal(H.combo(m, null, null, settings).reason, 'BOTH_SENSORS_INVALID');
    assert.equal(H.combo(m, 20, 23, settings).demand, true);
});
test('cascade matches actual Plod reference for normal and air-offline cases', () => {
    const reference = fs.readFileSync(path.join(repo, 'objects/05_38_Plod_47/etc/wb-rules/600_thermostats.js'), 'utf8');
    function fn(name) {
        const start = reference.indexOf('function ' + name + '(');
        assert.ok(start >= 0);
        const end = reference.indexOf('\nfunction ', start + 1);
        return reference.slice(start, end);
    }
    const c = vm.createContext({ AC_MODE_OFF: 0, hasTopic: () => true });
    for (const n of ['updateAirMode', 'calculateFloorCommand', 'calculateComboDecision']) vm.runInContext(fn(n), c);
    const m = {}, zone = { state: {}, airHysteresis: 0.3, floorHysteresis: 1 };
    for (const [a, f] of [[20,22],[22,28.5],[22,29],[23,23],[23,25],[null,23],[null,25],[20,23]]) {
        const zs = { airValid: a !== null, floorValid: true, air: a, floor: f, target: 22,
            floorHoldTarget: 25, floorHeatTarget: 29, enabled: true };
        assert.equal(H.combo(m, a, f, settings).demand, c.calculateComboDecision(zone, zs).heat);
    }
    const ref = c.calculateComboDecision(zone, { airValid:true, floorValid:false, air:20, target:22, enabled:true });
    assert.equal(ref.heat, true); // Explicit intentional difference: reference heats without floor sensor.
    assert.equal(H.combo(m, 20, null, settings).demand, false);
});
test('invalid settings and coercions are blocked', () => {
    for (const bad of [null, NaN, Infinity, '22', true, -1, 100]) {
        assert.equal(H.combo({}, 20, 22, { ...settings, target: bad }).valid, false);
    }
    assert.equal(H.combo({}, 20, 22, { ...settings, hold: 30, heat: 20 }).valid, false);
    assert.equal(H.number(''), null); assert.equal(H.number('  '), null); assert.equal(H.number(true), null);
});
test('sensor retained/startup/error/TTL/clock rollback', () => {
    const s = H.sensor();
    s.sample('22', true, epoch); assert.equal(s.read(epoch, -20, 60), null);
    s.sample('22', false, epoch); assert.equal(s.read(epoch, -20, 60), 22);
    assert.equal(s.read(epoch - 1, -20, 60), null);
    assert.equal(s.read(epoch + H.SENSOR_TTL_MS, -20, 60), null);
    s.error('r'); s.sample('22', false, epoch); assert.equal(s.read(epoch, -20, 60), null);
    s.error(''); assert.equal(s.read(epoch, -20, 60), null);
    s.sample('22', false, epoch); assert.equal(s.read(epoch, -20, 60), 22);
});
test('receiver requires two spaced fresh frames; duplicates never refresh age', () => {
    const r = H.receiver(epoch);
    assert.equal(receive(r, {}, epoch, true), 'RETAINED_REJECTED');
    assert.equal(receive(r, {}), 'STARTUP_VALIDATION');
    assert.equal(r.read(epoch).fresh, false);
    assert.equal(receive(r, {seq:2,sent_ms:epoch+5000}, epoch+5000), 'NORMAL');
    assert.equal(r.read(epoch+5000).fresh, true);
    assert.equal(receive(r, {seq:2,sent_ms:epoch+5000}, epoch+20000), 'DUPLICATE_OR_OLD');
    assert.equal(r.read(epoch+35000).fresh, false);
});
test('outage/reconnect and burst queue require revalidation; auto-return', () => {
    const r = H.receiver(epoch);
    receive(r, {}); receive(r, {seq:2,sent_ms:epoch+5000}, epoch+5000);
    assert.equal(r.read(epoch+35000).reason, 'MQTT_STALE');
    receive(r, {seq:3,sent_ms:epoch+40000}, epoch+40000);
    receive(r, {seq:4,sent_ms:epoch+40001}, epoch+40001);
    assert.equal(r.read(epoch+40001).fresh, false);
    receive(r, {seq:5,sent_ms:epoch+45000}, epoch+45000);
    assert.equal(r.read(epoch+45000).fresh, true);
});
test('sender and receiver reboot, old session, stale/future frames', () => {
    const r = H.receiver(epoch);
    receive(r, {}); receive(r, {seq:2,sent_ms:epoch+5000}, epoch+5000);
    assert.equal(receive(r, {boot_ms:epoch+10000,sent_ms:epoch+10000}, epoch+10000), 'STARTUP_VALIDATION');
    assert.equal(receive(r, {seq:3,sent_ms:epoch+11000}, epoch+11000), 'DUPLICATE_OR_OLD');
    assert.equal(receive(r, {boot_ms:epoch+10000,seq:2,sent_ms:epoch+15000}, epoch+15000), 'NORMAL');
    const reboot = H.receiver(epoch+20000);
    assert.equal(receive(reboot, {seq:4,sent_ms:epoch+19000}, epoch+20000), 'STALE_OR_CLOCK');
    assert.equal(receive(reboot, {seq:5,sent_ms:epoch+21000}, epoch+20000), 'STALE_OR_CLOCK');
    assert.equal(receive(reboot, {seq:6,sent_ms:epoch+20000}, epoch+50000), 'STALE_OR_CLOCK');
});
test('wire schema refuses extra keys, invalid identity/types, demand without freshness', () => {
    const r = H.receiver(epoch);
    for (const f of [{source:'foreign'},{v:2},{seq:0},{seq:1.5},{seq:'1'},{ttl_ms:999999},
        {floor:null},{valid:false},{demand:1},{target:null},{on:true},{air:Infinity}]) {
        assert.equal(receive(r, f), 'INVALID_FRAME', JSON.stringify(f));
    }
    assert.equal(r.accept('bad', false, epoch), 'INVALID_JSON');
    assert.equal(r.accept('{}', undefined, epoch), 'RETAINED_REJECTED');
});
function sensorTopic(p) { const i=p.indexOf('/'); return '/devices/'+p.slice(0,i)+'/controls/'+p.slice(i+1); }
function localSamples(h, supply = 25) {
    h.emit(sensorTopic('wb-m1w2_173/External Sensor 1'), supply);
    h.emit(sensorTopic('wb-m1w2_173/External Sensor 2'), 24);
    h.emit(sensorTopic('wb-m1w2_170/External Sensor 1'), 45);
}
test('sender integration: retained cannot demand; fresh sensors publish valid exact non-retained frame', () => {
    const h = harness(senderPath, { values: {'NL_combo_thermostat_504/target_state':1} });
    h.emit(sensorTopic('921.09_MSW_TH/Temperature'),20,true);
    h.emit(sensorTopic('921.10_TEMP_NONE/External Sensor 1'),23,true); h.tick();
    assert.equal(JSON.parse(h.published.at(-1)[1]).valid,false);
    h.emit(sensorTopic('921.09_MSW_TH/Temperature'),20);
    h.emit(sensorTopic('921.10_TEMP_NONE/External Sensor 1'),23); h.tick();
    const [topic, payload, qos, retain] = h.published.at(-1);
    assert.equal(topic,H.TOPIC); assert.equal(qos,0); assert.equal(retain,false);
    assert.equal(H.frameValid(JSON.parse(payload)),true);
    assert.equal(JSON.parse(payload).demand,true);
});
test('settings survive restart; calculated state and sensor freshness do not', () => {
    const values = { 'NL_combo_thermostat_504/target_temperature':24,
        'NL_combo_thermostat_504/floor_min_temperature':26,
        'NL_combo_thermostat_504/floor_max_temperature':30,
        'NL_combo_thermostat_504/target_state':1, 'NL_combo_thermostat_504/current_state':1 };
    const h = harness(senderPath,{values}); h.tick();
    assert.equal(h.values['NL_combo_thermostat_504/target_temperature'],24);
    assert.equal(h.values['NL_combo_thermostat_504/floor_min_temperature'],26);
    assert.equal(h.values['NL_combo_thermostat_504/current_state'],0);
    const h2 = harness(senderPath,{values:h.values,stores:h.stores,now:epoch+5000}); h2.tick();
    assert.ok(JSON.parse(h2.published[0][1]).boot_ms > JSON.parse(h.published[0][1]).boot_ms);
    assert.equal(JSON.parse(h2.published[0][1]).demand,false);
});
test('manager startup/all gates forced off, no physical writes including OFF', () => {
    const values = {};
    for (const k of ['enabled','commissioned','outputs_enabled','physical_write_grant','valid','heat_demand','path_ready']) values['hm2_504_gp_besedka/'+k]=true;
    const h = harness(managerPath,{values});
    localSamples(h); h.tick();
    for (const k of Object.keys(values)) assert.equal(h.values[k],false,k);
    assert.equal(h.values['hm2_504_gp_besedka/state'],'UNKNOWN');
    assert.equal(JSON.parse(h.values['hm2_504_gp_besedka/request_json']).valid,false);
});
test('manager valid transport -> blocked; outage -> DEGRADED; reconnect -> blocked automatically', () => {
    const h = harness(managerPath); localSamples(h);
    h.emit(H.TOPIC,JSON.stringify(frame()));
    h.time(epoch+5000); h.emit(H.TOPIC,JSON.stringify(frame({seq:2,sent_ms:epoch+5000}))); h.tick();
    assert.equal(h.values['hm2_504_gp_besedka/request_reason'],'DECISION_REQUIRED');
    assert.equal(h.values['hm2_504_gp_besedka/remote_demand'],true);
    h.time(epoch+35000); h.tick();
    assert.equal(h.values['hm2_504_gp_besedka/request_reason'],'DEGRADED_POLICY_NOT_CONFIRMED');
    assert.equal(h.values['hm2_504_gp_besedka/remote_demand'],false);
    h.emit(H.TOPIC,JSON.stringify(frame({seq:3,sent_ms:epoch+35000})));
    h.time(epoch+40000); h.emit(H.TOPIC,JSON.stringify(frame({seq:4,sent_ms:epoch+40000}))); h.tick();
    assert.equal(h.values['hm2_504_gp_besedka/request_reason'],'DECISION_REQUIRED');
});
test('411/418/419 errors independently interlock, local safety dominates link loss', () => {
    for (const p of ['wb-m1w2_170/External Sensor 1','wb-m1w2_173/External Sensor 1','wb-m1w2_173/External Sensor 2']) {
        const h=harness(managerPath); localSamples(h);
        h.emit(sensorTopic(p)+'/meta/error','r'); h.tick();
        assert.equal(h.values['hm2_504_gp_besedka/request_reason'],'LOCAL_SENSOR_INTERLOCK');
    }
});
test('overheat inputs and prolonged watchdog scenario remain non-writing; no claimed commissioned safety', () => {
    const h=harness(managerPath);
    for (const t of [40,60,90,120,NaN]) {
        localSamples(h,t); h.time(epoch+3600000); h.tick();
        assert.equal(h.values['hm2_504_gp_besedka/valid'],false);
        assert.equal(h.values['hm2_504_gp_besedka/response_status'],'NOT_COMMISSIONED');
        assert.equal(h.values['hm2_504_gp_besedka/physical_write_grant'],false);
    }
});
test('persistent dangerous latch survives reload and reset is refused without proven limits', () => {
    const stores={ivolga_504_safety:{fault:'SUPPLY_HARD_MAX'}};
    const h=harness(managerPath,{stores}); localSamples(h); h.tick();
    assert.equal(h.values['hm2_504_gp_besedka/fault_latched'],true);
    h.rules.hm2_504_reset.then(); assert.equal(stores.ivolga_504_safety.fault,'SUPPLY_HARD_MAX');
    const h2=harness(managerPath,{stores}); assert.equal(h2.values['hm2_504_gp_besedka/fault_latched'],true);
});
test('unconfirmed mixing tuning cannot instantiate a controller', () => {
    assert.equal(H.shadowMixer(Mixing,null),null);
    assert.throws(()=>H.shadowMixer(Mixing,{hardMaxC:null}),/Unconfirmed/);
    assert.throws(()=>H.shadowMixer(Mixing,{}),/invalid/);
});
test('shadow adapter executes real MixingController using test-only tuning without outputs', () => {
    // Fixture from existing consumer is used ONLY for the adapter API, never as 504 settings.
    const consumer=fs.readFileSync(path.join(root,'Wirenboard/wb-rules/502_gp_dom_manager.js'),'utf8');
    const start=consumer.indexOf('var CFG = {'),end=consumer.indexOf('var CELL_TYPE =');
    const c=vm.createContext({});vm.runInContext(consumer.slice(start,end),c);
    const mix=H.shadowMixer(Mixing,c.CFG.tuning);
    const result=mix.step({now:1000,enabled:true,pumpOn:true,supplyTempC:20,sourceTempC:45,
        targetC:30,sensorOffsetC:0,valveEnableOn:true,phaseMode:'auto',freeze:false,manualValvePct:0});
    assert.ok(Number.isFinite(result.valvePositionPct));
    const input={now:1030,enabled:true,pumpOn:true,supplyTempC:50,sourceTempC:60,
        targetC:30,sensorOffsetC:0,valveEnableOn:true,phaseMode:'auto',freeze:false,manualValvePct:0};
    // The generic module filters supply; production manager must also guard raw temperature.
    mix.step(input); input.now=1060;
    const over=mix.step(input);
    assert.equal(over.status,'SUPPLY_HARD_MAX_SAFE_CLOSE');
    assert.equal(over.valvePositionPct,0);
});
function incumbents() {
    const values={};
    for (const id of ['hm2_501_tp_dom','hm2_502_gp_dom','hm2_503_rad_dom']) {
        for (const [k,v] of Object.entries({state:'ACTIVE',valid:true,heat_demand:true,path_ready:true,
            fault_latched:false,requested_source_temperature:45,request_timestamp:new Date(epoch).toISOString(),request_ttl_s:90})) values[id+'/'+k]=v;
    }
    return values;
}
function request504(extra={}) { return JSON.stringify(Object.assign({state:'ACTIVE',valid:true,heat_demand:true,path_ready:true,
    fault_latched:false,requested_source_temperature:50,request_timestamp:new Date(epoch).toISOString(),request_ttl_s:15},extra)); }
test('gate OFF preserves baseline arbiter decisions and all incumbent grants (250 scenarios)', () => {
    const original=cp.execFileSync('git',['show','c221f528b115341d79fc7d3a453463d53ec44cda:objects/05_31_Ivolga_13/Wirenboard/wb-rules/HM2_arbiter_request.js'],{cwd:repo,encoding:'utf8'});
    const keys=['state','valid','selected_consumer','selected_consumer_title','selected_requested_temperature',
        'selected_reason','no_demand_contract','active_candidate_count','rejected_candidate_count','last_update_ts'];
    for(const n of ['501','502','503']) keys.push('grant_'+n+'_state','grant_'+n+'_reason');
    for(let i=0;i<250;i++) {
        const values=incumbents();
        ['hm2_501_tp_dom','hm2_502_gp_dom','hm2_503_rad_dom'].forEach((id,j)=>{
            values[id+'/requested_source_temperature']=35+(i*(j+1))%20;
            values[id+'/fault_latched']=(i+j)%5===0;
            values[id+'/valid']=(i+j)%7!==0;
            values[id+'/heat_demand']=(i+j)%3!==0;
            values[id+'/request_timestamp']=new Date(epoch-((i+j)%11)*10000).toISOString();
        });
        values['hm2_504_gp_besedka/request_json']=i%2?request504():'malformed';
        const before=harness(arbiterPath,{values,code:original}),after=harness(arbiterPath,{values});
        before.tick();after.tick();
        for(const k of keys) assert.equal(after.values['hm2_request_arbiter/'+k],before.values['hm2_request_arbiter/'+k],k);
        assert.equal(after.values['hm2_request_arbiter/grant_504_reason'],'FEATURE_DISABLED');
    }
});
test('504 independent atomic validation: TTL boundary, faults, malformed, future and missing fields', () => {
    const code=fs.readFileSync(arbiterPath,'utf8').replace('var ENABLE_504_SELECTION = false;','var ENABLE_504_SELECTION = true;');
    for (const bad of [{fault_latched:true},{fault_latched:null},{valid:false},{path_ready:false},
        {request_ttl_s:16},{request_ttl_s:0},{request_ttl_s:'15'},{requested_source_temperature:'50'},
        {request_timestamp:new Date(epoch-15000).toISOString()},{request_timestamp:new Date(epoch+1).toISOString()}]) {
        const values=incumbents(); values['hm2_504_gp_besedka/request_json']=request504(bad);
        const h=harness(arbiterPath,{values,code});h.tick();
        assert.equal(h.values['hm2_request_arbiter/selected_consumer'],'hm2_503_rad_dom');
        assert.equal(h.values['hm2_request_arbiter/grant_504_state'],'REJECTED');
    }
});
test('gated synthetic selection MAX, equal tie stays 503 > 502 > 501 > 504', () => {
    const code=fs.readFileSync(arbiterPath,'utf8').replace('var ENABLE_504_SELECTION = false;','var ENABLE_504_SELECTION = true;');
    for(const [temperature,winner] of [[50,'hm2_504_gp_besedka'],[45,'hm2_503_rad_dom']]) {
        const values=incumbents();values['hm2_504_gp_besedka/request_json']=request504({requested_source_temperature:temperature});
        const h=harness(arbiterPath,{values,code});h.tick();assert.equal(h.values['hm2_request_arbiter/selected_consumer'],winner);
    }
});
test('bridge exact outbound namespace only; ACL no physical commands', () => {
    const config=fs.readFileSync(path.join(root,'Besedka/mosquitto/504-bridge.conf.example'),'utf8');
    const lines=config.split(/\r?\n/).filter(l=>l && !l.startsWith('#'));
    assert.deepEqual(lines.filter(l=>l.startsWith('topic ')),['topic '+H.TOPIC+' out 0']);
    assert.ok(!lines.some(l=>/[+#]/.test(l)||l.includes('/devices/')));
    assert.ok(lines.includes('cleansession true')); assert.ok(lines.includes('notifications false'));
    assert.ok(!lines.includes('bridge_outgoing_retain false'));
});
console.log('RESULT: '+count+' groups passed; 250 baseline comparisons. LIVE_NOT_VERIFIED.');
