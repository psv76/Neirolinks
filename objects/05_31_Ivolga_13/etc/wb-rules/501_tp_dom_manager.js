// 501_tp_dom_manager.js
// 05 31 Иволга 13 — HM2 manager контура 501: тёплый пол дома / паркет.
// Использует общий модуль /etc/wb-rules-modules/MixingController.js.
// Безопасный старт: enabled=false, commissioned=false, outputs_enabled=false.
//
// Fix 2026-09-10:
// - wb-rules не принимает null/undefined в числовые controls виртуального устройства;
// - diagnostic/output cells теперь нормализуются перед записью через sc().

// Hardened output contract: blocked operation actively writes three safe zeros.
var MixingController = require('MixingController');

var SCRIPT = '501_tp_dom_manager';
var VD = 'hm2_501_tp_dom';

var CH = {
    pump: 'A03/K1',
    valveEnable: 'A05/Channel 1 Switch',
    valvePosition: 'A05/Channel 1 Dimming Level',
    supply: 'wb-m1w2_141/External Sensor 1', // 413
    ret: 'wb-m1w2_141/External Sensor 2',    // 414
    source: 'wb-m1w2_170/External Sensor 1', // 411
    zones: ['A08/K1', 'A08/K2', 'A08/K3', 'A08/K4']
};

var CFG = {
    periodS: 30,
    requestTtlS: 90,
    actuatorDelayS: 180,
    targetSupplyC: 30,
    requestedSourceMarginC: 5,
    tempMinC: -20,
    tempMaxC: 95,
    tuning: {
        bandC: 0.5,
        biasC: 0.2,
        farErrorC: 3.0,
        fastHoldColdS: 120,
        fastHoldHotS: 120,
        fastMinStepPct: 2,
        fastMaxStepPct: 6,
        trimHoldColdS: 180,
        trimHoldHotS: 180,
        trimMinStepPct: 1,
        trimMaxStepPct: 3,
        pctPerCCold: 1.2,
        pctPerCHot: 1.2,
        reverseLockS: 300,
        trendOkCPerMin: 0.4,
        trendSlowCPerMin: 0.1,
        stagnationS: 900,
        postMoveSettleS: 120,
        minPosPct: 0,
        maxPosPct: 100,
        hardMaxC: 42,
        supplyValidMinC: -20,
        supplyValidMaxC: 80,
        sensorBadLimit: 3,
        sourceGuardEnabled: true,
        sourceMarginC: 3,
        sourceValidMinC: -20,
        sourceValidMaxC: 95,
        startupCapEnabled: true,
        startupDurationS: 600,
        startupMaxPosPct: 25,
        enableRetryS: 60,
        safeCloseOnDisable: true
    }
};

var CELL_TYPE = {
    response_rise_c: 'number',
    response_elapsed_s: 'number',
    response_status: 'text',
    physical_active_output_count: 'number',
    physical_readback_valid: 'switch',
    valve_enable_physical: 'switch',
    valve_position_physical: 'number',
    pump_physical_state: 'switch',
    grant_reason: 'text',
    grant_state: 'text',
    response_commissioned: 'switch',
    manual_commissioning_grant: 'switch',
    enabled: 'switch',
    commissioned: 'switch',
    outputs_enabled: 'switch',
    local_permit: 'switch',
    freeze: 'switch',
    status: 'text',
    state: 'text',
    valid: 'switch',
    heat_demand: 'switch',
    requested_supply_c: 'number',
    requested_source_temperature: 'number',
    request_reason: 'text',
    request_timestamp: 'text',
    request_ttl_s: 'number',
    path_ready: 'switch',
    fault_latched: 'switch',
    fault_text: 'text',
    active_zone_count: 'number',
    zone_demand: 'switch',
    pump_cmd: 'switch',
    supply_temp_c: 'number',
    return_temp_c: 'number',
    source_temp_c: 'number',
    delta_t_c: 'number',
    valve_position_cmd: 'number',
    phase: 'text',
    trend_c_per_min: 'number',
    effective_target_c: 'number',
    source_guard_active: 'switch',
    startup_remaining_s: 'number',
    mixing_sensor_fault: 'switch',
    bad_sensor_count: 'number',
    mixing_alarm_active: 'switch',
    mixing_alarm_text: 'text',
    mixing_status: 'text',
    commissioned_state: 'switch',
    local_permit_state: 'switch',
    outputs_enabled_state: 'switch',
    target_supply_c: 'number',
    actuator_delay_s: 'number',
    period_s: 'number',
    manual_valve_pct: 'number'
};

