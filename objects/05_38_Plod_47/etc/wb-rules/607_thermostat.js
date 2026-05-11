// 607_thermostat.js
// Зональный термостат WB для комнаты "Детская справа".
//
// Логика:
// - воздух выбирает режим: нагрев комнаты или поддержание пола;
// - при нагреве комнаты пол работает по высокой цели;
// - при нормальном воздухе пол работает по низкой цели;
// - при ошибке одного датчика зона работает по оставшемуся;
// - при ошибке обоих датчиков сервоприводы закрываются.

// -------------------- ПАСПОРТ СКРИПТА --------------------

var SYSTEM_NAME = "отопление";
var SCRIPT_NAME = "607_thermostat";
var ZONE_NAME = "детская справа";

var VDEVICE = "heating_child_right_thermostat";
var TITLE = "Термостат детская справа";

// Реальные каналы датчиков.
var AIR_TEMP_TOPIC = "wb-msw-v4_142/Temperature";              // температура воздуха
var FLOOR_TEMP_TOPIC = "wb-m1w2_126/External Sensor 2";        // температура пола

// Реальные исполнительные каналы.
var VALVE_607_TOPIC = "wb-mr6cu_224/K1";                       // 607 Сервопривод 1
var VALVE_608_TOPIC = "wb-mr6cu_224/K2";                       // 608 Сервопривод 2

// -------------------- УСТАВКИ И ОГРАНИЧЕНИЯ --------------------

var DEFAULT_TARGET_TEMP = 22.0;

var DEFAULT_FLOOR_HOLD_TARGET = 25.0;      // цель пола при поддержании
var DEFAULT_FLOOR_HEAT_TARGET = 29.0;      // цель пола при нагреве комнаты

var AIR_TARGET_MIN = 15;
var AIR_TARGET_MAX = 30;

var FLOOR_HOLD_MIN = 18;
var FLOOR_HOLD_MAX = 30;

var FLOOR_HEAT_MIN = 20;
var FLOOR_HEAT_MAX = 35;

// Воздух: нагрев включается ниже уставки - 0.3 и выключается выше уставки + 0.3.
var AIR_HYSTERESIS = 0.3;

// Пол: открыть ниже цели - 1.0, закрыть на цели.
var FLOOR_HYSTERESIS = 1.0;

// Границы правдоподобности датчиков.
var AIR_VALID_MIN = -20;
var AIR_VALID_MAX = 60;
var FLOOR_VALID_MIN = -20;
var FLOOR_VALID_MAX = 70;

// Публикация температур в виртуальные каналы для Sprut.hub.
var TEMP_PUBLISH_MIN_INTERVAL_MS = 60000;
var TEMP_PUBLISH_MIN_DELTA = 0.1;

// -------------------- СОСТОЯНИЕ СКРИПТА --------------------

var STATE = {
    initialized: false,

    airHeatMode: false,
    floorHeatCommand: false,

    lastStateText: null,
    lastHeatCommand: null,

    lastAirPublishTs: 0,
    lastFloorPublishTs: 0,
    lastPublishedAir: null,
    lastPublishedFloor: null
};

// -------------------- ВИРТУАЛЬНОЕ УСТРОЙСТВО --------------------

defineVirtualDevice(VDEVICE, {
    title: TITLE,
    cells: {
        target_state: {
            title: "Термостат",
            type: "switch",
            value: true,
            readonly: false,
            order: 10
        },
        air_temperature: {
            title: "Температура воздуха",
            type: "temperature",
            value: 0,
            readonly: true,
            order: 20
        },
        target_temperature: {
            title: "Уставка воздуха",
            type: "range",
            value: DEFAULT_TARGET_TEMP,
            min: AIR_TARGET_MIN,
            max: AIR_TARGET_MAX,
            readonly: false,
            order: 30
        },
        state: {
            title: "Состояние",
            type: "text",
            value: "Инициализация",
            readonly: true,
            order: 40
        },
        floor_temperature: {
            title: "Температура пола",
            type: "temperature",
            value: 0,
            readonly: true,
            order: 50
        },
        floor_min_temperature: {
            title: "Пол при поддержании",
            type: "range",
            value: DEFAULT_FLOOR_HOLD_TARGET,
            min: FLOOR_HOLD_MIN,
            max: FLOOR_HOLD_MAX,
            readonly: false,
            order: 60
        },
        floor_max_temperature: {
            title: "Пол при нагреве",
            type: "range",
            value: DEFAULT_FLOOR_HEAT_TARGET,
            min: FLOOR_HEAT_MIN,
            max: FLOOR_HEAT_MAX,
            readonly: false,
            order: 70
        },
        current_state: {
            title: "Sprut: текущий режим",
            type: "switch",
            value: false,
            readonly: true,
            order: 800
        }
    }
});

