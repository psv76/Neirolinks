/* 05_16_Iset: K1, термостат БКН и ограниченный приоритет. Уставкой OT не владеет. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_dhw_manager", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_dhw_manager || []});
var dhwReady = HC.stableGate(), dhwWatch = HC.responseWatch();
var dhwDemand = false, dhwStart = null, dhwPriorityStart = null, dhwReliefUntil = 0;
var dhwOverrunUntil = 0, dhwFault = false, dhwBoost = false, dhwStartTemp = null;
var dhwReset = HC.stableGate(), dhwResetReady = false;
hc.device("heating_dhw", "ГВС", {
    tank_temp: hc.cell("НЕТ ДАННЫХ", "Температура бойлера, °C"),
    pump_status: hc.cell("НЕИЗВЕСТНО", "Насос ГВС"),
    mode_ui: hc.cell("Ожидание", "Режим ГВС"),
    transfer_ui: hc.cell("Не контролируется", "Контроль нагрева"),
    fault_ui: hc.cell(false, "Авария нагрева ГВС"),
    mode: {
        type: "text", value: "IDLE", readonly: true, forceDefault: true,
        hidden: true, title: "Режим (код)"
    },
    transfer: {
        type: "text", value: "NOT_MONITORED", readonly: true, forceDefault: true,
        hidden: true, title: "Контроль нагрева (код)"
    },
    accelerate: {type: "pushbutton", title: "Разовый ускоренный нагрев"},
    reset_fault: {type: "pushbutton", title: "Подтвердить проверку БКН"}
}, true);
hc.watch(CFG.channels.dhw); hc.watch(CFG.channels.common); hc.watch(CFG.channels.outdoor);
hc.watch("wb-mr6cu_37/K1");
function dhwPriorityLimit(outdoor) {
    if (outdoor === null || outdoor <= -20) return 900;
    if (outdoor >= 10) return 2700;
    return 900 + (outdoor + 20) * 60;
}
function dhwTick() {
    var now = hc.now(), cfg = CFG.dhw, t = hc.num(CFG.channels.dhw, 0, 85);
    var common = hc.num(CFG.channels.common, 5, 95), outdoor = hc.num(CFG.channels.outdoor, -60, 60, CFG.ttl.outdoor);
    var ready = dhwReady(t !== null, now, CFG.ttl.dhwRecovery);
    var state = "UNKNOWN", reason = "SENSOR_FAILSAFE_OR_STARTUP", mode = "IDLE", pause = false;
    var wasDemand = dhwDemand;
    if (ready && !dhwFault) {
        if (t <= cfg.target - cfg.hysteresis || (dhwBoost && t < cfg.target)) dhwDemand = true;
        if (t >= cfg.target) dhwDemand = false;
        if (dhwDemand && dhwStart === null) { dhwStart = now; dhwStartTemp = t; }
        if (dhwDemand && now - dhwStart >= cfg.timeout) { dhwFault = true; dhwDemand = false; }
        if (!dhwDemand) {
            if (wasDemand && !dhwFault) dhwOverrunUntil = now + cfg.overrun;
            dhwStart = null; dhwPriorityStart = null; dhwBoost = false;
        }
        state = dhwFault ? "UNKNOWN" : dhwDemand ? "ACTIVE" : "INACTIVE";
        reason = dhwFault ? "DHW_TOTAL_TIMEOUT_LATCHED" : "TANK_THERMOSTAT";
        mode = dhwDemand ? "SUPPORT" : "IDLE";
    } else {
        /* UNKNOWN aborts the session, including one-shot boost and forecast baseline.
         * Recovery starts a new session after dhwRecovery; unknown time is never heating time. */
        dhwDemand = false; dhwPriorityStart = null; dhwOverrunUntil = 0;
        dhwStart = null; dhwStartTemp = null; dhwBoost = false; dhwReliefUntil = 0;
    }
    if (dhwFault) reason = "DHW_TOTAL_TIMEOUT_LATCHED";
    var transfer = dhwWatch(dhwDemand && CFG.outputsEnabled && hc.bool("wb-mr6cu_37/K1") === true && hc.permit("dhw") && common !== null && common >= cfg.target + cfg.margin,
        t, now, CFG.response.dhwWindow, CFG.response.dhwRise);
    var elapsed = dhwStart === null ? 0 : now - dhwStart;
    var rise = t === null || dhwStartTemp === null ? 0 : t - dhwStartTemp;
    var forecastSlow = elapsed >= 900 && rise > 0 && (cfg.target - t) * elapsed / rise > 2700;
    var priorityWanted = cfg.policy === "HARD" || (cfg.policy === "CONDITIONAL" &&
        (t <= cfg.trigger || dhwBoost || forecastSlow)); /* trend alone cannot pause space heating */
    if (dhwDemand && priorityWanted && now >= dhwReliefUntil) {
        if (dhwPriorityStart === null) dhwPriorityStart = now;
        if (now - dhwPriorityStart >= dhwPriorityLimit(outdoor)) {
            dhwPriorityStart = null; dhwReliefUntil = now + cfg.relief;
        } else { mode = "ACCELERATED"; pause = true; }
    } else dhwPriorityStart = null;
    var p = HC.request(state, HC.clamp(cfg.target + (pause ? cfg.priorityMargin : cfg.margin), 55, 80), "DHW", reason, now);
    p.mode = mode; p.pause_heating_requested = pause; p.transfer = transfer; p.fault_latched = dhwFault;
    p.commissioned = hc.inputStatus(CFG.channels.dhw) !== "NOT_COMMISSIONED";
    p.session_policy = "ABORT_ON_UNKNOWN_NEW_SESSION_AFTER_RECOVERY";
    p.session_elapsed_s = elapsed;
    dhwResetReady = dhwReset(ready && t < 85 && common !== null &&
        hc.bool("wb-mr6cu_37/K1") === false, now, CFG.ttl.dhwRecovery);
    p.priority_remaining_s = pause ? Math.max(0, dhwPriorityLimit(outdoor) - (now - dhwPriorityStart)) : 0;
    hc.publish("heating_dhw", p);
    var safety = hc.packet("heating_safety/packet"), arbiter = hc.packet("heating_state/packet");
    var overrun = state === "INACTIVE" && now < dhwOverrunUntil && common !== null && t !== null && common - t >= 7 &&
        safety && safety.allow_normal && arbiter && arbiter.state !== "FROST_OVERRIDE";
    hc.output("wb-mr6cu_37/K1", !!((state === "ACTIVE" && hc.permit("dhw")) || overrun), CFG.outputsEnabled);
    dev["heating_dhw/tank_temp"] = t === null ? "НЕТ ДАННЫХ" : String(Math.round(t * 10) / 10);
    dev["heating_dhw/pump_status"] = hc.bool("wb-mr6cu_37/K1") === true ? "ВКЛ" :
        hc.bool("wb-mr6cu_37/K1") === false ? "ВЫКЛ" : "НЕТ ДАННЫХ";
    dev["heating_dhw/mode_ui"] = mode === "ACCELERATED" ? "Ускоренный нагрев" :
        mode === "SUPPORT" ? "Нагрев / поддержание" : "Ожидание";
    dev["heating_dhw/transfer_ui"] = transfer === "RESPONSE_CONFIRMED" ? "Нагрев подтверждён" :
        transfer === "OBSERVING" ? "Идёт проверка нагрева" :
        transfer === "NO_RESPONSE" ? "Нет ожидаемого нагрева" : "Не контролируется";
    dev["heating_dhw/fault_ui"] = dhwFault;
    dev["heating_dhw/mode"] = mode; dev["heating_dhw/transfer"] = transfer;
}
defineRule("hm2_dhw_boost", {whenChanged: "heating_dhw/accelerate", then: function () { dhwBoost = true; }});
defineRule("hm2_dhw_reset", {whenChanged: "heating_dhw/reset_fault", then: function () {
    dhwTick();
    if (dhwResetReady) { dhwFault = false; dhwStart = null; dhwStartTemp = null; dhwBoost = false; dhwWatch = HC.responseWatch(); }
}});
setInterval(dhwTick, CFG.ttl.tick * 1000); dhwTick();
