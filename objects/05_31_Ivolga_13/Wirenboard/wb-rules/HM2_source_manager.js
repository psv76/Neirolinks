// HM2_source_manager.js
// HM2 Иволга / #40: писатель уставки котла и контроль источника.
// По умолчанию физическая запись запрещена: все live-разрешения сбрасываются при старте.

var VD = 'hm2_source_manager';
var ARBITER = 'hm2_request_arbiter';

var OT = 'wbe2-i-opentherm_11';
var CH = {
    heatingSetpoint: OT + '/Heating Setpoint',
    sourceTemp: 'wb-m1w2_170/External Sensor 1',
    boilerFault: OT + '/Boiler fault indication',
    invalidConnection: OT + '/Invalid Connection',
    flame: OT + '/Boiler Flame Status',
    chMode: OT + '/Boiler CH mode',
    chEnable: OT + '/Master CH enable',
    errorCode: OT + '/Error Code',
    lowWaterPress: OT + '/Low water press',
    gasFlame: OT + '/GAS Flame fault',
    airPress: OT + '/Air press fault',
    overtemp: OT + '/Water overtemp',
    modulation: OT + '/Burner Modulation Level'
};

// Объектные пределы Иволги. Уставки от потребителей уже ограничены в 501/502/503,
// здесь стоит последний общий ограничитель источника.
var CFG = {
    minSetpointC: 30,
    maxSetpointC: 60,
    sourceHardMaxC: 75,
    sourceHotThresholdC: 35,
    sourceResponseTimeoutS: 900,
    arbiterTtlS: 15,
    writeMinIntervalS: 60,
    writeHysteresisC: 1,
    evalIntervalMs: 5000
};

var cells = {};
function cell(name, type, value, readonly, title) {
    cells[name] = { title: title || name, type: type, value: value, readonly: readonly };
}

// Совместимые поля старой shadow-версии.
cell('state', 'text', 'UNKNOWN', true, 'Состояние');
cell('source_state', 'text', 'NOT_COMMISSIONED', true, 'Состояние источника');
cell('selected_consumer', 'text', '', true, 'Выбранный потребитель');
cell('intended_heating_setpoint', 'value', 0, true, 'Предполагаемая уставка');
cell('no_demand_contract', 'switch', true, true, 'Нет валидного запроса');
cell('write_enabled', 'switch', false, false, 'Устаревший флаг, не используется');
cell('physical_write_grant', 'switch', false, true, 'Физическая запись разрешена');
cell('last_update_ts', 'text', '', true, 'Последнее обновление');
cell('status', 'text', 'STARTUP; запись запрещена', true, 'Статус');

// Новые поля #40.
cell('source_commissioned', 'switch', false, false, 'Источник введён в работу');
cell('source_write_enabled', 'switch', false, false, 'Разрешить запись источника');
cell('manual_source_grant', 'switch', false, false, 'Ручное live-разрешение');
cell('source_endpoint_confirmed', 'switch', false, false, 'Endpoint источника подтверждён');
cell('safe_off_commissioned', 'switch', false, false, 'Safe-off подтверждён');
cell('safe_off_setpoint_c', 'value', 0, false, 'Safe-off уставка');
cell('reset_fault', 'pushbutton', false, false, 'Сброс аварии источника');

cell('requested_heating_setpoint', 'value', 0, true, 'Запрошенная уставка');
cell('limited_heating_setpoint', 'value', 0, true, 'Ограниченная уставка');
cell('written_heating_setpoint', 'value', 0, true, 'Последняя записанная уставка');
cell('last_written_ts', 'text', '', true, 'Последняя запись');

cell('source_temperature_c', 'value', 0, true, 'Температура источника 411');
cell('source_response_status', 'text', 'IDLE', true, 'Контроль отклика источника');
cell('source_response_elapsed_s', 'value', 0, true, 'Ожидание отклика, с');
cell('source_fault_latched', 'switch', false, true, 'Защёлкнутая авария источника');
cell('source_fault_latch_enabled', 'switch', false, false, 'Разрешить защёлкивание аварии источника');
cell('source_interlock', 'switch', false, true, 'Блокировка источника');
cell('fault_reason', 'text', '', true, 'Причина аварии');
cell('boiler_connection', 'text', 'UNKNOWN', true, 'Связь OpenTherm');
cell('boiler_fault', 'switch', false, true, 'Авария котла');
cell('boiler_flame', 'switch', false, true, 'Пламя котла');
cell('boiler_modulation', 'value', 0, true, 'Модуляция горелки');
cell('arbiter_age_s', 'value', -1, true, 'Возраст решения арбитра, с');
cell('write_block_reason', 'text', 'STARTUP', true, 'Почему запись запрещена');

