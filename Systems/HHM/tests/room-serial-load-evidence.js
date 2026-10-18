/* Offline regression for read-only wb-mqtt-serial device/Load contract. */
var assert=require('assert');
var Load=require('../core/HHMRoomSerialLoadEvidence');
var Evidence=require('../core/HHMRoomSensorEvidence');
var total=0;
function check(name,fn){fn();total++;console.log('PASS '+name);}
function create(){return Load.create({sensorId:'wb-msw-v4_22/Temperature',
    deviceType:'WB-MSW v.4',slaveId:22,
    portPath:'/dev/ttyRS485-2',baudRate:9600,parity:'N',dataBits:8,stopBits:2,
    temperatureTopic:'/devices/wb-msw-v4_22/controls/Temperature',
    channel:'Temperature',clientPrefix:'hhm_2056_test_boot_unique',
    minC:-20,maxC:60,replyTimeoutMs:5000,freshMs:30000,maxSequence:100},Evidence);}
function success(request,value,id){return {nowMs:1100,bootEpoch:'A',topic:request.replyTopic,
    retained:false,payload:JSON.stringify({id:id||1,error:null,
        result:{channels:{Temperature:value}}})};}
function warm(){var x=create(),r=x.request(1000,'A');return {x:x,r:r};}
check('unprobed sensor is UNKNOWN',function(){assert.strictEqual(create().sample(1,'A').ok,false);});
check('read-only request has exact Load topic and one Temperature channel',function(){
    var p=warm().r;
    assert.strictEqual(p.send,true);
    assert.strictEqual(p.topic.indexOf('wb-mqtt-serial/device/Load/'),0);
    assert.deepStrictEqual(p.payload,{slave_id:22,device_type:'WB-MSW v.4',
        channels:['Temperature'],path:'/dev/ttyRS485-2',baud_rate:9600,
        parity:'N',data_bits:8,stop_bits:2});
    assert.strictEqual(p.retained,false);
});
check('successful direct driver read qualifies fresh local sample',function(){
    var v=warm();assert.strictEqual(v.x.reply(success(v.r,24)).accepted,true);
    assert.strictEqual(v.x.sample(1150,'A').temperatureC,24);
});
check('constant temperatures are healthy only after a second direct read',function(){
    var v=warm();v.x.reply(success(v.r,24));
    var r=v.x.request(20000,'A'),reply=success(r,24,2);reply.nowMs=20050;
    assert.strictEqual(v.x.reply(reply).accepted,true);
    assert.strictEqual(v.x.sample(50000,'A').ok,true);
});
check('stale sample expires regardless of retained MQTT temperature',function(){
    var v=warm();v.x.reply(success(v.r,24));
    assert.strictEqual(v.x.sample(31101,'A').ok,false);
});
check('no unmatched unsolicited MQTT reply qualifies sensor',function(){
    var x=create();assert.strictEqual(x.reply({nowMs:100,bootEpoch:'A',
        topic:'wb-mqtt-serial/device/Load/other/reply',retained:false,
        payload:'{"id":1,"error":null,"result":{"channels":{"Temperature":24}}}'}).accepted,false);
    assert.strictEqual(x.sample(110,'A').ok,false);
});
check('retained reply is rejected and cannot consume pending request',function(){
    var v=warm(),bad=success(v.r,24);bad.retained=true;
    assert.strictEqual(v.x.reply(bad).accepted,false);
    assert.strictEqual(v.x.sample(1200,'A').ok,false);
    var good=success(v.r,24);good.nowMs=1250;
    assert.strictEqual(v.x.reply(good).accepted,true);
});
check('wrong topic and sensor cannot cross-qualify',function(){
    var v=warm(),r=success(v.r,22);r.topic='/devices/wb-msw-v4_53/controls/Temperature';
    assert.strictEqual(v.x.reply(r).accepted,false);
    assert.strictEqual(v.x.sample(1200,'A').ok,false);
});
check('same reply cannot be replayed as successful poll',function(){
    var v=warm(),r=success(v.r,24);v.x.reply(r);
    assert.strictEqual(v.x.reply(r).accepted,false);
    assert.strictEqual(v.x.snapshot().nextSequence,1);
});
check('pending request prevents duplicate bus load',function(){
    var v=warm();assert.strictEqual(v.x.request(1100,'A').send,false);
    assert.strictEqual(v.x.snapshot().nextSequence,1);
});
check('timeout revokes prior health and permits a new unique request',function(){
    var v=warm();v.x.reply(success(v.r,23));
    var r2=v.x.request(2000,'A');
    assert.strictEqual(v.x.sample(7001,'A').ok,false);
    var r3=v.x.request(7002,'A');
    assert.strictEqual(r3.send,true);
    assert.notStrictEqual(r2.replyTopic,r3.replyTopic);
    var late=success(r2,99);late.nowMs=7050;
    assert.strictEqual(v.x.reply(late).accepted,false);
    var good=success(r3,23,3);good.nowMs=7100;
    assert.strictEqual(v.x.reply(good).accepted,true);
});
check('failed driver RPC revokes previous reading',function(){
    var v=warm();v.x.reply(success(v.r,24));
    var r=v.x.request(2000,'A'),bad=success(r,24,2);bad.nowMs=2100;
    bad.payload=JSON.stringify({id:2,error:{code:-32000},result:null});
    assert.strictEqual(v.x.reply(bad).accepted,false);
    assert.strictEqual(v.x.sample(2101,'A').ok,false);
});
check('missing Temperature channel rejected, not made healthy',function(){
    var v=warm(),r=success(v.r,22);
    r.payload=JSON.stringify({id:1,error:null,result:{channels:{Humidity:40}}});
    assert.strictEqual(v.x.reply(r).accepted,false);
    assert.strictEqual(v.x.sample(1200,'A').ok,false);
});
check('malformed reply rejected and consumed',function(){
    var v=warm(),r=success(v.r,22);r.payload='{broken';
    assert.strictEqual(v.x.reply(r).accepted,false);
    assert.strictEqual(v.x.reply(success(v.r,22)).accepted,false);
});
check('driver replies must contain valid request id',function(){
    var v=warm(),r=success(v.r,22);
    r.payload=JSON.stringify({error:null,result:{channels:{Temperature:22}}});
    assert.strictEqual(v.x.reply(r).accepted,false);
});
check('implausible physical sample not qualified',function(){
    var v=warm(),r=success(v.r,999);
    assert.strictEqual(v.x.reply(r).accepted,false);
    assert.strictEqual(v.x.sample(1101,'A').ok,false);
});
check('non-numeric string temperature rejected',function(){
    var v=warm(),r=success(v.r,'24.00');
    assert.strictEqual(v.x.reply(r).accepted,false);
});
check('new boot discards request and previous reading',function(){
    var v=warm();v.x.reply(success(v.r,23));
    assert.strictEqual(v.x.sample(1500,'B').ok,false);
    var r=v.x.request(1600,'B');
    assert.strictEqual(r.send,true);
    var old=success(v.r,26);old.nowMs=1650;
    assert.strictEqual(v.x.reply(old).accepted,false);
    var recent=success(r,23,2);recent.bootEpoch='B';recent.nowMs=1700;
    assert.strictEqual(v.x.reply(recent).accepted,true);
});
check('clock rewind rejects request and revokes sample',function(){
    var v=warm();v.x.reply(success(v.r,23));
    assert.strictEqual(v.x.request(1000,'A').send,false);
    assert.strictEqual(v.x.sample(1001,'A').ok,false);
});
check('timed-out first reply cannot be mistaken for second',function(){
    var v=warm(),r2=v.x.request(6002,'A');
    assert.strictEqual(r2.send,true);
    var stale=success(v.r,21);stale.nowMs=6050;
    assert.strictEqual(v.x.reply(stale).accepted,false);
    assert.strictEqual(v.x.snapshot().pending,true);
});
check('request sequence exhausted fail-closed',function(){
    var v=create(),i,r;for(i=0;i<100;i++){
        r=v.request(i*100,'A');assert.strictEqual(r.send,true);
        var fail=success(r,20,i+1);fail.nowMs=i*100+1;
        v.reply(fail);
    }
    assert.strictEqual(v.request(10100,'A').send,false);
});
check('rejects unsafe or incomplete configuration',function(){
    assert.throws(function(){Load.create({deviceId:'wb-msw-v4_22'},Evidence);},/RPC configuration/);
});
check('actual Iset sensor 22 requires explicit verified serial port contract',function(){
    var p=warm().r.payload;
    assert.strictEqual(p.slave_id,22);
    assert.strictEqual(p.device_type,'WB-MSW v.4');
    assert.strictEqual(p.path,'/dev/ttyRS485-2');
    assert.strictEqual(p.baud_rate,9600);
    assert.strictEqual(p.data_bits,8);
    assert.strictEqual(p.stop_bits,2);
    assert.strictEqual(p.parity,'N');
    assert.strictEqual(p.device_id,undefined);
});
check('wrong port metadata and missing slave id fail configuration',function(){
    var c={sensorId:'wb-msw-v4_22/Temperature',deviceType:'WB-MSW v.4',
        slaveId:22,portPath:'/dev/ttyRS485-2',baudRate:9600,parity:'N',
        dataBits:8,stopBits:2,temperatureTopic:'/devices/wb-msw-v4_22/controls/Temperature',
        channel:'Temperature',clientPrefix:'hhm_2056_test_boot_unique',
        minC:-20,maxC:60,replyTimeoutMs:5000,freshMs:30000,maxSequence:100};
    c.portPath='/tmp/serial2';
    assert.throws(function(){Load.create(c,Evidence);},/RPC configuration/);
    c.portPath='/dev/ttyRS485-2';c.slaveId=null;
    assert.throws(function(){Load.create(c,Evidence);},/RPC configuration/);
});
check('requires injected WB-compatible evidence dependency',function(){
    assert.throws(function(){Load.create({});},/injected evidence module/);
});
console.log('TOTAL PASS '+total);
