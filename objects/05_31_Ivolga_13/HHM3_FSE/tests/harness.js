'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),epoch=1800000000000;
exports.create=function(options={}){
    let now=epoch,owner='',failPath='',bridge=true;
    const stores=options.stores||{},values={boiler:Object.assign({},options.values&&options.values.boiler),gazebo:Object.assign({},options.values&&options.values.gazebo)};
    const handlers={boiler:{},gazebo:{}},modules={},contexts={},writes=[],messages=[],rules={boiler:{},gazebo:{}},definitions={};
    function load(n){
        if(modules[n])return modules[n];
        const e={};modules[n]=e;
        vm.runInNewContext(fs.readFileSync(path.join(root,'modules',n+'.js'),'utf8'),{exports:e,require:load},{filename:n});
        return e;
    }
    const C=load('HHM3Config').config,Z=load('HHM3Config').zones;
    if(options.configure)options.configure(C);
    const own={};
    Z.forEach(z=>z.outputs.forEach(p=>own[p]='620'));
    Object.values(C.circuits).forEach(c=>{own[c.pump]='500';if(c.level){own[c.level]='500';own[c.enable]='500';}});
    own[C.source.setpoint]=own[C.source.chEnable]='500';
    function deliver(board,topic,value,retained=false){
        const m={topic,value:String(value),qos:0};if(retained!==undefined)m.retained=retained;
        for(const h of handlers[board][topic]||[]){const saved=owner;owner=h.owner;try{h.fn(m);}finally{owner=saved;}}
    }
    function publish(board,topic,payload,qos,retained){
        messages.push({board,topic,payload,retained,owner,at:now});
        deliver(board,topic,payload,retained);
        if(board==='gazebo'&&topic==='/neiro/ivolga/504/v2/frame'&&bridge)deliver('boiler',topic,payload,retained);
    }
    function topic(p){const i=p.indexOf('/');return '/devices/'+p.slice(0,i)+'/controls/'+p.slice(i+1);}
    function runtime(board,name,file){
        const saved=owner;owner=name;
        class Clock extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
        const dev=new Proxy(values[board],{set(o,k,v){
            const isPhysical=!!own[k]||/^(A\d+\/|wbe2-i-opentherm_11\/)/.test(k);
            if(isPhysical){assert.equal(board,'boiler');assert.equal(own[k],owner,'writer '+owner+' -> '+k);}
            else assert.ok((owner==='620'&&k.startsWith('NL_simple_thermostat_'))||(owner==='624'&&k.startsWith('NL_combo_thermostat_504/'))||(owner==='500'&&k.startsWith('HHM3_FSE/')),'unknown VD writer '+owner+' '+k);
            assert.notEqual(v,null);assert.notEqual(v,undefined);if(typeof v==='number')assert.ok(Number.isFinite(v));
            writes.push({owner,path:k,value:v,at:now,board});
            if(k===failPath)throw new Error('simulated IO failure');
            o[k]=v;if(isPhysical)deliver(board,topic(k),v===true?1:v===false?0:v,false);
            return true;
        }});
        const context=vm.createContext({dev,Date:Clock,require:load,log:()=>{},
            PersistentStorage:function(n){return stores[n]||(stores[n]={});},
            defineVirtualDevice:(id,d)=>{definitions[id]=d;Object.entries(d.cells).forEach(([k,c])=>{if(c.forceDefault||values[board][id+'/'+k]===undefined)values[board][id+'/'+k]=c.value;});},
            defineRule:(key,r)=>{rules[board][key]={owner:name,...r};},
            trackMqtt:(t,fn)=>{(handlers[board][t]||(handlers[board][t]=[])).push({owner:name,fn});},
            publish:(...a)=>publish(board,...a),setInterval:()=>1,setTimeout:()=>1});
        context.log.info=context.log.warning=context.log.error=context.log;
        vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context,{filename:file});
        contexts[name]=context;owner=saved;
    }
    runtime('boiler','500','boiler/wb-rules/500_HHM3_FSE.js');
    runtime('boiler','620','boiler/wb-rules/620_thermostats.js');
    runtime('gazebo','624','gazebo/wb-rules/624_combo_besedka.js');
    function tick(id){const saved=owner;owner=id;try{contexts[id].evaluate();}finally{owner=saved;}}
    function rule(board,name,value){const r=rules[board][name],saved=owner;owner=r.owner;try{r.then(value);}finally{owner=saved;}}
    const temperatures={};
    Object.values(C.circuits).forEach(c=>{temperatures[c.supply]=25;temperatures[c.ret]=23;});
    temperatures[C.source.temperature]=50;temperatures[C.source.connection]=0;temperatures[C.source.fault]=0;
    Z.forEach(z=>temperatures[z.sensor]=z.kind==='floor'?20:18);
    const gazeboTemperatures={'921.09_MSW_TH/Temperature':20,'921.10_TEMP_NONE/External Sensor 1':23};
    function samples(){for(const [p,v]of Object.entries(temperatures))if(v!==undefined)deliver('boiler',topic(p),v,false);
        for(const[p,v]of Object.entries(gazeboTemperatures))if(v!==undefined)deliver('gazebo',topic(p),v,false);}
    return {C,Z,stores,values,definitions,writes,messages,contexts,load,temperatures,gazeboTemperatures,topic,
        now:()=>now,time:t=>now=t,tick,rule,deliver,samples,
        start:()=>rule('boiler','hhm3_first_start',true),
        set:(board,p,v)=>{values[board][p]=v;},
        enableAll:()=>Z.forEach(z=>values.boiler['NL_simple_thermostat_'+z.id+'/target_state']=true),
        advance:(ms,feed=true)=>{for(let t=0;t<ms;t+=5000){now+=5000;if(feed)samples();tick('620');tick('624');tick('500');}},
        fail:p=>failPath=p,bridge:v=>bridge=v,
        report:()=>JSON.parse(values.boiler['HHM3_FSE/circuits_json']),
        source:()=>JSON.parse(values.boiler['HHM3_FSE/source_json']),
        physical:()=>writes.filter(w=>own[w.path]),
        request:()=>values.boiler['HHM3_FSE/requested_source_temperature']
    };
};
exports.epoch=epoch;exports.root=root;
