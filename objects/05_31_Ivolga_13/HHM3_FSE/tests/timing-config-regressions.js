'use strict';
const assert=require('node:assert/strict');
const C=require('../modules/HHM3Config');
const c=C.config.circuits['502'];
assert.deepEqual(C.timing(c),{zoneActuatorOpenMs:180000,zoneActuatorCloseMs:180000,pumpPostrunMs:120000,collectorHasBypass:false});
for(const pumpPostrunMs of [180000,180001,Infinity,NaN,-1])
 assert.throws(()=>C.timing({...c,pumpPostrunMs}));
for(const key of ['zoneActuatorOpenMs','zoneActuatorCloseMs'])
 for(const value of [-1,Infinity,NaN,'180000'])assert.throws(()=>C.timing({...c,[key]:value}));
assert.throws(()=>C.timing({...c,collectorHasBypass:'false'}));
assert.equal(C.timing({...c,collectorHasBypass:true,pumpPostrunMs:180000}).pumpPostrunMs,180000);
assert.throws(()=>C.timing({...c,collectorHasBypass:true,pumpPostrunMs:Infinity}));
assert.deepEqual(C.timing({zoneDelayMs:180000,postrunMs:120000}),
 {zoneActuatorOpenMs:180000,zoneActuatorCloseMs:180000,pumpPostrunMs:0,collectorHasBypass:false});
assert.equal(C.timing({zoneDelayMs:0,postrunMs:120000}).pumpPostrunMs,120000);
assert.equal(c.zoneDelayMs,c.zoneActuatorOpenMs);
assert.equal(c.postrunMs,c.pumpPostrunMs);
for(const id of ['501','502','503','504'])
 assert.equal(C.config.circuits[id].pumpPostrunMs,120000,id+' должен иметь выбег 120 с');
assert.equal(C.config.circuits['504'].postrunMs,120000);
assert.equal(C.config.circuits['505'].zoneActuatorOpenMs,0);
assert.equal(C.config.circuits['505'].pumpPostrunMs,0,'505 остаётся без выбега до отдельного решения');
console.log('PASS объектные времена, недопустимые значения, миграция и соседние контуры');
