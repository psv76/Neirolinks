/* Offline WB rule VM smoke tests. NO WB, MQTT or physical I/O. */
var assert=require('assert'),fs=require('fs'),path=require('path'),vm=require('vm');
var root=path.resolve(__dirname,'../../..');
var Map=require(path.join(root,'Objects/05_16_Iset/HHM/room_zones.js'));
var aliases={
    IsetRoomSimpleThermostat:require(path.join(root,'Objects/05_16_Iset/HHM/simple_room_thermostat.js')),
    IsetRoomSettingsStore:require(path.join(root,'Objects/05_16_Iset/HHM/room_settings_store.js')),
    IsetRoomLocalRuntime:require(path.join(root,'Objects/05_16_Iset/HHM/room_local_runtime.js')),
    IsetRoomZones:Map,
    HHMRoomPathGate:require(path.join(root,'Systems/HHM/core/HHMRoomPathGate.js'))
};
var source=fs.readFileSync(path.join(root,'Objects/05_16_Iset/Wirenboard/wb-rules/28_hhm_rooms_shadow.js'),'utf8');
var total=0;function check(label,fn){fn();total++;console.log('PASS '+label);}
function seed(store,id,t){
    var s=aliases.IsetRoomSettingsStore.create(store,id);
    store[s.key]=s.proposeInitial('HEAT',t||22);
}
function instantiate(settings,initial){
    var values={},rules=[],topics={},declared={},writes=[],logs=[];
    var backing=settings||{};
    var storeConstructor=function(){return backing;};
    var proxy=new Proxy(values,{set:function(t,k,v){
        writes.push({path:k,value:v});t[k]=v;return true;}});
    var ctx={dev:proxy,Date:Date,Math:Math,JSON:JSON,
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
        assert.ok(z);proxy[z.primarySensor]=v;
        rules[0].rule.then();
    }
    function fault(id,val){
        var z=Map.zones.filter(function(x){return x.id===id;})[0];
        topics['/devices/'+z.primarySensor.split('/')[0]+'/meta/error']({value:val});
    }
    return {declared:declared,rules:rules,topics:topics,values:values,
        writes:writes,logs:logs,room:room,tick:tick,fault:fault,storage:backing};
}
check('eight named room virtual diagnostics and one global state',function(){
    var m=instantiate({});
    assert.strictEqual(Object.keys(m.declared).length,9);
    assert.strictEqual(Object.keys(m.topics).length,8);
    assert.strictEqual(m.rules.length,1);
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
    assert.strictEqual(source.indexOf('dev[z.outputs'),-1);
    assert.strictEqual(source.indexOf('dev[IS_MAP.pump]'),-1);
    assert.ok(m.logs.some(function(s){return s.indexOf('запись_выходов=ЗАПРЕЩЕНА')>=0;}));
});
check('shadow control fields are readonly and never act as writable setpoints',function(){
    var m=instantiate({}),fields=m.declared.iset_hhm_office_shadow.cells;
    Object.keys(fields).forEach(function(c){assert.strictEqual(fields[c].readonly,true);});
});
console.log('TOTAL PASS '+total);