var STATE = {
    timer: null,
    demandWasOn: false,
    demandSince: 0,
    lastStatus: '',
    lastPump: null,
    lastFault: false
};

function nowSec()
{
    return Math.floor(new Date().getTime() / 1000);
}

function rb(v)
{
    return v === true || v === 1 || v === '1' || v === 'true' || v === 'ON';
}

function rn(v)
{
    if (v === null || v === undefined || v === '')
        return null;

    v = Number(v);
    return isNaN(v) || !isFinite(v) ? null : v;
}

function clamp(v, min, max)
{
    v = Number(v);
    if (isNaN(v) || !isFinite(v))
        v = min;
    if (v < min)
        return min;
    if (v > max)
        return max;
    return v;
}

function r1(v)
{
    v = rn(v);
    return v === null ? null : Math.round(v * 10) / 10;
}

function r2(v)
{
    v = rn(v);
    return v === null ? null : Math.round(v * 100) / 100;
}

function normalizeCellValue(name, value)
{
    var t = CELL_TYPE[name] || '';

    if (t === 'switch')
        return value === true;

    if (t === 'number')
    {
        value = rn(value);
        return value === null ? 0 : value;
    }

    if (t === 'text')
    {
        if (value === null || value === undefined)
            return '';
        return String(value);
    }

    if (value === null || value === undefined)
        return '';

    return value;
}

function sc(name, value)
{
    var p = VD + '/' + name;
    var safeValue = normalizeCellValue(name, value);

    if (dev[p] !== safeValue)
        dev[p] = safeValue;
}

function logMsg(level, eventName, text)
{
    var msg = '[отопление][' + SCRIPT + '][501 ТП дом]; ' + eventName + '=' + text;
    if (level === 'error')
        log.error(msg);
    else if (level === 'warning')
        log.warning(msg);
    else
        log.info(msg);
}

function outputsEnabled()
{
    return rb(dev[VD + '/outputs_enabled']);
}

// Callbacks accept calculated commands only. Physical writes occur after all checks.
function writeOut(topic, value) { return true; }

function physicalWrite(topic, value)
{
    try { dev[topic] = value; return true; }
    catch (e) { logMsg('error', 'OUTPUT_WRITE_FAILED', topic + ': ' + e); return false; }
}

function safeOutputs()
{
    // Attempt every output even if another write fails; repeat on each safety tick.
    physicalWrite(CH.pump, false);
    physicalWrite(CH.valvePosition, 0);
    physicalWrite(CH.valveEnable, false);
}

function latchFault(reason)
{
    if (!rb(dev[VD + '/fault_latched'])) logMsg('error', 'FAULT', reason);
    sc('fault_latched', true);
    if (!dev[VD + '/fault_text']) sc('fault_text', reason);
    safeOutputs();
}

var WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0 };
var zoneSince = [0, 0, 0];
var lastMode = '';
var lastRealRun = false;
var lastTarget = null;
var readbackWaitSince = 0;
function resetWatchdog() { WD = { since: 0, baseline: 0, badSince: 0, samples: 0, lastSample: 0 }; }

// Object commissioning values; must be explicitly confirmed before active operation.
var RESPONSE = { graceS: 300, windowS: 600, stabilityS: 120,
    sampleS: 30, minSamples: 3, minRiseC: 1, minValvePct: 5, targetBandC: 1 };
function responseWatchdog(now, running, pump, valveOn, position, supply, source, target)
{
    if (!running) { resetWatchdog(); return 'IDLE'; }
    if (!pump || !valveOn || position === null || position < RESPONSE.minValvePct) {
        resetWatchdog(); return 'WAIT_OUTPUT_READBACK';
    }
    if (source < target + CFG.tuning.sourceMarginC) {
        resetWatchdog(); return 'WAIT_HOT_SOURCE';
    }
    if (supply >= target - RESPONSE.targetBandC) {
        resetWatchdog(); return 'AT_TARGET';
    }
    if (!WD.since) { WD.since = now; WD.baseline = supply; }
    if (supply - WD.baseline >= RESPONSE.minRiseC) {
        WD.since = now; WD.baseline = supply; WD.badSince = 0; WD.samples = 0;
        return 'RESPONSE_OK';
    }
    if (now - WD.since < RESPONSE.graceS) return 'START_GRACE';
    if (now - WD.since < RESPONSE.graceS + RESPONSE.windowS) return 'OBSERVING';
    if (!WD.badSince) WD.badSince = now;
    if (!WD.lastSample || now - WD.lastSample >= RESPONSE.sampleS) {
        WD.samples++; WD.lastSample = now;
    }
    if (now - WD.badSince >= RESPONSE.stabilityS && WD.samples >= RESPONSE.minSamples) {
        latchFault('RESPONSE_TIMEOUT_413'); return 'FAULT_LATCHED';
    }
    return 'CONFIRMING_NO_RESPONSE';
}

