// 05 31 Иволга 13 / 503: прямой радиаторный контур дома. ES5 / wb-rules.
// Только shadow/gate до отдельного очного ПНР. Production enable отсутствует.
// Единственный физический выход manager — насос. Зональные выходы только читаются.
var SCRIPT = '503_rad_dom_manager';
var VD = 'hm2_503_rad_dom';
var CH = {
    pump: 'A03/K3',
    source: 'wb-m1w2_170/External Sensor 1', // 411, одновременно подача контура
    ret: 'wb-m1w2_121/External Sensor 1',    // 417
    zones: ['A08/K5', 'A08/K6', 'A09/K1', 'A09/K2', 'A09/K3', 'A09/K4', 'A09/K5']
};
// Модель по заданию #28: 005..009 — отдельные зоны, 010 = K4 OR K5 гостиной.
// В текущем 620 K4/K5 ещё имеют отдельные термостаты 010/011. Их writer не меняется.
var GROUPS = [[0], [1], [2], [3], [4], [5, 6]];

// ПНР-параметры, НЕ подтверждённые объектные уставки/тепловые пределы.
var CFG = {
    targetSourceC: 45, targetMinC: 35, targetMaxC: 60,
    actuatorDelayS: 180, periodS: 30, requestTtlS: 90,
    tempMinC: -20, tempMaxC: 95
};
// Предварительная проверка реакции обратки 417, не доказательство протока.
var RESPONSE = {
    graceS: 300, windowS: 600, stabilityS: 120, sampleS: 30, minSamples: 3,
    minRiseC: 1, sourceToleranceC: 3, returnApproachC: 10, minDeltaC: 3,
    readbackTimeoutS: 120
};
var STATE = {timer: null, mode: '', grant: '', demand: null, target: null, readbackSince: null};
var zoneSince = [null, null, null, null, null, null];
var WD;
function resetWatchdog() {
    WD = {since: null, baseline: 0, badSince: null, samples: 0, lastSample: null};
}
resetWatchdog();

function nowSec() { return Math.floor(new Date().getTime() / 1000); }
function boolOrNull(v) {
    if (v === true || v === 1 || v === '1' || v === 'true' || v === 'ON') return true;
    if (v === false || v === 0 || v === '0' || v === 'false' || v === 'OFF') return false;
    return null;
}
function rb(v) { return boolOrNull(v) === true; }
function rn(v) {
    if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
    v = Number(v);
    return isNaN(v) || !isFinite(v) ? null : v;
}
function clamp(v, min, max) {
    v = rn(v);
    return v === null ? min : Math.max(min, Math.min(max, v));
}
function temp(channel) {
    var v = rn(dev[channel]);
    return v === null || v < CFG.tempMinC || v > CFG.tempMaxC ? null : v;
}
function logMsg(level, event, message) {
    var text = '[отопление][' + SCRIPT + '][503 Радиаторы дом]; ' + event + '=' + message;
    if (level === 'error') log.error(text);
    else if (level === 'warning') log.warning(text);
    else log.info(text);
}

