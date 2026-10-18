/* Iset HHM: autonomous heat decision coordinator, no HA/MQTT/writes.
 * Joins already implemented room plans, DHW, basement, source request.
 * Floor mixer must be independently commissioned before inclusion.
 * K1/K3 intents are logical plans, not physical output writes.
 */
function finite(x){return typeof x==='number'&&isFinite(x);}
exports.create=function(o){
    if(!o||!o.rooms||!o.dhw||!o.demand||!o.source||
       !o.services||!o.services.outputs)
        throw new Error('Iset coordinator: explicit service modules required');
    var c=o.services;
    return {
        boostDhw:function(){o.dhw.boost();},
        resetDhwFault:function(){o.dhw.reset();},
        step:function(i){
            if(!i||!finite(i.nowMs)||!i.roomsFrame||!i.plant||
               !i.plant.outputs)
                throw new Error('Iset coordinator: explicit plant input');
            var plant=i.plant,at=i.nowMs/1000;
            var rooms=o.rooms.step(i.roomsFrame);
            var hot=o.dhw.step({nowS:at,tankC:plant.tankC,
                outdoorC:plant.outdoorC,commonC:plant.commonC,
                sourceAvailable:plant.sourceAvailable===true,
                pumpReadback:plant.outputs[c.outputs.dhwPump]});
            var service=o.demand.step({livingDemands:rooms.demands,
                basementTemps:plant.basementTemps,
                outdoorC:plant.outdoorC,
                dhw:hot,floorCommissioned:plant.floorCommissioned===true,
                floor:plant.floor||null});
            var source=o.source.step({nowS:at,
                sourceRequestedC:service.sourceRequestedC,
                dhwPriorityPause:service.dhwPriorityPause,
                otConnectionInvalid:plant.otConnectionInvalid,
                equipmentAllowsHeat:plant.equipmentAllowsHeat,
                offMethodCommissioned:plant.offMethodCommissioned,
                flame:plant.flame});
            // Source priority applies to pump runtime, NOT room actuators.
            // A room calling for heat must not be treated as sensor error
            // because the source is temporarily paused for DHW.
            var plantMayHeat=plant.equipmentAllowsHeat===true &&
                plant.otConnectionInvalid===false;
            var k1=hot.pumpWanted&&plantMayHeat;
            var basementGranted=service.grants.basement==='REQUESTED';
            var k3=basementGranted&&plantMayHeat;
            var k4Granted=service.grants.living==='REQUESTED'&&plantMayHeat;
            return {mode:'OFFLINE_PLAN_ONLY',objectId:'05_16_Iset',
                rooms:rooms,dhw:hot,requests:service,source:source,
                livingPumpGranted:k4Granted,
                livingPumpPermissionReason:!plantMayHeat?'INDEPENDENT_PLANT_PROTECTION':
                    service.grants.living,
                intents:[
                    {path:c.outputs.dhwPump,requested:k1,
                        reason:hot.mode},
                    {path:c.outputs.basementPump,requested:k3,
                        reason:service.grants.basement}
                ],
                // K4 and zone actuators handled by independent NO planner;
                // mixer K2 and OT require their own approved writers.
                physicalWriteAllowed:false};
        },
        acknowledgeOtWrite:function(nowS,value){
            return o.source.acknowledge(nowS,value);
        }
    };
};