function temp(path)
{
    var v = rn(dev[path]);
    if (v === null || v < CFG.tempMinC || v > CFG.tempMaxC)
        return null;
    return v;
}

function countZones()
{
    var i;
    var n = 0;
    for (i = 0; i < CH.zones.length; i++)
    {
        if (rb(dev[CH.zones[i]]))
            n++;
    }
    return n;
}

function getTarget()
{
    var v = clamp(dev[VD + '/target_supply_c'], 20, 38);
    sc('target_supply_c', v);
    return v;
}

function getDelay()
{
    var v = clamp(dev[VD + '/actuator_delay_s'], 0, 900);
    sc('actuator_delay_s', v);
    return v;
}

var mix = MixingController.create({
    initialValvePositionPct: 0,
    tuning: CFG.tuning
}, {
    writeValvePosition: function (pct) {
        return writeOut(CH.valvePosition, Number(pct));
    },
    writeValveEnable: function (enabled) {
        return writeOut(CH.valveEnable, !!enabled);
    }
});

function publishMix(r)
{
    sc('valve_position_cmd', r1(r.valvePositionPct));
    sc('phase', r.phase || '');
    sc('trend_c_per_min', r2(r.trendCPerMin));
    sc('effective_target_c', r1(r.effectiveTargetC));
    sc('source_guard_active', r.sourceGuardActive === true);
    sc('startup_remaining_s', r.startupRemainingS || 0);
    sc('mixing_sensor_fault', r.sensorFault === true);
    sc('bad_sensor_count', r.badSensorCount || 0);
    sc('mixing_alarm_active', r.alarmActive === true);
    sc('mixing_alarm_text', r.alarmText || '');
    sc('mixing_status', r.status || '');
}

function resetFault()
{
    // Reset is a stopped recovery operation, never an implicit restart.
    safeOutputs();
    sc('outputs_enabled', false);
    sc('manual_commissioning_grant', false);
    var t = temp(CH.supply);
    if (t === null || temp(CH.source) === null || t >= CFG.tuning.hardMaxC - 2) {
        logMsg('warning', 'RESET_REJECTED', 'Restore valid sensors and supply below hardMax - 2 C');
        evaluate('reset_rejected'); return;
    }
    sc('fault_latched', false); sc('fault_text', '');
    mix.reset({ valvePositionPct: 0, pumpOn: false, now: nowSec() });
    resetWatchdog();
    logMsg('info', 'RESET', 'Fault reset; physical operation remains disarmed');
    evaluate('reset_fault');
}

