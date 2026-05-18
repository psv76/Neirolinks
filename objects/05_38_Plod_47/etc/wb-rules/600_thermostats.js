// 600_thermostats.js
// Каскадная логика зональных термостатов WB: воздух выбирает режим отопления,
// пол ограничивает/разрешает фактическое открытие сервоприводов, а запрос тепла
// зоны считается только по команде открытия физических сервоприводов.
// Физические каналы, которые пишет скрипт:
// - wb-mr6cu_218/K1, wb-mr6cu_218/K2, wb-mr6cu_218/K3, wb-mr6cu_218/K4, wb-mr6cu_218/K5, wb-mr6cu_218/K6
// - wb-mr6cu_224/K1, wb-mr6cu_224/K2, wb-mr6cu_224/K3, wb-mr6cu_224/K4, wb-mr6cu_224/K5, wb-mr6cu_224/K6
// - wb-mr6cu_219/K1
// - ONOKOM-AIR-GR-3-MB-B_10/Active mode, ONOKOM-AIR-GR-3-MB-B_10/Target temperature, ONOKOM-AIR-GR-3-MB-B_10/Horizontal vanes, ONOKOM-AIR-GR-3-MB-B_10/Smart fan speed
// - ONOKOM-AIR-GR-3-MB-B_20/Active mode, ONOKOM-AIR-GR-3-MB-B_20/Target temperature, ONOKOM-AIR-GR-3-MB-B_20/Horizontal vanes, ONOKOM-AIR-GR-3-MB-B_20/Smart fan speed

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
        ac: {
            activeModeTopic: "ONOKOM-AIR-GR-3-MB-B_10/Active mode",
            targetTemperatureTopic: "ONOKOM-AIR-GR-3-MB-B_10/Target temperature",
            indoorTemperatureTopic: "ONOKOM-AIR-GR-3-MB-B_10/Indoor air temperature",
            thermostatStateTopic: "ONOKOM-AIR-GR-3-MB-B_10/Thermostat state",
            connectedTopic: "ONOKOM-AIR-GR-3-MB-B_10/AC connected",
            horizontalVanesTopic: "ONOKOM-AIR-GR-3-MB-B_10/Horizontal vanes",
            smartFanSpeedTopic: "ONOKOM-AIR-GR-3-MB-B_10/Smart fan speed"
        },
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
        ac: {
            activeModeTopic: "ONOKOM-AIR-GR-3-MB-B_20/Active mode",
            targetTemperatureTopic: "ONOKOM-AIR-GR-3-MB-B_20/Target temperature",
            indoorTemperatureTopic: "ONOKOM-AIR-GR-3-MB-B_20/Indoor air temperature",
            thermostatStateTopic: "ONOKOM-AIR-GR-3-MB-B_20/Thermostat state",
            connectedTopic: "ONOKOM-AIR-GR-3-MB-B_20/AC connected",
            horizontalVanesTopic: "ONOKOM-AIR-GR-3-MB-B_20/Horizontal vanes",
            smartFanSpeedTopic: "ONOKOM-AIR-GR-3-MB-B_20/Smart fan speed"
        },
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
        floorTopic: "wb-m1w2_108/External Sensor 1",
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

var CLIMATE_MODE_OFF = 0;
var CLIMATE_MODE_HEAT = 1;
var CLIMATE_MODE_COOL = 2;
var CLIMATE_MODE_AUTO = 3;

var CLIMATE_CURRENT_OFF = 0;
var CLIMATE_CURRENT_HEAT = 1;
var CLIMATE_CURRENT_COOL = 2;

var AC_MODE_OFF = 0;
var AC_MODE_COOL = 2;

var AC_HORIZONTAL_VANES_DOWN = 5; // базовое положение жалюзи при включённом контроле: выше среднего
var AC_NIGHT_FAN_SPEED_QUIET = 1;
var AC_NIGHT_FAN_SPEED_MIN = 0;
var AC_NIGHT_FAN_SPEED_MAX = 7;
var DAY_NIGHT_TOPIC = "day_night/is_night";
var NIGHT_CHANNEL_MISSING_LOGGED = false;
var AC_MIN_ON_TIME_MS = 10 * 60 * 1000;
var AC_MIN_OFF_TIME_MS = 10 * 60 * 1000;
var AC_MANUAL_OFF_PAUSE_MS = 2 * 60 * 60 * 1000;

var CLIMATE_MIN_HEAT_COOL_GAP = 1;
var CLIMATE_MAX_HEAT_COOL_GAP = 2;

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

function readBoolValue(value) {
    return value === true || value === 1 || value === "1" || value === "true";
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
    var params = {
        "причина": reason,
        "режим": zoneState.modeName,
        "уставка": formatNumber(zoneState.target),
        "пол": formatNumber(zoneState.floor),
        "цель_пола": formatNumber(zoneState.floorTarget),
        "канал": zoneValveText(zone)
    };

    if (zone.model !== "NL_simple_thermostat") {
        params["воздух"] = formatNumber(zoneState.air);
        params["пол_поддержание"] = formatNumber(zoneState.floorHoldTarget);
        params["пол_нагрев"] = formatNumber(zoneState.floorHeatTarget);
    }

    if (zone.model === "NL_climate_thermostat") {
        params["порог_охлаждения"] = formatNumber(zoneState.coolingTarget);
    }

    return params;
}

