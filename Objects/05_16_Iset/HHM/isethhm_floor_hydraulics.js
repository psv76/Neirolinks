/* 05 16 Iset floor — independent K12..K16 / K2 hydraulic preflight.
 * Object-specific 120s NO opening; MAO4 min active 1% as-built.
 * Pure ES5 intents, NO physical writes. Mixing temperature STEP controller
 * is separate and NOT commissioned by this preflight module.
 * Local high supply response: close hot port at 40C, hard K2 stop at 45C
 * (source: live 21_heating_floor_manager.js, ISSUE #194).
 */
function finite(x){return typeof x==='number'&&isFinite(x);}
function relay(x){
    if(x===true||x===1)return true;
    if(x===false||x===0)return false;
    return null;
}
exports.create=function(c){
    if(!c||!c.outputs||!c.outputs.floorLoops||
       c.outputs.floorLoops.length!==5||
       c.actuatorOpenWaitMs!==120000)
        throw new Error('Iset floor preflight: as-built K12..K16 / 120s required');
    var seen={},i,p,when={},epoch=null,lastMs=null,hotAt=null;
    for(i=0;i<c.outputs.floorLoops.length;i++){
        p=c.outputs.floorLoops[i];
        if(!p||seen[p])throw new Error('Iset floor preflight: duplicate output');
        seen[p]=true;
    }
    return {step:function(f){
        if(!f||!finite(f.nowMs)||!f.bootEpoch||!f.readbacks||
           typeof f.enabled!=='boolean'||typeof f.localSetpointC!=='number')
            throw new Error('Iset floor preflight: explicit local input');
        if(epoch!==f.bootEpoch||lastMs!==null&&f.nowMs<lastMs){
            epoch=f.bootEpoch;when={};hotAt=null;
        }
        lastMs=f.nowMs;
        var actions=[],loops=[],ready=true,remaining=0,waiting=false;
        for(i=0;i<c.outputs.floorLoops.length;i++){
            p=c.outputs.floorLoops[i];
            var actual=relay(f.readbacks[p]);
            if(actual===false){
                if(when[p]===undefined)when[p]=f.nowMs;
            }else when[p]=undefined;
            var left=actual===false?
                Math.max(0,c.actuatorOpenWaitMs-(f.nowMs-when[p])):null;
            loops.push({path:p,openRelay:actual,remainingMs:left});
            if(actual!==false){ready=false;waiting=true;}
            else if(left>0){ready=false;remaining=Math.max(remaining,left);}
            if(f.enabled&&actual!==false)
                actions.push({path:p,value:false,action:'FLOOR_LOOP_OPEN'});
        }
        var supply=finite(f.supplyC)?f.supplyC:null;
        var hot=supply!==null&&supply>=40;
        var stop=supply!==null&&supply>=45;
        if(hot){
            if(hotAt===null)hotAt=f.nowMs;
            // Close the MAO4 hot port; K2 only stopped at the separate
            // actual supply hard limit or independent source protection.
            actions.push({path:c.outputs.floorValveLevel,value:0,
                action:'FLOOR_HOT_PORT_CLOSE'});
        }else hotAt=null;
        var valveOn=relay(f.readbacks[c.outputs.floorValveEnable]);
        var valvePct=f.readbacks[c.outputs.floorValveLevel];
        var preflight=valveOn===true&&finite(valvePct)&&
            valvePct>=0.5&&valvePct<=1.5;
        if(f.enabled&&!hot&&relay(f.readbacks[c.outputs.floorPump])!==true){
            // MAO4 preflight: 1% means switch ON, 0 means switch OFF.
            if(!preflight){
                actions.push({path:c.outputs.floorValveLevel,
                    value:1,action:'FLOOR_VALVE_PREFLIGHT'});
            }
        }
        var pumpActual=relay(f.readbacks[c.outputs.floorPump]);
        var pumpWanted=f.enabled&&ready&&
            (preflight||pumpActual===true)&&!stop&&
            f.independentEquipmentProtection!==true;
        // For this component only: K2 does not wait for HA, but it
        // does wait for opening and MAO4 preflight.
        if(stop||f.independentEquipmentProtection===true){
            if(pumpActual!==false)actions.push({
                path:c.outputs.floorPump,value:false,
                action:'FLOOR_PUMP_STOP_PROTECTION'});
        }else if(pumpWanted&&pumpActual!==true){
            actions.push({path:c.outputs.floorPump,value:true,
                action:'FLOOR_PUMP_START'});
        }else if(!f.enabled&&pumpActual===true){
            actions.push({path:c.outputs.floorPump,value:false,
                action:'FLOOR_PUMP_STOP_NO_DEMAND'});
        }
        return {state:!f.enabled?'OFF':stop?'HARD_SUPPLY_STOP':
                hot?'HOT_PORT_CLOSED_CIRCULATION_ALLOWED':
                !ready?'WAIT_LOOPS':!preflight?'WAIT_MAO4_PREFLIGHT':
                'READY',loops:loops,remainingOpenMs:waiting?null:remaining,
            allLoopsReady:ready,preflightReadbackOk:preflight,
            pumpWanted:pumpWanted,
            pumpReadback:pumpActual,
            requestSupplyC:f.enabled?f.localSetpointC:null,
            hotPortClose:hot,
            actions:actions,physicalWriteAllowed:false};
    }};
};
