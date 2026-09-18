/* 05_16_Iset: локальный термостат четырёх помещений; единственный owner K3. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_basement_manager", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_basement_manager || []});
var basementDemand = false, basementReady = HC.stableGate();
var basementWatch = HC.responseWatch();
hc.device("heating_basement", "Отопление / Цоколь", {
    room_target: hc.cell(String(CFG.basementTarget), "Уставка помещений, °C"),
    room_min: hc.cell("НЕТ ДАННЫХ", "Минимальная температура помещений, °C"),
    pump_status: hc.cell("НЕИЗВЕСТНО", "Насос цоколя"),
    transfer_ui: hc.cell("Не контролируется", "Диагностика нагрева")
}, true);
for (var bi = 0; bi < CFG.basementSensors.length; bi++) hc.watch(CFG.basementSensors[bi]);
hc.watch(CFG.channels.outdoor); hc.watch(CFG.channels.common); hc.watch(CFG.channels.basement);
hc.watch("wb-mr6cu_37/K3");
function basementTick() {
    var now = hc.now(), min = 100, all = true, i, t, missingSensors = [];
    var target = HC.number(CFG.basementTarget);
    for (i = 0; i < CFG.basementSensors.length; i++) {
        t = hc.num(CFG.basementSensors[i], -10, 50);
        if (t === null) { all = false; missingSensors.push(CFG.basementSensors[i]); } else min = Math.min(min, t);
    }
    var outdoor = hc.num(CFG.channels.outdoor, -60, 60, CFG.ttl.outdoor);
    var state = "UNKNOWN", reason = "STARTUP_VALIDATION", requested = "NOT_READY";
    var valid = basementReady(all && target !== null && target >= 10 && target <= 30 && outdoor !== null, now, CFG.ttl.recovery);
    if (target === null) reason = "SETPOINT_NOT_COMMISSIONED_21_VS_26";
    else if (!valid) reason = "REQUIRED_TEMPERATURE_NOT_READY:" + missingSensors.join(",");
    else {
        if (min < target - 0.7) basementDemand = true;
        else if (min > target + 0.7) basementDemand = false;
        var base = outdoor >= 0 ? 48 - HC.clamp(outdoor, 0, 10) :
            outdoor >= -10 ? 48 - outdoor : 58 + HC.clamp(-outdoor - 10, 0, 15) * 10 / 15;
        requested = HC.clamp(base + HC.clamp(2 * (target - min), 0, 6), 35, 75);
        state = basementDemand ? "ACTIVE" : "INACTIVE"; reason = "LOCAL_THERMOSTAT";
    }
    var common = hc.num(CFG.channels.common, 5, 95), branch = hc.num(CFG.channels.basement, 5, 95);
    var transfer = basementWatch(CFG.outputsEnabled && state === "ACTIVE" && hc.permit("basement") &&
        hc.bool("wb-mr6cu_37/K3") === true && common !== null && common >= requested &&
        branch !== null && branch < requested - 2, branch, now, CFG.response.branchWindow, CFG.response.branchRise);
    /* Недостаточный рост температуры — диагностика, а не доказательство отсутствия протока.
     * Не лишаем дом отопления из-за этого измерения. */
    hc.changed("basement_heat_response", "СОСТОЯНИЕ", transfer === "NO_RESPONSE" ?
        "Недостаточный рост температуры (диагностика)" : "Контроль нагрева: норма", {});
    if (state === "UNKNOWN") basementDemand = false;
    var p = HC.request(state, requested, "COMFORT", reason, now);
    p.transfer = transfer; p.fault_latched = false; p.missing_sensors = missingSensors;
    p.commissioned = target !== null && target >= 10 && target <= 30 && hc.commissioned(CFG.basementSensors.concat([CFG.channels.outdoor]));
    hc.publish("heating_basement", p);
    hc.output("wb-mr6cu_37/K3", state === "ACTIVE" && hc.permit("basement"), CFG.outputsEnabled);
    dev["heating_basement/room_target"] = String(target);
    dev["heating_basement/room_min"] = all ? String(Math.round(min * 10) / 10) : "НЕТ ДАННЫХ";
    dev["heating_basement/pump_status"] = hc.bool("wb-mr6cu_37/K3") === true ? "ВКЛ" :
        hc.bool("wb-mr6cu_37/K3") === false ? "ВЫКЛ" : "НЕТ ДАННЫХ";
    dev["heating_basement/transfer_ui"] = transfer === "RESPONSE_CONFIRMED" ? "Передача тепла подтверждена" :
        transfer === "OBSERVING" ? "Идёт проверка реакции" :
        transfer === "NO_RESPONSE" ? "Нет ожидаемого роста температуры" : "Не контролируется";
}
setInterval(basementTick, CFG.ttl.tick * 1000); basementTick();