var cells = {};
var nextOrder = 0;
function cell(name, title, type, value, readonly, min, max) {
    nextOrder += 10;
    cells[name] = {title: title, type: type, value: value, readonly: readonly, order: nextOrder};
    if (type === 'range') { cells[name].min = min; cells[name].max = max; }
}
cell('enabled', 'Manager включен', 'switch', false, false);
cell('commissioned', 'ПНР: контур проверен', 'switch', false, false);
cell('outputs_enabled', 'ПНР: физический выход разрешён', 'switch', false, false);
cell('local_permit', 'Локальное разрешение', 'switch', false, false);
cell('manual_commissioning_grant', 'ПНР: ручной GRANT вместо arbiter', 'switch', false, false);
cell('response_commissioned', 'ПНР: параметры response подтверждены', 'switch', false, false);
cell('target_source_c', 'ПНР 503: запрос источника, °C', 'range', CFG.targetSourceC, false, CFG.targetMinC, CFG.targetMaxC);
cell('actuator_delay_s', 'Задержка сервоприводов, с', 'range', CFG.actuatorDelayS, false, 0, 900);
cell('period_s', 'Период расчёта, с', 'range', CFG.periodS, false, 5, 30);
cell('reset_fault', 'Сброс аварии 503 без повторного пуска', 'pushbutton', false, false);
cell('status', 'Состояние', 'text', 'Инициализация', true);
cell('state', 'HM2 state', 'text', 'UNKNOWN', true);
cell('valid', 'HM2 valid', 'switch', false, true);
cell('heat_demand', 'HM2 heat demand', 'switch', false, true);
cell('active_zone_count', 'Активных логических зон (макс. 6)', 'value', 0, true);
cell('physical_active_output_count', 'Активных выходов зон (макс. 7)', 'value', 0, true);
cell('zone_inputs_valid', 'Все зональные состояния доступны', 'switch', false, true);
cell('path_ready', 'Путь готов после задержки', 'switch', false, true);
cell('pump_cmd', 'Расчётная команда насоса 503', 'switch', false, true);
cell('pump_physical_state', 'Readback реле насоса (не проток)', 'switch', false, true);
cell('physical_readback_valid', 'Readback реле доступен (не свежесть)', 'switch', false, true);
cell('source_temp_c', 'Источник / подача 411, °C', 'temperature', 0, true);
cell('return_temp_c', 'Обратка 417, °C', 'temperature', 0, true);
cell('delta_t_c', 'ΔT 411−417, °C', 'value', 0, true);
cell('requested_source_temperature', 'Запрос температуры источника, °C', 'value', 0, true);
cell('request_reason', 'Причина запроса', 'text', '', true);
cell('request_timestamp', 'Время расчёта запроса', 'text', '', true);
cell('request_ttl_s', 'TTL запроса, с', 'value', CFG.requestTtlS, true);
cell('grant_state', 'Grant', 'text', 'NO_ARBITER', true);
cell('grant_reason', 'Причина grant', 'text', 'No arbiter connected; real operation denied', true);
cell('response_status', 'Response watchdog', 'text', 'IDLE', true);
cell('response_elapsed_s', 'Response: прошло, с', 'value', 0, true);
cell('response_rise_c', 'Response: рост обратки 417, °C', 'value', 0, true);
cell('fault_latched', 'Защёлкнутая авария', 'switch', false, true);
cell('fault_text', 'Причина аварии', 'text', '', true);
defineVirtualDevice(VD, {title: 'HM2 503 Радиаторы дом', cells: cells});

