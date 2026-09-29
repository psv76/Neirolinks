// Offline regression: no MQTT, controller or physical outputs.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '..');
let checks = 0;
function check(name, fn) { fn(); checks++; console.log('PASS ' + name); }
function manager(file, retained) {
    let clock = 1000;
    const logs = [], rules = {};
    const dev = Object.assign({}, retained);
    const ctx = {
        dev, require: () => require(path.resolve(root, '../../Templates/WB-rules/Heating/HM2/MixingController/MixingController.js')),
        log: { info: x => logs.push(x), warning: x => logs.push(x), error: x => logs.push(x) },
        defineVirtualDevice: (id, spec) => Object.keys(spec.cells).forEach(k => {
            if (!(id + '/' + k in dev)) dev[id + '/' + k] = spec.cells[k].value;
        }),
        defineRule: (id, spec) => { rules[id] = spec; },
        setTimeout: () => 1, setInterval: () => 1, clearInterval: () => {}
    };
    vm.createContext(ctx);
    vm.runInContext(fs.readFileSync(path.join(root, 'Wirenboard/wb-rules', file), 'utf8'), ctx);
    ctx.nowSec = () => clock;
    ctx.tick = (t, supply = 18, source = 45, pos = 100, pump = true, valve = true) => {
        clock = t;
        return ctx.responseWatchdog(t, true, pump, valve, pos, supply, source, 30);
    };
    ctx.run = (start, end, fn) => { let s; for (let t = start; t <= end; t += 30) s = fn(t); return s; };
    ctx.logs = logs;
    return ctx;
}
for (const file of ['501_tp_dom_manager.js', '502_gp_dom_manager.js']) {
    const label = file.slice(0, 3);
    check(label + ' retained grants reset; no automatic start', () => {
        const id = label === '501' ? 'hm2_501_tp_dom' : 'hm2_502_gp_dom';
        const retained = {};
        for (const k of ['enabled', 'outputs_enabled', 'local_permit', 'manual_commissioning_grant', 'response_commissioned']) retained[id+'/'+k] = true;
        const c = manager(file, retained);
        for (const k of Object.keys(retained)) assert.strictEqual(c.dev[k], false);
        assert.strictEqual(c.dev[c.CH.pump], false);
        assert.strictEqual(c.dev[c.CH.valvePosition], 0);
    });
    check(label + ' falling supply is hydraulic only; high valve eventually closes', () => {
        const c = manager(file);
        c.tick(1000, 20);
        assert.strictEqual(c.tick(1030, 18), 'HYDRAULIC_RESPONSE');
        const s = c.run(1060, 1840, t => c.tick(t));
        assert.strictEqual(s, 'FAULT_LATCHED');
        assert.strictEqual(c.dev[c.VD+'/fault_text'], 'NO_WARMUP_PROGRESS');
        assert.strictEqual(c.WD.progressCount, 0);
        assert.strictEqual(c.dev[c.CH.pump], false);
        assert.strictEqual(c.dev[c.CH.valvePosition], 0);
        const baseline = c.WD.baseline;
        c.responseWatchdog(1900, false, false, false, 0, 18, 45, 30);
        assert.strictEqual(c.WD.baseline, baseline);
    });
    check(label + ' cold rebound needs spaced samples; checkpoint cannot follow oscillations', () => {
        const c = manager(file);
        c.tick(1000, 20); c.tick(1030, 18);
        c.tick(1060, 19.2);
        for (let t=1061; t<1080; t++) c.tick(t,19.2);
        assert.strictEqual(c.WD.progressCount, 0);
        c.tick(1090, 19.2);
        assert.strictEqual(c.tick(1120, 19.2), 'WARMUP_PROGRESS');
        assert.strictEqual(c.WD.progressCount, 1);
        c.run(1150, 1990, t => c.tick(t, t % 60 ? 18 : 19.2,45,50));
        assert.strictEqual(c.WD.progressCount, 1);
        assert.strictEqual(c.dev[c.VD+'/fault_latched'], true);
    });
    check(label + ' direct rise and target confirmation; renewed cooling gets new deadline', () => {
        const c=manager(file);
        c.tick(1000,18);
        c.tick(1030,19.2); c.tick(1060,19.2);
        assert.strictEqual(c.tick(1090,19.2),'RESPONSE_OK');
        c.tick(1120,29); c.tick(1150,29);
        assert.strictEqual(c.tick(1180,29),'AT_TARGET');
        assert.strictEqual(c.tick(10000,29),'AT_TARGET');
        c.tick(10030,18);
        assert.strictEqual(c.WD.since,10030);
    });
    check(label + ' target remains valid with mixing valve closed or below 5 percent', () => {
        const c=manager(file);
        c.tick(1000,29,45,0); c.tick(1030,29,45,0);
        assert.strictEqual(c.tick(1060,29,45,0),'AT_TARGET');
        assert.strictEqual(c.tick(5000,29,45,2),'AT_TARGET');
        assert.strictEqual(c.dev[c.VD+'/fault_latched'],false);
        c.tick(5030,18,45,0);
        assert.strictEqual(c.WD.since,5030);
        assert.strictEqual(c.tick(8660,18,45,0),'FAULT_LATCHED');
    });
    check(label + ' source flapping cannot reset absolute warmup deadline', () => {
        const c=manager(file);
        c.run(1000,4600,t=>c.tick(t,18,t%60 ? 20:45,50));
        assert.strictEqual(c.dev[c.VD+'/fault_text'],'WARMUP_TIMEOUT');
    });
    check(label + ' output wait is bounded; no invented progress', () => {
        const c=manager(file);
        assert.strictEqual(c.tick(1000,18,45,0),'WAIT_OUTPUT_READBACK');
        c.run(1030,4600,t=>c.tick(t,18,45,0));
        assert.strictEqual(c.dev[c.VD+'/fault_text'],'WARMUP_TIMEOUT');
        assert.strictEqual(c.WD.progressCount,0);
    });
    check(label + ' slow progress cannot keep cold slab active beyond total deadline', () => {
        const c=manager(file);
        c.run(1000,4600,t=>c.tick(t, 10+Math.floor((t-1000)/300)*1.1,45,50));
        assert(c.WD.progressCount>3);
        assert.strictEqual(c.dev[c.VD+'/fault_text'],'WARMUP_TIMEOUT');
    });
    check(label + ' evaluate invalidates fault request and all three physical outputs', () => {
        const c=manager(file);
        c.dev[c.CH.supply]=18; c.dev[c.CH.source]=45; c.dev[c.CH.ret]=17;
        for (const k of ['enabled','commissioned','outputs_enabled','local_permit','manual_commissioning_grant','response_commissioned']) c.dev[c.VD+'/'+k]=true;
        c.dev[c.VD+'/actuator_delay_s']=0;
        c.CH.zones.forEach(x=>{c.dev[x]=true;});
        c.dev[c.CH.pump]=true; c.dev[c.CH.valveEnable]=true; c.dev[c.CH.valvePosition]=100;
        c.tick(1000,20); c.run(1030,1840,t=>c.tick(t));
        c.evaluate('test');
        for (const k of ['valid','heat_demand','path_ready','pump_cmd']) assert.strictEqual(c.dev[c.VD+'/'+k],false);
        assert.strictEqual(c.dev[c.VD+'/requested_source_temperature'],0);
        assert.strictEqual(c.dev[c.VD+'/response_status'],'FAULT_LATCHED');
        assert.strictEqual(c.dev[c.CH.valveEnable],false);
        c.resetFault();
        assert.strictEqual(c.dev[c.VD+'/outputs_enabled'],false);
        assert.strictEqual(c.dev[c.VD+'/manual_commissioning_grant'],false);
    });
    check(label + ' unchanged readback timeout remains active', () => {
        const c=manager(file);
        c.dev[c.CH.supply]=18; c.dev[c.CH.source]=45;
        for (const k of ['enabled','commissioned','outputs_enabled','local_permit','manual_commissioning_grant','response_commissioned']) c.dev[c.VD+'/'+k]=true;
        c.dev[c.VD+'/actuator_delay_s']=0;
        c.CH.zones.forEach(x=>{c.dev[x]=true;});
        for(let t=1000;t<=1150;t+=30){
            c.nowSec=()=>t;
            c.dev[c.CH.pump]=false; c.dev[c.CH.valveEnable]=false; c.dev[c.CH.valvePosition]=0;
            c.evaluate('test');
        }
        assert.strictEqual(c.dev[c.VD+'/fault_text'],'OUTPUT_READBACK_TIMEOUT');
        assert.strictEqual(c.dev[c.VD+'/response_status'],'FAULT_LATCHED');
    });
}
check('620 periodic sync quiet; changes and errors remain logged', () => {
    const logs=[], rules={}, dev={};
    const log=x=>logs.push(x); log.info=log;log.warning=log;log.error=log;
    const c={dev,log,defineVirtualDevice:(id,spec)=>Object.keys(spec.cells).forEach(k=>{dev[id+'/'+k]=spec.cells[k].value;}),
        defineRule:(id,spec)=>{rules[id]=spec;},cron:x=>x,setTimeout:()=>{}};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(path.join(root,'Wirenboard/wb-rules/620_thermostats.js'),'utf8'),c);
    c.evaluateAll(false); logs.length=0;
    rules.thermostats_620_periodic_sync.then();
    assert.strictEqual(logs.length,0);
    const z=c.ZONES[0]; dev[z.deviceId+'/target_state']=true;dev[z.sensor]=10;
    rules.thermostats_620_periodic_sync.then();
    assert(logs.length>0); logs.length=0;
    dev[z.sensor]='invalid'; rules.thermostats_620_periodic_sync.then();
    assert(logs.some(x=>x.includes('АВАРИЯ')));
});
check('runner requires sustained thermal evidence and rejects subsequent loss', () => {
    const source=fs.readFileSync(path.join(__dirname,'hm2_integrated_commissioning_runner.sh'),'utf8');
    const helpers=source.slice(source.indexOf('is_num() {'),source.indexOf('check_eq() {'));
    const update=source.slice(source.indexOf('update_warmup_progress() {'),source.indexOf('run_contour_test() {'));
    const script=helpers+update+`
set -eu
VD=hm2_501_tp_dom; ARB_NOW=$VD; PUMP_NOW=1; VALVE_SW_NOW=1; VALVE_POS_NOW=100
SOURCE_NOW=45; TARGET_NOW=30; PROGRESS_NOW=0; WARMUP_SAMPLES=0; WARMUP_PROGRESS_SEEN=0; WARMUP_MIN=20
SUPPLY_NOW=18; RESP_NOW=HYDRAULIC_RESPONSE
update_warmup_progress; update_warmup_progress; update_warmup_progress
[ "$WARMUP_SAMPLES" = 0 ]
RESP_NOW=SOURCE_HOT
update_warmup_progress
[ "$WARMUP_SAMPLES" = 0 ]
SUPPLY_NOW=19.2; RESP_NOW=WARMUP_PROGRESS; PROGRESS_NOW=1
update_warmup_progress; update_warmup_progress; update_warmup_progress
[ "$WARMUP_SAMPLES" = 3 ]
RESP_NOW=NO_WARMUP_PROGRESS
update_warmup_progress
[ "$WARMUP_SAMPLES" = 0 ]
RESP_NOW=AT_TARGET; SUPPLY_NOW=18
update_warmup_progress
[ "$WARMUP_SAMPLES" = 0 ]
SUPPLY_NOW=29; VALVE_POS_NOW=0
update_warmup_progress; update_warmup_progress; update_warmup_progress
[ "$WARMUP_SAMPLES" = 3 ]
PUMP_NOW=0
update_warmup_progress
[ "$WARMUP_SAMPLES" = 0 ]
`;
    const sh=process.platform==='win32' ? 'C:/Program Files/Git/bin/sh.exe' : 'sh';
    const result=require('child_process').spawnSync(sh,['-s'],{input:script,encoding:'utf8'});
    assert.strictEqual(result.status,0,result.stderr);
});
console.log('Checks: '+checks);
