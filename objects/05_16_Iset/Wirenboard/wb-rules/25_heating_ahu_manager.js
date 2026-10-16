/* 05_16_Iset: owner K6; локальная защита Breezart остаётся самостоятельной. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_ahu_manager", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_ahu_manager || []});
var ahuFrostLatched = false, ahuFrostSeen = false;
hc.device("heating_ahu", "Отопление / ПВУ", {
    frost: hc.cell("UNKNOWN", "Защита калорифера"),
    reset_frost: {type: "pushbutton", title: "Подтвердить восстановление локальной защиты"}
}, true);
function ahuTick() {
    var cfg = CFG.ahu, now = hc.now(), frost = hc.bool(cfg.frost), run = hc.bool(cfg.run), demand = hc.bool(cfg.heatDemand);
    var normalSupply = HC.number(cfg.normalSupply), frostSupply = HC.number(cfg.frostSupply);
    var commissioned = cfg.commissioned && cfg.localProtectionConfirmed && cfg.frost && cfg.run && cfg.heatDemand &&
        normalSupply !== null && normalSupply >= 40 && normalSupply <= 75 &&
        frostSupply !== null && frostSupply >= 40 && frostSupply <= 82 &&
        (cfg.sourceUnavailablePump === "ON" || cfg.sourceUnavailablePump === "OFF") &&
        hc.commissioned([cfg.frost, cfg.run, cfg.heatDemand]);
    var state = "UNKNOWN", priority = "PROCESS", reason = "AHU_FROST_CONTRACT_NOT_COMMISSIONED", target = "NOT_READY";
    if (frost !== null) ahuFrostSeen = true;
    var validatingFrost = commissioned && frost === null && !ahuFrostSeen && now - hc.boot < CFG.ttl.startup;
    /* При подтверждённом контракте потеря frost рассматривается как угроза. */
    if (commissioned) {
        if (frost !== false && !validatingFrost) ahuFrostLatched = true;
        if (ahuFrostLatched || validatingFrost) {
            state = "ACTIVE"; priority = "FROST_SAFETY"; target = frostSupply;
            reason = validatingFrost ? "FROST_INPUT_STARTUP_VALIDATION" : frost === null ? "FROST_INPUT_LOST_LATCHED" : "FROST_LATCHED";
        } else if (run !== null && demand !== null) {
            state = run && demand ? "ACTIVE" : "INACTIVE"; target = normalSupply;
            reason = "COMMISSIONED_AHU_REQUEST";
        } else reason = "AHU_RUN_UNKNOWN";
    }
    var p = HC.request(state, target, priority, reason, now);
    p.frost = commissioned ? (validatingFrost ? "STARTUP_VALIDATION" : ahuFrostLatched ? "ACTIVE" : "INACTIVE") : "UNKNOWN";
    p.fan_interlock = ahuFrostLatched || validatingFrost ? "STOP_REQUIRED_LOCAL_BREEZART" : "NONE";
    p.outside_damper_interlock = ahuFrostLatched || validatingFrost ? "CLOSE_REQUIRED_LOCAL_BREEZART" : "NONE";
    p.local_protection_confirmed = commissioned === true;
    p.commissioned = commissioned === true;
    var safety = hc.packet("heating_safety/packet");
    var sourceAvailable = !!(safety && safety.allow_frost === true);
    p.source_unavailable_contract = cfg.sourceUnavailablePump || "BLOCKER_K6_ON_OR_OFF_UNRESOLVED";
    p.source_available = sourceAvailable;
    hc.publish("heating_ahu", p); dev["heating_ahu/frost"] = p.frost;
    /* Неподтверждённый K6 не выключаем: runtime owner и безопасное состояние неизвестны. */
    if (commissioned) hc.output("wb-mr6cu_37/K6", ahuFrostLatched || validatingFrost ?
        (sourceAvailable || cfg.sourceUnavailablePump === "ON") : (state === "ACTIVE" && hc.permit("ahu")), CFG.outputsEnabled);
}
hc.watch(CFG.ahu.run); hc.watch(CFG.ahu.heatDemand); hc.watch(CFG.ahu.frost, ahuTick);
var ahuRestore = HC.stableGate();
function ahuResetValid() {
    var safety = hc.packet("heating_safety/packet");
    return CFG.ahu.commissioned && CFG.ahu.localProtectionConfirmed && hc.bool(CFG.ahu.frost) === false &&
        hc.bool(CFG.ahu.run) !== null && hc.bool(CFG.ahu.heatDemand) !== null && !!(safety && safety.allow_frost);
}
defineRule("hm2_ahu_reset", {whenChanged: "heating_ahu/reset_frost", then: function () {
    if (ahuRestore(ahuResetValid(), hc.now(), CFG.ttl.recovery)) ahuFrostLatched = false;
}});
setInterval(function () { ahuRestore(ahuResetValid(), hc.now(), CFG.ttl.recovery); ahuTick(); }, CFG.ttl.tick * 1000);
ahuTick();