function evaluate(reason)
{
    var ts = nowSec();
    // Capture MQTT readback BEFORE issuing commands. This is not proof of flow/stem travel.
    var pumpRaw = dev[CH.pump], pos = rn(dev[CH.valvePosition]);
    var enableRaw = dev[CH.valveEnable];
    var pump = rb(pumpRaw), valveOn = rb(enableRaw);
    var readbackKnown = pumpRaw !== undefined && pumpRaw !== null &&
        enableRaw !== undefined && enableRaw !== null && pos !== null;
    var enabled = rb(dev[VD + '/enabled']);
    var commissioned = rb(dev[VD + '/commissioned']);
    var permit = rb(dev[VD + '/local_permit']);
    var supply = temp(CH.supply), source = temp(CH.source), ret = temp(CH.ret);
    var sensorsOk = supply !== null && source !== null;
    var target = getTarget(), delay = getDelay();
    var physicalCount = countZones();
    var groups = [rb(dev[CH.zones[0]]) || rb(dev[CH.zones[3]]),
        rb(dev[CH.zones[1]]), rb(dev[CH.zones[2]])];
    var zones = 0, ready = false, i;
    for (i = 0; i < groups.length; i++) {
        if (!groups[i]) zoneSince[i] = 0;
        else {
            zones++;
            if (!zoneSince[i]) zoneSince[i] = ts;
            if (ts - zoneSince[i] >= delay) ready = true;
        }
    }
    if (supply !== null && supply >= CFG.tuning.hardMaxC) latchFault('SUPPLY_HARD_MAX');
    var fault = rb(dev[VD + '/fault_latched']);
    var valid = enabled && commissioned && sensorsOk && !fault;
    var cmd = valid && zones > 0 && ready && permit;
    // No arbiter adapter exists yet. Only an explicit, visible commissioning grant.
    var manual = rb(dev[VD + '/manual_commissioning_grant']);
    var grant = manual ? 'GRANTED' : 'NO_ARBITER';
    var grantReason = manual ? 'MANUAL_COMMISSIONING_GRANT' : 'No arbiter connected; real operation denied';
    var real = cmd && outputsEnabled() && manual && rb(dev[VD + '/response_commissioned']);
    var mode = real ? 'PHYSICAL_MANUAL_COMMISSIONING' : 'SAFE_OUTPUTS';
    if (mode + ':' + grantReason !== lastMode) {
        logMsg('warning', 'OUTPUT_MODE', mode + '; ' + grantReason);
        lastMode = mode + ':' + grantReason;
    }
    // Never carry a calculated shadow opening into the first physical step.
    if (real !== lastRealRun) mix.reset({ valvePositionPct: 0, pumpOn: false, now: ts });
    lastRealRun = real;
    var r = mix.step({ now: ts, enabled: cmd, pumpOn: cmd,
        supplyTempC: supply, sourceTempC: source, targetC: cmd ? target : null,
        sensorOffsetC: 0, valveEnableOn: real ? valveOn : true, phaseMode: 'auto',
        freeze: manual && rb(dev[VD + '/freeze']),
        manualValvePct: clamp(dev[VD + '/manual_valve_pct'], 0, 100) });
    if (r.alarmActive) latchFault(r.alarmText || 'MIXING_ALARM');
    if (lastTarget !== target) { resetWatchdog(); lastTarget = target; }
    if (real && (!readbackKnown || !pump || !valveOn)) {
        if (!readbackWaitSince) readbackWaitSince = ts;
        if (ts - readbackWaitSince >= 120) latchFault('OUTPUT_READBACK_TIMEOUT');
    } else readbackWaitSince = 0;
    var wd = responseWatchdog(ts, real, pump, valveOn, pos, supply, source, target);
    fault = rb(dev[VD + '/fault_latched']);
    if (fault) { real = false; cmd = false; valid = false; }
    if (!real) safeOutputs();
    else {
        // Pump and valve power first; opening waits for a subsequent readback.
        var ok = physicalWrite(CH.pump, true);
        ok = physicalWrite(CH.valveEnable, true) && ok;
        ok = physicalWrite(CH.valvePosition, pump && valveOn ? r.valvePositionPct : 0) && ok;
        if (!ok) { latchFault('OUTPUT_WRITE_FAILED'); fault = true; valid = false; cmd = false; }
    }
    if (fault) r = mix.reset({ valvePositionPct: 0, pumpOn: false, now: ts });
    sc('grant_state', grant); sc('grant_reason', grantReason);
    sc('pump_cmd', cmd);
    sc('pump_physical_state', pump); sc('valve_position_physical', pos);
    sc('valve_enable_physical', valveOn); sc('physical_readback_valid', readbackKnown);
    sc('response_status', wd); sc('response_elapsed_s', WD.since ? ts - WD.since : 0);
    sc('response_rise_c', WD.since && supply !== null ? supply - WD.baseline : 0);
    sc('physical_active_output_count', physicalCount); sc('active_zone_count', zones);
    sc('zone_demand', zones > 0); sc('path_ready', ready);
    sc('state', valid ? (zones ? 'ACTIVE' : 'INACTIVE') : 'UNKNOWN');
    sc('valid', valid); sc('heat_demand', valid && zones > 0);
    sc('requested_supply_c', valid && zones ? target : 0);
    sc('requested_source_temperature', valid && zones ? target + CFG.requestedSourceMarginC : 0);
    sc('request_timestamp', new Date(ts * 1000).toISOString());
    sc('request_ttl_s', CFG.requestTtlS);
    var why = fault ? dev[VD + '/fault_text'] : (!cmd ? 'LOCAL_NOT_READY_OR_NO_DEMAND' :
        (!outputsEnabled() ? 'SHADOW_SAFE_OUTPUTS' : (!manual ? 'NO_ARBITER' :
        (!rb(dev[VD + '/response_commissioned']) ? 'RESPONSE_NOT_COMMISSIONED' : 'MANUAL_COMMISSIONING'))));
    sc('request_reason', why); sc('status', why + '; grant=' + grant + '; response=' + wd);
    sc('supply_temp_c', supply); sc('source_temp_c', source); sc('return_temp_c', ret);
    sc('delta_t_c', supply !== null && ret !== null ? supply - ret : 0);
    sc('commissioned_state', commissioned); sc('local_permit_state', permit);
    sc('outputs_enabled_state', outputsEnabled()); publishMix(r);
}

