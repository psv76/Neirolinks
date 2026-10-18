/* 05 16 Iset: one shadow-only eight-room evaluation pass.
 * Read WB-MSW values, local settings and explicit per-device errors.
 * Result is diagnostic intentions only. NEVER writes K1..K11 or K4.
 */
function key(s){return typeof s==='string'&&s.length>0;}
function numeric(x){return typeof x==='number'&&isFinite(x);}
exports.create=function(o){
    if(!o||!o.map||!o.map.zones||!o.Simple||
       typeof o.Simple.create!=='function'||!o.Settings||
       typeof o.Settings.create!=='function'||!o.PathGate||
       typeof o.PathGate.create!=='function'||!o.storage)
        throw new Error('Iset rooms: missing explicit dependencies');
    var zones=o.map.zones,all={},stores={},room={},i,z;
    function loadRoom(id){
        var z=all[id],record=stores[id].read();
        if(record===null||record.setpointC<o.minSetpointC||
           record.setpointC>o.maxSetpointC){
            room[id]=null;return false;
        }
        room[id]=o.Simple.create({zoneId:z.id,sensorId:z.primarySensor,
            minSetpointC:o.minSetpointC,maxSetpointC:o.maxSetpointC,
            hysteresisC:o.hysteresisC,minMeasuredC:o.minMeasuredC,
            maxMeasuredC:o.maxMeasuredC},stores[id]);
        return true;
    }
    for(i=0;i<zones.length;i++){
        z=zones[i];
        if(!key(z.id)||all[z.id])throw new Error('Iset rooms: duplicate zone');
        all[z.id]=z;
        stores[z.id]=o.Settings.create(o.storage,z.id);
        // Never invent initial setpoints. Invalid/missing records remain
        // NOT_COMMISSIONED until separately approved & provisioned.
        loadRoom(z.id);
    }
    var path=o.PathGate.create({zones:zones,openCommand:0,
        closeCommand:1,openWaitMs:o.map.actuators.nominalOpenWaitMs});
    return {
        provisionCandidate:function(zoneId,mode,setpointC){
            if(!all[zoneId]||!numeric(setpointC)||
               setpointC<o.minSetpointC||setpointC>o.maxSetpointC)
                return null;
            return stores[zoneId].proposeInitial(mode,setpointC);
        },
        provisionApproved:function(zoneId,mode,setpointC){
            if(!all[zoneId]||!numeric(setpointC)||
               setpointC<o.minSetpointC||setpointC>o.maxSetpointC)
                return {accepted:false,reason:'OUT_OF_RANGE_OR_UNKNOWN_ZONE'};
            if(room[zoneId])
                return {accepted:false,reason:'ALREADY_COMMISSIONED'};
            if(!stores[zoneId].provisionApproved(mode,setpointC))
                return {accepted:false,reason:'PERSISTENCE_FAILED'};
            return {accepted:loadRoom(zoneId),reason:'APPLIED'};
        },
        applySettings:function(zoneId,cmd){
            if(!all[zoneId])return {accepted:false,reason:'UNKNOWN_ZONE'};
            if(!room[zoneId])return {accepted:false,reason:'ROOM_NOT_COMMISSIONED'};
            return room[zoneId].applySettings(cmd);
        },
        settings:function(zoneId){return room[zoneId]?room[zoneId].settings():null;},
        step:function(frame){
            if(!frame||!numeric(frame.nowMs)||frame.nowMs<0||
               !key(frame.bootEpoch)||!frame.temperatures||!frame.sensorErrors||
               !frame.outputReadbacks||
               typeof frame.protectionActive!=='boolean')
                throw new Error('Iset rooms: missing read-only input frame');
            var requests={},states={},x,reading,report;
            for(var k=0;k<zones.length;k++){
                z=zones[k];
                if(!room[z.id]){
                    requests[z.id]=null;
                    states[z.id]={zoneId:z.id,state:'NOT_COMMISSIONED',
                        heatDemand:null,measuredC:null};
                    continue;
                }
                x=frame.temperatures[z.id];
                reading=x===undefined||x===null?null:
                    {id:z.primarySensor,temperatureC:x};
                // A missing error event is NOT a missing heartbeat.
                report=room[z.id].step({reading:reading,
                    sensorError:frame.sensorErrors[z.id]===true});
                states[z.id]=report;
                requests[z.id]=report.heatDemand;
            }
            var plan=path.step({nowMs:frame.nowMs,
                bootEpoch:frame.bootEpoch,demands:requests,
                outputs:frame.outputReadbacks,
                protectionActive:frame.protectionActive});
            return {objectId:o.map.objectId,mode:'SHADOW_ONLY',
                physicalWriteAllowed:false,roomStates:states,
                demands:requests,pathPlan:plan};
        }
    };
};
