/* #204. Mock actual wb-rules API with the single full Iset HHM entrypoint.
 * Tests load source in a fresh VM; no network, no controller, no writes.
 */
var assert=require('assert'),vm=require('vm'),fs=require('fs'),
    path=require('path');
var root=path.resolve(__dirname,'../../..');
function obj(file){return require(path.join(root,'Objects/05_16_Iset/HHM',file));}
var modules={
    IsetRoomZones:obj('room_zones.js'),
    IsetServiceConfig:obj('isethhm_service_config.js'),
    IsetRoomSettingsStore:obj('room_settings_store.js'),
    IsetRoomSimpleThermostat:obj('simple_room_thermostat.js'),
    IsetRoomLocalRuntime:obj('room_local_runtime.js'),
    HHMRoomPathGate:require('../core/HHMRoomPathGate'),
    IsetRoomOutputPlanner:obj('room_output_planner.js'),
    IsetDhw:obj('isethhm_dhw.js'),
    IsetDemand:obj('isethhm_demand.js'),
    IsetSource:obj('isethhm_source.js'),
    IsetCoordinator:obj('isethhm_coordinator.js'),
    IsetFloorHydraulics:obj('isethhm_floor_hydraulics.js'),
    IsetFloorMixing:obj('isethhm_floor_mixing.js'),
    HHM3Mixing:require('../core/HHM3Mixing'),
    IsetUnifiedRuntime:obj('isethhm_runtime.js')
};
var source=fs.readFileSync(path.join(root,
    'Objects/05_16_Iset/Wirenboard/wb-rules/29_hhm_iset.js'),'utf8');
var count=0;
function check(s,fn){fn();count++;console.log('PASS '+s);}
function boot(initialStorage){
    var devices={},controls={},outputs=[],events={},timers=[],
        logs=[],now=100000,storage=initialStorage||{};
    var dev=new Proxy(controls,{set:function(t,k,value){
        outputs.push({path:k,value:value});t[k]=value;return true;
    }});
    var ctx={dev:dev,JSON:JSON,Math:Math,
        Date:{now:function(){return now;}},
        PersistentStorage:function(){return storage;},
        isFinite:isFinite,
        require:function(k){assert.ok(modules[k],k);return modules[k];},
        defineVirtualDevice:function(name,spec){
            assert.ok(!devices[name],name);
            devices[name]=spec;
            Object.keys(spec.cells).forEach(function(cell){
                controls[name+'/'+cell]=spec.cells[cell].value;
            });
        },
        defineRule:function(name,r){
            assert.ok(!events[r.whenChanged],name);
            events[r.whenChanged]=r.then;
        },
        trackMqtt:function(){},
        setInterval:function(fn,period){timers.push({fn:fn,period:period});},
        log:{info:function(s){logs.push(['info',s]);},
            warning:function(s){logs.push(['warning',s]);},
            error:function(s){logs.push(['error',s]);}}
    };
    vm.runInNewContext(source,ctx,{filename:'29_hhm_iset.js'});
    function external(p,v){controls[p]=v;}
    function click(p){assert.ok(events[p],p);events[p]();}
    function step(ms){now+=ms;timers.forEach(function(x){x.fn();});}
    return {devices:devices,controls:controls,outputs:outputs,
        storage:storage,logs:logs,timers:timers,
        external:external,click:click,step:step};
}
check('WB loads full HHM module dependency set and 1s clock',function(){
    var w=boot();
    assert.strictEqual(w.timers.length,1);
    assert.strictEqual(w.timers[0].period,1000);
    assert.strictEqual(w.controls['iset_hhm/status'],'РАСЧЁТ, КОМАНД НЕТ');
});
check('no physical I/O from entrypoint while preview setting false',function(){
    var w=boot();
    w.step(1000);
    w.outputs.forEach(function(a){
        assert.ok(/^iset_hhm/.test(a.path),a.path);
    });
});
check('eight WB room VDs plus four pump VDs and floor',function(){
    var w=boot(),map=modules.IsetRoomZones;
    map.zones.forEach(function(z){
        assert.ok(w.devices['iset_hhm_'+z.id]);
        z.outputs.forEach(function(p){
            var k='servo_'+p.split('/')[1].toLowerCase();
            assert.ok(w.devices['iset_hhm_'+z.id].cells[k]);
        });
    });
    ['k1','k2','k3','k4'].forEach(function(p){
        var x=w.devices['iset_hhm_'+p];
        assert.ok(x.cells.run_timer);
        assert.ok(x.cells.stop_timer);
    });
    assert.ok(w.devices.iset_hhm_floor.cells.k12_timer);
    assert.ok(w.devices.iset_hhm_floor.cells.k16_timer);
});
check('unconfigured rooms stay uncommissioned without default setpoint',function(){
    var w=boot();
    assert.strictEqual(w.controls['iset_hhm_office/saved'],
        'Уставка не задана');
    assert.strictEqual(Object.keys(w.storage).length,0);
});
check('explicit office setpoint Apply creates durable local record',function(){
    var w=boot();
    w.external('iset_hhm_office/setpoint_input',22);
    w.click('iset_hhm_office/apply');
    assert.strictEqual(JSON.parse(
        w.storage.iset_hhm_room_v1_office).setpointC,22);
    assert.strictEqual(w.controls['iset_hhm_office/demand'],'UNKNOWN');
    w.external('wb-msw-v4_22/Temperature',19);
    w.step(1000);
    assert.strictEqual(w.controls['iset_hhm_office/demand'],'HEAT');
    w.outputs.forEach(function(a){
        assert.ok(/^iset_hhm/.test(a.path),a.path);
    });
});
check('same setpoint survives a restarted WB rules VM',function(){
    var one=boot();
    one.external('iset_hhm_office/setpoint_input',22);
    one.click('iset_hhm_office/apply');
    var two=boot(one.storage);
    assert.strictEqual(two.controls['iset_hhm_office/saved'],'HEAT / 22°C');
});
check('out-of-range 40 C room setpoint rejected',function(){
    var w=boot();
    w.external('iset_hhm_office/setpoint_input',40);
    w.click('iset_hhm_office/apply');
    assert.strictEqual(w.storage.iset_hhm_room_v1_office,undefined);
    assert.ok(w.logs.some(function(a){
        return a[0]==='warning'&&a[1].indexOf('Уставка не сохранена')>=0;
    }));
});
check('floor is OFF until explicitly stored, remains OFF after restart',function(){
    var a=boot();
    assert.strictEqual(a.controls['iset_hhm_floor/state'],'OFF');
    a.external('iset_hhm_floor/enable',true);
    a.external('iset_hhm_floor/target',34);
    a.click('iset_hhm_floor/save');
    assert.strictEqual(JSON.parse(
        a.storage.iset_hhm_floor_cfg_v1).targetC,34);
    var b=boot(a.storage);
    assert.strictEqual(b.controls['iset_hhm_floor/enable'],true);
    assert.strictEqual(b.controls['iset_hhm_floor/target'],34);
});
check('physical outputs remain untouched after room and floor operation',function(){
    var w=boot();
    w.external('iset_hhm_office/setpoint_input',22);
    w.click('iset_hhm_office/apply');
    w.external('wb-msw-v4_22/Temperature',18);
    w.external('iset_hhm_floor/enable',true);
    w.click('iset_hhm_floor/save');
    w.step(120000);
    w.outputs.forEach(function(a){
        assert.ok(/^iset_hhm/.test(a.path),'Unexpected write: '+a.path);
    });
});
console.log('TOTAL PASS '+count);
