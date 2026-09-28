'use strict';
const assert=require('node:assert/strict'),Outputs=require('../modules/HHM3Outputs');
function fixture(autoOn=false){
 const c={periodMs:5000,commandTimeoutMs:10000,commandRetryMs:5000,valveActiveMinLevel:1,valveActiveMaxLevel:100,valveOffCommand:false,level:'level',enable:'switch',pump:'pump'};
 let now=100000,drop=false;const values={},seq={},writes=[],stale={};
 function emit(p,v){values[p]=v;seq[p]=(seq[p]||0)+1;stale[p]=false;}
 const io={read:p=>stale[p]?null:(values[p]===undefined?null:values[p]),matches:(p,v)=>io.read(p)===Number(v),
  readback:p=>({value:io.read(p),seq:seq[p]||0,at:stale[p]?null:now}),
  write:(p,v)=>{writes.push({p,v});if(!drop){emit(p,Number(v));if(p==='level'&&autoOn)emit('switch',1);}return {ok:true};}};
 const step=Outputs.create(c,io);
 return {values,writes,emit,drop:v=>drop=v,expire:(...p)=>p.forEach(x=>stale[x]=true),run:(valve=0,pump=false,dt=5000)=>step({valve,pump},now+=dt)};
}
for(const autoOn of [false,true]){
 const f=fixture(autoOn);f.run();f.run(19.1919191919,true); // отображаемый Level 20
 assert.equal(f.values.level,20);assert.equal(f.values.switch,1);
 const n=f.writes.length;f.run();assert.equal(f.values.level,20);assert.equal(f.values.switch,0);
 assert.equal(f.writes.slice(n).some(w=>w.p==='level'),false);
 const k=f.writes.length,r=f.run(29.29292929,true);
 assert.equal(r.ready,true);assert.equal(f.values.level,30);assert.equal(f.values.switch,1);
 const writes=f.writes.slice(k),li=writes.findIndex(w=>w.p==='level'),si=writes.findIndex(w=>w.p==='switch');
 assert.ok(li>=0);if(autoOn)assert.equal(si,-1);else assert.ok(si>li);
 console.log('PASS 20/ON → 20/OFF → новая цель 30, AUTO-ON='+autoOn);
}
{
 const f=fixture();f.run();f.run(40,true);f.run(0,true);
 f.emit('switch',1);f.drop(true);const n=f.writes.length;
 let r=f.run(0,true);assert.equal(r.ready,false);
 f.run(0,true);r=f.run(0,true);
 assert.equal(r.state,'CLOSURE_UNCERTAIN');assert.equal(r.pump,false);
 assert.equal(f.writes.slice(n).filter(w=>w.p==='switch'&&w.v===false).length,2);
 for(let i=0;i<10;i++)assert.equal(f.run(0,true).ready,false);
 assert.equal(f.writes.slice(n).filter(w=>w.p==='switch'&&w.v===false).length,2);
 assert.equal(f.writes.slice(n).some(w=>w.p==='level'),false);
 f.drop(false);f.emit('switch',0);assert.equal(f.run(0,false).fault,'');
 console.log('PASS свежий ON после OFF: два повтора, конечная ошибка, насос OFF, восстановление');
}
{
 const f=fixture();f.run();f.drop(true);let r=f.run(40,true);
 assert.equal(r.ready,false);assert.equal(r.pump,false);
 f.emit('level',41);r=f.run(40,true);assert.equal(r.ready,false);
 f.emit('switch',1);f.drop(false);r=f.run(40,true);assert.equal(r.ready,true);
 console.log('PASS готовность только после обоих свежих атрибутов');
}
{
 const f=fixture();f.run();let r=f.run(40,true);assert.equal(r.ready,true);const n=f.writes.length;
 f.expire('level','switch');
 for(let i=0;i<5;i++){r=f.run(40,true);assert.equal(r.ready,true);assert.equal(r.pump,true);assert.equal(r.state,'HEAT_COMMANDED');}
 assert.equal(f.writes.slice(n).some(w=>w.p==='pump'&&w.v===false),false);
 assert.equal(f.writes.slice(n).some(w=>w.p==='switch'&&w.v===false),false);
 console.log('PASS steady HEAT не теряет READY из-за TTL без нового A05 readback');
}
{
 const f=fixture();f.run();f.run(40,true);let r=f.run(0,true);assert.equal(r.ready,true);const n=f.writes.length;
 f.expire('switch');
 for(let i=0;i<4;i++){r=f.run(0,true);assert.equal(r.ready,true);assert.equal(r.pump,true);}
 assert.equal(f.writes.slice(n).some(w=>w.p==='pump'&&w.v===false),false);
 assert.equal(f.writes.slice(n).some(w=>w.p==='switch'&&w.v===false),false);
 console.log('PASS подтверждённый OFF не теряется из-за TTL без нового A05 readback');
}