defineVirtualDevice(VD, { title: 'HM2 Иволга — менеджер источника', cells: cells });

var lastWrittenValue = null;
var lastWriteMs = 0;
var demandStartMs = null;
var faultLatched = false;
var faultReason = '';

function sc(name, value) {
    if (dev[VD + '/' + name] !== value) dev[VD + '/' + name] = value;
}

function bool(value) {
    if (value === true || value === 1 || value === '1' || value === 'true') return true;
    if (value === false || value === 0 || value === '0' || value === 'false') return false;
    return null;
}

function num(value) {
    if (typeof value !== 'number' && typeof value !== 'string') return null;
    var n = Number(value);
    return isFinite(n) ? n : null;
}

function positive(value) {
    var n = num(value);
    return n !== null && n > 0 ? n : null;
}

function clamp(value, minValue, maxValue) {
    if (value < minValue) return minValue;
    if (value > maxValue) return maxValue;
    return value;
}

function knownConsumer(consumer) {
    return consumer === 'hm2_501_tp_dom' ||
        consumer === 'hm2_502_gp_dom' ||
        consumer === 'hm2_503_rad_dom';
}

function boolTopic(path) {
    return bool(dev[path]) === true;
}

function readArbiter(now) {
    var result = {
        valid: false,
        noDemand: true,
        consumer: '',
        requested: 0,
        ageS: -1,
        reason: 'ARBITER_READ_ERROR'
    };

    try {
        var valid = bool(dev[ARBITER + '/valid']);
        var noDemand = bool(dev[ARBITER + '/no_demand_contract']);
        var state = dev[ARBITER + '/state'];
        var consumer = dev[ARBITER + '/selected_consumer'];
        var requested = positive(dev[ARBITER + '/selected_requested_temperature']);
        var ts = dev[ARBITER + '/last_update_ts'];
        var parsed = typeof ts === 'string' ? Date.parse(ts) : NaN;
        var age = isFinite(parsed) ? (now - parsed) / 1000 : -1;

        result.noDemand = noDemand === true;
        result.consumer = typeof consumer === 'string' ? consumer : '';
        result.requested = requested === null ? 0 : requested;
        result.ageS = isFinite(age) ? age : -1;

        if (valid !== true) result.reason = 'ARBITER_INVALID';
        else if (state !== 'ACTIVE' && noDemand === true) result.reason = 'NO_DEMAND';
        else if (state !== 'ACTIVE') result.reason = 'ARBITER_NOT_ACTIVE';
        else if (noDemand !== false) result.reason = 'NO_DEMAND_FLAG_NOT_FALSE';
        else if (!knownConsumer(result.consumer)) result.reason = 'UNKNOWN_CONSUMER';
        else if (requested === null) result.reason = 'INVALID_REQUESTED_SETPOINT';
        else if (age < 0 || age > CFG.arbiterTtlS) result.reason = 'ARBITER_STALE';
        else {
            result.valid = true;
            result.noDemand = false;
            result.reason = 'VALID_DEMAND';
        }
    } catch (error) {
        result.reason = 'ARBITER_READ_ERROR';
        log('[HM2 Иволга/HM2_source_manager] ошибка чтения арбитра: ' + String(error));
    }

    return result;
}

function readBoiler() {
    var sourceTemp = num(dev[CH.sourceTemp]);
    var err = num(dev[CH.errorCode]);
    var mod = num(dev[CH.modulation]);

    var invalidConnection = boolTopic(CH.invalidConnection);
    var boilerFault = boolTopic(CH.boilerFault) ||
        boolTopic(CH.lowWaterPress) ||
        boolTopic(CH.gasFlame) ||
        boolTopic(CH.airPress) ||
        boolTopic(CH.overtemp) ||
        (err !== null && err !== 0);

    return {
        sourceTemp: sourceTemp,
        invalidConnection: invalidConnection,
        boilerFault: boilerFault,
        flame: boolTopic(CH.flame),
        chMode: boolTopic(CH.chMode),
        chEnable: boolTopic(CH.chEnable),
        modulation: mod === null ? 0 : mod
    };
}

function gates() {
    return {
        commissioned: bool(dev[VD + '/source_commissioned']) === true,
        writeEnabled: bool(dev[VD + '/source_write_enabled']) === true,
        manualGrant: bool(dev[VD + '/manual_source_grant']) === true,
        endpointConfirmed: bool(dev[VD + '/source_endpoint_confirmed']) === true,
        safeOffCommissioned: bool(dev[VD + '/safe_off_commissioned']) === true,
        sourceFaultLatchEnabled: bool(dev[VD + '/source_fault_latch_enabled']) === true
    };
}

