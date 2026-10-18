/* 05 16 Iset HHM: single offline command plan K1-K4, NO, MAO4, OT11.
 * No physical commands and no HA dependency. For wb-rules ES5.
 * One WB entrypoint owns all writes after old HM2 is stopped.
 */
function validNumber(x){return typeof x==='number'&&isFinite(x);}
function relay(x){return x===true||x===1||x==='1'?true:
    x===false||x===0||x==='0'?false:null;}
function same(a,b){return typeof a==='number'&&typeof b==='number'?
    Math.abs(a-b)<0.01:a===b;}
exports.create=function(o){
    if(!o||!o.map||!o.services||!o.coordinator||
       !o.roomsPlanner||!o.floorHydraulics)
        throw new Error('Iset runtime: dependencies required');
    var svc=o.services,allowed={},pumpPaths=[
        svc.outputs.dhwPump,svc.outputs.floorPump,
        svc.outputs.basementPump,svc.outputs.livingPump
    ];
    function add(p){
        if(!p||allowed[p])throw new Error('Iset runtime: duplicate path '+p);
        allowed[p]=true;
    }
    for(var i=0;i<pumpPaths.length;i++)add(pumpPaths[i]);
    for(i=0;i<o.map.zones.length;i++){
        for(var j=0;j<o.map.zones[i].outputs.length;j++)
            add(o.map.zones[i].outputs[j]);
    }
    for(i=0;i<svc.outputs.floorLoops.length;i++)
        add(svc.outputs.floorLoops[i]);
    add(svc.outputs.floorValveLevel);
    add(svc.outputs.floorValveEnable);
    add(svc.channels.otSetpoint);
    var pumpStarts={},pumpStopStart={},epoch=null,previousTime=null;
    function timer(path,readback,now){
        var state=relay(readback);
        if(state===true&&pumpStarts[path]===undefined)
            pumpStarts[path]=now;
        if(state!==true)delete pumpStarts[path];
        return {readback:state,observedRunMs:
            state===true?now-pumpStarts[path]:null,
            stopWaitMs:pumpStopStart[path]===undefined?null:
                now-pumpStopStart[path]};
    }
    return {
        allowedTargets:function(){return Object.keys(allowed).sort();},
        step:function(f){
            if(!f||!validNumber(f.nowMs)||!f.bootEpoch||
               !f.plant||!f.plant.outputs||!f.roomsFrame||
               !f.floorControl||typeof f.floorControl.enabled!=='boolean')
                throw new Error('Iset runtime: explicit inputs required');
            if(epoch!==f.bootEpoch||
               previousTime!==null&&f.nowMs<previousTime){
                epoch=f.bootEpoch;pumpStarts={};pumpStopStart={};
            }
            previousTime=f.nowMs;
            var output=f.plant.outputs,floorControl=f.floorControl;
            var floor=o.floorHydraulics.step({
                nowMs:f.nowMs,bootEpoch:f.bootEpoch,
                readbacks:output,
                enabled:floorControl.enabled,
                localSetpointC:floorControl.targetC,
                supplyC:f.plant.floorSupplyC,
                independentEquipmentProtection:
                    f.plant.equipmentAllowsHeat!==true||
                    f.plant.otConnectionInvalid!==false
            });
            // The floor contributes heat only if locally switched on.
            // Its source supply request must be explicitly configured.
            f.plant.floorCommissioned=floorControl.enabled&&
                validNumber(floorControl.sourceRequestC);
            f.plant.floor=f.plant.floorCommissioned?
                {demand:true,requestC:floorControl.sourceRequestC}:null;
            var co=o.coordinator.step({
                nowMs:f.nowMs,roomsFrame:f.roomsFrame,plant:f.plant});
            var living=o.roomsPlanner.plan({
                nowMs:f.nowMs,bootEpoch:f.bootEpoch,
                demands:co.rooms.demands,readbacks:output,
                protectionActive:false});
            // The DHW source pause holds K4, NOT room actuators.
            var commands=[],seen={};
            function put(path,value,action,reason){
                if(!allowed[path])throw new Error('Iset runtime: unexpected path '+path);
                if(seen[path]!==undefined){
                    // Higher-priority later stop/close may supersede an
                    // earlier tentative command in the same calculation.
                    if(seen[path].value!==value)
                        throw new Error('Iset runtime: conflicting commands '+path);
                    return;
                }
                if(same(output[path],value))return;
                var cmd={path:path,value:value,action:action,reason:reason||''};
                seen[path]=cmd;commands.push(cmd);
            }
            // K1/K3 — separate local demand, not HA packets.
            for(i=0;i<co.intents.length;i++){
                var req=co.intents[i];
                put(req.path,req.requested,req.requested?'PUMP_START':'PUMP_STOP',
                    req.reason);
            }
            var pumpRunning=relay(output[svc.outputs.livingPump]);
            var k4MayRun=co.livingPumpGranted===true;
            if(!k4MayRun&&pumpRunning!==false){
                put(svc.outputs.livingPump,false,'PUMP_STOP',
                    co.livingPumpPermissionReason);
            }
            for(i=0;i<living.actions.length;i++){
                var la=living.actions[i];
                if(la.path===svc.outputs.livingPump){
                    if(la.value===true&&!k4MayRun)continue;
                    // If planner also wants stop, it must agree.
                    if(!k4MayRun&&la.value===false)continue;
                }
                put(la.path,la.value,la.action,la.reason);
            }
            // Floor hardware: local enabled setting, no HA mode.
            for(i=0;i<floor.actions.length;i++){
                var fa=floor.actions[i];
                put(fa.path,fa.value,fa.action,floor.state);
            }
            // When TPs are disabled, remove MAO4's previous hot command.
            var hotLevel=output[svc.outputs.floorValveLevel];
            if(!floorControl.enabled&&validNumber(hotLevel)&&hotLevel>0)
                put(svc.outputs.floorValveLevel,0,'FLOOR_HOT_PORT_CLOSE',
                    'LOCAL_OFF');
            // Mixing controller calculates only AFTER K2 is really
            // switched ON. Its output is a single MAO4 channel.
            var mixing=null;
            if(o.mixing&&floorControl.enabled&&
               relay(output[svc.outputs.floorPump])===true&&
               floor.hotPortClose!==true){
                mixing=o.mixing.step({
                    nowS:f.nowMs/1000,enabled:true,pumpReadback:true,
                    supplyC:f.plant.floorSupplyC,
                    sourceC:f.plant.commonC,
                    targetC:floorControl.targetC,
                    valveEnableReadback:
                        relay(output[svc.outputs.floorValveEnable])===true
                });
                // The module's injected IO creates candidate actions, not
                // direct physical writes. See setMixerIntent().
                if(o.mixerIntents){
                    var mixed=o.mixerIntents.drain();
                    for(i=0;i<mixed.length;i++)
                        put(mixed[i].path,mixed[i].value,
                            mixed[i].action,'FLOOR_MIXING');
                }
            }
            var ot=co.source.desiredWrite;
            if(ot)put(ot.path,ot.value,'OT_SETPOINT',co.source.reason);
            var diagnostics={},now=f.nowMs;
            for(i=0;i<pumpPaths.length;i++){
                var path=pumpPaths[i];
                var pm=timer(path,output[path],now),stopping=false;
                for(j=0;j<commands.length;j++)
                    if(commands[j].path===path&&commands[j].value===false)
                        stopping=true;
                if(stopping&&pm.readback===true){
                    if(pumpStopStart[path]===undefined)
                        pumpStopStart[path]=now;
                }else delete pumpStopStart[path];
                pm.stopWaitMs=pumpStopStart[path]===undefined?
                    null:now-pumpStopStart[path];
                diagnostics[path]=pm;
            }
            return {
                state:'PLANNED_ONLY',physicalWriteAllowed:false,
                commands:commands,rooms:co.rooms,
                living:living,services:co,
                floor:floor,mixing:mixing,
                pumpTimers:diagnostics
            };
        }
    };
};