function settingParams(zone, zoneState, settingName) {
    var params = {
        "причина": "изменение настройки",
        "настройка": settingName,
        "уставка": formatNumber(zoneState.target),
        "пол": formatNumber(zoneState.floor)
    };

    if (zone.model !== "NL_simple_thermostat") {
        params["воздух"] = formatNumber(zoneState.air);
        params["пол_поддержание"] = formatNumber(zoneState.floorHoldTarget);
        params["пол_нагрев"] = formatNumber(zoneState.floorHeatTarget);
    }

    if (zone.model === "NL_climate_thermostat") {
        params["порог_охлаждения"] = formatNumber(zoneState.coolingTarget);
    }

    return params;
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

function makeReadonlyValueCell(title, value, order) {
    return {
        title: title,
        type: "value",
        value: value,
        readonly: true,
        order: order
    };
}

function makeValueEnumCell(title, value, enumValues, readonly, order) {
    return {
        title: title,
        type: "value",
        value: value,
        enum: enumValues,
        readonly: !!readonly,
        order: order
    };
}

function climateTargetModeEnum() {
    return {
        0: { ru: "Выключен" },
        1: { ru: "Нагрев" },
        2: { ru: "Охлаждение" },
        3: { ru: "Авто" }
    };
}

function climateCurrentModeEnum() {
    return {
        0: { ru: "Выключен" },
        1: { ru: "Нагрев" },
        2: { ru: "Охлаждение" }
    };
}

function defineComboDevice(zone) {
    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: {
            target_state: makeSwitchCell("Термостат", true, false, 10),
            air_temperature: makeTemperatureCell("Температура воздуха", 20),
            target_temperature: makeRangeCell("Уставка воздуха", zone.defaultTarget, zone.airMin, zone.airMax, 30),
            state: makeTextCell("Состояние", "Инициализация", 40),
            floor_temperature: makeTemperatureCell("Температура пола", 50),
            floor_min_temperature: makeRangeCell("Пол при поддержании", zone.defaultFloorHold, FLOOR_HOLD_MIN, FLOOR_HOLD_MAX, 60),
            floor_max_temperature: makeRangeCell("Пол при нагреве", zone.defaultFloorHeat, FLOOR_HEAT_MIN, FLOOR_HEAT_MAX, 70),
            current_state: makeSwitchCell("Sprut: текущий режим", false, true, 800)
        }
    });
}

function defineClimateDevice(zone) {
    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: {
            target_state: makeValueEnumCell("Целевой режим", CLIMATE_MODE_AUTO, climateTargetModeEnum(), false, 10),
            air_temperature: makeTemperatureCell("Температура воздуха", 20),
            target_temperature: makeRangeCell("Порог нагрева", zone.defaultTarget, zone.airMin, zone.airMax, 30),
            cooling_temperature: makeRangeCell("Порог охлаждения", zone.defaultCooling, COOLING_MIN, COOLING_MAX, 35),
            state: makeTextCell("Состояние", "Инициализация", 40),
            floor_temperature: makeTemperatureCell("Температура пола", 50),
            floor_min_temperature: makeRangeCell("Пол при поддержании", zone.defaultFloorHold, FLOOR_HOLD_MIN, FLOOR_HOLD_MAX, 60),
            floor_max_temperature: makeRangeCell("Пол при нагреве", zone.defaultFloorHeat, FLOOR_HEAT_MIN, FLOOR_HEAT_MAX, 70),
            ac_vanes_control: makeSwitchCell("Контроль жалюзи", false, false, 75),
            saved_horizontal_vanes: makeRangeCell("Запомненное положение жалюзи", AC_HORIZONTAL_VANES_DOWN, 2, 6, 76),
            ac_min_on_timer_sec: makeReadonlyValueCell("Таймер работы охлаждения, сек", 0, 77),
            ac_min_off_timer_sec: makeReadonlyValueCell("Пауза между включениями, сек", 0, 78),
            ac_manual_pause_timer_sec: makeReadonlyValueCell("Ручная пауза охлаждения, сек", 0, 79),
            ac_timer_status: makeTextCell("Статус таймеров охлаждения", "Таймеры не активны", 80),
            ac_night_mode_enabled: makeSwitchCell("Ночной режим кондиционера", true, false, 81),
            ac_night_fan_speed: makeRangeCell("Ночная скорость вентилятора", AC_NIGHT_FAN_SPEED_QUIET, AC_NIGHT_FAN_SPEED_MIN, AC_NIGHT_FAN_SPEED_MAX, 82),
            ac_night_mode_status: makeTextCell("Статус ночного режима", "Инициализация", 83),
            current_state: makeValueEnumCell("Sprut: текущий режим", CLIMATE_CURRENT_OFF, climateCurrentModeEnum(), true, 800)
        }
    });
}

function defineSimpleDevice(zone) {
    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: {
            target_state: makeSwitchCell("Термостат", true, false, 10),
            temperature: makeTemperatureCell("Температура пола", 20),
            target_temperature: makeRangeCell("Уставка пола", zone.defaultFloorHold, zone.airMin, zone.airMax, 30),
            current_state: makeSwitchCell("Sprut: текущий режим", false, true, 800)
        }
    });
}

function defineZoneDevice(zone) {
    if (zone.model === "NL_simple_thermostat") {
        defineSimpleDevice(zone);
        return;
    }

    if (zone.model === "NL_climate_thermostat") {
        defineClimateDevice(zone);
        return;
    }

    defineComboDevice(zone);
}

// -------------------- СОСТОЯНИЕ ЗОН --------------------