function restartLoop()
{
    var p = clamp(dev[VD + '/period_s'], 5, 30);

    sc('period_s', p);

    if (STATE.timer)
        clearInterval(STATE.timer);

    STATE.timer = setInterval(function () {
        evaluate('periodic');
    }, p * 1000);
}

defineVirtualDevice(VD, {
    title: 'HM2 501 ТП дом / паркет',
    cells: {
        response_rise_c: {"title": "Response: рост подачи, C", "type": "value", "value": 0, "readonly": true},
        response_elapsed_s: {"title": "Response: прошло, с", "type": "value", "value": 0, "readonly": true},
        response_status: {"title": "Response watchdog", "type": "text", "value": "IDLE", "readonly": true},
        physical_active_output_count: {"title": "Активных физических выходов зон", "type": "value", "value": 0, "readonly": true},
        physical_readback_valid: {"title": "Readback доступен", "type": "switch", "value": false, "readonly": true},
        valve_enable_physical: {"title": "Readback питания клапана", "type": "switch", "value": false, "readonly": true},
        valve_position_physical: {"title": "Readback выхода клапана, % (не положение штока)", "type": "value", "value": 0, "readonly": true},
        pump_physical_state: {"title": "Readback реле насоса (не датчик потока)", "type": "switch", "value": false, "readonly": true},
        grant_reason: {"title": "Причина grant", "type": "text", "value": "No arbiter connected", "readonly": true},
        grant_state: {"title": "Grant", "type": "text", "value": "NO_ARBITER", "readonly": true},
        response_commissioned: {"title": "ПНР: параметры response watchdog подтверждены", "type": "switch", "value": false, "readonly": false},
        manual_commissioning_grant: {"title": "ПНР: ручной GRANT вместо арбитра", "type": "switch", "value": false, "readonly": false},
        enabled: { title: 'Manager включен', type: 'switch', value: false, order: 10 },
        commissioned: { title: 'Контур введён в эксплуатацию', type: 'switch', value: false, order: 20 },
        outputs_enabled: { title: 'Физические выходы разрешены', type: 'switch', value: false, order: 30 },
        local_permit: { title: 'Локальное разрешение до arbiter', type: 'switch', value: false, order: 40 },
        target_supply_c: { title: 'Цель подачи ТП, °C', type: 'range', value: CFG.targetSupplyC, min: 20, max: 38, order: 50 },
        actuator_delay_s: { title: 'Задержка открытия сервоприводов, с', type: 'range', value: CFG.actuatorDelayS, min: 0, max: 900, order: 60 },
        period_s: { title: 'Период расчёта, с', type: 'range', value: CFG.periodS, min: 5, max: 30, order: 70 },
        freeze: { title: 'ПНР: удерживать клапан вручную', type: 'switch', value: false, order: 80 },
        manual_valve_pct: { title: 'ПНР: положение клапана, %', type: 'range', value: 0, min: 0, max: 100, order: 90 },
        reset_fault: { title: 'Сброс аварии 501', type: 'pushbutton', order: 100 },

        status: { title: 'Состояние', type: 'text', value: 'Инициализация', readonly: true, order: 200 },
        state: { title: 'HM2 state', type: 'text', value: 'UNKNOWN', readonly: true, order: 210 },
        valid: { title: 'HM2 valid', type: 'switch', value: false, readonly: true, order: 220 },
        heat_demand: { title: 'HM2 heat demand', type: 'switch', value: false, readonly: true, order: 230 },
        requested_supply_c: { title: 'Запрошенная подача контура, °C', type: 'value', value: 0, readonly: true, order: 240 },
        requested_source_temperature: { title: 'Запрошенная общая подача, °C', type: 'value', value: 0, readonly: true, order: 250 },
        request_reason: { title: 'Причина запроса', type: 'text', value: '', readonly: true, order: 260 },
        request_timestamp: { title: 'Время запроса', type: 'text', value: '', readonly: true, order: 270 },
        request_ttl_s: { title: 'TTL запроса, с', type: 'value', value: CFG.requestTtlS, readonly: true, order: 280 },
        path_ready: { title: 'Path ready', type: 'switch', value: false, readonly: true, order: 290 },
        fault_latched: { title: 'Защёлкнутая авария', type: 'switch', value: false, readonly: true, order: 300 },
        fault_text: { title: 'Текст аварии', type: 'text', value: '', readonly: true, order: 310 },

        active_zone_count: { title: 'Открытых зон ТП', type: 'value', value: 0, readonly: true, order: 400 },
        zone_demand: { title: 'Есть запрос зон', type: 'switch', value: false, readonly: true, order: 410 },
        pump_cmd: { title: 'Расчётная команда насоса 501', type: 'switch', value: false, readonly: true, order: 420 },
        supply_temp_c: { title: 'Подача ТП 413, °C', type: 'temperature', value: 0, readonly: true, order: 430 },
        return_temp_c: { title: 'Обратка ТП 414, °C', type: 'temperature', value: 0, readonly: true, order: 440 },
        source_temp_c: { title: 'Общая подача 411, °C', type: 'temperature', value: 0, readonly: true, order: 450 },
        delta_t_c: { title: 'ΔT ТП дом', type: 'value', value: 0, readonly: true, order: 460 },

        valve_position_cmd: { title: 'Команда клапана 560, %', type: 'value', value: 0, readonly: true, order: 500 },
        phase: { title: 'Фаза регулятора', type: 'text', value: '', readonly: true, order: 510 },
        trend_c_per_min: { title: 'Тренд подачи, °C/мин', type: 'value', value: 0, readonly: true, order: 520 },
        effective_target_c: { title: 'Эффективная цель, °C', type: 'value', value: 0, readonly: true, order: 530 },
        source_guard_active: { title: 'Source guard', type: 'switch', value: false, readonly: true, order: 540 },
        startup_remaining_s: { title: 'Startup cap осталось, с', type: 'value', value: 0, readonly: true, order: 550 },
        mixing_sensor_fault: { title: 'Ошибка датчика подачи', type: 'switch', value: false, readonly: true, order: 560 },
        bad_sensor_count: { title: 'Плохих замеров подряд', type: 'value', value: 0, readonly: true, order: 570 },
        mixing_alarm_active: { title: 'Авария регулятора', type: 'switch', value: false, readonly: true, order: 580 },
        mixing_alarm_text: { title: 'Текст аварии регулятора', type: 'text', value: '', readonly: true, order: 590 },
        mixing_status: { title: 'Статус MixingController', type: 'text', value: '', readonly: true, order: 600 },

        commissioned_state: { title: 'Диагностика: commissioned', type: 'switch', value: false, readonly: true, order: 900 },
        local_permit_state: { title: 'Диагностика: local permit', type: 'switch', value: false, readonly: true, order: 910 },
        outputs_enabled_state: { title: 'Диагностика: outputs enabled', type: 'switch', value: false, readonly: true, order: 920 }
    }
});