function writeAllowed(now, gate, arbiter, boiler) {
    if (!gate.commissioned) return { allowed: false, reason: 'SOURCE_NOT_COMMISSIONED' };
    if (!gate.writeEnabled) return { allowed: false, reason: 'SOURCE_WRITE_DISABLED' };
    if (!gate.manualGrant) return { allowed: false, reason: 'NO_MANUAL_SOURCE_GRANT' };
    if (!gate.endpointConfirmed) return { allowed: false, reason: 'SOURCE_ENDPOINT_NOT_CONFIRMED' };
    if (!gate.safeOffCommissioned) return { allowed: false, reason: 'SAFE_OFF_NOT_COMMISSIONED' };
    if (faultLatched) return { allowed: false, reason: 'SOURCE_FAULT_LATCHED' };
    if (boiler.invalidConnection) return { allowed: false, reason: 'OPENTHERM_INVALID_CONNECTION' };
    if (boiler.boilerFault) return { allowed: false, reason: 'BOILER_FAULT' };
    if (boiler.sourceTemp === null) return { allowed: false, reason: 'SOURCE_SENSOR_INVALID' };
    if (boiler.sourceTemp >= CFG.sourceHardMaxC) return { allowed: false, reason: 'SOURCE_HARD_MAX' };
    if (!arbiter.valid && !arbiter.noDemand) return { allowed: false, reason: arbiter.reason };
    return { allowed: true, reason: 'ALLOWED' };
}

function writeSetpoint(value, now, force) {
    var shouldWrite = force;
    if (lastWrittenValue === null) shouldWrite = true;
    if (Math.abs(Number(value) - Number(lastWrittenValue)) >= CFG.writeHysteresisC) shouldWrite = true;
    if ((now - lastWriteMs) / 1000 >= CFG.writeMinIntervalS) shouldWrite = true;

    if (!shouldWrite) return false;

    dev[CH.heatingSetpoint] = value;
    lastWrittenValue = value;
    lastWriteMs = now;
    sc('written_heating_setpoint', value);
    sc('last_written_ts', new Date(now).toISOString());
    log('[HM2 Иволга/HM2_source_manager] записана уставка источника: ' + value + ' C');
    return true;
}

function updateResponse(now, arbiter, boiler, gate) {
    var elapsed = 0;
    var status = 'IDLE';

    if (!arbiter.valid) {
        demandStartMs = null;
        sc('source_response_elapsed_s', 0);
        sc('source_response_status', arbiter.noDemand ? 'IDLE' : 'WAIT_VALID_ARBITER');
        return;
    }

    if (demandStartMs === null) demandStartMs = now;
    elapsed = (now - demandStartMs) / 1000;

    if (boiler.sourceTemp === null) {
        status = 'SOURCE_SENSOR_INVALID';
    } else if (boiler.invalidConnection) {
        status = 'OPENTHERM_INVALID_CONNECTION';
    } else if (boiler.boilerFault) {
        status = 'BOILER_FAULT';
    } else if (boiler.sourceTemp >= CFG.sourceHardMaxC) {
        status = 'SOURCE_OVERHEAT';
    } else if (boiler.sourceTemp >= CFG.sourceHotThresholdC || boiler.sourceTemp >= arbiter.requested - 5) {
        status = 'SOURCE_HOT';
    } else if (elapsed < CFG.sourceResponseTimeoutS) {
        status = 'WAIT_HOT_SOURCE';
    } else {
        status = 'SOURCE_RESPONSE_TIMEOUT';
    }

    if ((status === 'SOURCE_RESPONSE_TIMEOUT' || status === 'SOURCE_OVERHEAT' ||
        status === 'BOILER_FAULT' || status === 'OPENTHERM_INVALID_CONNECTION') &&
        gate.sourceFaultLatchEnabled) {
        faultLatched = true;
        faultReason = status;
    }

    sc('source_response_elapsed_s', Math.round(elapsed));
    sc('source_response_status', status);
}

