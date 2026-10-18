/* #204 offline NST-adoption preservation inventory review. */
var assert=require('assert'),fs=require('fs'),path=require('path');
var dir=path.resolve(__dirname,'../../../Objects/05_16_Iset/HHM');
var m=JSON.parse(fs.readFileSync(path.join(dir,'nst_preserve_inventory.json'),'utf8'));
var done=0;function test(n,f){f();done++;console.log('PASS '+n);}
test('inventory is explicitly not an approved NST registration',function(){
    assert.strictEqual(m.object,'05_16_Iset');
    assert.strictEqual(m.not_live_registration,true);
    assert.strictEqual(m.files.length,16);
});
test('every preserved file is only a complete /etc/wb-rules JS name',function(){
    m.files.forEach(function(f){
        assert.ok(/^\/etc\/wb-rules\/[A-Za-z0-9_-]+\.js$/.test(f.target),f.target);
        assert.ok(/^[0-9a-f]{64}$/.test(f.sha256),f.target);
    });
});
test('no duplicate file target or HM2 20..27 in preserved list',function(){
    var seen={};m.files.forEach(function(f){
        assert.strictEqual(seen[f.target],undefined,f.target);
        seen[f.target]=true;
        assert.ok(!/\/2[0-7]_heating_/.test(f.target));
    });
});
test('nonheating rules remain mandatory preserve candidates',function(){
    ['Light_4.js','Master-Light.js','Vilpe_control_v3.js',
     'House_mode_manager.js','Email_service.js','rules.js'].forEach(function(n){
        var f=m.files.filter(function(x){return x.target.endsWith('/'+n);})[0];
        assert.ok(f,n);assert.strictEqual(f.classification,'PRESERVE');
    });
});
test('possible historic heating observers are RETAIN pending separate review',function(){
    ['Heating_watchdog.js','Floor_performance_monitor.js',
     '30_floor_status_ru.js','Heating_notifications.js'].forEach(function(n){
        var f=m.files.filter(function(x){return x.target.endsWith('/'+n);})[0];
        assert.ok(f,n);assert.strictEqual(f.classification,'REVIEW_RETAIN');
    });
});
test('shared WB helpers are accounted for before NST inventory',function(){
    ['HeatingCommon.js','HeatingConfig.js','WBHelpers.js'].forEach(function(n){
        var f=m.files.filter(function(x){
            return x.target==='/etc/wb-rules-modules/'+n;
        })[0];
        assert.ok(f,n);
        assert.ok(/^[0-9a-f]{64}$/.test(f.sha256),n);
    });
    assert.strictEqual(m.files.filter(function(x){
        return x.target==='/etc/wb-rules-modules/WBHelpers.js';
    })[0].classification,'PRESERVE');
});
console.log('TOTAL PASS '+done);
