'use strict';
const assert=require('node:assert/strict');
const {create,epoch}=require('./harness');
let count=0;
function test(title,fn){fn();count++;console.log('PASS RPC '+title);}
function rig(){
    const h=create(),W=h.load('HHM3Wire'),Fresh=h.load('HHM3Freshness');
    let now=epoch;const handlers={},writes=[];
    const e={now:()=>now,trackMqtt:(p,cb)=>handlers[p]=cb,
        publish:(p,s,q,r)=>writes.push({p,body:JSON.parse(s),q,r,at:now})};
    const reader=Fresh.create(e,'unit',null),s=W.sensor();
    const path='921.10_TEMP_NONE/External Sensor 1';
    reader.add(path,s,-20,70);s.sample(18.75,false,now);
    function answer(overrides={},retained=false){
        const req=writes.at(-1),b={id:req.body.id,error:null,
            result:{channels:{'External Sensor 1':18.75},readonly:['External Sensor 1']}};
        Object.assign(b,overrides);
        handlers[reader.replyTopic]({value:JSON.stringify(b),retained});
    }
    return {s,reader,writes,answer,advance:n=>now+=n,now:()=>now,handlers,e};
}
test('only proven sensor read after 70s, read-only device/Load exact one channel',()=>{
    const x=rig();x.advance(69999);x.reader.tick();assert.equal(x.writes.length,0);
    x.advance(1);x.reader.tick();assert.equal(x.writes.length,1);
    const w=x.writes[0];assert.match(w.p,/^\/rpc\/v1\/wb-mqtt-serial\/device\/Load\/hhm3-unit-/);
    assert.equal(w.r,false);assert.equal(w.q,0);assert.equal(w.body.params.device_id,'921.10_TEMP_NONE');
    assert.deepEqual(Array.from(w.body.params.channels),['External Sensor 1']);
    assert.equal(w.body.params.total_timeout,10000);assert.equal(x.reader.pending(),'921.10_TEMP_NONE/External Sensor 1');
    x.answer();assert.equal(x.reader.pending(),null);assert.equal(x.s.timestamp(),x.now());
    assert.equal(x.s.read(x.now(),-20,70),18.75);
});
test('retained reply, wrong ID and duplicate cannot complete request',()=>{
    const x=rig();x.advance(70000);x.reader.tick();const t=x.s.timestamp();
    x.answer({},true);assert.equal(x.reader.pending(),'921.10_TEMP_NONE/External Sensor 1');assert.equal(x.s.timestamp(),t);
    x.answer({id:999});assert.notEqual(x.reader.pending(),null);
    x.answer();assert.equal(x.reader.pending(),null);x.answer();assert.equal(x.s.timestamp(),x.now());
});
test('error/foreign channel/readonly missing/out of range/null fail closed',()=>{
    for(const invalid of [
        {error:{code:-32000},result:null},
        {result:{channels:{Temperature:18.75},readonly:['Temperature']}},
        {result:{channels:{'External Sensor 1':18.75},readonly:[]}},
        {result:{channels:{'External Sensor 1':null},readonly:['External Sensor 1']}},
        {result:{channels:{'External Sensor 1':85},readonly:['External Sensor 1']}}
    ]){
        const x=rig();x.advance(70000);x.reader.tick();x.answer(invalid);
        assert.equal(x.s.read(x.now(),-20,70),null);
        assert.equal(x.reader.pending(),null);
        assert.equal(x.reader.status('921.10_TEMP_NONE/External Sensor 1'),'INVALID_RESPONSE');
    }
});
test('timeout invalidates current reading, backoff and late answer ignored',()=>{
    const x=rig();x.advance(70000);x.reader.tick();const prev=x.writes[0];
    x.advance(12000);x.reader.tick();assert.equal(x.s.read(x.now(),-20,70),null);
    assert.equal(x.reader.pending(),null);x.answer();assert.equal(x.s.read(x.now(),-20,70),null);
    x.advance(29999);x.reader.tick();assert.equal(x.writes.length,1);
    x.advance(4000);x.reader.tick();assert.equal(x.writes.length,2);
    assert.notEqual(x.writes[1].body.id,prev.body.id);
});
test('newer non-retained MQTT cannot be overwritten by older delayed RPC',()=>{
    const x=rig();x.advance(70000);x.reader.tick();x.advance(100);
    x.s.sample(21,false,x.now());x.answer();
    assert.equal(x.s.read(x.now(),-20,70),21);
    assert.equal(x.reader.pending(),null);
});
test('error event and error clearance invalidate in-flight read',()=>{
    const x=rig();x.advance(70000);x.reader.tick();x.s.error('Wire Error',false);
    x.answer();assert.equal(x.s.read(x.now(),-20,70),null);
    const y=rig();y.advance(70000);y.reader.tick();y.s.error('',false);
    y.answer();assert.equal(y.s.read(y.now(),-20,70),null);
});
test('2.40 missing retain metadata cannot launder RPC as trustworthy',()=>{
    const x=rig();x.advance(70000);x.reader.tick();
    x.handlers[x.reader.replyTopic]({value:JSON.stringify({id:x.writes[0].body.id,error:null,
        result:{channels:{'External Sensor 1':18.75},readonly:['External Sensor 1']}})});
    assert.notEqual(x.reader.pending(),null);
    x.s.sample(20,undefined,x.now());x.answer();
    assert.equal(x.s.read(x.now(),-20,70),null);
});
test('19 stale sensors are read within 40 seconds with 2-second scheduler, one RPC at once',()=>{
    const h=create(),W=h.load('HHM3Wire'),Fresh=h.load('HHM3Freshness');
    let now=epoch,reply=null,requests=0;const map={};
    const broker={now:()=>now,trackMqtt:(topic,fn)=>{reply=fn;},
        publish:(topic,body)=>{
            const p=JSON.parse(body);requests++;
            const channel=p.params.channels[0];
            reply({retained:false,value:JSON.stringify({id:p.id,error:null,
                result:{channels:{[channel]:19},readonly:[channel]}})});
        }};
    const rpc=Fresh.create(broker,'bulk',null);
    for(let i=0;i<19;i++){
        const sensor=W.sensor(),path='921.'+String(i+1).padStart(2,'0')+'_M1W2/External Sensor 1';
        sensor.sample(18,false,now);rpc.add(path,sensor,-20,70);map[path]=sensor;
    }
    now+=70000;
    for(let i=0;i<19;i++){rpc.tick();now+=2000;}
    assert.equal(requests,19);
    for(const sensor of Object.values(map))assert.ok(sensor.timestamp()>=epoch+70000);
});
test('unknown channels rejected before publishing any RPC',()=>{
    const x=rig();assert.throws(()=>x.reader.add('A03/K4',x.s,0,1));
    assert.throws(()=>x.reader.add('wbe2-i-opentherm_11/Heating Setpoint',x.s,-20,110));
    assert.throws(()=>x.reader.add('921.10_TEMP_NONE/External Sensor 1',x.s,70,-20));
    assert.equal(x.writes.length,0);
});
test('three independent consumers publish only temperature read requests',()=>{
    const h=create();h.samples();h.advance(75000,false);
    const requests=h.messages.filter(m=>m.topic.includes('/rpc/v1/wb-mqtt-serial/device/Load/'));
    assert.equal(requests.length,3,'500,620,624 one pending per script');
    for(const r of requests){const o=JSON.parse(r.payload);assert.equal(r.retained,false);assert.equal(o.params.channels.length,1);
        assert.match(o.params.channels[0],/^(Temperature|External Sensor [12])$/);
        assert.doesNotMatch(r.topic,/\/Set\/|\/on$/);
    }
    assert.ok(requests.some(r=>r.board==='gazebo'));
});
console.log('RESULT RPC: '+count+' groups PASS; read-only mocked broker, NOT live/protocol acceptance.');

module.exports=count;
