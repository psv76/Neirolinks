/* Offline passive WB-MSW MQTT publication evidence tests: no MQTT traffic. */
var assert=require('assert'),M=require('../core/HHMRoomMqttReadEvidence');
var count=0;
function check(n,fn){fn();count++;console.log('PASS '+n);}
var HASH=new Array(65).join('a');
function cfg(){return {sensorId:'wb-msw-v4_22/Temperature',
    topic:'/devices/wb-msw-v4_22/controls/Temperature',
    errorTopic:'/devices/wb-msw-v4_22/meta/error',
    driverVersion:'2.268.0-wb102',expectedConfigSHA256:HASH,
    unchangedIntervalS:30,freshMs:90000,minC:-20,maxC:60};}
function policy(more){var p={source:'LOCAL_SERVICE_AND_CONFIG_AUDIT',
    confirmed:true,bootEpoch:'wb-boot-1',driverEpoch:'serial-pid-start-1',
    observedAtMs:1000,driverVersion:'2.268.0-wb102',
    configSHA256:HASH,maxUnchangedIntervalS:30,cachedRepublishEnabled:false};
    var k;for(k in (more||{}))p[k]=more[k];return p;}
function frame(ms,value,more){var e={receivedAtMs:ms,bootEpoch:'wb-boot-1',
    driverEpoch:'serial-pid-start-1',
    topic:'/devices/wb-msw-v4_22/controls/Temperature',
    source:'WB_MQTT_SERIAL_TEMPERATURE_PUBLISH',
    qualifiedLocalTransport:true,retained:false,payload:value};
    var k;for(k in (more||{}))e[k]=more[k];return e;}
function error(ms,active,more){var e={receivedAtMs:ms,bootEpoch:'wb-boot-1',
    driverEpoch:'serial-pid-start-1',source:'WB_MQTT_SERIAL_ERROR_TOPIC',
    topic:'/devices/wb-msw-v4_22/meta/error',errorActive:active,
    retained:false};
    var k;for(k in (more||{}))e[k]=more[k];return e;}
function setup(){var m=M.create(cfg());
    assert.strictEqual(m.qualifyPolicy(policy()).accepted,true);return m;}
