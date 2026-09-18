/* 05_16_Iset: единственный новый writer OT11 Heating Setpoint. OT12 кандидат не управляет. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_source_manager", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_source_manager || []});
var sourceLast = null, sourceWriteAt = 0, sourceRamp = null, sourceTickAt = null;
var sourceHigh = null, sourceReleaseAt = null, sourceFlame = null, sourceStarts = [];
var sourceWriteFailed = false;
hc.device("heating_source", "Источник тепла", {
    target: hc.cell("NOT_READY", "Команда OpenTherm, °C"),
    ot_actual: hc.cell("НЕТ ДАННЫХ", "Фактическая уставка OpenTherm, °C"),
    boiler_temp: hc.cell("НЕТ ДАННЫХ", "Температура котла, °C"),
    flame_ui: hc.cell("НЕТ ДАННЫХ", "Горелка"),
    starts_hour: hc.cell(0, "Пуски горелки за час")
}, false);
hc.watch(CFG.channels.connection); hc.watch(CFG.channels.flame);
hc.watch(CFG.channels.ot);
function sourceTick() {
    var now = hc.now(), cfg = CFG.source, s = hc.packet("heating_safety/packet"), a = hc.packet("heating_state/packet");
    var link = hc.bool(CFG.channels.connection) === false;
    var frost = !!(a && a.state === "FROST_OVERRIDE");
    var raw = a ? HC.number(a.target) : null;
    var permitted = link && s && s.ot_writable === true && (frost ? s.allow_frost === true : s.allow_normal === true);
    var off = !permitted || raw === null || raw < 35 || raw > 82;
    var target = off ? cfg.off : HC.clamp(raw + cfg.offset, cfg.min, frost ? cfg.frostMax : cfg.max);
    var operating = now - hc.boot < CFG.ttl.startup && (!s || !a || !link) ? "STARTUP_VALIDATION" :
        !link || (s && s.state === "BOILER_FAULT") ? "BOILER_FAULT" :
        !s ? (now - hc.boot < CFG.ttl.startup ? "STARTUP_VALIDATION" : "SAFETY_INTERLOCK") :
        !permitted ? (s.state === "STARTUP_VALIDATION" ? "STARTUP_VALIDATION" : "SAFETY_INTERLOCK") :
        !a ? "SAFETY_INTERLOCK" : off ? "NO_DEMAND" : frost ? "FROST_OVERRIDE" : a.dhw_priority ? "DHW" : "ACTIVE";
    var shutdownReason = !s ? "SAFETY_PACKET_MISSING_OR_INVALID" : !a ? "ARBITER_PACKET_MISSING_OR_INVALID" : operating;
    var state = !CFG.outputsEnabled ? "OUTPUTS_DISABLED" : off && !CFG.otOffMethodCommissioned ? "OFF_METHOD_NOT_COMMISSIONED" : operating;
    var dt = sourceTickAt === null ? 0 : HC.clamp(now - sourceTickAt, 0, CFG.ttl.tick * 2);
    sourceTickAt = now;
    if (off) { sourceRamp = cfg.off; sourceHigh = null; sourceReleaseAt = null; }
    else if (frost) { sourceRamp = target; sourceHigh = target; sourceReleaseAt = null; }
    else {
        if (sourceHigh === null || target >= sourceHigh) { sourceHigh = target; sourceReleaseAt = null; }
        else {
            if (sourceReleaseAt === null) sourceReleaseAt = now;
            if (now - sourceReleaseAt < cfg.releaseHold) target = sourceHigh;
            else { sourceHigh = target; sourceReleaseAt = null; }
        }
        if (sourceRamp === null || sourceRamp < cfg.min) sourceRamp = cfg.min;
        var up = a.dhw_priority ? cfg.dhwUp : cfg.up;
        sourceRamp += HC.clamp(target - sourceRamp, -cfg.down * dt / 60, up * dt / 60);
        sourceRamp = HC.clamp(sourceRamp, cfg.min, cfg.max);
    }
    var command = Math.round(sourceRamp * 10) / 10;
    var actual = hc.num(CFG.channels.ot, 0, 90);
    var monitor = HC.readbackMatch(actual, command, CFG.ownershipMonitor);
    var reassert = off && monitor === false && now - sourceWriteAt >= Math.max(cfg.writeInterval, CFG.ownershipMonitor.settleSeconds);
    var urgent = off || frost;
    /* SAFE-OFF depends on the commissioned method and our own live link, never on a missing safety permit. */
    var canWrite = off ? CFG.otOffMethodCommissioned === true && link : permitted;
    if (canWrite && (urgent || now - sourceWriteAt >= cfg.writeInterval) &&
        (sourceLast === null || Math.abs(command - sourceLast) >= cfg.epsilon || reassert)) {
        if (hc.output("wbe2-i-opentherm_11/Heating Setpoint", command, CFG.outputsEnabled)) {
            sourceLast = command; sourceWriteAt = now; sourceWriteFailed = false;
        } else if (CFG.outputsEnabled) sourceWriteFailed = true;
    }
    var flame = hc.bool(CFG.channels.flame);
    if (sourceFlame === false && flame === true) sourceStarts.push(now);
    sourceFlame = flame;
    while (sourceStarts.length && sourceStarts[0] < now - 3600) sourceStarts.shift();
    var reason = state === "OFF_METHOD_NOT_COMMISSIONED" ? state + ":" + shutdownReason :
        !CFG.outputsEnabled ? "OUTPUTS_DISABLED:" + shutdownReason : off ? shutdownReason : operating + ":LIMIT_RAMP";
    var p = {state: state, reason: reason, operating_state: operating,
        shutdown_required: off, shutdown_reason: off ? shutdownReason : "NONE",
        shutdown_status: !off ? "NOT_REQUIRED" : !CFG.otOffMethodCommissioned ? "OFF_METHOD_NOT_COMMISSIONED" :
            !CFG.outputsEnabled ? "OUTPUTS_DISABLED" : !link ? "OFF_LINK_UNAVAILABLE" : sourceWriteFailed ? "OFF_WRITE_FAILED" :
                sourceLast === cfg.off ? "OFF_COMMAND_ACCEPTED_NOT_PHYSICAL_PROOF" : "OFF_WRITE_FAILED",
        command_status: sourceWriteFailed ? "OUTPUT_WRITE_FAILED" : "COMMAND_ACCEPTANCE_ONLY",
        ownership_monitor: HC.readbackMatch(0, 0, CFG.ownershipMonitor) === null ? "OWNERSHIP_MONITOR_NOT_COMMISSIONED" :
            monitor === null ? "READBACK_UNKNOWN" : monitor ? "MATCH" : "MISMATCH",
        updated_at: now, target: command, last_command: sourceLast, last_command_at: sourceWriteAt,
        electric_allowed: false, electric_reason: s && s.generator_active === "ACTIVE" ? "GENERATOR_INTERLOCK" : "NOT_COMMISSIONED",
        starts_hour: sourceStarts.length, short_cycle_warning: sourceStarts.length > 6};
    hc.publish("heating_source", p); dev["heating_source/target"] = String(command);
    dev["heating_source/ot_actual"] = actual === null ? "НЕТ ДАННЫХ" :
        String(Math.round(actual * 10) / 10);
    var boilerUi = hc.num(CFG.channels.boiler, 0, 110);
    dev["heating_source/boiler_temp"] = boilerUi === null ? "НЕТ ДАННЫХ" :
        String(Math.round(boilerUi * 10) / 10);
    dev["heating_source/flame_ui"] = flame === true ? "ГОРИТ" :
        flame === false ? "НЕ ГОРИТ" : "НЕТ ДАННЫХ";
    dev["heating_source/starts_hour"] = sourceStarts.length;
}
defineRule("hm2_source_arbiter_event", {whenChanged: "heating_state/packet", then: sourceTick});
defineRule("hm2_source_safety_event", {whenChanged: "heating_safety/packet", then: sourceTick});
setInterval(sourceTick, CFG.ttl.tick * 1000); sourceTick();
