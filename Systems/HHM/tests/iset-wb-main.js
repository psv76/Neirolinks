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
function boot(initialStorage,physical,blockedHardwareReadbacks){
    var devices={},controls={},outputs=[],events={},timers=[],mqttTracks={},
        logs=[],now=100000,storage=initialStorage||{};
    var blocked=blockedHardwareReadbacks||[];
    var dev=new Proxy(controls,{set:function(t,k,value){
        outputs.push({path:k,value:value});
        if(blocked.indexOf(k)<0)t[k]=value;
        return true;
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
        trackMqtt:function(topic,handler){
            assert.ok(!mqttTracks[topic],'Duplicate trackMqtt: '+topic);
            mqttTracks[topic]=handler;
        },
        setInterval:function(fn,period){timers.push({fn:fn,period:period});},
        log:{info:function(s){logs.push(['info',s]);},
            warning:function(s){logs.push(['warning',s]);},
            error:function(s){logs.push(['error',s]);}}
    };
    // Test both modes using the EXACT same WB script structure,
    // regardless of the Git release candidate's default mode.
    var program=source.replace(/var HHM_PHYSICAL_OUTPUTS=(true|false);/,
        'var HHM_PHYSICAL_OUTPUTS='+(physical===true?'true':'false')+';');
    vm.runInNewContext(program,ctx,{filename:'29_hhm_iset.js'});
    function external(p,v){controls[p]=v;}
    function click(p){assert.ok(events[p],p);events[p]();}
    function step(ms){now+=ms;timers.forEach(function(x){x.fn();});}
    return {devices:devices,controls:controls,outputs:outputs,
        storage:storage,logs:logs,timers:timers,
        external:external,click:click,step:step,
        emit:function(topic,value){
            assert.ok(mqttTracks[topic],'Unknown MQTT watch '+topic);
            mqttTracks[topic]({topic:topic,value:value});
        },
        physicalWrite:function(cmd){return ctx.hhWrite(cmd,now);}};
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
check('approved 25C HEAT is saved in all eight rooms, 32C floor enabled',function(){
    var w=boot();
    modules.IsetRoomZones.zones.forEach(function(z){
        var key='iset_hhm_room_v1_'+z.id;
        assert.strictEqual(JSON.parse(w.storage[key]).setpointC,25);
        assert.strictEqual(JSON.parse(w.storage[key]).mode,'HEAT');
    });
    assert.strictEqual(w.controls['iset_hhm_office/saved'],'HEAT / 25°C');
    assert.strictEqual(w.controls['iset_hhm_floor/target'],32);
    assert.strictEqual(w.controls['iset_hhm_floor/enable'],true);
    assert.strictEqual(Object.keys(w.storage).length,9);
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
    assert.strictEqual(JSON.parse(w.storage.iset_hhm_room_v1_office).setpointC,25);
    assert.ok(w.logs.some(function(a){
        return a[0]==='warning'&&a[1].indexOf('Уставка не сохранена')>=0;
    }));
});
check('floor starts with approved 32C and supports stored override',function(){
    var a=boot();
    assert.strictEqual(JSON.parse(a.storage.iset_hhm_floor_cfg_v1).targetC,32);
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
check('mock physical mode writes exact output paths only after local requests',function(){
    var w=boot({},true);
    var before=w.outputs.length;
    w.external('wbe2-i-opentherm_11/Invalid Connection',false);
    w.external('wbe2-i-opentherm_11/Boiler Fault Indication',false);
    w.external('wbe2-i-opentherm_11/Error Code',0);
    w.external('wbe2-i-opentherm_11/Heating Temperature',55);
    w.external('wbe2-i-opentherm_11/Water Pressure',1.5);
    w.external('wb-mio-gpio_195:1/IN1',true);
    w.external('wb-m1w2_65/External Sensor 2',-10);
    ['45','61','202','209'].forEach(function(i){
        w.external('wb-msw-v4_'+i+'/Temperature',19);
    });
    w.external('iset_hhm_office/setpoint_input',22);
    w.click('iset_hhm_office/apply');
    w.external('wb-msw-v4_22/Temperature',19);
    w.step(1000);
    var writes=w.outputs.slice(before).filter(function(x){
        return !/^iset_hhm/.test(x.path);
    });
    assert.ok(writes.some(function(x){
        return x.path==='wb-mr6cu_37/K3'&&x.value===true;
    }));
    assert.ok(writes.some(function(x){
        return x.path==='wb-mio-gpio_195:2/K1'&&x.value===false;
    }));
    assert.ok(writes.every(function(x){return /^wb-|^wbe2-/.test(x.path);}));
});
check('K4 physical pump starts only after 120s observed NO relay OPEN',function(){
    var w=boot({},true);
    w.external('wbe2-i-opentherm_11/Invalid Connection',false);
    w.external('wbe2-i-opentherm_11/Boiler Fault Indication',false);
    w.external('wbe2-i-opentherm_11/Error Code',0);
    w.external('wbe2-i-opentherm_11/Heating Temperature',55);
    w.external('wbe2-i-opentherm_11/Water Pressure',1.5);
    w.external('wb-mio-gpio_195:1/IN1',true);
    w.external('wb-m1w2_65/External Sensor 2',-10);
    w.external('wb-msw-v4_22/Temperature',19);
    w.external('iset_hhm_office/setpoint_input',22);
    w.click('iset_hhm_office/apply');
    w.external('wb-mio-gpio_195:2/K1',false);
    w.external('wb-mr6cu_37/K4',false);
    var before=w.outputs.length;
    w.step(1000);w.step(119000);w.step(1000);
    var writes=w.outputs.slice(before).filter(function(x){
        return x.path==='wb-mr6cu_37/K4'&&x.value===true;
    });
    assert.strictEqual(writes.length,1);
    assert.strictEqual(w.controls['iset_hhm_k4/relay'],'OFF');
});
check('physical mode only sends a repeated unconfirmed command after 5 seconds',function(){
    var w=boot({},true),path='wb-mr6cu_37/K1';
    var first=w.outputs.filter(function(x){return x.path===path;}).length;
    w.step(1000);w.step(1000);
    var shortly=w.outputs.filter(function(x){return x.path===path;}).length;
    assert.strictEqual(shortly,first);
    w.step(4000);
    var later=w.outputs.filter(function(x){return x.path===path;}).length;
    assert.ok(later>=first);
});
check('basement target persists to WB storage and survives restart',function(){
    var w=boot();
    w.external('iset_hhm_basement/target_input',25);
    w.click('iset_hhm_basement/save');
    assert.strictEqual(w.storage.iset_hhm_basement_target_v1,'25');
    assert.strictEqual(w.controls['iset_hhm_basement/target_saved'],'25 °C');
    var later=boot(w.storage);
    assert.strictEqual(later.controls['iset_hhm_basement/target_saved'],'25 °C');
    assert.strictEqual(later.controls['iset_hhm_basement/target_input'],25);
});
check('out of range basement request cannot alter approved target',function(){
    var w=boot();
    w.external('iset_hhm_basement/target_input',35);
    w.click('iset_hhm_basement/save');
    assert.strictEqual(w.storage.iset_hhm_basement_target_v1,undefined);
});
check('DHW operator panel includes K1 priority and overrun remaining timers',function(){
    var w=boot(),d=w.devices.iset_hhm_dhw.cells;
    assert.ok(d.priority_timer.readonly);
    assert.ok(d.overrun_timer.readonly);
    assert.ok(d.boost);
    assert.ok(d.reset_fault);
});
check('manual DHW acceleration works on WB without HA',function(){
    var w=boot();
    w.external('wb-m1w2_67/External Sensor 2',51);
    w.external('wb-m1w2_65/External Sensor 2',-10);
    w.click('iset_hhm_dhw/boost');
    w.step(60000);
    assert.strictEqual(w.controls['iset_hhm_dhw/mode'],'ACCELERATED');
    assert.ok(w.controls['iset_hhm_dhw/priority_timer'].indexOf('с')>=0);
});
check('DHW fault reset requires K1 observed OFF and valid tank',function(){
    var w=boot();
    w.external('wb-m1w2_67/External Sensor 2',52);
    w.external('wb-mr6cu_37/K1',true);
    w.click('iset_hhm_dhw/reset_fault');
    assert.ok(w.logs.some(function(x){
        return x[0]==='warning'&&x[1].indexOf('Сброс не разрешён')>=0;
    }));
});
check('physical WB floor closes MAO4 hot port at 40C without K2 stop',function(){
    var stored={iset_hhm_floor_cfg_v1:
        JSON.stringify({version:1,enabled:true,targetC:34})};
    var w=boot(stored,true);
    w.external('wb-mio-gpio_195:1/IN1',true);
    w.external('wbe2-i-opentherm_11/Invalid Connection',false);
    w.external('wbe2-i-opentherm_11/Boiler Fault Indication',false);
    w.external('wbe2-i-opentherm_11/Error Code',0);
    w.external('wbe2-i-opentherm_11/Heating Temperature',58);
    w.external('wbe2-i-opentherm_11/Water Pressure',1.5);
    w.external('wb-m1w2_67/External Sensor 1',40);
    w.external('wb-mao4_131/Channel 1 Dimming Level',20);
    w.external('wb-mr6cu_37/K2',true);
    var old=w.outputs.length;
    w.step(1000);
    var actions=w.outputs.slice(old);
    assert.ok(actions.some(function(c){
        return c.path==='wb-mao4_131/Channel 1 Dimming Level'&&
            c.value===0;
    }));
    assert.strictEqual(actions.some(function(c){
        return c.path==='wb-mr6cu_37/K2'&&c.value===false;
    }),false);
});
check('physical WB floor at 45C commands K2 OFF independently',function(){
    var stored={iset_hhm_floor_cfg_v1:
        JSON.stringify({version:1,enabled:true,targetC:34})};
    var w=boot(stored,true);
    w.external('wb-mio-gpio_195:1/IN1',true);
    w.external('wbe2-i-opentherm_11/Invalid Connection',false);
    w.external('wbe2-i-opentherm_11/Boiler Fault Indication',false);
    w.external('wbe2-i-opentherm_11/Error Code',0);
    w.external('wbe2-i-opentherm_11/Heating Temperature',58);
    w.external('wbe2-i-opentherm_11/Water Pressure',1.5);
    w.external('wb-m1w2_67/External Sensor 1',45);
    w.external('wb-mr6cu_37/K2',true);
    w.external('wb-mao4_131/Channel 1 Dimming Level',20);
    var old=w.outputs.length;
    w.step(1000);
    var actions=w.outputs.slice(old);
    assert.ok(actions.some(function(c){
        return c.path==='wb-mr6cu_37/K2'&&c.value===false;
    }));
    assert.ok(actions.some(function(c){
        return c.path==='wb-mao4_131/Channel 1 Dimming Level'&&c.value===0;
    }));
});
check('full WB K2 preflight drives Switch ON then waits 10s and NO 120s',function(){
    var stored={iset_hhm_floor_cfg_v1:JSON.stringify({
        version:1,enabled:true,targetC:34
    })};
    var w=boot(stored,true);
    w.external('wb-mio-gpio_195:1/IN1',true);
    w.external('wbe2-i-opentherm_11/Invalid Connection',false);
    w.external('wbe2-i-opentherm_11/Boiler Fault Indication',false);
    w.external('wbe2-i-opentherm_11/Error Code',0);
    w.external('wbe2-i-opentherm_11/Heating Temperature',55);
    w.external('wbe2-i-opentherm_11/Water Pressure',1.5);
    w.external('wb-m1w2_67/External Sensor 1',30);
    modules.IsetServiceConfig.outputs.floorLoops.forEach(function(p){
        w.external(p,false);
    });
    w.external('wb-mao4_131/Channel 1 Switch',false);
    w.external('wb-mao4_131/Channel 1 Dimming Level',1);
    w.external('wb-mr6cu_37/K2',false);
    var before=w.outputs.length;
    w.step(1000);
    assert.ok(w.outputs.slice(before).some(function(a){
        return a.path==='wb-mao4_131/Channel 1 Switch'&&a.value===true;
    }));
    assert.strictEqual(w.outputs.some(function(a){
        return a.path==='wb-mr6cu_37/K2'&&a.value===true;
    }),false);
    w.external('wb-mao4_131/Channel 1 Switch',true);
    w.step(1000);
    assert.strictEqual(w.controls['iset_hhm_floor/preflight_timer'],'10 с');
    w.step(119000);
    assert.ok(w.outputs.some(function(a){
        return a.path==='wb-mr6cu_37/K2'&&a.value===true;
    }));
    assert.ok(w.devices.iset_hhm_k2.cells.start_timer);
});
check('valid operator preferences persist and are never reset to 25/32',function(){
    var a=boot();
    a.external('iset_hhm_office/setpoint_input',22);
    a.click('iset_hhm_office/apply');
    a.external('iset_hhm_floor/target',35);
    a.click('iset_hhm_floor/save');
    var b=boot(a.storage);
    assert.strictEqual(b.controls['iset_hhm_office/setpoint_input'],22);
    assert.strictEqual(b.controls['iset_hhm_floor/target'],35);
    assert.strictEqual(JSON.parse(b.storage.iset_hhm_room_v1_office).setpointC,22);
});
check('operator setpoint values are writable in real WB virtual-device schema',function(){
    var w=boot();
    assert.strictEqual(w.devices.iset_hhm_office.cells.setpoint_input.readonly,false);
    assert.strictEqual(w.devices.iset_hhm_floor.cells.target.readonly,false);
    assert.strictEqual(w.devices.iset_hhm_basement.cells.target_input.readonly,false);
});
check('physical MQTT write without readback raises warning after 30s, then recovers',function(){
    var output='wb-mio-gpio_195:2/K12';
    var w=boot({},true,[output]);
    // The NO floor loop is locally enabled and must be commanded
    // open, but the simulated Modbus driver ignores the write.
    w.step(31000);
    assert.strictEqual(w.controls['iset_hhm/io_state'],'NO_READBACK');
    assert.strictEqual(w.controls['iset_hhm/io_unconfirmed'],1);
    assert.ok(w.controls['iset_hhm/io_details'].indexOf(output)>=0);
    var n=w.logs.filter(function(x){
        return x[0]==='warning'&&
            x[1].indexOf('Нет подтверждения MQTT')>=0;
    }).length;
    assert.strictEqual(n,1);
    w.step(60000);
    assert.strictEqual(w.logs.filter(function(x){
        return x[0]==='warning'&&
            x[1].indexOf('Нет подтверждения MQTT')>=0;
    }).length,1,'no warning on every retry');
    w.external(output,false);
    w.step(1000);
    assert.strictEqual(w.controls['iset_hhm/io_unconfirmed'],0);
    assert.strictEqual(w.controls['iset_hhm/io_state'],'READBACK_OK');
    assert.ok(w.logs.some(function(x){
        return x[0]==='info'&&x[1].indexOf('ВОССТАНОВЛЕНИЕ')>=0;
    }));
});
check('preview runtime never reports physical readback confirmation',function(){
    var w=boot();
    assert.strictEqual(w.controls['iset_hhm/io_state'],'PREVIEW');
    assert.strictEqual(w.controls['iset_hhm/io_unconfirmed'],0);
});
check('floor own state remains equal to shared HHM state after tick',function(){
    var w=boot();
    w.external('wb-m1w2_67/External Sensor 1',30);
    w.step(1000);
    assert.strictEqual(w.controls['iset_hhm_floor/state'],
        w.controls['iset_hhm/floor_state']);
    assert.notStrictEqual(w.controls['iset_hhm_floor/state'],'OFF');
});
check('physical MAO4 writer suppresses already-confirmed same position',function(){
    var w=boot({},true),p='wb-mao4_131/Channel 1 Dimming Level';
    w.external(p,'25');
    var before=w.outputs.filter(function(x){return x.path===p;}).length;
    assert.strictEqual(w.physicalWrite({path:p,value:25,
        action:'MIX_VALVE_POS',reason:'FLOOR_MIXING'}),true);
    assert.strictEqual(w.outputs.filter(function(x){return x.path===p;}).length,
        before,'no-op must not send /on again');
    assert.strictEqual(w.logs.filter(function(x){
        return x[1].indexOf('КОМАНДА=MIX_VALVE_POS')>=0;
    }).length,0,'no per-tick operator log');
});
check('physical MAO4 writer still sends changed and safe close values',function(){
    var w=boot({},true),p='wb-mao4_131/Channel 1 Dimming Level';
    w.external(p,25);
    var before=w.outputs.filter(function(x){return x.path===p;}).length;
    assert.strictEqual(w.physicalWrite({path:p,value:0,
        action:'MIX_VALVE_POS',reason:'HOT_PORT_PREVENTIVE_CLOSE'}),true);
    assert.strictEqual(w.outputs.filter(function(x){return x.path===p;}).length,
        before+1,'emergency close must not be suppressed');
    assert.strictEqual(w.controls[p],0);
});
check('physical MAO4 missing readback preserves retry and watchdog',function(){
    var p='wb-mao4_131/Channel 1 Dimming Level';
    var w=boot({},true,[p]);
    w.external(p,20);
    var cmd={path:p,value:25,action:'MIX_VALVE_POS',reason:'FLOOR_MIXING'};
    var initial=w.outputs.filter(function(x){return x.path===p;}).length;
    w.physicalWrite(cmd);
    w.physicalWrite(cmd);
    assert.strictEqual(w.outputs.filter(function(x){return x.path===p;}).length,
        initial+1,'identical unacknowledged write throttled');
    w.step(6000);
    w.physicalWrite(cmd);
    assert.ok(w.outputs.filter(function(x){return x.path===p;}).length>=
        initial+2,'retry still allowed after 5s');
    w.step(31000);
    assert.ok(w.logs.some(function(x){
        return x[1].indexOf('Нет подтверждения MQTT')>=0 &&
            x[1].indexOf(p)>=0;
    }), '30s watchdog still warns on missing readback');
});
check('six M1W2 channels are diagnosed without changing heating outputs',function(){
    var w=boot(),spec=[
        ['wb-m1w2_65',1],['wb-m1w2_65',2],
        ['wb-m1w2_66',1],['wb-m1w2_66',2],
        ['wb-m1w2_67',1],['wb-m1w2_67',2]];
    spec.forEach(function(pair){
        var d=pair[0],n=pair[1],p=d+'/External Sensor '+n;
        w.external(p,30);w.external(p+' OK',1);
        w.external(d+'/ext_sens'+n+'_presense',1);
    });
    var before=w.outputs.filter(function(x){return !/^iset_hhm/.test(x.path);}).length;
    w.step(15000);
    assert.strictEqual(w.controls['iset_hhm/sensor_issues'],0);
    assert.strictEqual(w.controls['iset_hhm/sensor_unverified'],6);
    assert.strictEqual(w.outputs.filter(function(x){
        return !/^iset_hhm/.test(x.path);
    }).length,before,'diagnostics must not actuate outputs in preview');
    assert.ok(w.devices.iset_hhm.cells.sensor_details.readonly);
});
check('M1W2 loss and recovery create bounded operator events',function(){
    var w=boot(),devname='wb-m1w2_67',p=devname+'/External Sensor 1';
    w.external(p,30);w.external(p+' OK',1);
    w.external(devname+'/ext_sens1_presense',1);
    w.step(16000);
    w.external(devname+'/ext_sens1_presense',0);
    w.step(1000);
    assert.ok(w.controls['iset_hhm/sensor_details'].indexOf(
        'M1W2 сообщает отсутствие датчика')>=0);
    w.external(devname+'/ext_sens1_presense',1);
    w.step(1000);
    assert.ok(w.logs.some(function(x){
        return x[1].indexOf('Показания датчика восстановились')>=0;
    }));
    assert.ok(w.controls['iset_hhm/trace_recent'].indexOf(
        'SENSOR_RECOVERED')>=0);
});
check('M1W2 MQTT retained-only value does not prove fresh measurements',function(){
    var w=boot(),devname='wb-m1w2_67',p=devname+'/External Sensor 1';
    var topic='/devices/'+devname+'/controls/External Sensor 1';
    w.external(p,30);w.external(p+' OK',1);
    w.external(devname+'/ext_sens1_presense',1);
    w.emit(topic,30);w.step(16000);
    assert.ok(w.controls['iset_hhm/sensor_details'].indexOf(
        'Подача ТП: Свежесть MQTT не подтверждена')>=0);
    w.external(p,30.5);w.emit(topic,30.5);w.step(1000);
    assert.ok(w.controls['iset_hhm/sensor_details'].indexOf(
        'Подача ТП: Есть новые показания')>=0);
});
check('machine trace keeps only 24 recent events and no passwords',function(){
    var w=boot({},true),p='wb-mao4_131/Channel 1 Dimming Level';
    w.external(p,0);
    for(var n=1;n<=40;n++){
        assert.strictEqual(w.physicalWrite({
            path:p,value:n,action:'MIX_VALVE_POS',
            reason:'FLOOR_MIXING'}),true);
    }
    var trace=JSON.parse(w.controls['iset_hhm/trace_recent']);
    assert.strictEqual(trace.length,24);
    assert.ok(trace[0].sequence<trace[23].sequence);
    assert.strictEqual(trace[23].event,'WRITE');
    assert.strictEqual(w.controls['iset_hhm/trace_seq']>=40,true);
    assert.strictEqual(w.devices.iset_hhm.cells.trace_recent.readonly,true);
});
console.log('TOTAL PASS '+count);
