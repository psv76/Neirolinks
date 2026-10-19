/* Offline WB-MAO4 writer tests: no MQTT, relays or controller. ES5. */
var assert=require('assert');
var Outputs=require('../adapters/HHM3Mao4Output');
var Circuit=require('../core/HHM3Circuit');
var Mixing=require('../core/HHM3Mixing');
var Loss=require('../core/HHM3SensorLossPolicy');
var pass=0, cfg={periodMs:5000,valveActiveMinLevel:1,
 valveActiveMaxLevel:100,valveOffCommand:false,
 pump:'test/K2',level:'test/Channel 1 Dimming Level',
 enable:'test/Channel 1 Switch',commandTimeoutMs:10000,commandRetryMs:5000};
function rig() {
 var data={},seq={},writes=[],errors={};
 data[cfg.pump]=false;data[cfg.level]=25;data[cfg.enable]=0;
 seq[cfg.pump]=0;seq[cfg.level]=0;seq[cfg.enable]=0;
 var io={
   read:function(p){return data[p];},
   readback:function(p){return {value:data[p],seq:seq[p],at:0};},
   matches:function(p,v){return data[p]===(p===cfg.enable?(v?1:0):v);},
   write:function(p,v,force){
     writes.push({path:p,value:v});
     if(errors[p])return {ok:false,sent:false};
     data[p]=p===cfg.enable?(v?1:0):v;seq[p]=(seq[p]||0)+1;
     // Simulate documented WB-MAO4 AUTO-ON upon changed Level.
     if(p===cfg.level&&v>0){data[cfg.enable]=1;seq[cfg.enable]++;}
     return {ok:true,sent:true};
   }
 };
 return {io:io,writes:writes,data:data,seq:seq,errors:errors,
   steps:Outputs.create(cfg,io)};
}
function request(a,v,p){return {valveAction:a,valve:v,pump:p,
 hydraulicPathReady:true};}
function check(name,fn){fn();pass++;console.log('PASS '+name);}
function open(r){
 r.steps(request('APPLY',30,true),5000); // startup close, no heat yet
 var o=r.steps(request('APPLY',30,true),10000);
 assert.strictEqual(o.state,'HEAT_COMMANDED');
 assert.strictEqual(o.ready,true);assert.strictEqual(o.pump,true);
 assert.strictEqual(o.acceptedValvePct,30);
 return o;
}
function valveWrites(r){return r.writes.filter(function(w){
 return w.path===cfg.level||w.path===cfg.enable;});}
