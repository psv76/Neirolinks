/* 05_16_Iset: достоверность, блокировки, watchdog. Физических writers нет. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_safety_supervisor", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_safety_supervisor || []});
var otReady = HC.stableGate(), safetyOwnership = false;
var ownershipExpected = null, ownershipSince = null, ownershipRestore = HC.stableGate(), ownershipResetReady = false;
var alarmArmed = {};
/* Shared service: Safety defines controls; only Notifications writes
 * notifications_status/notification_memory. Safety ticks/resets never overwrite them. */
var sensorIds = ["dhw", "basement", "outdoor", "floor", "living", "common"];
var managerIds = ["floor", "basement", "living", "dhw", "ahu", "source"];
hc.device("heating_safety", "Безопасность отопления", {
    problems: hc.cell("Проверка при запуске", "Что требует внимания"),
    ot_health: hc.cell("UNKNOWN", "OpenTherm"),
    wire_health: hc.cell("UNKNOWN", "Датчики 1-Wire"),
    ha_health: hc.cell("UNKNOWN", "Home Assistant"),
    alarms: {
        type: "text",
        value: "{}",
        readonly: true,
        forceDefault: true,
        hidden: true,
        title: "Аварии JSON"
    },
    reset_ownership: {type: "pushbutton", title: "Подтвердить устранение чужого writer"}
}, false);
defineVirtualDevice("heating_service", {
    title: "Отопление / Сервис",
    cells: {
        basement_target: {
            type: "text",
            value: String(CFG.basementTarget),
            readonly: true,
            forceDefault: true,
            order: 1,
            title: "Уставка цоколя, °C"
        }
    }
});
for (var si = 0; si < sensorIds.length; si++) hc.watch(CFG.channels[sensorIds[si]]);
hc.watch(CFG.channels.connection); hc.watch(CFG.channels.fault); hc.watch(CFG.channels.error);
hc.watch(CFG.channels.boiler); hc.watch(CFG.channels.pressure); hc.watch(CFG.channels.ot);
hc.watch(CFG.haHeartbeat); hc.watch(CFG.interlocks.generator); hc.watch(CFG.interlocks.leak); hc.watch(CFG.channels.fire);
function safetyTri(value) { return value === null ? "UNKNOWN" : value ? "ACTIVE" : "INACTIVE"; }
function safetyCommissioned(paths) {
    for (var i = 0; i < paths.length; i++) if (hc.inputStatus(paths[i]) === "NOT_COMMISSIONED") return false;
    return paths.length > 0;
}
function safetyTick() {
    var now = hc.now(), startup = now - hc.boot < CFG.ttl.startup;
    var connection = hc.bool(CFG.channels.connection), fault = hc.bool(CFG.channels.fault);
    var error = hc.num(CFG.channels.error, 0, 65535), boiler = hc.num(CFG.channels.boiler, 0, 110);
    var pressure = hc.num(CFG.channels.pressure, 0, 10), common = hc.num(CFG.channels.common, 5, 95);
    var otWritable = connection === false;
    var overheat = boiler !== null && boiler >= 85;
    var lowPressure = pressure !== null && pressure < 0.8;
    var healthyNow = otWritable && fault === false && error === 0 && boiler !== null && pressure !== null && !overheat && !lowPressure;
    var healthy = otReady(healthyNow, now, CFG.ttl.otRecovery);
    var wireInvalid = 0, i, id, packet, missing = [], invalid = [], transfer = {}, contradictory = [];
    for (i = 0; i < sensorIds.length; i++) {
        id = sensorIds[i];
        if (hc.num(CFG.channels[id], id === "outdoor" ? -60 : 0, id === "outdoor" ? 60 : 95) === null) wireInvalid++;
    }
    var source = hc.packet("heating_source/packet"), actual = hc.num(CFG.channels.ot, 0, 90);
    var match = source ? HC.readbackMatch(actual, source.last_command, CFG.ownershipMonitor) : null;
    if (!source || HC.number(source.last_command) === null) { ownershipExpected = null; ownershipSince = null; }
    else if (ownershipExpected !== source.last_command) { ownershipExpected = source.last_command; ownershipSince = now; }
    if (match === false && ownershipSince !== null && now - ownershipSince >= CFG.ownershipMonitor.settleSeconds) safetyOwnership = true;
    ownershipResetReady = ownershipRestore(match === true && healthyNow, now, CFG.ttl.recovery);
    for (i = 0; i < managerIds.length; i++) {
        id = managerIds[i]; packet = hc.packet("heating_" + id + "/packet");
        if (!packet) missing.push(id);
        else if (packet.state === "UNKNOWN" && packet.commissioned === true) invalid.push(id);
        if (packet && id !== "source" &&
            ((packet.state === "UNKNOWN" && packet.valid !== 0) ||
            (packet.state === "ACTIVE" && (packet.valid !== 1 || HC.number(packet.requested_supply) === null)) ||
            (packet.state === "INACTIVE" && packet.requested_supply !== "NOT_READY"))) contradictory.push(id);
        transfer[id] = packet && (packet.fault_latched === true || packet.transfer === "NO_RESPONSE");
    }
    var arbiter = hc.packet("heating_state/packet");
    if (!arbiter) missing.push("arbiter");
    var floor = hc.packet("heating_floor/packet"), ahu = hc.packet("heating_ahu/packet");
    var ha = !CFG.haHeartbeat ? null : hc.heartbeatFresh(CFG.haHeartbeat, CFG.ttl.haHeartbeat);
    var generator = safetyTri(hc.bool(CFG.interlocks.generator));
    var fireValue = hc.bool(CFG.channels.fire), fire = safetyTri(fireValue === null ? null : !fireValue);
    var leak = safetyTri(hc.bool(CFG.interlocks.leak));
    var floorTemp = hc.num(CFG.channels.floor, 10, 60);
    var blockFloor = floorTemp === null || floorTemp >= 45 || !!(floor && floor.fault_latched);
    var sourceMissing = missing.indexOf("source") >= 0 || missing.indexOf("arbiter") >= 0;
    var allowNormal = !startup && healthy && !safetyOwnership && !sourceMissing;
    var state = startup ? "STARTUP_VALIDATION" : !healthy ? "BOILER_FAULT" :
        safetyOwnership || sourceMissing ? "WATCHDOG_INTERLOCK" : wireInvalid || invalid.length || missing.length || ha !== true || !CFG.ahu.commissioned ? "DEGRADED" : "READY";
    var alarms = {
        ot_unavailable: !healthy, boiler_fault: fault === true || (error !== null && error > 0),
        low_pressure: lowPressure, overheat: overheat, mass_1wire: wireInvalid === sensorIds.length,
        ha_unavailable: ha !== true, floor_transfer: !!transfer.floor, dhw_transfer: !!transfer.dhw,
        basement_transfer: !!transfer.basement, living_transfer: !!transfer.living,
        ownership_violation: safetyOwnership, manager_watchdog: !startup && missing.length > 0,
        ahu_contract_unknown: !ahu || ahu.frost === "UNKNOWN", ahu_frost: !!(ahu && ahu.frost === "ACTIVE"),
        request_unknown: invalid.length > 0, contradictory_request: contradictory.length > 0,
        short_cycle: !!(source && source.short_cycle_warning)
    };
    var otCommissioned = safetyCommissioned([CFG.channels.connection, CFG.channels.fault, CFG.channels.error,
        CFG.channels.boiler, CFG.channels.pressure]);
    var wirePaths = []; for (i = 0; i < sensorIds.length; i++) wirePaths.push(CFG.channels[sensorIds[i]]);
    var classes = {}, key, commissioned;
    for (key in alarms) if (Object.prototype.hasOwnProperty.call(alarms, key)) {
        commissioned = true;
        if (["ot_unavailable", "boiler_fault", "low_pressure", "overheat"].indexOf(key) >= 0) commissioned = otCommissioned;
        if (key === "mass_1wire") commissioned = safetyCommissioned(wirePaths);
        if (key === "ha_unavailable") commissioned = safetyCommissioned([CFG.haHeartbeat]);
        if (key === "ahu_contract_unknown" || key === "ahu_frost") commissioned = !!(ahu && ahu.commissioned);
        if (key === "ownership_violation") commissioned = HC.readbackMatch(0, 0, CFG.ownershipMonitor) !== null;
        if (!commissioned) { classes[key] = "NOT_COMMISSIONED"; alarms[key] = null; }
        else {
            if (!alarms[key] && !startup) alarmArmed[key] = true;
            if (!alarmArmed[key] && now - hc.boot < CFG.ttl.startup + CFG.ttl.otRecovery + CFG.ttl.tick) {
                classes[key] = "STARTUP_VALIDATION"; alarms[key] = null;
            } else classes[key] = alarms[key] ? "RUNTIME_FAULT" : "HEALTHY";
        }
    }
    var p = {state: state, reason: "missing=" + missing.join(",") + "; invalid=" + invalid.join(",") + "; wire_invalid=" + wireInvalid,
        updated_at: now, allow_normal: allowNormal, allow_frost: healthyNow,
        ot_writable: otWritable, block_floor: blockFloor, alarms: alarms, alarm_classes: classes, generator_active: generator,
        commissioning: {off: CFG.otOffMethodCommissioned ? "COMMISSIONED" : "OFF_METHOD_NOT_COMMISSIONED",
            ownership: CFG.ownershipMonitor.commissioned ? "COMMISSIONED" : "OWNERSHIP_MONITOR_NOT_COMMISSIONED",
            email: CFG.emailAdapter ? "ADAPTER_CONFIGURED" : "NOT_COMMISSIONED"},
        fire_alarm: fire, leak_alarm: leak, ventilation_load_shed: generator === "ACTIVE" ? "REQUESTED" : generator,
        electric_allowed: false, external_action_matrix: "NOT_COMMISSIONED", common_valid: common !== null};
    hc.publish("heating_safety", p);
    var problemText = [];
    if (!healthy) problemText.push("OpenTherm / котёл");
    if (wireInvalid > 0) problemText.push("1-Wire: недоступно датчиков " + wireInvalid);
    if (ha !== true) problemText.push("Home Assistant: нет свежего heartbeat");
    if (safetyOwnership) problemText.push("Обнаружен чужой writer OpenTherm");
    if (missing.length) problemText.push("Нет heartbeat менеджеров: " + missing.join(", "));
    if (invalid.length) problemText.push("Недостоверные менеджеры: " + invalid.join(", "));
    if (transfer.floor) problemText.push("Тёплый пол: нет подтверждения передачи тепла");
    if (transfer.dhw) problemText.push("ГВС: нет подтверждения нагрева");
    if (transfer.basement) problemText.push("Цоколь: недостаточный температурный отклик (диагностика)");
    if (transfer.living) problemText.push("Жилая зона: недостаточный температурный отклик (диагностика)");
    /* ПВУ сейчас сознательно работает вне HM2 — это не неисправность. */
    dev["heating_safety/problems"] = problemText.length ? problemText.join("; ") : "Активных проблем нет";
    dev["heating_safety/ot_health"] = healthy ? "НОРМА" : "НЕТ ДАННЫХ / АВАРИЯ";
    dev["heating_safety/wire_health"] = wireInvalid === 0 ? "НОРМА" :
        wireInvalid === 6 ? "МАССОВАЯ ПОТЕРЯ" : "ЧАСТИЧНАЯ ПОТЕРЯ";
    dev["heating_safety/ha_health"] = ha === true ? "НОРМА" : "НЕТ HEARTBEAT";
    dev["heating_safety/alarms"] = JSON.stringify({active: alarms, classes: classes, updated_at: now});
}
defineRule("hm2_ownership_reset", {whenChanged: "heating_safety/reset_ownership", then: function () {
    if (ownershipResetReady) { safetyOwnership = false; ownershipExpected = null; ownershipSince = null; }
}});
setInterval(safetyTick, CFG.ttl.tick * 1000); safetyTick();