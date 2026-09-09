// 501_tp_dom_manager.js
// 05 31 Иволга 13 — HM2 manager контура 501: тёплый пол дома / паркет.
// Использует общий модуль /etc/wb-rules-modules/MixingController.js.
// Безопасный старт: enabled=false, commissioned=false, outputs_enabled=false.

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

function fmt(v)
{
    v = r1(v);
    return v === null ? 'нет данных' : String(v);
}

function sc(name, value)
{
    var p = VD + '/' + name;
    if (dev[p] !== value)
        dev[p] = value;
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

function writeOut(topic, value)
{
    if (!outputsEnabled())
        return true;

    if (dev[topic] !== value)
        dev[topic] = value;

    return true;
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

function setPump(on)
{
    on = !!on;

    if (outputsEnabled() && rb(dev[CH.pump]) !== on)
        dev[CH.pump] = on;

    sc('pump_on', on);

    if (STATE.lastPump !== on)
    {
        logMsg('info', 'КОМАНДА', on ? 'Включить насос A03/K1' : 'Выключить насос A03/K1');
        STATE.lastPump = on;
    }
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
    var r;

    sc('fault_latched', false);
    STATE.lastFault = false;

    r = mix.reset({
        valvePositionPct: 0,
        pumpOn: false,
        now: nowSec()
    });

    publishMix(r);
    logMsg('info', 'RESET', 'Авария контура 501 сброшена');
    evaluate('reset_fault');
}

function evaluate(reason)
{
    var ts = nowSec();
    var enabled = rb(dev[VD + '/enabled']);
    var commissioned = rb(dev[VD + '/commissioned']);
    var permit = rb(dev[VD + '/local_permit']);
    var fault = rb(dev[VD + '/fault_latched']);
    var zones = countZones();
    var demand = zones > 0;
    var delayS = getDelay();
    var target = getTarget();
    var tSupply = temp(CH.supply);
    var tReturn = temp(CH.ret);
    var tSource = temp(CH.source);
    var sensorsOk = tSupply !== null && tSource !== null;
    var pathReady = false;
    var canRun;
    var reqSource = null;
    var state;
    var why;
    var r;
    var status;

    if (demand && !STATE.demandWasOn)
    {
        STATE.demandSince = ts;
        logMsg('info', 'DEMAND', 'Появился запрос зон ТП дом');
    }

    if (!demand && STATE.demandWasOn)
    {
        STATE.demandSince = 0;
        logMsg('info', 'DEMAND', 'Запрос зон ТП дом снят');
    }

    STATE.demandWasOn = demand;

    if (demand && STATE.demandSince > 0 && ts - STATE.demandSince >= delayS)
        pathReady = true;

    if (demand)
        reqSource = target + CFG.requestedSourceMarginC;

    if (!enabled)
        why = 'manager disabled';
    else if (!commissioned)
        why = 'not commissioned';
    else if (fault)
        why = 'fault latched';
    else if (!demand)
        why = 'no active zones';
    else if (!sensorsOk)
        why = 'required sensor invalid';
    else if (!permit)
        why = 'local permit is off';
    else if (!pathReady)
        why = 'waiting actuator delay';
    else
        why = 'ready';

    canRun = enabled && commissioned && demand && sensorsOk && permit && pathReady && !fault;

    setPump(canRun);

    r = mix.step({
        now: ts,
        enabled: canRun,
        pumpOn: canRun,
        supplyTempC: dev[CH.supply],
        sourceTempC: dev[CH.source],
        targetC: canRun ? target : null,
        sensorOffsetC: 0,
        valveEnableOn: rb(dev[CH.valveEnable]),
        phaseMode: 'auto',
        freeze: rb(dev[VD + '/freeze']),
        manualValvePct: rn(dev[VD + '/manual_valve_pct']) || 0
    });

    if (r.alarmActive === true && !fault)
    {
        fault = true;
        sc('fault_latched', true);
        logMsg('error', 'АВАРИЯ', 'Защёлкнута авария MixingController: ' + (r.alarmText || r.status || 'unknown'));
    }

    if (fault && !STATE.lastFault)
        logMsg('warning', 'FAULT', 'Контур 501 исключён до сброса аварии');

    STATE.lastFault = fault;

    state = fault || !(enabled && commissioned && sensorsOk) ? 'UNKNOWN' : (demand ? 'ACTIVE' : 'INACTIVE');

    status =
        'state=' + state +
        '; demand=' + (demand ? 'yes' : 'no') +
        '; path_ready=' + (pathReady ? 'yes' : 'no') +
        '; permit=' + (permit ? 'yes' : 'no') +
        '; pump=' + (canRun ? 'on' : 'off') +
        '; reason=' + why +
        '; mix=' + (r.status || '');

    sc('state', state);
    sc('valid', enabled && commissioned && sensorsOk && !fault);
    sc('heat_demand', enabled && commissioned && demand && sensorsOk && !fault);
    sc('requested_supply_c', demand ? target : null);
    sc('requested_source_temperature', reqSource);
    sc('request_reason', why);
    sc('request_timestamp', demand ? new Date(ts * 1000).toISOString() : '');
    sc('request_ttl_s', CFG.requestTtlS);
    sc('path_ready', pathReady);
    sc('fault_latched', fault);
    sc('fault_text', fault ? (r.alarmText || r.status || 'fault latched') : '');
    sc('status', status);

    sc('active_zone_count', zones);
    sc('zone_demand', demand);
    sc('supply_temp_c', r1(tSupply));
    sc('return_temp_c', r1(tReturn));
    sc('source_temp_c', r1(tSource));
    sc('delta_t_c', tSupply !== null && tReturn !== null ? r1(tSupply - tReturn) : null);
    sc('commissioned_state', commissioned);
    sc('local_permit_state', permit);
    sc('outputs_enabled_state', outputsEnabled());

    publishMix(r);

    if (status !== STATE.lastStatus)
    {
        logMsg(fault ? 'warning' : 'info', 'STATE', status + '; trigger=' + (reason || 'evaluate'));
        STATE.lastStatus = status;
    }
}

function restartLoop()
{
    var p = clamp(dev[VD + '/period_s'], 5, 300);

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
        enabled: { title: 'Manager включен', type: 'switch', value: false, order: 10 },
        commissioned: { title: 'Контур введён в эксплуатацию', type: 'switch', value: false, order: 20 },
        outputs_enabled: { title: 'Физические выходы разрешены', type: 'switch', value: false, order: 30 },
        local_permit: { title: 'Локальное разрешение до arbiter', type: 'switch', value: false, order: 40 },
        target_supply_c: { title: 'Цель подачи ТП, °C', type: 'range', value: CFG.targetSupplyC, min: 20, max: 38, order: 50 },
        actuator_delay_s: { title: 'Задержка открытия сервоприводов, с', type: 'range', value: CFG.actuatorDelayS, min: 0, max: 900, order: 60 },
        period_s: { title: 'Период расчёта, с', type: 'range', value: CFG.periodS, min: 5, max: 300, order: 70 },
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
        pump_on: { title: 'Насос 501', type: 'switch', value: false, readonly: true, order: 420 },
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

setTimeout(function () {
    restartLoop();
    evaluate('startup');
    logMsg('info', 'SCRIPT', 'Скрипт загружен');
}, 3000);