check('legacy APPLY initializes closed before first hot output',function(){
 var r=rig(),o=r.steps(request('APPLY',30,true),5000);
 assert.strictEqual(o.state,'OFF_COMMANDED');
 assert.strictEqual(o.ready,false);
 assert.strictEqual(r.data[cfg.enable],0);
});
check('APPLY retains approved MAO4 AUTO-ON and fresh readback sequence',function(){
 var r=rig(),o=open(r);
 assert.strictEqual(r.data[cfg.enable],1);
 assert.ok(r.data[cfg.level]>0);
 assert.strictEqual(o.acceptedValveConfirmed,true);
});
check('HOLD does not write Level or Switch and preserves pump',function(){
 var r=rig();open(r);
 var count=valveWrites(r).length;
 var o=r.steps(request('HOLD',30,true),15000);
 assert.strictEqual(o.state,'HEAT_HELD');
 assert.strictEqual(o.ready,true);
 assert.strictEqual(o.acceptedValvePct,30);
 assert.strictEqual(valveWrites(r).length,count);
 assert.strictEqual(r.data[cfg.pump],true);
});
check('repeated long HOLD never reasserts analog Level or Switch',function(){
 var r=rig();open(r);var n=valveWrites(r).length;
 for(var i=0;i<20;i++){
   var o=r.steps(request('HOLD',30,true),15000+i*5000);
   assert.strictEqual(o.state,'HEAT_HELD');assert.strictEqual(o.ready,true);
 }
 assert.strictEqual(valveWrites(r).length,n);
});
check('NO_COMMAND makes no physical writes including pump',function(){
 var r=rig();open(r);var n=r.writes.length;
 var o=r.steps(request('NO_COMMAND',null,true),15000);
 assert.strictEqual(o.state,'OUTPUT_NO_COMMAND');
 assert.strictEqual(o.ready,false);
 assert.strictEqual(r.writes.length,n);
});
check('HOLD at cold boot issues no OFF / ON commands',function(){
 var r=rig();var o=r.steps(request('HOLD',30,true),5000);
 assert.strictEqual(o.state,'HOLD_UNQUALIFIED');
 assert.strictEqual(o.ready,false);
 assert.strictEqual(r.writes.length,0);
});
check('NO_COMMAND at cold boot issues no OFF / ON commands',function(){
 var r=rig();var o=r.steps(request('NO_COMMAND',null,true),5000);
 assert.strictEqual(o.state,'OUTPUT_NO_COMMAND');
 assert.strictEqual(o.ready,false);assert.strictEqual(r.writes.length,0);
});
check('first APPLY after cold-boot HOLD uses normal start sequence',function(){
 var r=rig();r.steps(request('HOLD',30,true),5000);
 var o=r.steps(request('APPLY',30,true),10000);
 assert.strictEqual(o.state,'OFF_COMMANDED');
 assert.strictEqual(r.data[cfg.enable],0);
 assert.strictEqual(o.ready,false);
});
check('APPLY after HOLD can move level with ordinary confirmation',function(){
 var r=rig();open(r);r.steps(request('HOLD',30,true),15000);
 var o=r.steps(request('APPLY',35,true),20000);
 assert.strictEqual(o.state,'HEAT_COMMANDED');
 assert.strictEqual(o.ready,true);assert.strictEqual(o.acceptedValvePct,35);
 assert.strictEqual(r.data[cfg.enable],1);
});
check('mismatching readback during HOLD does not force a new valve command',function(){
 var r=rig();open(r);var count=valveWrites(r).length;
 r.data[cfg.enable]=0;r.seq[cfg.enable]++;
 var o=r.steps(request('HOLD',30,true),15000);
 assert.strictEqual(o.state,'HOLD_READBACK_MISMATCH');
 assert.strictEqual(o.ready,false);
 assert.strictEqual(o.acceptedValveConfirmed,false);
 assert.strictEqual(valveWrites(r).length,count);
});
check('HOLD invalidates itself on time discontinuity without valve writes',function(){
 var r=rig();open(r);var count=valveWrites(r).length;
 var o=r.steps(request('HOLD',30,true),40000);
 assert.strictEqual(o.state,'HOLD_UNQUALIFIED');
 assert.strictEqual(o.ready,false);assert.strictEqual(valveWrites(r).length,count);
});
check('HOLD pump failure does not send hidden Switch OFF',function(){
 var r=rig();open(r);
 r.errors[cfg.pump]=true;var count=valveWrites(r).length;
 var o=r.steps(request('HOLD',30,true),15000);
 assert.strictEqual(o.state,'PUMP_WRITE_ERROR');
 assert.strictEqual(o.ready,false);assert.strictEqual(valveWrites(r).length,count);
});
check('unknown action rejected rather than treated as OFF',function(){
 var r=rig();assert.throws(function(){
   r.steps(request('BAD',0,true),5000);
 },/Unknown valveAction/);
 assert.strictEqual(r.writes.length,0);
});
check('explicit APPLY without action preserves old writer behavior',function(){
 var r=rig();r.steps({valve:30,pump:true},5000);
 var o=r.steps({valve:30,pump:true},10000);
 assert.strictEqual(o.state,'HEAT_COMMANDED');assert.strictEqual(o.ready,true);
});
check('legacy close uses Switch OFF without touching retained Level',function(){
 var r=rig();open(r);var level=r.data[cfg.level];
 var o=r.steps(request('APPLY',0,false),15000);
 assert.strictEqual(o.state,'OFF_COMMANDED');
 assert.strictEqual(r.data[cfg.level],level);
 assert.strictEqual(r.data[cfg.enable],0);
});
check('NO_COMMAND retains known accepted output evidence without writes',function(){
 var r=rig();open(r);var n=r.writes.length;
 var a=r.steps(request('NO_COMMAND',null,true),15000);
 assert.strictEqual(a.ready,false);
 assert.strictEqual(a.acceptedValveConfirmed,true);
 assert.strictEqual(a.acceptedValvePct,30);
 assert.strictEqual(r.writes.length,n);
 r.data[cfg.level]=40;r.seq[cfg.level]++;
 var b=r.steps(request('NO_COMMAND',null,true),20000);
 assert.strictEqual(b.acceptedValveConfirmed,false);
 assert.strictEqual(b.acceptedValvePct,null);
});
check('NO_COMMAND then HOLD resumes last qualified position without close',function(){
 var r=rig();open(r);var n=valveWrites(r).length;
 var a=r.steps(request('NO_COMMAND',null,true),15000);
 assert.strictEqual(a.state,'OUTPUT_NO_COMMAND');assert.strictEqual(a.ready,false);
 var b=r.steps(request('HOLD',30,true),20000);
 assert.strictEqual(b.state,'HEAT_HELD');assert.strictEqual(b.ready,true);
 assert.strictEqual(b.acceptedValvePct,30);
 assert.strictEqual(valveWrites(r).length,n);
});
check('NO_COMMAND after qualified state never changes Switch',function(){
 var r=rig();open(r);
 var before=r.data[cfg.enable],n=valveWrites(r).length;
 r.steps(request('NO_COMMAND',null,false),15000);
 assert.strictEqual(r.data[cfg.enable],before);
 assert.strictEqual(valveWrites(r).length,n);
});
console.log('TOTAL PASS '+pass);