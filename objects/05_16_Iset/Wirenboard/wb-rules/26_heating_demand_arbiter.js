/* 05_16_Iset: MAX запросов и grants. Физических выходов нет. */
var HC = require("HeatingCommon"), CFG = require("HeatingConfig");
var hc = HC.create({dev: dev, log: log, trackMqtt: trackMqtt, defineVirtualDevice: defineVirtualDevice}, "Heating_demand_arbiter", CFG.ttl, {allowedOutputs: CFG.allowedOutputs.Heating_demand_arbiter || []});
var consumers = ["floor", "basement", "living", "dhw", "ahu"];
var limits = {floor: [35, 60], basement: [35, 75], living: [35, 75], dhw: [55, 80], ahu: [40, 82]};
var rank = {COMFORT: 0, DHW: 1, PROCESS: 2, FROST_SAFETY: 3};
hc.device("heating_state", "Отопление / Состояние", {
    winner_ui: hc.cell("Никто", "Победивший потребитель"),
    target: hc.cell("NOT_READY", "Требуемая общая подача, °C"),
    grants_ui: hc.cell("—", "Разрешения потребителей"),
    winner: {
        type: "text", value: "NONE", readonly: true, forceDefault: true,
        hidden: true, title: "Победитель (код)"
    },
    grants: {
        type: "text", value: "{}", readonly: true, forceDefault: true,
        hidden: true, title: "Разрешения JSON"
    }
}, false);
var consumerTitles = {floor: "Тёплый пол", basement: "Цоколь", living: "Жилая зона", dhw: "ГВС", ahu: "ПВУ"};
var grantTitles = {GRANTED: "разрешён", NO_DEMAND: "нет запроса", INVALID: "недостоверен / не введён",
    INTERLOCK: "заблокирован защитой", SUPPRESSED: "временно подавлен"};
function arbiterTick() {
    var now = hc.now(), requests = {}, grants = {}, i, id, r, invalid = 0;
    var frost = false, dhwPause = false, target = null, winner = "NONE", winningClass = "COMFORT";
    var safety = hc.packet("heating_safety/packet");
    for (i = 0; i < consumers.length; i++) {
        id = consumers[i]; r = hc.packet("heating_" + id + "/packet");
        if (!HC.validRequest(r, now, CFG.ttl.request, hc.boot, limits[id][0], limits[id][1]) ||
            r.fault_latched === true ||
            (r.priority_class === "FROST_SAFETY" && id !== "ahu") ||
            (id === "dhw" && r.priority_class !== "DHW")) {
            grants[id] = "INVALID"; invalid++; continue;
        }
        requests[id] = r;
        if (id === "ahu" && r.state === "ACTIVE" && r.priority_class === "FROST_SAFETY" && r.local_protection_confirmed === true) frost = true;
        if (id === "dhw" && r.state === "ACTIVE" && r.mode === "ACCELERATED" && r.pause_heating_requested === true &&
            HC.number(r.priority_remaining_s) !== null && r.priority_remaining_s > 0 && r.priority_remaining_s <= 2700) dhwPause = true;
    }
    for (i = 0; i < consumers.length; i++) {
        id = consumers[i]; r = requests[id]; if (!r) continue;
        if (r.state === "INACTIVE") { grants[id] = "NO_DEMAND"; continue; }
        if (frost && id !== "ahu") { grants[id] = "SUPPRESSED"; continue; }
        if (!frost && (!safety || !safety.allow_normal)) { grants[id] = "INTERLOCK"; continue; }
        if (id === "floor" && safety && safety.block_floor) { grants[id] = "INTERLOCK"; continue; }
        /* Обычная ПВУ не подавляется без подтверждённого снижения воздушного расхода. */
        if (dhwPause && (id === "floor" || id === "basement" || id === "living")) { grants[id] = "SUPPRESSED"; continue; }
        grants[id] = "GRANTED";
        var t = HC.number(r.requested_supply);
        if (target === null || t > target || (t === target && rank[r.priority_class] > rank[winningClass])) {
            target = t; winner = id; winningClass = r.priority_class;
        }
    }
    var state = frost ? "FROST_OVERRIDE" : !safety ? "STARTUP_VALIDATION" : !safety.allow_normal ? safety.state :
        target === null ? (invalid ? "DEGRADED" : "NO_DEMAND") : dhwPause ? "DHW_CONDITIONAL_PRIORITY" : "ACTIVE_PARALLEL";
    var p = {state: state, reason: "winner=" + winner + "; invalid=" + invalid, updated_at: now,
        target: target === null ? "NOT_READY" : target, winner: winner, grants: grants, priority_class: winningClass,
        degraded: invalid > 0, dhw_priority: dhwPause};
    hc.publish("heating_state", p);
    var grantText = [], gi;
    for (gi = 0; gi < consumers.length; gi++) {
        id = consumers[gi];
        grantText.push(consumerTitles[id] + ": " + (grantTitles[grants[id]] || grants[id] || "—"));
    }
    dev["heating_state/winner_ui"] = winner === "NONE" ? "Никто" : (consumerTitles[winner] || winner);
    dev["heating_state/grants_ui"] = grantText.join("; ");
    dev["heating_state/winner"] = winner; dev["heating_state/target"] = String(p.target);
    dev["heating_state/grants"] = JSON.stringify(grants);
}
defineRule("hm2_arbiter_frost_event", {whenChanged: "heating_ahu/packet", then: arbiterTick});
setInterval(arbiterTick, CFG.ttl.tick * 1000); arbiterTick();