// wb-rules не принимает null/undefined в числовые controls.
function sc(name, value) {
    var type = cells[name].type;
    if (type === 'switch') value = value === true;
    else if (type === 'text') value = value === null || value === undefined ? '' : String(value);
    else {
        value = rn(value);
        value = value === null ? 0 : Math.round(value * 10) / 10;
    }
    if (dev[VD + '/' + name] !== value) dev[VD + '/' + name] = value;
}
function writePump(on) {
    try { dev[CH.pump] = on === true; return true; }
    catch (e) { logMsg('error', 'OUTPUT_WRITE_FAILED', CH.pump + ': ' + e); return false; }
}
function safeOutputs() { return writePump(false); }
function latchFault(reason) {
    if (!rb(dev[VD + '/fault_latched'])) logMsg('error', 'FAULT', reason);
    sc('fault_latched', true);
    if (!dev[VD + '/fault_text']) sc('fault_text', reason);
    safeOutputs();
}
function readZones(ts, delay) {
    var active = [], allKnown = true, physical = 0, logical = 0, ready = false;
    var i, j, on, known;
    for (i = 0; i < CH.zones.length; i++) {
        active[i] = boolOrNull(dev[CH.zones[i]]);
        if (active[i] === null) allKnown = false;
        if (active[i] === true) physical++;
    }
    for (i = 0; i < GROUPS.length; i++) {
        on = false; known = true;
        for (j = 0; j < GROUPS[i].length; j++) {
            if (active[GROUPS[i][j]] === null) known = false;
            if (active[GROUPS[i][j]] === true) on = true;
        }
        if (on) logical++;
        if (!on || !known) zoneSince[i] = null;
        else {
            if (zoneSince[i] === null || ts < zoneSince[i]) zoneSince[i] = ts;
            if (ts - zoneSince[i] >= delay) ready = true;
        }
    }
    return {logical: logical, physical: physical, known: allKnown, ready: allKnown && ready};
}
function responseWatchdog(ts, running, pump, source, ret, target) {
    if (!running) { resetWatchdog(); return 'IDLE'; }
    if (!pump) { resetWatchdog(); return 'WAIT_OUTPUT_READBACK'; }
    if (source < target - RESPONSE.sourceToleranceC) {
        resetWatchdog(); return 'WAIT_HOT_SOURCE';
    }
    // Тёплая обратка не требует дальнейшего роста; это не подтверждение протока.
    if (ret >= target - RESPONSE.returnApproachC) {
        resetWatchdog(); return 'RETURN_WARM';
    }
    if (source - ret < RESPONSE.minDeltaC) { resetWatchdog(); return 'WAIT_THERMAL_HEAD'; }
    if (WD.since === null || ts < WD.since) {
        resetWatchdog(); WD.since = ts; WD.baseline = ret;
    }
    if (ret - WD.baseline >= RESPONSE.minRiseC) {
        resetWatchdog(); WD.since = ts; WD.baseline = ret; return 'RESPONSE_OK';
    }
    if (ts - WD.since < RESPONSE.graceS) return 'START_GRACE';
    if (ts - WD.since < RESPONSE.graceS + RESPONSE.windowS) return 'OBSERVING';
    if (WD.badSince === null) WD.badSince = ts;
    if (WD.lastSample === null || ts - WD.lastSample >= RESPONSE.sampleS) {
        WD.samples++; WD.lastSample = ts;
    }
    if (ts - WD.badSince >= RESPONSE.stabilityS && WD.samples >= RESPONSE.minSamples) {
        latchFault('RESPONSE_TIMEOUT_417'); return 'FAULT_LATCHED';
    }
    return 'CONFIRMING_NO_RESPONSE';
}
function resetFault() {
    sc('outputs_enabled', false);
    sc('manual_commissioning_grant', false);
    sc('response_commissioned', false);
    if (!safeOutputs() || temp(CH.source) === null || temp(CH.ret) === null ||
            !readZones(nowSec(), 0).known) {
        logMsg('warning', 'RESET_REJECTED', 'Restore valid inputs and pump write access');
        evaluate(); return;
    }
    sc('fault_latched', false); sc('fault_text', '');
    resetWatchdog(); STATE.readbackSince = null;
    logMsg('info', 'RESET', 'Fault reset; physical operation remains disarmed');
    evaluate();
}
function evaluate() {
    var ts = nowSec();
    // Снимок readback ДО команды, не измерение протока и не проверка свежести MQTT.
    var pumpRaw = boolOrNull(dev[CH.pump]);
    var pump = pumpRaw === true, readbackKnown = pumpRaw !== null;
    var source = temp(CH.source), ret = temp(CH.ret);
    var target = clamp(dev[VD + '/target_source_c'], CFG.targetMinC, CFG.targetMaxC);
    var delay = clamp(dev[VD + '/actuator_delay_s'], 0, 900);
    sc('target_source_c', target); sc('actuator_delay_s', delay);
    var z = readZones(ts, delay);
    var fault = rb(dev[VD + '/fault_latched']);
    var valid = rb(dev[VD + '/enabled']) && rb(dev[VD + '/commissioned']) &&
        source !== null && ret !== null && z.known && !fault;
    var demand = valid && z.logical > 0;
    var cmd = demand && z.ready && rb(dev[VD + '/local_permit']);
    var manual = rb(dev[VD + '/manual_commissioning_grant']);
    var grant = manual ? 'GRANTED' : 'NO_ARBITER';
    var grantReason = manual ? 'MANUAL_COMMISSIONING_GRANT' : 'No arbiter connected; real operation denied';
    var real = cmd && rb(dev[VD + '/outputs_enabled']) && manual && rb(dev[VD + '/response_commissioned']);
    if (STATE.target !== target) { resetWatchdog(); STATE.target = target; }
    if (real && !pump) {
        if (STATE.readbackSince === null || ts < STATE.readbackSince) STATE.readbackSince = ts;
        if (ts - STATE.readbackSince >= RESPONSE.readbackTimeoutS) latchFault('OUTPUT_READBACK_TIMEOUT');
    } else STATE.readbackSince = null;
    var wd = responseWatchdog(ts, real && !rb(dev[VD + '/fault_latched']), pump, source, ret, target);
    if (rb(dev[VD + '/fault_latched'])) real = false;
    // Даже outputs_enabled=false требует активной нулевой команды на каждом расчёте.
    if (!writePump(real)) { latchFault('OUTPUT_WRITE_FAILED'); real = false; }
    fault = rb(dev[VD + '/fault_latched']);
    if (fault) {
        valid = false; demand = false; cmd = false; wd = 'FAULT_LATCHED';
        resetWatchdog(); STATE.readbackSince = null;
    }
    var mode = real ? 'PHYSICAL_MANUAL_COMMISSIONING' : 'SAFE_OUTPUTS';
    if (STATE.mode !== mode) { logMsg('warning', 'OUTPUT_MODE', mode); STATE.mode = mode; }
    if (STATE.grant !== grant) { logMsg('warning', 'GRANT', grant + '; ' + grantReason); STATE.grant = grant; }
    if (STATE.demand !== demand) { logMsg('info', 'DEMAND', demand ? 'ON' : 'OFF'); STATE.demand = demand; }
    var why = fault ? dev[VD + '/fault_text'] : (!valid ? 'INVALID_OR_DISABLED' :
        (!demand ? 'NO_DEMAND' : (!z.ready ? 'ACTUATOR_DELAY' :
        (!rb(dev[VD + '/local_permit']) ? 'LOCAL_NOT_PERMITTED' :
        (!rb(dev[VD + '/outputs_enabled']) ? 'SHADOW_SAFE_OUTPUTS' :
        (!manual ? 'NO_ARBITER' : (!rb(dev[VD + '/response_commissioned']) ?
        'RESPONSE_NOT_COMMISSIONED' : 'MANUAL_COMMISSIONING')))))));
    sc('status', why + '; grant=' + grant + '; response=' + wd);
    sc('state', valid ? (demand ? 'ACTIVE' : 'INACTIVE') : 'UNKNOWN');
    sc('valid', valid); sc('heat_demand', demand);
    sc('active_zone_count', z.logical); sc('physical_active_output_count', z.physical);
    sc('zone_inputs_valid', z.known); sc('path_ready', z.ready); sc('pump_cmd', cmd);
    sc('pump_physical_state', pump); sc('physical_readback_valid', readbackKnown);
    sc('source_temp_c', source); sc('return_temp_c', ret);
    sc('delta_t_c', source !== null && ret !== null ? source - ret : null);
    sc('requested_source_temperature', demand ? target : 0);
    sc('request_reason', why); sc('request_ttl_s', CFG.requestTtlS);
    sc('grant_state', grant); sc('grant_reason', grantReason);
    sc('response_status', wd);
    sc('response_elapsed_s', WD.since === null ? 0 : ts - WD.since);
    sc('response_rise_c', WD.since === null || ret === null ? 0 : ret - WD.baseline);
    // Последнее поле публикуется после расчёта остальных controls.
    sc('request_timestamp', new Date(ts * 1000).toISOString());
}
function restartLoop() {
    var period = clamp(dev[VD + '/period_s'], 5, 30);
    sc('period_s', period);
    if (STATE.timer) clearInterval(STATE.timer);
    STATE.timer = setInterval(evaluate, period * 1000);
}
defineRule('hm2_503_rad_dom_inputs', {
    whenChanged: [CH.source, CH.ret].concat(CH.zones).concat([
        VD + '/enabled', VD + '/commissioned', VD + '/outputs_enabled', VD + '/local_permit',
        VD + '/manual_commissioning_grant', VD + '/response_commissioned',
        VD + '/target_source_c', VD + '/actuator_delay_s'
    ]),
    then: evaluate
});
defineRule('hm2_503_rad_dom_period_changed', {
    whenChanged: VD + '/period_s', then: function () { restartLoop(); evaluate(); }
});
defineRule('hm2_503_rad_dom_reset_fault', {
    whenChanged: VD + '/reset_fault', then: function (value) { if (rb(value)) resetFault(); }
});
// Не доверять сохранённым физическим разрешениям после перезагрузки.
sc('outputs_enabled', false);
sc('manual_commissioning_grant', false);
sc('response_commissioned', false);
if (!safeOutputs()) latchFault('OUTPUT_WRITE_FAILED');
setTimeout(function () {
    restartLoop(); evaluate(); logMsg('info', 'SCRIPT', 'Скрипт загружен');
}, 3000);