// -------------------- ОБЩИЕ ФУНКЦИИ --------------------

function nowMs() {
    return new Date().getTime();
}

function round1(value) {
    return Math.round(Number(value) * 10) / 10;
}

function clamp(value, minValue, maxValue) {
    var n = Number(value);

    if (!isFinite(n)) {
        return minValue;
    }

    if (n < minValue) {
        return minValue;
    }

    if (n > maxValue) {
        return maxValue;
    }

    return n;
}

function setIfChanged(topic, value) {
    if (dev[topic] !== value) {
        dev[topic] = value;
    }
}

function setNumberIfChanged(topic, value) {
    var oldValue = Number(dev[topic]);
    var newValue = Number(value);

    if (!isFinite(oldValue) || Math.abs(oldValue - newValue) > 0.001) {
        dev[topic] = newValue;
    }
}

function setBoolIfChanged(topic, value) {
    var newValue = !!value;

    if (!!dev[topic] !== newValue) {
        dev[topic] = newValue;
    }
}

function formatNumber(value) {
    var n = Number(value);

    if (!isFinite(n)) {
        return "нет данных";
    }

    return String(round1(n));
}

function formatParams(params) {
    var list = [];
    var k;

    if (!params) {
        return "";
    }

    for (k in params) {
        if (params.hasOwnProperty(k)) {
            if (params[k] !== undefined && params[k] !== null && params[k] !== "") {
                list.push(k + "=" + params[k]);
            }
        }
    }

    if (list.length === 0) {
        return "";
    }

    return "; " + list.join("; ");
}

// -------------------- СИСТЕМНЫЙ ЖУРНАЛ --------------------

function writeLog(eventName, eventText, params) {
    var message = "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "][" + ZONE_NAME + "]; " +
        eventName + "=" + eventText + formatParams(params);

    if (eventName === "АВАРИЯ") {
        log.error(message);
        return;
    }

    if (eventName === "ОШИБКА") {
        log.warning(message);
        return;
    }

    log.info(message);
}

function baseParams(zoneState, reason) {
    return {
        "причина": reason,
        "режим": zoneState.modeName,
        "воздух": formatNumber(zoneState.air),
        "уставка": formatNumber(zoneState.target),
        "пол": formatNumber(zoneState.floor),
        "цель_пола": formatNumber(zoneState.floorTarget),
        "пол_поддержание": formatNumber(zoneState.floorHoldTarget),
        "пол_нагрев": formatNumber(zoneState.floorHeatTarget),
        "канал": VALVE_607_TOPIC + ", " + VALVE_608_TOPIC
    };
}

function settingParams(zoneState, settingName) {
    return {
        "причина": "изменение настройки",
        "настройка": settingName,
        "воздух": formatNumber(zoneState.air),
        "уставка": formatNumber(zoneState.target),
        "пол": formatNumber(zoneState.floor),
        "пол_поддержание": formatNumber(zoneState.floorHoldTarget),
        "пол_нагрев": formatNumber(zoneState.floorHeatTarget)
    };
}

// -------------------- ЧТЕНИЕ СОСТОЯНИЯ --------------------

function isValidAir(value) {
    var n = Number(value);
    return isFinite(n) && n >= AIR_VALID_MIN && n <= AIR_VALID_MAX;
}

function isValidFloor(value) {
    var n = Number(value);
    return isFinite(n) && n >= FLOOR_VALID_MIN && n <= FLOOR_VALID_MAX;
}

function readZoneState() {
    var airRaw = dev[AIR_TEMP_TOPIC];
    var floorRaw = dev[FLOOR_TEMP_TOPIC];

    var target = round1(clamp(dev[VDEVICE + "/target_temperature"], AIR_TARGET_MIN, AIR_TARGET_MAX));
    var floorHoldTarget = round1(clamp(dev[VDEVICE + "/floor_min_temperature"], FLOOR_HOLD_MIN, FLOOR_HOLD_MAX));
    var floorHeatTarget = round1(clamp(dev[VDEVICE + "/floor_max_temperature"], FLOOR_HEAT_MIN, FLOOR_HEAT_MAX));

    if (floorHeatTarget < floorHoldTarget) {
        floorHeatTarget = floorHoldTarget;
    }

    setNumberIfChanged(VDEVICE + "/target_temperature", target);
    setNumberIfChanged(VDEVICE + "/floor_min_temperature", floorHoldTarget);
    setNumberIfChanged(VDEVICE + "/floor_max_temperature", floorHeatTarget);

    return {
        enabled: !!dev[VDEVICE + "/target_state"],

        air: isValidAir(airRaw) ? round1(airRaw) : NaN,
        floor: isValidFloor(floorRaw) ? round1(floorRaw) : NaN,

        airValid: isValidAir(airRaw),
        floorValid: isValidFloor(floorRaw),

        target: target,
        floorHoldTarget: floorHoldTarget,
        floorHeatTarget: floorHeatTarget,

        floorTarget: NaN,
        modeName: ""
    };
}

