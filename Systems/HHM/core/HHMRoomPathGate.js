/* HHM room path permission: local NO actuator timing / readback gate.
 * Pure ES5 decision code. Produces no pump/actuator writes.
 * Readback and time delay are logical permission, NOT proof of water flow.
 */
function finite(n){return typeof n==='number'&&isFinite(n);}
function name(s){return typeof s==='string'&&s.length>0;}
exports.create=function(config){
    if(!config||!finite(config.openWaitMs)||config.openWaitMs<=0||
       !config.zones||!config.zones.length||
       config.openCommand!==0||config.closeCommand!==1)
        throw new Error('Room path: missing approved NO actuator contract');
    var map={},paths={},i,j,z,p;
    for(i=0;i<config.zones.length;i++){
        z=config.zones[i];
        if(!z||!name(z.id)||map[z.id]||!z.outputs||!z.outputs.length)
            throw new Error('Room path: duplicate/invalid zone');
        map[z.id]=z;
        for(j=0;j<z.outputs.length;j++){
            p=z.outputs[j];
            if(!name(p)||paths[p])
                throw new Error('Room path: duplicate/invalid output');
            paths[p]=true;
        }
    }
    return {
        step:function(frame){
            if(!frame||!finite(frame.nowMs)||frame.nowMs<0||
               !name(frame.bootEpoch)||
               !frame.demands||!frame.outputs||
               typeof frame.protectionActive!=='boolean')
                throw new Error('Room path: explicit readback/safety frame required');
            var actions=[],states={},readyCount=0,needsHeat=0,
                unknownCount=0,offCount=0,missing=0;
            for(i=0;i<config.zones.length;i++){
                z=config.zones[i];
                var demand=frame.demands[z.id];
                if(demand!==true&&demand!==false&&demand!==null)
                    throw new Error('Room path: three-state demand required: '+z.id);
                // A separate physical protection owns the safe action;
                // this planner must not propose opening against it.
                var action=frame.protectionActive?'HOLD':
                    (demand===true?'OPEN':(demand===false?'CLOSE':'HOLD'));
                if(demand===true)needsHeat++;
                else if(demand===false)offCount++;
                else unknownCount++;
                var qualified=demand===true&&frame.protectionActive===false;
                var reasons=[];
                for(j=0;j<z.outputs.length;j++){
                    p=z.outputs[j];
                    actions.push({zoneId:z.id,path:p,action:action,
                        desiredOutput:action==='OPEN'?0:action==='CLOSE'?1:null});
                    if(demand===true){
                        var rb=frame.outputs[p];
                        if(!rb||rb.valid!==true||rb.value!==0||
                           rb.bootEpoch!==frame.bootEpoch||
                           !finite(rb.acceptedOpenAtMs)||rb.acceptedOpenAtMs<0||
                           rb.acceptedOpenAtMs>frame.nowMs ||
                           frame.nowMs-rb.acceptedOpenAtMs<config.openWaitMs){
                            qualified=false;
                            reasons.push(p+':OPEN_NOT_QUALIFIED');
                            missing++;
                        }
                    }
                }
                if(qualified)readyCount++;
                states[z.id]={action:action,heatDemand:demand,
                    pathReady:qualified,
                    reason:frame.protectionActive?'PHYSICAL_PROTECTION':
                        demand===null?'UNKNOWN_DEMAND_HOLD':
                        demand===false?'NO_DEMAND':
                        qualified?'OPEN_PATH_QUALIFIED':
                        'WAIT_OPEN_AND_READBACK',
                    evidence:reasons};
            }
            // This module only grants pump START in a verified path.
            // It never commands OFF: postrun/deadhead/frost policy belongs
            // to the unique physical pump writer and independent protections.
            var pumpState=frame.protectionActive?'PROTECTION':
                readyCount>0?'START_PERMITTED':
                needsHeat>0?'WAIT_READY_PATH':
                unknownCount>0?'UNKNOWN_DEMAND_NO_START':'ALL_OFF';
            return {pumpState:pumpState,pumpStartPermitted:readyCount>0&&
                frame.protectionActive===false,
                allExplicitlyOff:offCount===config.zones.length,
                anyDemandUnknown:unknownCount>0,readyZones:readyCount,
                requestingZones:needsHeat,unqualifiedOutputs:missing,
                zones:states,actuatorActions:actions};
        }
    };
};
