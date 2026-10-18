/* #204 installation dependency closure; does not install to live WB. */
var assert=require('assert'),fs=require('fs'),path=require('path');
var root=path.resolve(__dirname,'../../..');
var manifest=JSON.parse(fs.readFileSync(path.join(root,
    'Objects/05_16_Iset/HHM/wb_install_map.json'),'utf8'));
var source=fs.readFileSync(path.join(root,manifest.main.source),'utf8');
var n=0;function check(x,f){f();n++;console.log('PASS '+x);}
check('source archive has one staged WB entrypoint and 15 alias modules',function(){
    assert.strictEqual(manifest.status,'DRAFT_NEVER_DEPLOYED');
    assert.strictEqual(manifest.modules.length,15);
    assert.strictEqual(manifest.main.target,'/etc/wb-rules/29_hhm_iset.js');
});
check('all requires of the live entrypoint are mapped exactly once',function(){
    var actual=[],re=/require\("([^"]+)"\)/g,m;
    while((m=re.exec(source))!==null)actual.push(m[1]);
    var mapped=manifest.modules.map(function(x){return x.require;});
    assert.deepStrictEqual(actual.slice().sort(),mapped.slice().sort());
});
check('all alias modules have existing repository files and WB module targets',function(){
    var seen={};manifest.modules.forEach(function(x){
        assert.strictEqual(seen[x.require],undefined,x.require);
        seen[x.require]=true;
        assert.strictEqual(x.target,'/etc/wb-rules-modules/'+x.require+'.js');
        assert.ok(fs.existsSync(path.join(root,x.source)),x.source);
    });
});
check('no old experimental sensor-health dependency shipped',function(){
    manifest.modules.forEach(function(x){
        assert.ok(!/Evidence|SensorHealth|SerialLoad/.test(x.require),x.require);
    });
});
check('installed script is disabled for real physical writes in Draft',function(){
    assert.ok(source.indexOf('var HHM_PHYSICAL_OUTPUTS=false;')>=0);
});
check('HM2 20–27 and duplicate diagnostic script are retirement targets',function(){
    assert.strictEqual(manifest.disable_legacy.length,9);
    assert.ok(manifest.disable_legacy.some(function(x){
        return x.endsWith('/28_hhm_rooms_shadow.js');
    }));
    assert.ok(manifest.disable_legacy.every(function(x){
        return /^\/etc\/wb-rules\//.test(x);
    }));
});
check('staging list never includes third-party preserved scripts',function(){
    var preserve=JSON.parse(fs.readFileSync(path.join(root,
        manifest.preserve_inventory),'utf8'));
    manifest.disable_legacy.forEach(function(p){
        assert.strictEqual(preserve.files.some(function(x){
            return x.target===p;
        }),false,p);
    });
});
console.log('TOTAL PASS '+n);