function makeRuntimeState() {
    return {
        initialized: false,
        airHeatMode: false,
        climateCoolMode: false,
        climateCoolStartedAt: 0,
        climateCoolLastStoppedAt: 0,
        acManualPauseUntil: 0,
        floorHeatCommand: false,
        lastStateText: null,
        lastHeatCommand: null,
        lastActualOpen: null,
        lastClimateCurrentState: null,
        lastAcModeCommand: null,
        lastAcTargetCommand: null,
        lastAcVanesCommand: null,
        lastAcVanesControlLog: null,
        lastNightFanCommand: null,
        lastNightValue: null,
        lastCoolingTargetCorrection: null,
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

function readClimateTargetMode(zone) {
    var raw = dev[zone.vdevice + "/target_state"];
    var n;

    if (raw === null || raw === undefined || raw === "") {
        return CLIMATE_MODE_AUTO;
    }

    if (raw === false || raw === "OFF") {
        return CLIMATE_MODE_OFF;
    }

    if (raw === true || raw === "ON") {
        return CLIMATE_MODE_HEAT;
    }

    n = Number(raw);

    if (n === CLIMATE_MODE_OFF || n === CLIMATE_MODE_HEAT || n === CLIMATE_MODE_COOL || n === CLIMATE_MODE_AUTO) {
        return n;
    }

    return CLIMATE_MODE_AUTO;
}

function normalizeCoolingTarget(zone, target) {
    var raw = dev[zone.vdevice + "/cooling_temperature"];
    var requested = round1(clamp(raw, COOLING_MIN, COOLING_MAX));
    var corrected = requested;
    var correctionKey;

    if (corrected < target + CLIMATE_MIN_HEAT_COOL_GAP) {
        corrected = round1(target + CLIMATE_MIN_HEAT_COOL_GAP);
    }

    if (corrected > target + CLIMATE_MAX_HEAT_COOL_GAP) {
        corrected = round1(target + CLIMATE_MIN_HEAT_COOL_GAP);
    }

    if (corrected > COOLING_MAX) {
        corrected = COOLING_MAX;
    }

    correctionKey = String(requested) + "->" + String(corrected) + "@" + String(target);

    if (Math.abs(Number(requested) - Number(corrected)) > 0.001 && zone.state.lastCoolingTargetCorrection !== correctionKey) {
        zone.state.lastCoolingTargetCorrection = correctionKey;
        writeLog(zone, "НАСТРОЙКА", "Порог охлаждения скорректирован", {
            "причина": "защита от старого или случайно завышенного значения",
            "уставка": formatNumber(target),
            "старое_значение": formatNumber(requested),
            "новое_значение": formatNumber(corrected)
        });
    }

    setNumberIfChanged(zone.vdevice + "/cooling_temperature", corrected);
    return corrected;
}

function readZoneState(zone) {
    var airRaw = hasTopic(zone.airTopic) ? dev[zone.airTopic] : undefined;
    var floorRaw = hasTopic(zone.floorTopic) ? dev[zone.floorTopic] : undefined;
    var airValid = hasTopic(zone.airTopic) && isValidAir(airRaw);
    var floorValid = hasTopic(zone.floorTopic) && isValidFloor(floorRaw);
    var target;
    var floorHoldTarget;
    var floorHeatTarget;
    var coolingTarget = NaN;
    var targetMode = null;

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
        targetMode = readClimateTargetMode(zone);
        coolingTarget = normalizeCoolingTarget(zone, target);
    }

    return {
        enabled: zone.model === "NL_climate_thermostat" ? targetMode !== CLIMATE_MODE_OFF : readTargetState(zone),
        targetMode: targetMode,
        air: airValid ? round1(airRaw) : NaN,
        floor: floorValid ? round1(floorRaw) : NaN,
        airValid: airValid,
        floorValid: floorValid,
        target: target,
        floorHoldTarget: floorHoldTarget,
        floorHeatTarget: floorHeatTarget,
        coolingTarget: coolingTarget,
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

function leftMs(untilTs) {
    var left = Number(untilTs) - nowMs();

    if (!isFinite(left) || left <= 0) {
        return 0;
    }

    return left;
}

function leftSec(untilTs) {
    return Math.ceil(leftMs(untilTs) / 1000);
}

function getAcMinOnLeftSec(zone) {
    if (!zone || !zone.state || !zone.state.climateCoolMode || zone.state.climateCoolStartedAt <= 0) {
        return 0;
    }

    return leftSec(zone.state.climateCoolStartedAt + AC_MIN_ON_TIME_MS);
}

function getAcMinOffLeftSec(zone) {
    if (!zone || !zone.state || zone.state.climateCoolMode || zone.state.climateCoolLastStoppedAt <= 0) {
        return 0;
    }

    return leftSec(zone.state.climateCoolLastStoppedAt + AC_MIN_OFF_TIME_MS);
}

function getAcManualPauseLeftSec(zone) {
    var left;

    if (!zone || !zone.state || zone.state.acManualPauseUntil <= 0) {
        return 0;
    }

    left = leftSec(zone.state.acManualPauseUntil);

    if (left <= 0) {
        zone.state.acManualPauseUntil = 0;
        return 0;
    }

    return left;
}

function isAcMinOffPauseActive(zone) {
    return getAcMinOffLeftSec(zone) > 0;
}

function isAcManualPauseActive(zone) {
    return getAcManualPauseLeftSec(zone) > 0;
}

function isCoolingRequestedByAir(zone, zoneState) {
    return zoneState.airValid && zoneState.air >= zoneState.coolingTarget + zone.airHysteresis;
}

function updateClimateTimers(zone) {
    var minOnLeft;
    var minOffLeft;
    var manualLeft;
    var status;

    if (!zone || zone.model !== "NL_climate_thermostat") {
        return;
    }

    minOnLeft = getAcMinOnLeftSec(zone);
    minOffLeft = getAcMinOffLeftSec(zone);
    manualLeft = getAcManualPauseLeftSec(zone);

    setNumberIfChanged(zone.vdevice + "/ac_min_on_timer_sec", minOnLeft);
    setNumberIfChanged(zone.vdevice + "/ac_min_off_timer_sec", minOffLeft);
    setNumberIfChanged(zone.vdevice + "/ac_manual_pause_timer_sec", manualLeft);

    if (manualLeft > 0) {
        status = "Ручная пауза охлаждения";
    } else if (minOnLeft > 0) {
        status = "Идёт минимальное время работы охлаждения";
    } else if (minOffLeft > 0) {
        status = "Пауза между включениями охлаждения";
    } else {
        status = "Таймеры не активны";
    }

    setIfChanged(zone.vdevice + "/ac_timer_status", status);
}

function setAcManualPause(zone, reason) {
    if (!zone || zone.model !== "NL_climate_thermostat") {
        return;
    }

    zone.state.acManualPauseUntil = nowMs() + AC_MANUAL_OFF_PAUSE_MS;
    zone.state.climateCoolMode = false;
    zone.state.climateCoolStartedAt = 0;
    zone.state.climateCoolLastStoppedAt = nowMs();

    writeLog(zone, "СОСТОЯНИЕ", "Охлаждение поставлено на ручную паузу", {
        "причина": reason,
        "пауза_сек": Math.ceil(AC_MANUAL_OFF_PAUSE_MS / 1000),
        "таймер": Math.ceil(AC_MANUAL_OFF_PAUSE_MS / 1000)
    });

    updateClimateTimers(zone);
}

function clearAcManualPause(zone, reason) {
    if (!zone || zone.model !== "NL_climate_thermostat") {
        return;
    }

    if (getAcManualPauseLeftSec(zone) <= 0) {
        return;
    }

    zone.state.acManualPauseUntil = 0;

    writeLog(zone, "СОСТОЯНИЕ", "Ручная пауза охлаждения снята", {
        "причина": reason
    });

    updateClimateTimers(zone);
}

function updateCoolingMode(zone, zoneState) {
    var coolingWasActive = zone.state.climateCoolMode;
    var stopByTemperature;
    var workedEnough;

    if (!zoneState.airValid) {
        return;
    }

    if (zoneState.air >= zoneState.coolingTarget + zone.airHysteresis) {
        if (isAcManualPauseActive(zone) || isAcMinOffPauseActive(zone)) {
            return;
        }

        zone.state.climateCoolMode = true;

        if (!coolingWasActive) {
            zone.state.climateCoolStartedAt = nowMs();
        }

        return;
    }

    stopByTemperature = zoneState.air <= zoneState.coolingTarget - zone.airHysteresis ||
        zoneState.air <= zoneState.target + zone.airHysteresis;

    if (zone.state.climateCoolMode && stopByTemperature) {
        workedEnough = zone.state.climateCoolStartedAt <= 0 ||
            (nowMs() - zone.state.climateCoolStartedAt) >= AC_MIN_ON_TIME_MS;

        if (!workedEnough) {
            return;
        }

        zone.state.climateCoolMode = false;
        zone.state.climateCoolStartedAt = 0;
        zone.state.climateCoolLastStoppedAt = nowMs();
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

function offDecision(zone, zoneState, reason) {
    zone.state.airHeatMode = false;

    if (zone.state.climateCoolMode) {
        zone.state.climateCoolLastStoppedAt = nowMs();
    }

    zone.state.climateCoolMode = false;
    zone.state.climateCoolStartedAt = 0;
    zone.state.floorHeatCommand = false;
    zoneState.floorTarget = NaN;
    zoneState.modeName = "выключен";

    return {
        heat: false,
        acMode: AC_MODE_OFF,
        acTarget: null,
        state: "Выключен",
        reason: reason,
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateSimpleDecision(zone, zoneState) {
    var heat;

    if (!zoneState.enabled) {
        return offDecision(zone, zoneState, "термостат выключен");
    }

    if (!zoneState.floorValid) {
        zone.state.floorHeatCommand = false;
        zoneState.floorTarget = NaN;
        zoneState.modeName = "нет датчика пола";

        return {
            heat: false,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: "Нет датчика пола, сервопривод закрыт",
            reason: "нет корректного значения пола",
            eventName: hasTopic(zone.floorTopic) ? "АВАРИЯ" : "ОШИБКА"
        };
    }

    zoneState.floorTarget = zoneState.floorHoldTarget;
    zoneState.modeName = "по полу";
    heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

    return {
        heat: heat,
        acMode: AC_MODE_OFF,
        acTarget: null,
        state: heat ? "Нагрев пола" : "Пол в норме",
        reason: heat ? "пол ниже уставки" : "пол достиг уставки",
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateComboDecision(zone, zoneState) {
    var heat;

    updateAirMode(zone, zoneState);

    if (!zoneState.enabled) {
        return offDecision(zone, zoneState, "термостат выключен");
    }

    if (!zoneState.airValid && !zoneState.floorValid) {
        zone.state.airHeatMode = false;
        zone.state.floorHeatCommand = false;
        zoneState.floorTarget = NaN;
        zoneState.modeName = "нет датчиков";

        return {
            heat: false,
            acMode: AC_MODE_OFF,
            acTarget: null,
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
            acMode: AC_MODE_OFF,
            acTarget: null,
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
            acMode: AC_MODE_OFF,
            acTarget: null,
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
            acMode: AC_MODE_OFF,
            acTarget: null,
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
        acMode: AC_MODE_OFF,
        acTarget: null,
        state: heat ? "Поддержание пола" : "Ожидание",
        reason: heat ? "воздух в норме, пол ниже цели поддержания" : "воздух и пол в норме",
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateClimateHeatDecision(zone, zoneState, modeReason) {
    var decision;

    decision = calculateComboDecision(zone, zoneState);
    decision.acMode = AC_MODE_OFF;
    decision.acTarget = null;

    if (modeReason) {
        decision.reason = modeReason + ": " + decision.reason;
    }

    return decision;
}

function calculateClimateCoolDecision(zone, zoneState, reason) {
    zone.state.airHeatMode = false;
    zone.state.floorHeatCommand = false;
    zoneState.floorTarget = NaN;
    zoneState.modeName = "охлаждение";

    if (!zoneState.airValid) {
        return {
            heat: false,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: "Нет датчика воздуха, охлаждение запрещено",
            reason: "нет корректного значения воздуха",
            eventName: "АВАРИЯ"
        };
    }

    return {
        heat: false,
        acMode: AC_MODE_COOL,
        acTarget: zoneState.coolingTarget,
        state: "Охлаждение кондиционером",
        reason: reason,
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateClimateCoolingWaitDecision(zone, zoneState, stateText, reason) {
    zone.state.floorHeatCommand = false;
    zoneState.floorTarget = NaN;
    zoneState.modeName = "пауза охлаждения";

    return {
        heat: false,
        acMode: AC_MODE_OFF,
        acTarget: null,
        state: stateText,
        reason: reason,
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateClimateAutoDecision(zone, zoneState) {
    var heat;

    updateAirMode(zone, zoneState);
    updateCoolingMode(zone, zoneState);

    if (!zoneState.airValid && !zoneState.floorValid) {
        zone.state.airHeatMode = false;
        zone.state.climateCoolMode = false;
        zone.state.floorHeatCommand = false;
        zoneState.floorTarget = NaN;
        zoneState.modeName = "нет датчиков";

        return {
            heat: false,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: "Нет датчиков, отопление и охлаждение выключены",
            reason: "нет корректных значений воздуха и пола",
            eventName: "АВАРИЯ"
        };
    }

    if (zone.state.climateCoolMode) {
        return calculateClimateCoolDecision(zone, zoneState, "авто: воздух выше порога охлаждения");
    }

    if (isCoolingRequestedByAir(zone, zoneState) && isAcManualPauseActive(zone)) {
        return calculateClimateCoolingWaitDecision(zone, zoneState, "Ручная пауза охлаждения", "кондиционер выключен извне, действует ручная пауза");
    }

    if (isCoolingRequestedByAir(zone, zoneState) && isAcMinOffPauseActive(zone)) {
        return calculateClimateCoolingWaitDecision(zone, zoneState, "Пауза между включениями охлаждения", "минимальная пауза после выключения кондиционера");
    }

    if (!zoneState.airValid && zoneState.floorValid) {
        zoneState.floorTarget = zoneState.floorHoldTarget;
        zoneState.modeName = "по полу";
        heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: heat ? "Нет воздуха, грею пол" : "Нет воздуха, пол в норме",
            reason: "нет датчика воздуха, охлаждение запрещено, работа по полу",
            eventName: "ОШИБКА"
        };
    }

    if (zone.state.airHeatMode) {
        if (!zoneState.floorValid) {
            zone.state.floorHeatCommand = false;
            zoneState.floorTarget = NaN;
            zoneState.modeName = "нет датчика пола";

            return {
                heat: false,
                acMode: AC_MODE_OFF,
                acTarget: null,
                state: "Нет пола, нагрев закрыт",
                reason: "авто: воздух ниже уставки, но нет корректного значения пола",
                eventName: "АВАРИЯ"
            };
        }

        zoneState.floorTarget = zoneState.floorHeatTarget;
        zoneState.modeName = "нагрев воздуха";
        heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

        return {
            heat: heat,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: heat ? "Нагревает" : "Пол нагрет",
            reason: heat ? "авто: воздух ниже уставки, пол ниже цели нагрева" : "авто: воздух ниже уставки, но пол уже нагрет",
            eventName: "СОСТОЯНИЕ"
        };
    }

    if (!zoneState.floorValid) {
        zoneState.floorTarget = NaN;
        zoneState.modeName = "ожидание";

        return {
            heat: false,
            acMode: AC_MODE_OFF,
            acTarget: null,
            state: "Ожидание",
            reason: "авто: воздух в норме, датчик пола недоступен",
            eventName: "ОШИБКА"
        };
    }

    zoneState.floorTarget = zoneState.floorHoldTarget;
    zoneState.modeName = "поддержание пола";
    heat = calculateFloorCommand(zone, zoneState.floor, zoneState.floorTarget);

    return {
        heat: heat,
        acMode: AC_MODE_OFF,
        acTarget: null,
        state: heat ? "Поддержание пола" : "Ожидание",
        reason: heat ? "авто: воздух между уставками, пол ниже цели поддержания" : "авто: воздух и пол в норме",
        eventName: "СОСТОЯНИЕ"
    };
}

function calculateClimateDecision(zone, zoneState) {
    if (!zoneState.enabled) {
        return offDecision(zone, zoneState, "термостат выключен");
    }

    if (zoneState.targetMode === CLIMATE_MODE_HEAT) {
        if (zone.state.climateCoolMode) {
            zone.state.climateCoolLastStoppedAt = nowMs();
        }

        zone.state.climateCoolMode = false;
        zone.state.climateCoolStartedAt = 0;
        return calculateClimateHeatDecision(zone, zoneState, "режим нагрева");
    }

    if (zoneState.targetMode === CLIMATE_MODE_COOL) {
        if (!zone.state.climateCoolMode) {
            zone.state.climateCoolStartedAt = nowMs();
        }

        zone.state.climateCoolMode = true;
        return calculateClimateCoolDecision(zone, zoneState, "выбран режим охлаждения");
    }

    return calculateClimateAutoDecision(zone, zoneState);
}

function calculateDecision(zone, zoneState) {
    if (zone.model === "NL_simple_thermostat") {
        return calculateSimpleDecision(zone, zoneState);
    }

    if (zone.model === "NL_climate_thermostat") {
        return calculateClimateDecision(zone, zoneState);
    }

    return calculateComboDecision(zone, zoneState);
}

// -------------------- УПРАВЛЕНИЕ СЕРВОПРИВОДАМИ И КОНДИЦИОНЕРАМИ --------------------

function writeValve(zone, topic, value, zoneState, reason) {
    var params = baseParams(zone, zoneState, reason);

    params["канал"] = topic;
    params["значение в канал"] = value ? "ON" : "OFF";

    if (dev[topic] === undefined || dev[topic] === null) {
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
        params["команда_сервоприводов"] = actualOpen ? "ON" : "OFF";
        writeLog(zone, "РЕЗУЛЬТАТ", actualOpen ? "Команда на открытие сервоприводов отправлена" : "Команда на закрытие сервоприводов отправлена", params);
    }

    return actualOpen;
}

function hasAc(zone) {
    return zone.ac && hasTopic(zone.ac.activeModeTopic);
}

function isControlAvailable(topic) {
    return hasTopic(topic) && dev[topic] !== undefined && dev[topic] !== null;
}

function readNumberControl(topic, fallback) {
    var raw;
    var n;

    if (!hasTopic(topic)) {
        return fallback;
    }

    raw = dev[topic];

    if (raw === null || raw === undefined || raw === "") {
        return fallback;
    }

    n = Number(raw);

    if (!isFinite(n)) {
        return fallback;
    }

    return n;
}

function isAcConnected(zone) {
    var raw;

    if (!hasAc(zone) || !hasTopic(zone.ac.connectedTopic)) {
        return true;
    }

    raw = dev[zone.ac.connectedTopic];

    if (raw === null || raw === undefined) {
        return false;
    }

    return !(raw === false || raw === 0 || raw === "0");
}

function acModeText(mode) {
    if (mode === AC_MODE_COOL) {
        return "охлаждение";
    }

    return "выключен";
}

function writeAcTarget(zone, target, zoneState, reason) {
    var topic;
    var params;

    if (!hasAc(zone) || target === null || target === undefined || !isFinite(Number(target))) {
        return true;
    }

    topic = zone.ac.targetTemperatureTopic;

    if (!isControlAvailable(topic)) {
        params = baseParams(zone, zoneState, reason);
        params["канал"] = topic;
        writeLog(zone, "ОШИБКА", "Канал уставки кондиционера недоступен", params);
        return false;
    }

    if (Math.abs(readNumberControl(topic, -999) - Number(target)) > 0.001) {
        dev[topic] = Number(target);
    }

    return true;
}

function isAcVanesControlEnabled(zone) {
    if (!zone || zone.model !== "NL_climate_thermostat") {
        return false;
    }

    return readBoolValue(dev[zone.vdevice + "/ac_vanes_control"]);
}

function getSavedHorizontalVanes(zone) {
    var saved = readNumberControl(zone.vdevice + "/saved_horizontal_vanes", AC_HORIZONTAL_VANES_DOWN);

    saved = Math.round(saved);

    if (saved < 2 || saved > 6) {
        saved = AC_HORIZONTAL_VANES_DOWN;
    }

    setNumberIfChanged(zone.vdevice + "/saved_horizontal_vanes", saved);
    return saved;
}

function rememberUserHorizontalVanes(zone, value, reason) {
    var saved;
    var params;

    if (!isAcVanesControlEnabled(zone)) {
        return;
    }

    saved = Math.round(Number(value));

    if (!isFinite(saved)) {
        return;
    }

    // 0 = остановить качание / не выбирать положение, 1 = качание.
    // Для автозапуска охлаждения запоминаем только фиксированные положения 2...6.
    if (saved < 2 || saved > 6) {
        return;
    }

    setNumberIfChanged(zone.vdevice + "/saved_horizontal_vanes", saved);

    params = {
        "причина": reason,
        "канал": zone.ac.horizontalVanesTopic,
        "значение": saved
    };

    writeLog(zone, "НАСТРОЙКА", "Запомнено пользовательское положение жалюзи", params);
}

function writeAcHorizontalVanesOnCoolingStart(zone, zoneState, reason) {
    var topic;
    var currentValue;
    var targetValue;
    var params;

    if (!hasAc(zone) || !hasTopic(zone.ac.horizontalVanesTopic)) {
        return true;
    }

    if (!isAcVanesControlEnabled(zone)) {
        if (zone.state.lastAcVanesControlLog !== "disabled") {
            zone.state.lastAcVanesControlLog = "disabled";
            writeLog(zone, "СОСТОЯНИЕ", "Контроль жалюзи выключен", {
                "причина": "команда на жалюзи не отправляется",
                "канал": zone.ac.horizontalVanesTopic
            });
        }
        return true;
    }

    zone.state.lastAcVanesControlLog = "enabled";

    topic = zone.ac.horizontalVanesTopic;
    currentValue = readNumberControl(topic, null);
    targetValue = getSavedHorizontalVanes(zone);

    params = baseParams(zone, zoneState, reason);
    params["канал"] = topic;
    params["значение в канал"] = String(targetValue);

    if (!isControlAvailable(topic)) {
        if (zone.state.lastAcVanesCommand !== "ac_vanes_unavailable") {
            zone.state.lastAcVanesCommand = "ac_vanes_unavailable";
            writeLog(zone, "ОШИБКА", "Канал горизонтальных жалюзи кондиционера недоступен", params);
        }
        return false;
    }

    if (currentValue !== targetValue || zone.state.lastAcVanesCommand !== targetValue) {
        writeLog(zone, "КОМАНДА", "Установить горизонтальные жалюзи кондиционера", params);
    }

    if (currentValue !== targetValue) {
        dev[topic] = targetValue;
    }

    zone.state.lastAcVanesCommand = targetValue;
    return true;
}

function readNightMode(zone) {
    var statusTopic;

    statusTopic = zone.vdevice + "/ac_night_mode_status";

    if (!isControlAvailable(DAY_NIGHT_TOPIC)) {
        setIfChanged(statusTopic, "Канал day_night/is_night недоступен, скорость не управляется");

        if (!NIGHT_CHANNEL_MISSING_LOGGED) {
            NIGHT_CHANNEL_MISSING_LOGGED = true;
            writeLog(zone, "ОШИБКА", "Канал ночного режима недоступен", {
                "причина": "нет day_night/is_night"
            });
        }

        return {
            available: false,
            isNight: false
        };
    }

    return {
        available: true,
        isNight: readBoolValue(dev[DAY_NIGHT_TOPIC])
    };
}

function isAcNightModeEnabled(zone) {
    return readBoolValue(dev[zone.vdevice + "/ac_night_mode_enabled"]);
}

function getAcNightFanSpeed(zone) {
    var speed = Math.round(readNumberControl(zone.vdevice + "/ac_night_fan_speed", AC_NIGHT_FAN_SPEED_QUIET));

    if (speed < AC_NIGHT_FAN_SPEED_MIN || speed > AC_NIGHT_FAN_SPEED_MAX) {
        speed = AC_NIGHT_FAN_SPEED_QUIET;
    }

    setNumberIfChanged(zone.vdevice + "/ac_night_fan_speed", speed);
    return speed;
}

function applyNightFanSpeed(zone, zoneState, reason, trigger) {
    var night;
    var topic;
    var speed;
    var currentValue;
    var commandKey;
    var params;

    if (!hasAc(zone) || !hasTopic(zone.ac.smartFanSpeedTopic)) {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "Канал скорости вентилятора не задан, скорость не управляется");
        return true;
    }

    if (!isAcNightModeEnabled(zone)) {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "Ночной режим кондиционера выключен");
        return true;
    }

    night = readNightMode(zone);

    if (!night.available) {
        return false;
    }

    if (!night.isNight) {
        zone.state.lastNightValue = false;
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "День, скорость вентилятора не меняется");
        return true;
    }

    topic = zone.ac.smartFanSpeedTopic;

    if (!isControlAvailable(topic)) {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "Канал скорости вентилятора недоступен");
        return false;
    }

    speed = getAcNightFanSpeed(zone);
    currentValue = readNumberControl(topic, null);
    commandKey = trigger + ":" + String(speed);

    params = baseParams(zone, zoneState, reason);
    params["канал"] = topic;
    params["значение в канал"] = String(speed);

    if (currentValue !== speed || zone.state.lastNightFanCommand !== commandKey) {
        writeLog(zone, "КОМАНДА", "Установить тихую скорость кондиционера", {
            "причина": "ночной режим охлаждения",
            "канал": topic,
            "значение в канал": String(speed)
        });
    }

    if (currentValue !== speed) {
        dev[topic] = speed;
    }

    zone.state.lastNightFanCommand = commandKey;
    zone.state.lastNightValue = true;
    setIfChanged(zone.vdevice + "/ac_night_mode_status", "Ночь, установлена скорость вентилятора " + speed);
    return true;
}

function updateNightModeStatusWithoutCommand(zone) {
    var night;

    if (zone.model !== "NL_climate_thermostat") {
        return;
    }

    if (!isAcNightModeEnabled(zone)) {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "Ночной режим кондиционера выключен");
        return;
    }

    night = readNightMode(zone);

    if (!night.available) {
        return;
    }

    zone.state.lastNightValue = night.isNight;

    if (night.isNight) {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "Ночь, ожидание охлаждения");
    } else {
        setIfChanged(zone.vdevice + "/ac_night_mode_status", "День, скорость вентилятора не меняется");
    }
}

function applyAc(zone, mode, target, zoneState, reason) {
    var topic;
    var currentMode;
    var params;
    var needCommandLog;
    var coolingStart;
    var text;

    if (!hasAc(zone)) {
        return false;
    }

    topic = zone.ac.activeModeTopic;
    currentMode = readNumberControl(topic, null);

    params = baseParams(zone, zoneState, reason);
    params["канал"] = topic;
    params["значение в канал"] = String(mode);
    params["кондиционер"] = acModeText(mode);

    if (!isAcConnected(zone)) {
        if (zone.state.lastAcModeCommand !== "ac_not_connected") {
            zone.state.lastAcModeCommand = "ac_not_connected";
            writeLog(zone, "ОШИБКА", "Кондиционер не подключен", params);
        }
        return false;
    }

    if (!isControlAvailable(topic)) {
        if (zone.state.lastAcModeCommand !== "ac_control_unavailable") {
            zone.state.lastAcModeCommand = "ac_control_unavailable";
            writeLog(zone, "ОШИБКА", "Канал управления кондиционером недоступен", params);
        }
        return false;
    }

    if (mode === AC_MODE_COOL) {
        writeAcTarget(zone, target, zoneState, reason);
        params["целевая_температура_кондиционера"] = formatNumber(target);
    }

    coolingStart = mode === AC_MODE_COOL &&
        (currentMode !== AC_MODE_COOL || zone.state.lastAcModeCommand !== AC_MODE_COOL);

    if (coolingStart) {
        writeAcHorizontalVanesOnCoolingStart(zone, zoneState, "старт охлаждения, контроль жалюзи включен");
        applyNightFanSpeed(zone, zoneState, "старт охлаждения", "cooling_start");
    } else if (mode === AC_MODE_COOL && readBoolValue(dev[DAY_NIGHT_TOPIC]) && zone.state.lastNightValue !== true) {
        applyNightFanSpeed(zone, zoneState, "наступила ночь при активном охлаждении", "night_started");
    } else if (mode !== AC_MODE_COOL) {
        updateNightModeStatusWithoutCommand(zone);
    }

    needCommandLog = (currentMode !== mode) ||
        (zone.state.lastAcModeCommand !== mode) ||
        (mode === AC_MODE_COOL && zone.state.lastAcTargetCommand !== target);

    if (needCommandLog) {
        text = mode === AC_MODE_COOL ? "Включить охлаждение кондиционера" : "Выключить кондиционер";
        writeLog(zone, "КОМАНДА", text, params);
    }

    if (currentMode === AC_MODE_COOL && mode === AC_MODE_OFF) {
        zone.state.climateCoolLastStoppedAt = nowMs();
    }

    if (currentMode !== mode) {
        dev[topic] = mode;
    }

    zone.state.lastAcModeCommand = mode;

    if (mode === AC_MODE_COOL) {
        zone.state.lastAcTargetCommand = target;
    } else {
        zone.state.lastAcTargetCommand = null;
    }

    return mode === AC_MODE_COOL;
}

function publishState(zone, stateText) {
    if (zone.model !== "NL_simple_thermostat") {
        setIfChanged(zone.vdevice + "/state", stateText);
    }
}

function publishCurrentState(zone, currentState) {
    if (zone.model === "NL_climate_thermostat") {
        setNumberIfChanged(zone.vdevice + "/current_state", currentState);
        return;
    }

    setBoolIfChanged(zone.vdevice + "/current_state", currentState === CLIMATE_CURRENT_HEAT);
}

function applyDecision(zone, decision, zoneState) {
    var params = baseParams(zone, zoneState, decision.reason);
    var stateChanged = (zone.state.lastStateText !== decision.state);
    var currentState;
    var actualOpen;
    var acCooling;

    actualOpen = applyValves(zone, decision.heat, zoneState, decision.reason);

    if (zone.model === "NL_climate_thermostat") {
        if (actualOpen || decision.heat) {
            acCooling = applyAc(zone, AC_MODE_OFF, null, zoneState, "нагрев пола активен, охлаждение запрещено");
        } else {
            acCooling = applyAc(zone, decision.acMode, decision.acTarget, zoneState, decision.reason);
        }

        currentState = actualOpen ? CLIMATE_CURRENT_HEAT : (acCooling ? CLIMATE_CURRENT_COOL : CLIMATE_CURRENT_OFF);
    } else {
        currentState = actualOpen ? CLIMATE_CURRENT_HEAT : CLIMATE_CURRENT_OFF;
    }

    publishState(zone, decision.state);
    publishCurrentState(zone, currentState);

    if (stateChanged) {
        writeLog(zone, decision.eventName, decision.state, params);
    }

    zone.state.lastStateText = decision.state;
    zone.state.lastClimateCurrentState = currentState;
}

// -------------------- ОСНОВНОЙ РАСЧЁТ --------------------

function evaluateZone(zone, forcePublish) {
    var zoneState = readZoneState(zone);
    var decision;

    publishTemperatures(zone, zoneState, !!forcePublish);
    decision = calculateDecision(zone, zoneState);
    applyDecision(zone, decision, zoneState);
    updateClimateTimers(zone);
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

function climateZoneWantsCooling(zone, zoneState) {
    if (!zoneState.enabled || !zoneState.airValid) {
        return false;
    }

    if (zoneState.targetMode === CLIMATE_MODE_COOL) {
        return true;
    }

    if (zoneState.targetMode === CLIMATE_MODE_AUTO && isCoolingRequestedByAir(zone, zoneState)) {
        return true;
    }

    return false;
}

function handleAcActiveModeChanged(zone) {
    var currentMode;
    var zoneState;

    if (!hasAc(zone)) {
        evaluateZone(zone, true);
        return;
    }

    currentMode = readNumberControl(zone.ac.activeModeTopic, null);
    zoneState = readZoneState(zone);

    if (currentMode === AC_MODE_OFF && zone.state.lastAcModeCommand === AC_MODE_COOL && zone.state.climateCoolMode && climateZoneWantsCooling(zone, zoneState)) {
        setAcManualPause(zone, "кондиционер выключен извне");
    }

    evaluateZone(zone, true);
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
            logUserSetting(zone, zone.model === "NL_climate_thermostat" ? "Порог нагрева" : "Уставка");
            evaluateZone(zone, true);
        }
    });

    defineRule("thermostat_" + zone.id + "_target_state_changed", {
        whenChanged: zone.vdevice + "/target_state",
        then: function () {
            if (zone.model === "NL_climate_thermostat") {
                clearAcManualPause(zone, "изменение целевого режима");
            }

            logUserSetting(zone, zone.model === "NL_climate_thermostat" ? "Целевой режим" : "Термостат");
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

        defineRule("thermostat_" + zone.id + "_ac_vanes_control_changed", {
            whenChanged: zone.vdevice + "/ac_vanes_control",
            then: function () {
                logUserSetting(zone, "Контроль жалюзи");
                evaluateZone(zone, true);
            }
        });

        defineRule("thermostat_" + zone.id + "_saved_horizontal_vanes_changed", {
            whenChanged: zone.vdevice + "/saved_horizontal_vanes",
            then: function () {
                logUserSetting(zone, "Запомненное положение жалюзи");
                evaluateZone(zone, true);
            }
        });

        defineRule("thermostat_" + zone.id + "_ac_night_mode_enabled_changed", {
            whenChanged: zone.vdevice + "/ac_night_mode_enabled",
            then: function () {
                logUserSetting(zone, "Ночной режим кондиционера");
                evaluateZone(zone, true);
            }
        });

        defineRule("thermostat_" + zone.id + "_ac_night_fan_speed_changed", {
            whenChanged: zone.vdevice + "/ac_night_fan_speed",
            then: function () {
                logUserSetting(zone, "Ночная скорость вентилятора");
                evaluateZone(zone, true);
            }
        });

        if (hasAc(zone)) {
            defineRule("thermostat_" + zone.id + "_ac_active_mode_changed", {
                whenChanged: zone.ac.activeModeTopic,
                then: function () {
                    handleAcActiveModeChanged(zone);
                }
            });

            if (hasTopic(zone.ac.connectedTopic)) {
                defineRule("thermostat_" + zone.id + "_ac_connected_changed", {
                    whenChanged: zone.ac.connectedTopic,
                    then: function () {
                        evaluateZone(zone, true);
                    }
                });
            }

            if (hasTopic(zone.ac.targetTemperatureTopic)) {
                defineRule("thermostat_" + zone.id + "_ac_target_changed", {
                    whenChanged: zone.ac.targetTemperatureTopic,
                    then: function () {
                        evaluateZone(zone, true);
                    }
                });
            }

            if (hasTopic(zone.ac.horizontalVanesTopic)) {
                defineRule("thermostat_" + zone.id + "_ac_horizontal_vanes_changed", {
                    whenChanged: zone.ac.horizontalVanesTopic,
                    then: function (newValue) {
                        if (Math.round(Number(newValue)) !== zone.state.lastAcVanesCommand) {
                            rememberUserHorizontalVanes(zone, newValue, "изменение положения жалюзи вне команды WB");
                        }

                        evaluateZone(zone, true);
                    }
                });
            }
        }
    }
}

function handleNightModeChanged() {
    evaluateAllZones(true);
}

function defineNightModeRule() {
    defineRule("thermostats_600_night_mode_changed", {
        whenChanged: DAY_NIGHT_TOPIC,
        then: function () {
            handleNightModeChanged();
        }
    });
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
defineNightModeRule();

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
        evaluateAllZones(true);
    }
});
