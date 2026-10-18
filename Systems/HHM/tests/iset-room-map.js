/* Offline as-built safety gate for Iset room thermostat conversion. */
var assert=require('assert');
var map=require('../../../Objects/05_16_Iset/HHM/room_zones');
var count=0;
function check(n,f){f();count++;console.log('PASS '+n);}
check('object map has confirmed eight rooms',function(){
    assert.strictEqual(map.objectId,'05_16_Iset');
    assert.strictEqual(map.zones.length,8);
});
check('eleven NO physical outputs are mapped uniquely',function(){
    var seen={},i,j,z,n=0;
    for(i=0;i<map.zones.length;i++){
        z=map.zones[i];
        for(j=0;j<z.outputs.length;j++){
            var p=z.outputs[j];
            assert.ok(/^wb-mio-gpio_195:2\/K(1[01]?|[1-9])$/.test(p),p);
            assert.strictEqual(seen[p],undefined,p);
            seen[p]=true;n++;
        }
    }
    assert.strictEqual(n,11);
    assert.strictEqual(map.actuators.type,'NO');
    assert.strictEqual(map.actuators.openCommand,0);
    assert.strictEqual(map.actuators.closeCommand,1);
});
check('living K4 pump differs from zone K4 actuator',function(){
    assert.strictEqual(map.pump,'wb-mr6cu_37/K4');
    assert.ok(map.zones.some(function(z){
        return z.outputs.indexOf('wb-mio-gpio_195:2/K4')!==-1;
    }));
});
check('seven direct WB temperature sensors match live climate dashboard',function(){
    var known={office:22,summer_kitchen:53,corridor:52,
        master_bathroom:54,living_kitchen:116,entrance:43,
        guest_bathroom:106};
    assert.strictEqual(map.roomSensorAudit.wbSerial,'AFMEUYOT');
    assert.strictEqual(map.roomSensorAudit.haClimateMappingsVerified,false);
    var verified=0;
    map.zones.forEach(function(z){
        assert.strictEqual(z.approvedSetpoint,null);
        if(Object.prototype.hasOwnProperty.call(known,z.id)){
            assert.strictEqual(z.primarySensor,
                'wb-msw-v4_'+known[z.id]+'/Temperature');
            assert.strictEqual(z.primaryEvidence,'WB_WEBUI_AND_LIVE_MQTT');
            verified++;
        }else assert.strictEqual(z.primarySensor,null);
    });
    assert.strictEqual(verified,7);
});
check('master bedroom wardrobe 47 remains a candidate, not invented primary',function(){
    var z=map.zones.filter(function(z){return z.id==='master_bedroom';})[0];
    assert.strictEqual(z.primarySensor,null);
    assert.strictEqual(z.candidateSensor,'wb-msw-v4_47/Temperature');
    assert.strictEqual(z.secondaryCandidateInvalidObserved,0);
});
check('commissioning blocked until all room sensor/setpoints approved',function(){
    assert.strictEqual(map.commissioned,false);
    assert.throws(function(){map.assertCommissionable();},/not commissioned/);
    map.commissioned=true;
    try{assert.throws(function(){map.assertCommissionable();},
        /unverified zone\/sensor\/setpoint/);}
    finally{map.commissioned=false;}
});
check('old HA demand topics are evidence, never thermostat sensors',function(){
    map.zones.forEach(function(z){
        assert.strictEqual(z.oldDemand,'ha_heating_air/'+z.id+'_demand');
    });
});
check('fake commissioning flag alone does not bypass missing sensors',function(){
    map.commissioned=true;
    try{assert.throws(function(){map.assertCommissionable();},
        /unverified zone\/sensor\/setpoint/);}
    finally{map.commissioned=false;}
});
console.log('TOTAL PASS '+count);
