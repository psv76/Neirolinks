// 600_thermostats.js
// Каскадная логика зональных термостатов WB: воздух выбирает режим отопления,
// пол ограничивает/разрешает фактическое открытие сервоприводов, а запрос тепла
// зоны считается только по команде открытия физических сервоприводов.
// Физические каналы, которые пишет скрипт:
// - wb-mr6cu_218/K1, wb-mr6cu_218/K2, wb-mr6cu_218/K3, wb-mr6cu_218/K4, wb-mr6cu_218/K5, wb-mr6cu_218/K6
// - wb-mr6cu_224/K1, wb-mr6cu_224/K2, wb-mr6cu_224/K3, wb-mr6cu_224/K4, wb-mr6cu_224/K5, wb-mr6cu_224/K6
// - wb-mr6cu_219/K1

// -------------------- ПАСПОРТ СКРИПТА --------------------

var SYSTEM_NAME = "отопление";
var SCRIPT_NAME = "600_thermostats";

// ZONES сформирован только по листу "Зоны" файла "Каналы отопления.xlsx".
var ZONES = [
    {
        id: "601",
        context: "гостевая",
        model: "NL_combo_thermostat",
        vdevice: "NL_combo_thermostat_601",
        title: "Термостат гостевая",
        airTopic: "wb-msw-v4_67/Temperature",
        floorTopic: "wb-m1w2_121/External Sensor 1",
        valveTopics: ["wb-mr6cu_218/K1"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "602",
        context: "душевая",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_602",
        title: "Термостат душевая",
        airTopic: "",
        floorTopic: "wb-m1w2_121/External Sensor 2",
        valveTopics: ["wb-mr6cu_218/K2"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "603",
        context: "кухня",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_603",
        title: "Термостат кухня",
        airTopic: "",
        floorTopic: "wb-m1w2_128/External Sensor 2",
        valveTopics: ["wb-mr6cu_218/K3"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "604",
        context: "выход на террасу",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_604",
        title: "Термостат выход на террасу",
        airTopic: "",
        floorTopic: "wb-m1w2_108/External Sensor 2",
        valveTopics: ["wb-mr6cu_218/K4"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "605",
        context: "гостиная",
        model: "NL_climate_thermostat",
        vdevice: "NL_climate_thermostat_605",
        title: "Термостат гостиная",
        airTopic: "wb-msw-v4_203/Temperature",
        floorTopic: "wb-m1w2_123_2/External Sensor 1",
        valveTopics: ["wb-mr6cu_218/K5"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: 25,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "606",
        context: "прихожая",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_606",
        title: "Термостат прихожая",
        airTopic: "",
        floorTopic: "wb-m1w2_120/External Sensor 1",
        valveTopics: ["wb-mr6cu_218/K6"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "607",
        context: "детская справа",
        model: "NL_combo_thermostat",
        vdevice: "NL_combo_thermostat_607",
        title: "Термостат детская справа",
        airTopic: "wb-msw-v4_142/Temperature",
        floorTopic: "wb-m1w2_126/External Sensor 2",
        valveTopics: ["wb-mr6cu_224/K1", "wb-mr6cu_224/K2"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "609",
        context: "детская слева",
        model: "NL_combo_thermostat",
        vdevice: "NL_combo_thermostat_609",
        title: "Термостат детская слева",
        airTopic: "",
        floorTopic: "wb-m1w2_126/External Sensor 1",
        valveTopics: ["wb-mr6cu_224/K3", "wb-mr6cu_224/K4"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "611",
        context: "гардероб",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_611",
        title: "Термостат гардероб",
        airTopic: "",
        floorTopic: "wb-m1w2_150/External Sensor 2",
        valveTopics: ["wb-mr6cu_224/K5"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "612",
        context: "спальня",
        model: "NL_climate_thermostat",
        vdevice: "NL_climate_thermostat_612",
        title: "Термостат спальня",
        airTopic: "wb-msw-v4_140/Temperature",
        floorTopic: "wb-m1w2_150/External Sensor 1",
        valveTopics: ["wb-mr6cu_224/K6"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: 25,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    },
    {
        id: "613",
        context: "ванная",
        model: "NL_simple_thermostat",
        vdevice: "NL_simple_thermostat_613",
        title: "Термостат ванная",
        airTopic: "",
        floorTopic: "",
        valveTopics: ["wb-mr6cu_219/K1"],
        defaultTarget: 22,
        defaultFloorHold: 25,
        defaultFloorHeat: 29,
        defaultCooling: null,
        airMin: 15,
        airMax: 30,
        airHysteresis: 0.3,
        floorHysteresis: 1
    }
];

// -------------------- УСТАВКИ И ОГРАНИЧЕНИЯ --------------------

var FLOOR_HOLD_MIN = 18;
var FLOOR_HOLD_MAX = 30;
var FLOOR_HEAT_MIN = 20;
var FLOOR_HEAT_MAX = 35;
var COOLING_MIN = 18;
var COOLING_MAX = 35;

var AIR_VALID_MIN = -20;
var AIR_VALID_MAX = 60;
var FLOOR_VALID_MIN = -20;
var FLOOR_VALID_MAX = 70;

var TEMP_PUBLISH_MIN_INTERVAL_MS = 60000;
var TEMP_PUBLISH_MIN_DELTA = 0.1;

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

function hasTopic(topic) {
    return typeof topic === "string" && topic !== "";
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

function writeLog(zone, eventName, eventText, params) {
    var message = "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "][" + zone.context + "]; " +
        eventName + "=" + eventText + formatParams(params);

    if (eventName === "АВАРИЯ" || eventName === "WATCHDOG") {
        log.error(message);
        return;
    }

    if (eventName === "ОШИБКА") {
        log.warning(message);
        return;
    }

    log.info(message);
}

function zoneValveText(zone) {
    return zone.valveTopics.join(", ");
}

function baseParams(zone, zoneState, reason) {
    return {
        "причина": reason,
        "режим": zoneState.modeName,
        "воздух": formatNumber(zoneState.air),
        "уставка": formatNumber(zoneState.target),
        "пол": formatNumber(zoneState.floor),
        "цель_пола": formatNumber(zoneState.floorTarget),
        "пол_поддержание": formatNumber(zoneState.floorHoldTarget),
        "пол_нагрев": formatNumber(zoneState.floorHeatTarget),
        "канал": zoneValveText(zone)
    };
}

function settingParams(zone, zoneState, settingName) {
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

// -------------------- ВИРТУАЛЬНЫЕ УСТРОЙСТВА --------------------

function makeSwitchCell(title, value, readonly, order) {
    return {
        title: title,
        type: "switch",
        value: !!value,
        readonly: !!readonly,
        order: order
    };
}

function makeTemperatureCell(title, order) {
    return {
        title: title,
        type: "temperature",
        value: 0,
        readonly: true,
        order: order
    };
}

function makeRangeCell(title, value, minValue, maxValue, order) {
    return {
        title: title,
        type: "range",
        value: value,
        min: minValue,
        max: maxValue,
        readonly: false,
        order: order
    };
}

function makeTextCell(title, value, order) {
    return {
        title: title,
        type: "text",
        value: value,
        readonly: true,
        order: order
    };
}

function defineComboOrClimateDevice(zone) {
    var cells = {
        target_state: makeSwitchCell("Термостат", true, false, 10),
        air_temperature: makeTemperatureCell("Температура воздуха", 20),
        target_temperature: makeRangeCell("Уставка воздуха", zone.defaultTarget, zone.airMin, zone.airMax, 30),
        state: makeTextCell("Состояние", "Инициализация", 40),
        floor_temperature: makeTemperatureCell("Температура пола", 50),
        floor_min_temperature: makeRangeCell("Пол при поддержании", zone.defaultFloorHold, FLOOR_HOLD_MIN, FLOOR_HOLD_MAX, 60),
        floor_max_temperature: makeRangeCell("Пол при нагреве", zone.defaultFloorHeat, FLOOR_HEAT_MIN, FLOOR_HEAT_MAX, 70),
        current_state: makeSwitchCell("Sprut: текущий режим", false, true, 800)
    };

    if (zone.model === "NL_climate_thermostat") {
        cells.cooling_temperature = makeRangeCell("Порог охлаждения", zone.defaultCooling, COOLING_MIN, COOLING_MAX, 90);
    }

    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: cells
    });
}

function defineSimpleDevice(zone) {
    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: {
            target_state: makeSwitchCell("Термостат", true, false, 10),
            temperature: makeTemperatureCell("Температура", 20),
            target_temperature: makeRangeCell("Уставка", zone.defaultFloorHold, zone.airMin, zone.airMax, 30),
            current_state: makeSwitchCell("Sprut: текущий режим", false, true, 800)
        }
    });
}

function defineZoneDevice(zone) {
    if (zone.model === "NL_simple_thermostat") {
        defineSimpleDevice(zone);
        return;
    }

    defineComboOrClimateDevice(zone);
}

// -------------------- СОСТОЯНИЕ ЗОН --------------------

function makeRuntimeState() {
    return {
        initialized: false,
        airHeatMode: false,
        floorHeatCommand: false,
        lastStateText: null,
        lastHeatCommand: null,
        lastActualOpen: null,
        lastAirPublishTs: 0,
        lastFloorPublishTs: 0,
        lastPublishedAir: null,
        lastPublishedFloor: null
    };
}

function isValidAir(value) {
    var n = Number(value);
    return isFinite(n) && n >= AIR_VALID_MIN && n <= AIR_VALID_MAX;
}

function isValidFloor(value) {
    var n = Number(value);
    return isFinite(n) && n >= FLOOR_VALID_MIN && n <= FLOOR_VALID_MAX;
}

function readTargetState(zone) {
    var raw = dev[zone.vdevice + "/target_state"];

    if (raw === 0 || raw === "0" || raw === false || raw === "OFF" || raw === 2 || raw === "2" || raw === "COOL") {
        return false;
    }

    return true;
}

function readZoneState(zone) {
    var airRaw = hasTopic(zone.airTopic) ? dev[zone.airTopic] : undefined;
    var floorRaw = hasTopic(zone.floorTopic) ? dev[zone.floorTopic] : undefined;
    var airValid = hasTopic(zone.airTopic) && isValidAir(airRaw);
    var floorValid = hasTopic(zone.floorTopic) && isValidFloor(floorRaw);
    var target;
    var floorHoldTarget;
    var floorHeatTarget;
    var coolingTarget;

    if (zone.model === "NL_simple_thermostat") {
        target = round1(clamp(dev[zone.vdevice + "/target_temperature"], zone.airMin, zone.airMax));
        floorHoldTarget = target;
    } else {
        target = round1(clamp(dev[zone.vdevice + "/target_temperature"], zone.airMin, zone.airMax));
        floorHoldTarget = round1(clamp(dev[zone.vdevice + "/floor_min_temperature"], FLOOR_HOLD_MIN, FLOOR_HOLD_MAX));
    }

    floorHeatTarget = round1(clamp(dev[zone.vdevice + "/floor_max_temperature"], FLOOR_HEAT_MIN, FLOOR_HEAT_MAX));

    if (floorHeatTarget < floorHoldTarget) {
        floorHeatTarget = floorHoldTarget;
    }

    setNumberIfChanged(zone.vdevice + "/target_temperature", target);

    if (zone.model !== "NL_simple_thermostat") {
        setNumberIfChanged(zone.vdevice + "/floor_min_temperature", floorHoldTarget);
        setNumberIfChanged(zone.vdevice + "/floor_max_temperature", floorHeatTarget);
    }

    if (zone.model === "NL_climate_thermostat") {
        coolingTarget = round1(clamp(dev[zone.vdevice + "/cooling_temperature"], COOLING_MIN, COOLING_MAX));
        setNumberIfChanged(zone.vdevice + "/cooling_temperature", coolingTarget);
    }

    return {
        enabled: readTargetState(zone),
        air: airValid ? round1(airRaw) : NaN,
        floor: floorValid ? round1(floorRaw) : NaN,
        airValid: airValid,
        floorValid: floorValid,
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

function publishTemperatureValue(topic, value, lastValue, lastTs, force) {
    if (shouldPublishTemperature(lastValue, value, lastTs, force)) {
        setNumberIfChanged(topic, value);
        return true;
    }

    return false;
}

function publishTemperatures(zone, zoneState, force) {
    if (zone.model === "NL_simple_thermostat") {
        if (zoneState.floorValid) {
            if (publishTemperatureValue(zone.vdevice + "/temperature", zoneState.floor, zone.state.lastPublishedFloor, zone.state.lastFloorPublishTs, force)) {
                zone.state.lastPublishedFloor = zoneState.floor;
                zone.state.lastFloorPublishTs = nowMs();
            }
        }
        return;
    }

    if (zoneState.airValid) {
        if (publishTemperatureValue(zone.vdevice + "/air_temperature", zoneState.air, zone.state.lastPublishedAir, zone.state.lastAirPublishTs, force)) {
            zone.state.lastPublishedAir = zoneState.air;
            zone.state.lastAirPublishTs = nowMs();
        }
    }

    if (zoneState.floorValid) {
        if (publishTemperatureValue(zone.vdevice + "/floor_temperature", zoneState.floor, zone.state.lastPublishedFloor, zone.state.lastFloorPublishTs, force)) {
            zone.state.lastPublishedFloor = zoneState.floor;
            zone.state.lastFloorPublishTs = nowMs();
        }
    }
}

// -------------------- РАСЧЁТ --------------------

function updateAirMode(zone, zoneState) {
    if (!zoneState.airValid) {
        return;
    }

    if (zoneState.air <= zoneState.target - zone.airHysteresis) {
        zone.state.airHeatMode = true;
    }

    if (zoneState.air >= zoneState.target + zone.airHysteresis) {
        zone.state.airHeatMode = false;
    }
}

function calculateFloorCommand(zone, floorTemp, floorTarget) {
    if (floorTemp <= floorTarget - zone.floorHysteresis) {
        zone.state.floorHeatCommand = true;
    }

    if (floorTemp >= floorTarget) {
        zone.state.floorHeatCommand = false;
    }

    return zone.state.floorHeatCommand;
}

function calculateDecision(zone, zoneState) {
    var heat;

    updateAirMode(zone, zoneState);

    if (!zoneState.enabled) {
        zone.state.airHeatMode = false;
        zone.state.floorHeatCommand = false;
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
        zone.state.airHeatMode = false;
        zone.state.floorHeatCommand = false;
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
        heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            state: heat ? "Нет воздуха, грею пол" : "Нет воздуха, пол в норме",
            reason: "нет датчика воздуха, работа по полу",
            eventName: hasTopic(zone.airTopic) ? "ОШИБКА" : "СОСТОЯНИЕ"
        };
    }

    if (zoneState.airValid && !zoneState.floorValid) {
        zoneState.floorTarget = NaN;
        zoneState.modeName = "по воздуху";
        heat = zone.state.airHeatMode;

        return {
            heat: heat,
            state: heat ? "Нет пола, грею воздух" : "Нет пола, ожидание",
            reason: "нет датчика пола, работа по воздуху",
            eventName: hasTopic(zone.floorTopic) ? "ОШИБКА" : "СОСТОЯНИЕ"
        };
    }

    if (zone.state.airHeatMode) {
        zoneState.floorTarget = zoneState.floorHeatTarget;
        zoneState.modeName = "нагрев воздуха";
        heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            state: heat ? "Нагревает" : "Пол нагрет",
            reason: heat ? "воздух ниже уставки, пол ниже цели нагрева" : "воздух ниже уставки, но пол уже нагрет",
            eventName: "СОСТОЯНИЕ"
        };
    }

    zoneState.floorTarget = zoneState.floorHoldTarget;
    zoneState.modeName = "поддержание пола";
    heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

    return {
        heat: heat,
        state: heat ? "Поддержание пола" : "Ожидание",
        reason: heat ? "воздух в норме, пол ниже цели поддержания" : "воздух и пол в норме",
        eventName: "СОСТОЯНИЕ"
    };
}

// -------------------- УПРАВЛЕНИЕ СЕРВОПРИВОДАМИ --------------------

function writeValve(zone, topic, value, zoneState, reason) {
    var params = baseParams(zone, zoneState, reason);

    params["канал"] = topic;
    params["значение в канал"] = value ? "ON" : "OFF";

    if (dev[topic] === undefined) {
        writeLog(zone, "ОШИБКА", "Канал сервопривода недоступен", params);
        return false;
    }

    if (!!dev[topic] !== !!value) {
        dev[topic] = !!value;
    }

    return true;
}

function applyValves(zone, heat, zoneState, reason) {
    var text;
    var params = baseParams(zone, zoneState, reason);
    var i;
    var ok;
    var actualOpen = false;

    if (zone.state.lastHeatCommand !== heat) {
        zone.state.lastHeatCommand = heat;
        text = heat ? "Открыть сервоприводы зоны" : "Закрыть сервоприводы зоны";
        params["значение в канал"] = heat ? "ON" : "OFF";
        writeLog(zone, "КОМАНДА", text, params);
    }

    for (i = 0; i < zone.valveTopics.length; i++) {
        ok = writeValve(zone, zone.valveTopics[i], heat, zoneState, reason);
        if (ok && heat) {
            actualOpen = true;
        }
    }

    if (zone.state.lastActualOpen !== actualOpen) {
        zone.state.lastActualOpen = actualOpen;
        params = baseParams(zone, zoneState, reason);
        params["фактически_открыто"] = actualOpen ? "да" : "нет";
        writeLog(zone, "РЕЗУЛЬТАТ", actualOpen ? "Сервоприводы зоны открыты" : "Сервоприводы зоны закрыты", params);
    }

    return actualOpen;
}

function publishState(zone, stateText) {
    if (zone.model !== "NL_simple_thermostat") {
        setIfChanged(zone.vdevice + "/state", stateText);
    }
}

function applyDecision(zone, decision, zoneState) {
    var params = baseParams(zone, zoneState, decision.reason);
    var stateChanged = (zone.state.lastStateText !== decision.state);
    var actualOpen;

    actualOpen = applyValves(zone, decision.heat, zoneState, decision.reason);
    publishState(zone, decision.state);
    setBoolIfChanged(zone.vdevice + "/current_state", actualOpen);

    if (stateChanged) {
        writeLog(zone, decision.eventName, decision.state, params);
    }

    zone.state.lastStateText = decision.state;
}

// -------------------- ОСНОВНОЙ РАСЧЁТ --------------------

function evaluateZone(zone, forcePublish) {
    var zoneState = readZoneState(zone);
    var decision;

    publishTemperatures(zone, zoneState, !!forcePublish);
    decision = calculateDecision(zone, zoneState);
    applyDecision(zone, decision, zoneState);
}

function evaluateAllZones(forcePublish) {
    var i;

    for (i = 0; i < ZONES.length; i++) {
        evaluateZone(ZONES[i], forcePublish);
    }
}

// -------------------- НАСТРОЙКИ --------------------

function logUserSetting(zone, settingName) {
    var zoneState;

    if (!zone.state.initialized) {
        return;
    }

    zoneState = readZoneState(zone);
    writeLog(zone, "НАСТРОЙКА", "Изменена настройка термостата", settingParams(zone, zoneState, settingName));
}

// -------------------- ПРАВИЛА --------------------

function defineZoneRules(zone) {
    if (hasTopic(zone.airTopic)) {
        defineRule("thermostat_" + zone.id + "_air_changed", {
            whenChanged: zone.airTopic,
            then: function () {
                evaluateZone(zone, false);
            }
        });
    }

    if (hasTopic(zone.floorTopic)) {
        defineRule("thermostat_" + zone.id + "_floor_changed", {
            whenChanged: zone.floorTopic,
            then: function () {
                evaluateZone(zone, false);
            }
        });
    }

    defineRule("thermostat_" + zone.id + "_target_temp_changed", {
        whenChanged: zone.vdevice + "/target_temperature",
        then: function () {
            logUserSetting(zone, "Уставка");
            evaluateZone(zone, true);
        }
    });

    defineRule("thermostat_" + zone.id + "_target_state_changed", {
        whenChanged: zone.vdevice + "/target_state",
        then: function () {
            logUserSetting(zone, "Термостат");
            evaluateZone(zone, true);
        }
    });

    if (zone.model !== "NL_simple_thermostat") {
        defineRule("thermostat_" + zone.id + "_floor_hold_changed", {
            whenChanged: zone.vdevice + "/floor_min_temperature",
            then: function () {
                logUserSetting(zone, "Пол при поддержании");
                evaluateZone(zone, true);
            }
        });

        defineRule("thermostat_" + zone.id + "_floor_heat_changed", {
            whenChanged: zone.vdevice + "/floor_max_temperature",
            then: function () {
                logUserSetting(zone, "Пол при нагреве");
                evaluateZone(zone, true);
            }
        });
    }

    if (zone.model === "NL_climate_thermostat") {
        defineRule("thermostat_" + zone.id + "_cooling_changed", {
            whenChanged: zone.vdevice + "/cooling_temperature",
            then: function () {
                logUserSetting(zone, "Порог охлаждения");
                evaluateZone(zone, true);
            }
        });
    }
}

function initializeZone(zone) {
    zone.state = makeRuntimeState();
    defineZoneDevice(zone);
    defineZoneRules(zone);
}

function initializeAllZones() {
    var i;

    for (i = 0; i < ZONES.length; i++) {
        initializeZone(ZONES[i]);
    }
}

function markAllInitialized() {
    var i;

    for (i = 0; i < ZONES.length; i++) {
        ZONES[i].state.initialized = true;
    }
}

initializeAllZones();

writeLog({ context: "общий" }, "СКРИПТ", "Скрипт загружен", {
    "зон": ZONES.length
});

evaluateAllZones(true);
markAllInitialized();

writeLog({ context: "общий" }, "СКРИПТ", "Стартовая инициализация завершена", {
    "зон": ZONES.length
});

defineRule("thermostats_600_periodic_sync", {
    when: cron("*/1 * * * *"),
    then: function () {
        writeLog({ context: "общий" }, "WATCHDOG", "Периодическая синхронизация", {
            "зон": ZONES.length
        });
        evaluateAllZones(true);
    }
});