defineRule('hm2_501_tp_dom_inputs', {
    whenChanged: [
        CH.supply,
        CH.ret,
        CH.source,
        CH.zones[0],
        CH.zones[1],
        CH.zones[2],
        CH.zones[3],
        VD + '/enabled',
        VD + '/commissioned',
        VD + '/outputs_enabled',
        VD + '/local_permit',
        VD + '/manual_commissioning_grant',
        VD + '/response_commissioned',
        VD + '/target_supply_c',
        VD + '/actuator_delay_s',
        VD + '/freeze',
        VD + '/manual_valve_pct'
    ],
    then: function () {
        evaluate('input_changed');
    }
});

defineRule('hm2_501_tp_dom_period_changed', {
    whenChanged: VD + '/period_s',
    then: function () {
        restartLoop();
        evaluate('period_changed');
    }
});

defineRule('hm2_501_tp_dom_reset_fault', {
    whenChanged: VD + '/reset_fault',
    then: function (newValue) {
        if (newValue)
            resetFault();
    }
});

// Re-arm is always explicit after reload; persistent true values cannot start outputs.
sc('outputs_enabled', false);
sc('manual_commissioning_grant', false);
safeOutputs();
setTimeout(function () {
    restartLoop();
    evaluate('startup');
    logMsg('info', 'SCRIPT', 'Скрипт загружен');
}, 3000);

