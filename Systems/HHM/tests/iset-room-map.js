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
check('commissioning is blocked with unverified room temperatures',function(){
    assert.strictEqual(map.commissioned,false);
    assert.throws(function(){map.assertCommissionable();},/not commissioned/);
    for(var i=0;i<map.zones.length;i++){
        assert.strictEqual(map.zones[i].primarySensor,null);
        assert.strictEqual(map.zones[i].approvedSetpoint,null);
    }
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