function sample(m,ms,b,d){return m.sample(ms,b||'wb-boot-1',d||'serial-pid-start-1');}
check('unverified policy never accepts warm MQTT cache',function(){
    var m=M.create(cfg());
    assert.strictEqual(m.observeTemperature(frame(1100,'24')).accepted,false);
    assert.strictEqual(sample(m,1200).ok,false);
});
check('positive bounded unchanged publication must be approved',function(){
    var c=cfg();c.unchangedIntervalS=-1;
    assert.throws(function(){M.create(c);},/read-bound/);
    c.unchangedIntervalS=30;c.freshMs=30000;
    assert.throws(function(){M.create(c);},/read-bound/);
});
check('actual driver version and config SHA must match approved policy',function(){
    var m=M.create(cfg());
    assert.strictEqual(m.qualifyPolicy(policy({driverVersion:'2.270.0'})).accepted,false);
    assert.strictEqual(m.qualifyPolicy(policy({configSHA256:new Array(65).join('b')})).accepted,false);
    assert.strictEqual(m.qualifyPolicy(policy()).accepted,true);
});
check('cache publishing must be ruled out by versioned policy',function(){
    var m=M.create(cfg());
    assert.strictEqual(m.qualifyPolicy(policy({cachedRepublishEnabled:true})).accepted,false);
});
check('non-retained numeric MQTT publishes qualify local sample',function(){
    var m=setup();
    assert.strictEqual(m.observeTemperature(frame(2000,'23.91')).accepted,true);
    var r=sample(m,2500);
    assert.strictEqual(r.ok,true);assert.strictEqual(r.temperatureC,23.91);
    assert.strictEqual(r.id,'wb-msw-v4_22/Temperature');
});
check('same numerical temperature is a new publication but not a loop tick',function(){
    var m=setup();m.observeTemperature(frame(2000,'24.1'));
    m.observeTemperature(frame(41000,'24.1'));
    assert.strictEqual(sample(m,100000).ok,true);
    assert.strictEqual(sample(m,131001).ok,false);
});
check('retained broker snapshot cannot qualify health',function(){
    var m=setup();assert.strictEqual(m.observeTemperature(frame(3000,'24',
        {retained:true})).accepted,false);
    assert.strictEqual(sample(m,3100).ok,false);
});
check('wrong device control and untrusted transport rejected',function(){
    var m=setup();
    assert.strictEqual(m.observeTemperature(frame(3000,'24',
        {topic:'/devices/wb-msw-v4_47/controls/Temperature'})).accepted,false);
    assert.strictEqual(m.observeTemperature(frame(3100,'24',
        {qualifiedLocalTransport:false})).accepted,false);
});
check('invalid readings cannot enter thermostat',function(){
    var m=setup();
    assert.strictEqual(m.observeTemperature(frame(2000,'NaN')).accepted,false);
    assert.strictEqual(m.observeTemperature(frame(3000,'100')).accepted,false);
    assert.strictEqual(m.observeTemperature(frame(4000,'')).accepted,false);
    assert.strictEqual(sample(m,4100).ok,false);
});
check('old and equal-time duplicate publications rejected',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(m.observeTemperature(frame(2000,'24')).accepted,false);
    assert.strictEqual(m.observeTemperature(frame(1900,'24')).accepted,false);
});
check('driver error invalidates good sample without waiting for staleness',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(m.observeError(error(3000,true)).accepted,true);
    assert.strictEqual(sample(m,3001).ok,false);
    assert.strictEqual(m.observeTemperature(frame(4000,'24')).accepted,false);
});
check('driver error requires clear plus subsequent fresh temperature',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    m.observeError(error(3000,true));
    m.observeError(error(3500,false));
    assert.strictEqual(m.observeTemperature(frame(3500,'24')).accepted,false);
    assert.strictEqual(m.observeTemperature(frame(3800,'24')).accepted,true);
    assert.strictEqual(sample(m,3801).ok,true);
});
check('foreign driver error topic cannot disable another sensor',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(m.observeError(error(2100,true,
        {topic:'/devices/wb-msw-v4_47/meta/error'})).accepted,false);
    assert.strictEqual(sample(m,2200).ok,true);
});
check('driver restart revokes reading even when WB itself stayed up',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(sample(m,3000,'wb-boot-1','serial-pid-start-2').ok,false);
    assert.strictEqual(m.observeTemperature(frame(4000,'24',
        {driverEpoch:'serial-pid-start-2'})).accepted,false);
    assert.strictEqual(m.qualifyPolicy(policy({observedAtMs:5000,
        driverEpoch:'serial-pid-start-2'})).accepted,true);
    assert.strictEqual(sample(m,5500,'wb-boot-1','serial-pid-start-2').ok,false);
});
check('controller reboot revokes retained and previous publication',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(sample(m,3000,'wb-boot-2').ok,false);
    assert.strictEqual(m.qualifyPolicy(policy({observedAtMs:4000,
        bootEpoch:'wb-boot-2'})).accepted,true);
    assert.strictEqual(m.observeTemperature(frame(5000,'24',
        {bootEpoch:'wb-boot-1'})).accepted,false);
});
check('monotonic rewind cancels session',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(sample(m,100,'wb-boot-1').ok,false);
    assert.strictEqual(m.observeTemperature(frame(500,'24')).accepted,false);
});
check('policy revocation when config changes',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(m.qualifyPolicy(policy({observedAtMs:3000,
        maxUnchangedIntervalS:-1})).accepted,false);
    assert.strictEqual(sample(m,3100).ok,false);
});
check('unchanged temperature expires after silence, no fake refresh',function(){
    var m=setup();m.observeTemperature(frame(2000,'24'));
    assert.strictEqual(sample(m,92001).ok,false);
    assert.strictEqual(sample(m,93000).temperatureC,null);
});
console.log('TOTAL PASS '+count);
