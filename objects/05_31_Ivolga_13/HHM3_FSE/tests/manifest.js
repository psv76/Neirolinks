'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
function walk(p){return fs.readdirSync(p,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(p,e.name)):[path.join(p,e.name)]);}
function destination(file){
 if(file.startsWith('modules/')){
  const name=path.basename(file),both=['HHM3Config.js','HHM3Wire.js','HHM3Runtime.js'].includes(name);
  return {boards:both?['boiler','gazebo']:['boiler'],destination:'/etc/wb-rules-modules/'+name,role:'module'};
 }
 if(file.includes('/wb-rules/'))return {boards:[file.split('/')[0]],destination:'/etc/wb-rules/'+path.basename(file),role:'rule'};
 if(file.includes('/mosquitto/'))return {boards:['gazebo','boiler'],role:'broker-template',installation:'Substitute local TLS/identity parameters; merge ACL, see INSTALL.md'};
 if(file.startsWith('ui/'))return {role:'optional-Sprut-template'};
 return {role:file.startsWith('tests/')?'test':'documentation'};
}
const files=walk(root).map(f=>path.relative(root,f).split(path.sep).join('/')).filter(f=>f!=='manifest.json').sort().map(file=>{
 const content=fs.readFileSync(path.join(root,file),'utf8').replace(/\r\n/g,'\n');
 return {file,sha256:sha(content),...destination(file)};
});
const result={release:'HHM 3.1.0',object:'05_31_Ivolga_13',issue:68,encoding:'UTF-8; SHA-256 over LF-normalized text',
 aggregate_sha256:sha(files.map(f=>f.file+'\0'+f.sha256+'\n').join('')),files};
if(process.argv.includes('--check')){
 const saved=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));assert.deepEqual(saved,result);
 const names=new Set(files.filter(f=>f.role==='module').map(f=>path.basename(f.file,'.js')));
 for(const f of files.filter(f=>f.role==='rule'||f.role==='module')){
  const text=fs.readFileSync(path.join(root,f.file),'utf8');
  for(const m of text.matchAll(/require\(['"]([^'"]+)['"]\)/g))assert.ok(names.has(m[1]),'Missing dependency '+m[1]);
 }
 console.log('PASS manifest: '+files.length+' files; SHA-256 '+result.aggregate_sha256);
}else{fs.writeFileSync(path.join(root,'manifest.json'),JSON.stringify(result,null,2)+'\n');console.log(result.aggregate_sha256);}