function evaluate() {
    var now = Date.now();

    if (bool(dev[VD + '/reset_fault']) === true) {
        faultLatched = false;
        faultReason = '';
        demandStartMs = null;
        sc('reset_fault', false);
        log('[HM2 Иволга/HM2_source_manager] авария источника сброшена вручную');
    }

    var arbiter = readArbiter(now);
    var boiler = readBoiler();
    var gate = gates();

    var requested = arbiter.valid ? arbiter.requested : 0;
    var limited = arbiter.valid ? clamp(requested, CFG.minSetpointC, CFG.maxSetpointC) : 0;
    var allowed = writeAllowed(now, gate, arbiter, boiler);
    var sourceState = 'NOT_COMMISSIONED';
    var state = 'INACTIVE';
    var status = '';
    var interlock = false;

    if (gate.commissioned && boiler.sourceTemp !== null && boiler.sourceTemp >= CFG.sourceHardMaxC) {
        faultLatched = true;
        faultReason = 'SOURCE_HARD_MAX';
    }

    updateResponse(now, arbiter, boiler, gate);

    if (!gate.commissioned) {
        sourceState = 'NOT_COMMISSIONED';
        status = 'Источник не введён в работу';
    } else if (faultLatched) {
        sourceState = 'SOURCE_FAULT';
        status = 'Защёлкнутая авария источника: ' + faultReason;
        interlock = true;
    } else if (boiler.invalidConnection) {
        sourceState = 'INTERLOCK';
        status = 'OpenTherm недоступен';
        interlock = true;
    } else if (boiler.boilerFault) {
        sourceState = 'SOURCE_FAULT';
        status = 'Котёл сообщает аварию';
        interlock = true;
    } else if (!arbiter.valid && arbiter.noDemand) {
        sourceState = allowed.allowed ? 'SAFE_OFF' : 'NO_DEMAND';
        status = 'Нет валидного запроса тепла';
    } else if (!arbiter.valid) {
        sourceState = 'UNKNOWN';
        status = 'Нет валидного решения арбитра: ' + arbiter.reason;
        interlock = true;
    } else if (!allowed.allowed) {
        sourceState = 'SHADOW_DEMAND';
        status = 'Есть запрос тепла, но физическая запись запрещена: ' + allowed.reason;
    } else if (boiler.sourceTemp === null) {
        sourceState = 'UNKNOWN';
        status = 'Нет валидной температуры источника';
        interlock = true;
    } else if (boiler.sourceTemp < CFG.sourceHotThresholdC && boiler.sourceTemp < limited - 5) {
        sourceState = 'WAIT_HOT_SOURCE';
        status = 'Уставка разрешена, источник ещё не горячий';
    } else {
        sourceState = 'ACTIVE';
        status = 'Источник доступен';
    }

    if (allowed.allowed) {
        sc('physical_write_grant', true);
        if (arbiter.valid) {
            writeSetpoint(limited, now, false);
            state = 'ACTIVE';
        } else if (arbiter.noDemand) {
            var safeOffSetpoint = num(dev[VD + '/safe_off_setpoint_c']);
            if (safeOffSetpoint === null) {
                sourceState = 'INTERLOCK';
                status = 'Safe-off уставка не задана';
                interlock = true;
            } else {
                writeSetpoint(safeOffSetpoint, now, false);
            }
        }
    } else {
        sc('physical_write_grant', false);
    }

    if (!arbiter.valid && !arbiter.noDemand) state = 'UNKNOWN';
    if (faultLatched) state = 'FAULT';

    sc('state', state);
    sc('source_state', sourceState);
    sc('selected_consumer', arbiter.valid ? arbiter.consumer : '');
    sc('intended_heating_setpoint', requested);
    sc('requested_heating_setpoint', requested);
    sc('limited_heating_setpoint', limited);
    sc('no_demand_contract', !arbiter.valid);
    sc('source_temperature_c', boiler.sourceTemp === null ? 0 : boiler.sourceTemp);
    sc('source_fault_latched', faultLatched);
    sc('source_interlock', interlock);
    sc('fault_reason', faultReason);
    sc('boiler_connection', boiler.invalidConnection ? 'INVALID_CONNECTION' : 'OK');
    sc('boiler_fault', boiler.boilerFault);
    sc('boiler_flame', boiler.flame);
    sc('boiler_modulation', boiler.modulation);
    sc('arbiter_age_s', arbiter.ageS);
    sc('write_block_reason', allowed.reason);
    sc('status', status);
    sc('last_update_ts', new Date(now).toISOString());

    if (bool(dev[VD + '/write_enabled']) === true) {
        sc('write_enabled', false);
        log('[HM2 Иволга/HM2_source_manager] устаревший write_enabled сброшен; используйте source_write_enabled');
    }
}

// Никогда не доверяем retained-разрешениям после restart/reload.
Object.keys(cells).forEach(function (name) {
    sc(name, cells[name].value);
});

setTimeout(function () {
    evaluate();
    setInterval(evaluate, CFG.evalIntervalMs);
    log('[HM2 Иволга/HM2_source_manager] старт; физическая запись запрещена, live-разрешения сброшены');
}, 3000);
