'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {create}=require('./harness');

// Real 21.09.2026 pre-fix WB virtual-device snapshot: 18 existing ON and new 505 OFF.
const snapshot={
    '601':[true,25],'602':[true,25],'603':[true,25],
    '005':[true,20],'006':[true,20],'007':[true,20],
    '008':[true,20],'009':[true,20],'010':[true,20],
    '606':[true,25],'607':[true,25],'608':[true,20],
    '609':[true,25],'610':[true,20],'611':[true,25],
    '612':[true,25],'613':[true,25],'614':[true,20],
    '505':[false,20]
};
const values={};
for(const [id,[state,target]] of Object.entries(snapshot)){
    const prefix='NL_simple_thermostat_'+id+'/';
    values[prefix+'target_state']=state;
    values[prefix+'target_temperature']=target;
}

const h=create({values:{boiler:values}});
assert.equal(h.Z.length,19,'expected exactly the 19 Ivolga thermostats');
assert.equal(h.physical().length,0,'no physical writes before commissioning');
assert.equal(h.stores.hhm3_operation.inService,undefined,'do not commission automatically');
for(const [id,[state,target]] of Object.entries(snapshot)){
    const entry=h.stores.hhm3_thermostats[id];
    assert.ok(entry,'first load failed to persist zone '+id);
    assert.equal(entry.state,state?1:0,'state mismatch for '+id);
    assert.equal(entry.target,target,'setpoint mismatch for '+id);
}
// The test must reproduce the exact WB restriction which the old harness missed.
assert.throws(()=>vm.runInContext(
    "new PersistentStorage('hhm3_thermostats',{global:true}).INVALID={state:1,target:25};",
    h.contexts['620']),/don't write pure objects to PersistentStorage/);

const prior=h.stores.hhm3_thermostats['601'];
h.samples();h.advance(15000);
assert.equal(h.stores.hhm3_thermostats['601'],prior,'unchanged settings must not be replaced every cycle');
assert.equal(h.physical().length,0,'no physical writes during first commissioning');

h.set('boiler','NL_simple_thermostat_601/target_state',false);
h.set('boiler','NL_simple_thermostat_601/target_temperature',23);
h.tick('620');
assert.equal(h.stores.hhm3_thermostats['601'].state,0,'explicit OFF not saved');
assert.equal(h.stores.hhm3_thermostats['601'].target,23,'new target not saved');
assert.equal(h.stores.hhm3_thermostats['505'].state,0,'505 must remain OFF');

// Simulate loss of all virtual-device controls: PersistentStorage must restore settings.
const restart=create({stores:h.stores,values:{boiler:{}}});
assert.equal(restart.physical().length,0,'restart without commissioning must not write outputs');
assert.equal(restart.values.boiler['NL_simple_thermostat_601/target_state'],false);
assert.equal(restart.values.boiler['NL_simple_thermostat_601/target_temperature'],23);
assert.equal(restart.values.boiler['NL_simple_thermostat_505/target_state'],false);
assert.equal(restart.values.boiler['NL_simple_thermostat_505/target_temperature'],20);
for(const [id,[state,target]] of Object.entries(snapshot)){
    if(id==='601')continue;
    const base='NL_simple_thermostat_'+id+'/';
    assert.equal(restart.values.boiler[base+'target_state'],state,'restart state '+id);
    assert.equal(restart.values.boiler[base+'target_temperature'],target,'restart target '+id);
}
console.log('PASS WB PersistentStorage rejects plain objects; snapshot 18+505, first-load, no-write, OFF, restart');