// -------------------- ПУБЛИКАЦИЯ ДЛЯ SPRUT.HUB --------------------

function shouldPublishTemperature(lastValue, newValue, lastTs, force) {
    if (force) {
        return true;
    }

    if (lastValue === null) {
        return true;
    }

    if (Math.abs(Number(lastValue) - Number(newValue)) >= TEMP_PUBLISH_MIN_DELTA) {
        return true;
    }

    return (nowMs() - lastTs) >= TEMP_PUBLISH_MIN_INTERVAL_MS;
}

function publishTemperatures(force, zoneState) {
    if (zoneState.airValid) {
        if (shouldPublishTemperature(STATE.lastPublishedAir, zoneState.air, STATE.lastAirPublishTs, force)) {
            setNumberIfChanged(VDEVICE + "/air_temperature", zoneState.air);
            STATE.lastPublishedAir = zoneState.air;
            STATE.lastAirPublishTs = nowMs();
        }
    }

    if (zoneState.floorValid) {
        if (shouldPublishTemperature(STATE.lastPublishedFloor, zoneState.floor, STATE.lastFloorPublishTs, force)) {
            setNumberIfChanged(VDEVICE + "/floor_temperature", zoneState.floor);
            STATE.lastPublishedFloor = zoneState.floor;
            STATE.lastFloorPublishTs = nowMs();
        }
    }
}

// -------------------- РАСЧЁТ --------------------

function updateAirMode(zoneState) {
    if (!zoneState.airValid) {
        return;
    }

    if (zoneState.air <= zoneState.target - AIR_HYSTERESIS) {
        STATE.airHeatMode = true;
    }

    if (zoneState.air >= zoneState.target + AIR_HYSTERESIS) {
        STATE.airHeatMode = false;
    }
}

function calculateFloorCommand(floorTemp, floorTarget) {
    if (floorTemp <= floorTarget - FLOOR_HYSTERESIS) {
        STATE.floorHeatCommand = true;
    }

    if (floorTemp >= floorTarget) {
        STATE.floorHeatCommand = false;
    }

    return STATE.floorHeatCommand;
}

function calculateDecision(zoneState) {
    var heat;

    updateAirMode(zoneState);

    if (!zoneState.enabled) {
        STATE.airHeatMode = false;
        STATE.floorHeatCommand = false;
        zoneState.floorTarget = NaN;
        zoneState.modeName = "выключен";

        return {
            heat: false,
            state: "Выключен",
            reason: "термостат выключен",
            eventName: "СОСТОЯНИЕ"
        };
    }

    if (!zoneState.airValid && !zoneState.floorValid) {
        STATE.airHeatMode = false;
        STATE.floorHeatCommand = false;
        zoneState.floorTarget = NaN;
        zoneState.modeName = "нет датчиков";

        return {
            heat: false,
            state: "Нет обоих датчиков, сервоприводы закрыты",
            reason: "нет корректных значений воздуха и пола",
            eventName: "АВАРИЯ"
        };
    }

    if (!zoneState.airValid && zoneState.floorValid) {
        zoneState.floorTarget = zoneState.floorHoldTarget;
        zoneState.modeName = "по полу";

        heat = calculateFloorCommand(zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            state: heat ? "Нет воздуха, грею пол" : "Нет воздуха, пол в норме",
            reason: "нет датчика воздуха, работа по полу",
            eventName: "ОШИБКА"
        };
    }

    if (zoneState.airValid && !zoneState.floorValid) {
        zoneState.floorTarget = NaN;
        zoneState.modeName = "по воздуху";

        heat = STATE.airHeatMode;

        return {
            heat: heat,
            state: heat ? "Нет пола, грею воздух" : "Нет пола, ожидание",
            reason: "нет датчика пола, работа по воздуху",
            eventName: "ОШИБКА"
        };
    }

    if (STATE.airHeatMode) {
        zoneState.floorTarget = zoneState.floorHeatTarget;
        zoneState.modeName = "нагрев воздуха";

        heat = calculateFloorCommand(zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            state: heat ? "Нагревает" : "Пол нагрет",
            reason: heat ? "воздух ниже уставки, пол ниже цели нагрева" : "воздух ниже уставки, но пол уже нагрет",
            eventName: "СОСТОЯНИЕ"
        };
    }

    zoneState.floorTarget = zoneState.floorHoldTarget;
    zoneState.modeName = "поддержание пола";

    heat = calculateFloorCommand(zoneState.floor, zoneState.floorTarget);

    return {
        heat: heat,
        state: heat ? "Поддержание пола" : "Ожидание",
        reason: heat ? "воздух в норме, пол ниже цели поддержания" : "воздух и пол в норме",
        eventName: "СОСТОЯНИЕ"
    };
}

