// Offline only. Verify canonical Git LF bytes; --write regenerates the review manifest.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const repo = path.resolve(__dirname, '../../..');
const base = 'objects/05_31_Ivolga_13/';
const files = [
    base+'Besedka/wb-rules/624_combo_besedka.js',
    base+'Besedka/mosquitto/504-bridge.conf.example',
    base+'Besedka/mosquitto/504-acl.example',
    base+'Wirenboard/wb-rules-modules/HM2504.js',
    base+'Wirenboard/wb-rules-modules/HM2504Config.js',
    base+'Wirenboard/wb-rules-modules/HM2504Control.js',
    base+'Wirenboard/wb-rules/504_gp_besedka_manager.js',
    base+'Wirenboard/wb-rules/HM2_arbiter_request.js',
    base+'Wirenboard/wb-rules/HM2_source_manager.js',
    base+'Sprut/Templates/NL_combo_thermostat.json',
    'Templates/WB-rules/Heating/HM2/MixingController/MixingController.js'
];
const manifest = path.join(__dirname, 'hm2_504.sha256');
const expected = files.map(f => crypto.createHash('sha256').update(
    fs.readFileSync(path.join(repo,f),'utf8').replace(/\r\n/g,'\n')).digest('hex')+'  '+f).join('\n')+'\n';
if (process.argv.length === 3 && process.argv[2] === '--write') fs.writeFileSync(manifest,expected);
else {
    if (process.argv.length !== 2) throw new Error('Usage: node verify_hm2_504_manifest.js [--write]');
    if (fs.readFileSync(manifest,'utf8').replace(/\r\n/g,'\n') !== expected) throw new Error('504 manifest mismatch');
}
console.log('504 manifest: '+files.length+' reviewed files OK (canonical LF)');
