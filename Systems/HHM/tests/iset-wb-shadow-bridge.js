/* Offline WB rule VM smoke tests. NO WB, MQTT or physical I/O. */
var assert=require('assert'),fs=require('fs'),path=require('path'),vm=require('vm');
var root=path.resolve(__dirname,'../../..');
var Map=require(path.join(root,'Objects/05_16_Iset/HHM/room_zones.js'));
var aliases={
    IsetRoomSimpleThermostat:require(path.join(root,'Objects/05_16_Iset/HHM/simple_room_thermostat.js')),
    IsetRoomSettingsStore:require(path.join(root,'Objects/05_16_Iset/HHM/room_settings_store.js')),
    IsetRoomLocalRuntime:require(path.join(root,'Objects/05_16_Iset/HHM/room_local_runtime.js')),
    IsetRoomZones:Map,
    IsetRoomOutputPlanner:require(path.join(root,'Objects/05_16_Iset/HHM/room_output_planner.js')),
    HHMRoomPathGate:require(path.join(root,'Systems/HHM/core/HHMRoomPathGate.js'))
};
var source=fs.readFileSync(path.join(root,'Objects/05_16_Iset/Wirenboard/wb-rules/28_hhm_rooms_shadow.js'),'utf8');
var total=0;function check(label,fn){fn();total++;console.log('PASS '+label);}
function seed(store,id,t){
    var s=aliases.IsetRoomSettingsStore.create(store,id);
    store[s.key]=s.proposeInitial('HEAT',t||22);
}
function instantiate(settings,initial){
    var values={},rules=[],topics={},declared={},writes=[],logs=[],timers=[];
    var now=1000;
    var backing=settings||{};
    var storeConstructor=function(){return backing;};
    var proxy=new Proxy(values,{set:function(t,k,v){
        writes.push({path:k,value:v});t[k]=v;return true;}});
    var ctx={dev:proxy,Date:{now:function(){return now;}},Math:Math,JSON:JSON,
        setInterval:function(fn,ms){timers.push({fn:fn,ms:ms});return timers.length;},
        PersistentStorage:storeConstructor,
        require:function(k){assert.ok(aliases[k],k);return aliases[k];},
        log:{info:function(s){logs.push(s);}},
        defineVirtualDevice:function(name,descriptor){
            assert.strictEqual(declared[name],undefined,'duplicate '+name);
            declared[name]=descriptor;
            Object.keys(descriptor.cells).forEach(function(c){
                proxy[name+'/'+c]=descriptor.cells[c].value;
            });
        },
        defineRule:function(name,rule){rules.push({name:name,rule:rule});},
        trackMqtt:function(topic,cb){
            assert.strictEqual(topics[topic],undefined,'duplicate '+topic);
            topics[topic]=cb;
            if(initial&&Object.prototype.hasOwnProperty.call(initial,topic))
                cb({value:initial[topic]});
        }
    };
    vm.runInNewContext(source,ctx,{filename:'28_hhm_rooms_shadow.js'});
    function room(id,c){return values['iset_hhm_'+id+'_shadow/'+c];}
    function tick(id,v){
        var z=Map.zones.filter(function(x){return x.id===id;})[0];
        assert.ok(z);values[z.primarySensor]=v; // external driver update, not a rule write
        rules[0].rule.then();
    }
    function fault(id,val){
        var z=Map.zones.filter(function(x){return x.id===id;})[0];
        topics['/devices/'+z.primarySensor.split('/')[0]+'/meta/error']({value:val});
    }
    return {declared:declared,rules:rules,topics:topics,values:values,
        writes:writes,logs:logs,room:room,tick:tick,fault:fault,storage:backing,
        timers:timers,readback:function(channel,value){values[channel]=value;
            rules[0].rule.then();},
        advance:function(ms){now+=ms;timers.forEach(function(t){t.fn();});}};
}
check('eight named room virtual diagnostics and one global state',function(){
    var m=instantiate({});
    assert.strictEqual(Object.keys(m.declared).length,9);
    assert.strictEqual(Object.keys(m.topics).length,8);
    assert.strictEqual(m.rules.length,1);
    assert.strictEqual(m.timers.length,1);
    assert.strictEqual(m.timers[0].ms,1000);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/status'],'SHADOW_ONLY');
});
check('empty store produces not commissioned and no arbitrary setpoints',function(){
    var m=instantiate({});
    assert.strictEqual(m.room('office','state'),'NOT_COMMISSIONED');
    assert.strictEqual(m.room('office','settings'),'NOT_COMMISSIONED');
    assert.strictEqual(Object.keys(m.storage).length,0);
});
check('approved WB local setpoint leads to simple ON demand',function(){
    var settings={};seed(settings,'office',22);
    var m=instantiate(settings);
    m.tick('office',19);
    assert.strictEqual(m.room('office','state'),'NORMAL');
    assert.strictEqual(m.room('office','demand'),'ON');
});
check('unchanged temperature yields normal demand, no invented stale timer',function(){
    var settings={};seed(settings,'office',22);
    var m=instantiate(settings);m.tick('office',19);
    m.tick('office',19);
    assert.strictEqual(m.room('office','demand'),'ON');
});
check('one explicit driver error disables only one zone',function(){
    var settings={};seed(settings,'office');seed(settings,'corridor');
    var m=instantiate(settings);
    m.tick('office',19);m.tick('corridor',19);
    m.fault('office','1');
    assert.strictEqual(m.room('office','demand'),'OFF');
    assert.strictEqual(m.room('corridor','demand'),'ON');
});
check('driver error clearing resumes this room demand',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    m.fault('office','true');
    assert.strictEqual(m.room('office','demand'),'OFF');
    m.fault('office','0');
    assert.strictEqual(m.room('office','demand'),'ON');
});
check('missing error event never gates otherwise valid room demand',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    assert.strictEqual(m.room('office','demand'),'ON');
});
check('early MQTT error callback safely executes after virtual devices exist',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings,{'/devices/wb-msw-v4_22/meta/error':'1'});
    m.tick('office',19);
    assert.strictEqual(m.room('office','demand'),'OFF');
});
check('corrupt temperature produces no new heating/closing intent',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office','garbage');
    assert.strictEqual(m.room('office','demand'),'UNKNOWN');
});
check('no current rules, virtual writes or logs address physical outputs',function(){
    var settings={};seed(settings,'office');var m=instantiate(settings);
    m.tick('office',19);m.fault('office','1');
    m.writes.forEach(function(w){assert.ok(/^iset_hhm_/.test(w.path),w.path);});
    // Physical actuator readback is allowed; assignment is forbidden.
    assert.strictEqual(/dev\\s*\\[\\s*z\\.outputs\\[j\\]\\s*\\]\\s*=/.test(source),false);
    // Reading the K4 relay is allowed. Assigning to it is not.
    assert.strictEqual(/dev\\s*\\[\\s*IS_MAP\\.pump\\s*\\]\\s*=/.test(source),false);
    assert.ok(m.logs.some(function(s){return s.indexOf('запись_выходов=ЗАПРЕЩЕНА')>=0;}));
});
check('shadow control fields are readonly and never act as writable setpoints',function(){
    var m=instantiate({}),fields=m.declared.iset_hhm_office_shadow.cells;
    Object.keys(fields).forEach(function(c){assert.strictEqual(fields[c].readonly,true);});
});
check('shadow displays exact NO valve OPEN intention without physical write',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_action'],'HOLD');
    assert.ok(m.values['iset_hhm_rooms_shadow/proposed_actions'].indexOf(
        'ZONE_OPEN wb-mio-gpio_195:2/K1')>=0);
    m.writes.forEach(function(w){assert.ok(/^iset_hhm_/.test(w.path));});
});
check('shadow shows pump START only after 120 seconds of observed open NO',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    m.readback('wb-mio-gpio_195:2/K1',false);
    m.readback(Map.pump,false);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_action'],'HOLD');
    m.advance(119000);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_action'],'HOLD');
    m.advance(1000);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_action'],'START');
});
check('periodic shadow tick does not flood unchanged virtual controls',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    var before=m.writes.length;m.advance(5000);
    assert.strictEqual(m.writes.length,before);
});
check('every physical NO K1..K11 has its own virtual timer',function(){
    var m=instantiate({}),seen={};
    Map.zones.forEach(function(z){
        var fields=m.declared['iset_hhm_'+z.id+'_shadow'].cells;
        assert.ok(fields.opening_timer);
        z.outputs.forEach(function(output){
            var id='servo_'+output.split('/')[1].toLowerCase()+'_timer';
            assert.strictEqual(fields[id].readonly,true);
            seen[output]=true;
        });
    });
    assert.strictEqual(Object.keys(seen).length,11);
});
check('K4 virtual device exposes start wait, observed RUN and STOP wait timers',function(){
    var m=instantiate({}),fields=m.declared.iset_hhm_rooms_shadow.cells;
    ['pump_status','pump_readback','pump_start_timer',
     'pump_run_timer','pump_stop_timer'].forEach(function(k){
        assert.strictEqual(fields[k].readonly,true,k);
    });
});
check('per-room K1 counter displays 120 to 119 to ready after OPEN readback',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    var timer=function(){return m.room('office','servo_k1_timer');};
    assert.strictEqual(timer(),'Ожидание OPEN');
    m.readback('wb-mio-gpio_195:2/K1',false);
    m.readback(Map.pump,false);
    assert.strictEqual(timer(),'120 с');
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_start_timer'],'120 с');
    m.advance(1000);
    assert.strictEqual(timer(),'119 с');
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_start_timer'],'119 с');
    m.advance(119000);
    assert.strictEqual(timer(),'Готово');
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_start_timer'],'Готов к пуску');
});
check('K2 and K3 report independent countdowns inside same room',function(){
    var settings={};seed(settings,'summer_kitchen');
    var m=instantiate(settings);m.tick('summer_kitchen',19);
    m.readback('wb-mio-gpio_195:2/K2',false);
    m.readback(Map.pump,false);
    assert.strictEqual(m.room('summer_kitchen','servo_k2_timer'),'120 с');
    assert.strictEqual(m.room('summer_kitchen','servo_k3_timer'),'Ожидание OPEN');
    m.advance(30000);m.readback('wb-mio-gpio_195:2/K3',false);
    assert.strictEqual(m.room('summer_kitchen','servo_k2_timer'),'90 с');
    assert.strictEqual(m.room('summer_kitchen','servo_k3_timer'),'120 с');
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_start_timer'],'120 с');
});
check('K4 run timer is observed elapsed, resets after relay OFF',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    m.readback(Map.pump,true);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_run_timer'],'0 с');
    m.advance(5000);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_run_timer'],'5 с');
    m.readback(Map.pump,false);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_run_timer'],'—');
});
check('K4 pending STOP timer shows elapsed feedback wait, no invented postrun',function(){
    var settings={};
    Map.zones.forEach(function(z){seed(settings,z.id);});
    var m=instantiate(settings);
    Map.zones.forEach(function(z){m.tick(z.id,26);});
    m.readback(Map.pump,true);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_stop_timer'],'0 с');
    m.advance(3000);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_stop_timer'],'3 с');
    m.readback(Map.pump,false);
    assert.strictEqual(m.values['iset_hhm_rooms_shadow/pump_stop_timer'],'—');
});
check('live timer ticks cannot write NO outputs or K4',function(){
    var settings={};seed(settings,'office');
    var m=instantiate(settings);m.tick('office',19);
    m.readback('wb-mio-gpio_195:2/K1',false);
    m.readback(Map.pump,false);
    m.advance(1000);m.advance(1000);m.advance(3000);
    m.writes.forEach(function(w){
        assert.ok(/^iset_hhm_/.test(w.path),'Physical write '+w.path);
    });
});
console.log('TOTAL PASS '+total);