// -------------------- УПРАВЛЕНИЕ СЕРВОПРИВОДАМИ --------------------

function writeValve(topic, value, zoneState, reason) {
    var params = baseParams(zoneState, reason);

    params["канал"] = topic;
    params["значение в канал"] = value ? "ON" : "OFF";

    if (dev[topic] === undefined) {
        writeLog("ОШИБКА", "Канал сервопривода недоступен", params);
        return false;
    }

    if (!!dev[topic] !== !!value) {
        dev[topic] = !!value;
    }

    return true;
}

function applyValves(heat, zoneState, reason) {
    var text;
    var params = baseParams(zoneState, reason);

    if (STATE.lastHeatCommand === heat) {
        return;
    }

    STATE.lastHeatCommand = heat;

    text = heat ? "Открыть сервоприводы зоны" : "Закрыть сервоприводы зоны";
    params["значение в канал"] = heat ? "ON" : "OFF";

    writeLog("КОМАНДА", text, params);

    writeValve(VALVE_607_TOPIC, heat, zoneState, reason);
    writeValve(VALVE_608_TOPIC, heat, zoneState, reason);
}

function applyDecision(decision, zoneState) {
    var params = baseParams(zoneState, decision.reason);
    var stateChanged = (STATE.lastStateText !== decision.state);

    setIfChanged(VDEVICE + "/state", decision.state);
    setBoolIfChanged(VDEVICE + "/current_state", decision.heat);

    if (stateChanged) {
        writeLog(decision.eventName, decision.state, params);
    }

    STATE.lastStateText = decision.state;

    applyValves(decision.heat, zoneState, decision.reason);
}

// -------------------- ОСНОВНОЙ РАСЧЁТ --------------------

function evaluateThermostat(forcePublish) {
    var zoneState = readZoneState();
    var decision;

    publishTemperatures(!!forcePublish, zoneState);

    decision = calculateDecision(zoneState);
    applyDecision(decision, zoneState);
}

// -------------------- НАСТРОЙКИ --------------------

function logUserSetting(settingName) {
    var zoneState;

    if (!STATE.initialized) {
        return;
    }

    zoneState = readZoneState();
    writeLog("НАСТРОЙКА", "Изменена настройка термостата", settingParams(zoneState, settingName));
}

// -------------------- ПРАВИЛА --------------------

defineRule("thermostat_child_right_607_air_changed", {
    whenChanged: AIR_TEMP_TOPIC,
    then: function () {
        evaluateThermostat(false);
    }
});

defineRule("thermostat_child_right_607_floor_changed", {
    whenChanged: FLOOR_TEMP_TOPIC,
    then: function () {
        evaluateThermostat(false);
    }
});

defineRule("thermostat_child_right_607_target_temp_changed", {
    whenChanged: VDEVICE + "/target_temperature",
    then: function () {
        logUserSetting("Уставка воздуха");
        evaluateThermostat(true);
    }
});

defineRule("thermostat_child_right_607_target_state_changed", {
    whenChanged: VDEVICE + "/target_state",
    then: function () {
        logUserSetting("Термостат");
        evaluateThermostat(true);
    }
});

defineRule("thermostat_child_right_607_floor_hold_changed", {
    whenChanged: VDEVICE + "/floor_min_temperature",
    then: function () {
        logUserSetting("Пол при поддержании");
        evaluateThermostat(true);
    }
});

defineRule("thermostat_child_right_607_floor_heat_changed", {
    whenChanged: VDEVICE + "/floor_max_temperature",
    then: function () {
        logUserSetting("Пол при нагреве");
        evaluateThermostat(true);
    }
});

defineRule("thermostat_child_right_607_periodic_sync", {
    when: cron("*/1 * * * *"),
    then: function () {
        evaluateThermostat(true);
    }
});

// -------------------- СТАРТ --------------------

writeLog("СКРИПТ", "Скрипт загружен", {
    "канал": VALVE_607_TOPIC + ", " + VALVE_608_TOPIC
});

evaluateThermostat(true);
STATE.initialized = true;

writeLog("СКРИПТ", "Стартовая инициализация завершена", {
    "канал": VALVE_607_TOPIC + ", " + VALVE_608_TOPIC
});
