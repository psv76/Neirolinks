/* 05 16 Iset: NO living actuators and K4 pump intent planner.
 * Computes commands; NEVER touches devices. HM2 remains live owner.
 * NO 0/false=OPEN, 1/true=CLOSE. Pump K4 true=ON.
 * Under unknown room demand, retain that zone's present command.
 * Avoid closing the final water path while the pump is observed ON.
 */
function name(s){return typeof s==='string'&&s.length>0;}
function time(n){return typeof n==='number'&&isFinite(n)&&n>=0;}
function relay(x){
    if(x===0||x===false)return false;
    if(x===1||x===true)return true;
    return null;
}
exports.create=function(c){
    if(!c||!c.map||!c.map.zones||!c.map.zones.length||
       !name(c.map.pump)||!time(c.openWaitMs)||c.openWaitMs<=0||
       !c.map.actuators||c.map.actuators.type!=='NO'||
       c.map.actuators.openCommand!==0||c.map.actuators.closeCommand!==1)
        throw new Error('Iset outputs: explicit as-built NO map required');
    var paths={},zones={},z,p,i,j;
    for(i=0;i<c.map.zones.length;i++){
        z=c.map.zones[i];
        if(!z||!name(z.id)||zones[z.id]||!z.outputs||!z.outputs.length)
            throw new Error('Iset outputs: invalid/duplicate room');
        zones[z.id]=z;
        for(j=0;j<z.outputs.length;j++){
            p=z.outputs[j];
            if(!name(p)||paths[p]||p===c.map.pump)
                throw new Error('Iset outputs: duplicate/unsafe physical path');
            paths[p]=true;
        }
    }
    var epoch=null,lastNow=null,openAt={};
    return {
        plan:function(f){
            if(!f||!time(f.nowMs)||!name(f.bootEpoch)||!f.demands||
               !f.readbacks||typeof f.protectionActive!=='boolean')
                throw new Error('Iset outputs: explicit current frame required');
            if(epoch!==f.bootEpoch||lastNow!==null&&f.nowMs<lastNow){
                epoch=f.bootEpoch;openAt={};
            }
            lastNow=f.nowMs;
            var actions=[],states={},requesting=0,unknown=0,off=0,ready=0;
            var pumpActual=relay(f.readbacks[c.map.pump]);
            // Build all-zone readback state before deciding which valve
            // may close while the common pump is still running.
            for(i=0;i<c.map.zones.length;i++){
                z=c.map.zones[i];
                var demand=f.demands[z.id],qualified=demand===true;
                if(demand!==true&&demand!==false&&demand!==null)
                    throw new Error('Iset outputs: invalid three-state demand '+z.id);
                if(demand===true)requesting++;
                else if(demand===false)off++;
                else unknown++;
                for(j=0;j<z.outputs.length;j++){
                    p=z.outputs[j];
                    var actual=relay(f.readbacks[p]);
                    if(actual===false){
                        if(openAt[p]===undefined)openAt[p]=f.nowMs;
                    }else openAt[p]=undefined;
                    if(actual!==false||openAt[p]===undefined||
                       f.nowMs-openAt[p]<c.openWaitMs)qualified=false;
                }
                if(qualified)ready++;
                states[z.id]={demand:demand,openReady:qualified,
                    state:demand===null?'UNKNOWN':
                        demand===false?'OFF':qualified?'READY':'OPENING'};
            }
            // Equipment protection, unlike sensor uncertainty, may ask
            // this unique pump owner to STOP immediately.
            var allOff=off===c.map.zones.length;
            var pumpAction='HOLD';
            if(f.protectionActive||allOff){
                if(pumpActual!==false)pumpAction='STOP';
            }else if(ready>0&&pumpActual!==true){
                pumpAction='START';
            }
            // Phase 0: remove pump power before commanding last NO CLOSE.
            if(pumpAction==='STOP')
                actions.push({path:c.map.pump,value:false,action:'PUMP_STOP',
                    reason:f.protectionActive?'EQUIPMENT_PROTECTION':'ALL_ROOMS_OFF'});
            // Phase 1: request valve OPEN; no global room dependency.
            if(!f.protectionActive){
                for(i=0;i<c.map.zones.length;i++){
                    z=c.map.zones[i];
                    if(f.demands[z.id]!==true)continue;
                    for(j=0;j<z.outputs.length;j++){
                        p=z.outputs[j];
                        if(relay(f.readbacks[p])!==false)
                            actions.push({path:p,value:false,action:'ZONE_OPEN',
                                zoneId:z.id,reason:'ROOM_HEAT_DEMAND'});
                    }
                }
            }
            // Phase 2: close only explicit OFF zones, only if pump is
            // observed stopped OR another requested zone has an open path.
            // If changing rooms, leave old one open until new one is ready.
            var canClose=pumpActual===false||ready>0;
            if(!f.protectionActive&&canClose){
                for(i=0;i<c.map.zones.length;i++){
                    z=c.map.zones[i];
                    if(f.demands[z.id]!==false)continue;
                    for(j=0;j<z.outputs.length;j++){
                        p=z.outputs[j];
                        if(relay(f.readbacks[p])!==true)
                            actions.push({path:p,value:true,action:'ZONE_CLOSE',
                                zoneId:z.id,reason:'ROOM_NO_DEMAND'});
                    }
                }
            }
            // Phase 3: K4 can start only with a requested, sufficiently
            // long OPEN/readback-qualified loop. Not a flow sensor.
            if(pumpAction==='START')
                actions.push({path:c.map.pump,value:true,action:'PUMP_START',
                    reason:'REQUESTED_ZONE_OPEN_WAIT_COMPLETE'});
            return {state:'PLANNED_ONLY',actions:actions,zones:states,
                requestingZones:requesting,unknownZones:unknown,
                readyZones:ready,pumpReadback:pumpActual,
                pumpAction:pumpAction,allExplicitlyOff:allOff,
                closureDeferred:!canClose&&off>0&&
                    !f.protectionActive};
        },
        snapshot:function(){return {bootEpoch:epoch,lastNowMs:lastNow};}
    };
};
