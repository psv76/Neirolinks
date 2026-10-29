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
    assert.strictEqual(map.pump,'wb-mr6cu_12/K4');
    assert.ok(map.zones.some(function(z){
        return z.outputs.indexOf('wb-mio-gpio_195:2/K4')!==-1;
    }));
});
check('all eight historic HA sensors match live WB sensor addresses',function(){
    var expected={
        office:[22,'sensor.temperatura_kabinet','climate.kabinet'],
        summer_kitchen:[53,'sensor.temperatura_letniaia_kukhnia','climate.letniaia_kukhnia'],
        corridor:[52,'sensor.temperatura_koridor_2_etazh','climate.koridor'],
        master_bathroom:[54,'sensor.temperatura_sanuzel_master_spalni','climate.master_sanuzel'],
        living_kitchen:[116,'sensor.temperatura_gostinaia_2','climate.gostinaia_kukhnia'],
        entrance:[43,'sensor.temperatura_prikhozhaia_2','climate.prikhozhaia'],
        guest_bathroom:[106,'sensor.temperatura_sanuzel_gostevoi','climate.gostevoi_sanuzel'],
        master_bedroom:[47,'sensor.temperatura_garderob_2','climate.master_spalnia']
    };
    assert.strictEqual(map.roomSensorAudit.wbSerial,'AFMEUYOT');
    assert.strictEqual(map.roomSensorAudit.haHistoricalMappingDocumented,true);
    assert.strictEqual(map.roomSensorAudit.haClimateMappingsVerified,false);
    var verified=0;
    map.zones.forEach(function(z){
        var x=expected[z.id];
        assert.ok(x,'Unexpected zone '+z.id);
        assert.strictEqual(z.primarySensor,
            'wb-msw-v4_'+x[0]+'/Temperature');
        assert.strictEqual(z.haSensor,x[1]);
        assert.strictEqual(z.haClimate,x[2]);
        assert.strictEqual(z.approvedSetpoint,null);
        verified++;
    });
    assert.strictEqual(verified,8);
});
check('master bedroom wardrobe 47 intentionally selected in 07 Sep HA',function(){
    var z=map.zones.filter(function(z){return z.id==='master_bedroom';})[0];
    assert.strictEqual(z.primarySensor,'wb-msw-v4_47/Temperature');
    assert.strictEqual(z.haSensor,'sensor.temperatura_garderob_2');
    assert.ok(z.primaryLocation.indexOf('Гардероб')!==-1);
    assert.strictEqual(z.alternateSensorObservedInvalid,0);
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
