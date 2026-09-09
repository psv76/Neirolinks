// 620_thermostats.js
// Объект: 05 31 Иволга 13
//
// Simple-термостаты отопления дома после фактической сверки каналов 09.09.2026.
// Wiren Board владеет логикой и физическими выходами. Sprut.hub используется как интерфейс.
//
// Не используется:
// - A14/K4: пустой канал, ничего не подключено.
// - NL_simple_thermostat_604: не создаётся, A08/K4 работает вместе с A08/K1.
// - NL_simple_thermostat_011: не создаётся, A09/K4 и A09/K5 работают вместе с NL_simple_thermostat_010.
// - NL_simple_thermostat_615: не создаётся, A14/K4 пустой.
//
// Первый запуск безопасный: DEFAULT_TARGET_STATE = false.
// После установки термостаты появляются выключенными. Включать вручную после проверки.

var SYSTEM_NAME = "отопление";
var SCRIPT_NAME = "620_thermostats";

var DEFAULT_TARGET_STATE = false;
var START_DELAY_MS = 3000;
var PERIODIC_SYNC_CRON = "*/1 * * * *";

var AIR_VALID_MIN = -20;
var AIR_VALID_MAX = 60;
var FLOOR_VALID_MIN = -20;
var FLOOR_VALID_MAX = 70;

var TEMP_PUBLISH_MIN_INTERVAL_MS = 60000;
var TEMP_PUBLISH_MIN_DELTA = 0.1;

var ZONES = [
    {
        id: "601",
        deviceId: "NL_simple_thermostat_601",
        title: "ТП мастер спальня + ТП мастер гардероб",
        context: "мастер спальня + мастер гардероб",
        sensor: "903.09_TEMP_NONE/External Sensor 1",
        sensorKind: "floor",
        outputs: ["A08/K1", "A08/K4"],
        defaultTarget: 26,
        minTarget: 18,
        maxTarget: 26,
        hysteresis: 1.0,
        hardMax: 27
    },
    {
        id: "602",
        deviceId: "NL_simple_thermostat_602",
        title: "ТП гостевая спальня",
        context: "гостевая спальня, тёплый пол",
        sensor: "902.11_M1W2_TEMP_NONE/External Sensor 1",
        sensorKind: "floor",
        outputs: ["A08/K2"],
        defaultTarget: 26,
        minTarget: 18,
        maxTarget: 26,
        hysteresis: 1.0,
        hardMax: 27
    },
    {
        id: "603",
        deviceId: "NL_simple_thermostat_603",
        title: "ТП кабинет",
        context: "кабинет, тёплый пол",
        sensor: "902.09_M1W2_TEMP_NONE/External Sensor 1",
        sensorKind: "floor",
        outputs: ["A08/K3"],
        defaultTarget: 26,
        minTarget: 18,
        maxTarget: 26,
        hysteresis: 1.0,
        hardMax: 27
    },
    {
        id: "005",
        deviceId: "NL_simple_thermostat_005",
        title: "Радиатор прихожая",
        context: "прихожая, радиатор",
        sensor: "902.05_MSW_THM/Temperature",
        sensorKind: "air",
        outputs: ["A08/K5"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "006",
        deviceId: "NL_simple_thermostat_006",
        title: "Радиатор гостевая спальня",
        context: "гостевая спальня, радиатор",
        sensor: "902.10_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A08/K6"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "007",
        deviceId: "NL_simple_thermostat_007",
        title: "Радиатор мастер санузел",
        context: "мастер санузел, радиатор",
        sensor: "903.05_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A09/K1"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "008",
        deviceId: "NL_simple_thermostat_008",
        title: "Радиатор кабинет",
        context: "кабинет, радиатор",
        sensor: "902.08_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A09/K2"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "009",
        deviceId: "NL_simple_thermostat_009",
        title: "Радиатор мастер спальня",
        context: "мастер спальня, радиатор",
        sensor: "903.08_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A09/K3"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "010",
        deviceId: "NL_simple_thermostat_010",
        title: "Радиаторы гостиная",
        context: "гостиная, радиаторы",
        sensor: "902.01_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A09/K4", "A09/K5"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "606",
        deviceId: "NL_simple_thermostat_606",
        title: "ГП прихожая",
        context: "прихожая, горячий пол",
        sensor: "902.06_M1W2_TEMP_NONE/External Sensor 1",
        sensorKind: "floor",
        outputs: ["A13/K1"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "607",
        deviceId: "NL_simple_thermostat_607",
        title: "ГП санузел",
        context: "санузел, горячий пол",
        sensor: "902.04_M1W2_LEAK_TEMP/External Sensor 2",
        sensorKind: "floor",
        outputs: ["A13/K2"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "608",
        deviceId: "NL_simple_thermostat_608",
        title: "ГП гардероб прихожей",
        context: "гардероб прихожей, горячий пол",
        sensor: "902.07_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A13/K3"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "609",
        deviceId: "NL_simple_thermostat_609",
        title: "ГП ванная",
        context: "ванная, горячий пол",
        sensor: "902.13_M1W2_LEAK_TEMP/External Sensor 2",
        sensorKind: "floor",
        outputs: ["A13/K4"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "610",
        deviceId: "NL_simple_thermostat_610",
        title: "ГП постирочная",
        context: "постирочная, горячий пол",
        sensor: "902.14_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A13/K5"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    },
    {
        id: "611",
        deviceId: "NL_simple_thermostat_611",
        title: "ГП гостиная",
        context: "гостиная, горячий пол",
        sensor: "902.02_M1W2_TEMP_NONE/External Sensor 1",
        sensorKind: "floor",
        outputs: ["A13/K6"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "612",
        deviceId: "NL_simple_thermostat_612",
        title: "ГП кухня",
        context: "кухня, горячий пол",
        sensor: "903.02_M1W2_LEAK_TEMP/External Sensor 2",
        sensorKind: "floor",
        outputs: ["A14/K1"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "613",
        deviceId: "NL_simple_thermostat_613",
        title: "ГП мастер санузел",
        context: "мастер санузел, горячий пол",
        sensor: "903.06_TEMP_NONE/External Sensor 2",
        sensorKind: "floor",
        outputs: ["A14/K2"],
        defaultTarget: 28,
        minTarget: 18,
        maxTarget: 35,
        hysteresis: 1.0,
        hardMax: null
    },
    {
        id: "614",
        deviceId: "NL_simple_thermostat_614",
        title: "ГП кладовка",
        context: "кладовка, горячий пол",
        sensor: "903.03_MSW_TH/Temperature",
        sensorKind: "air",
        outputs: ["A14/K3"],
        defaultTarget: 22,
        minTarget: 15,
        maxTarget: 28,
        hysteresis: 0.3,
        hardMax: null
    }
];

function ts() {
    return new Date().getTime();
}

function round1(value) {
    return Math.round(Number(value) * 10) / 10;
}

function isNumber(value) {
    return typeof value === "number" && isFinite(value) && !isNaN(value);
}

function boolValue(value) {
    return value === true || value === 1 || value === "1" || value === "true" || value === "ON";
}

function setIfChanged(topic, value) {
    if (dev[topic] !== value) {
        dev[topic] = value;
        return true;
    }
    return false;
}

function setBoolIfChanged(topic, value) {
    var next = !!value;
    if (boolValue(dev[topic]) !== next) {
        dev[topic] = next;
        return true;
    }
    return false;
}

function setNumberIfChanged(topic, value) {
    var oldValue = Number(dev[topic]);
    var newValue = Number(value);
    if (!isFinite(oldValue) || Math.abs(oldValue - newValue) > 0.001) {
        dev[topic] = newValue;
        return true;
    }
    return false;
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

function fmt(value) {
    var n = Number(value);
    if (!isFinite(n)) {
        return "нет данных";
    }
    return String(round1(n));
}

function kindTitle(zone) {
    return zone.sensorKind === "floor" ? "пол" : "воздух";
}

function validTemp(zone, value) {
    var n = Number(value);
    if (!isFinite(n)) {
        return false;
    }
    if (zone.sensorKind === "floor") {
        return n >= FLOOR_VALID_MIN && n <= FLOOR_VALID_MAX;
    }
    return n >= AIR_VALID_MIN && n <= AIR_VALID_MAX;
}

function paramsText(params) {
    var res = [];
    var k;
    for (k in params) {
        if (params.hasOwnProperty(k)) {
            res.push(k + "=" + params[k]);
        }
    }
    return res.length ? "; " + res.join("; ") : "";
}

function writeLog(zone, level, eventName, text, params) {
    var context = zone && zone.context ? zone.context : "общий";
    var msg = "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "][" + context + "]; " + eventName + "=" + text + paramsText(params || {});
    if (level === "error") {
        log.error(msg);
    } else if (level === "warning") {
        log.warning(msg);
    } else {
        log.info(msg);
    }
}

function defineThermostat(zone) {
    defineVirtualDevice(zone.deviceId, {
        title: zone.title,
        cells: {
            target_state: {
                title: "Термостат",
                type: "switch",
                value: DEFAULT_TARGET_STATE,
                order: 10
            },
            temperature: {
                title: zone.sensorKind === "floor" ? "Температура пола" : "Температура воздуха",
                type: "temperature",
                value: 0,
                readonly: true,
                order: 20
            },
            target_temperature: {
                title: zone.sensorKind === "floor" ? "Уставка пола" : "Уставка воздуха",
                type: "range",
                value: zone.defaultTarget,
                min: zone.minTarget,
                max: zone.maxTarget,
                order: 30
            },
            state: {
                title: "Состояние",
                type: "text",
                value: "Инициализация",
                readonly: true,
                order: 40
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

    zone.state = {
        heat: false,
        lastText: "",
        lastTemp: null,
        lastTempTs: 0
    };
}

function readZone(zone) {
    var raw = dev[zone.sensor];
    var target = clamp(dev[zone.deviceId + "/target_temperature"], zone.minTarget, zone.maxTarget);

    setNumberIfChanged(zone.deviceId + "/target_temperature", target);

    return {
        enabled: boolValue(dev[zone.deviceId + "/target_state"]),
        valid: validTemp(zone, raw),
        temperature: Number(raw),
        target: target
    };
}

function publishTemperature(zone, temperature) {
    var now = ts();
    if (zone.state.lastTemp === null || Math.abs(temperature - zone.state.lastTemp) >= TEMP_PUBLISH_MIN_DELTA || now - zone.state.lastTempTs >= TEMP_PUBLISH_MIN_INTERVAL_MS) {
        setNumberIfChanged(zone.deviceId + "/temperature", round1(temperature));
        zone.state.lastTemp = temperature;
        zone.state.lastTempTs = now;
    }
}

function decide(zone, data) {
    if (!data.enabled) {
        zone.state.heat = false;
        return { heat: false, text: "Термостат выключен", level: "info", reason: "выключен пользователем" };
    }

    if (!data.valid) {
        zone.state.heat = false;
        return { heat: false, text: "Ошибка датчика, сервопривод закрыт", level: "error", reason: "нет корректного значения датчика" };
    }

    if (zone.hardMax !== null && data.temperature >= zone.hardMax) {
        zone.state.heat = false;
        return { heat: false, text: "Жёсткое ограничение температуры, сервопривод закрыт", level: "error", reason: "достигнут предел " + zone.hardMax + " °C" };
    }

    if (data.temperature <= data.target - zone.hysteresis) {
        zone.state.heat = true;
    }
    if (data.temperature >= data.target) {
        zone.state.heat = false;
    }

    if (zone.state.heat) {
        return { heat: true, text: zone.sensorKind === "floor" ? "Нагрев пола" : "Нагрев помещения", level: "info", reason: kindTitle(zone) + " ниже уставки" };
    }
    return { heat: false, text: zone.sensorKind === "floor" ? "Пол в норме" : "Температура в норме", level: "info", reason: kindTitle(zone) + " достиг уставки" };
}

function applyOutputs(zone, heat, data, reason) {
    var i;
    var changed = false;

    for (i = 0; i < zone.outputs.length; i++) {
        if (setBoolIfChanged(zone.outputs[i], heat)) {
            changed = true;
        }
    }

    setBoolIfChanged(zone.deviceId + "/current_state", heat);

    if (changed) {
        writeLog(zone, "info", "КОМАНДА", heat ? "Открыть сервопривод" : "Закрыть сервопривод", {
            причина: reason,
            датчик: zone.sensor,
            температура: fmt(data.temperature),
            уставка: fmt(data.target),
            каналы: zone.outputs.join(", "),
            команда: heat ? "ON" : "OFF"
        });
    }
}

function publishState(zone, decision, data) {
    var changed = false;

    if (zone.state.lastText !== decision.text) {
        setIfChanged(zone.deviceId + "/state", decision.text);
        changed = true;
    }

    if (changed) {
        writeLog(zone, decision.level, decision.level === "error" ? "АВАРИЯ" : "СОСТОЯНИЕ", decision.text, {
            причина: decision.reason,
            датчик: zone.sensor,
            тип: kindTitle(zone),
            температура: data.valid ? fmt(data.temperature) : "нет данных",
            уставка: fmt(data.target),
            каналы: zone.outputs.join(", ")
        });
    }

    zone.state.lastText = decision.text;
}

function evaluateZone(zone, forceLog) {
    var data = readZone(zone);
    var decision = decide(zone, data);

    if (data.valid) {
        publishTemperature(zone, data.temperature);
    }

    applyOutputs(zone, decision.heat, data, decision.reason);
    publishState(zone, decision, data);

    if (forceLog) {
        writeLog(zone, "info", "ПРОВЕРКА", "Расчёт зоны выполнен", {
            датчик: zone.sensor,
            тип: kindTitle(zone),
            температура: data.valid ? fmt(data.temperature) : "нет данных",
            уставка: fmt(data.target),
            нагрев: decision.heat ? "ON" : "OFF"
        });
    }
}

function evaluateAll(forceLog) {
    var i;
    for (i = 0; i < ZONES.length; i++) {
        evaluateZone(ZONES[i], forceLog);
    }
}

function logUserSetting(zone, name) {
    writeLog(zone, "info", "НАСТРОЙКА", "Пользователь изменил настройку", {
        параметр: name,
        термостат: zone.deviceId,
        включен: boolValue(dev[zone.deviceId + "/target_state"]) ? "да" : "нет",
        уставка: fmt(dev[zone.deviceId + "/target_temperature"])
    });
}

function defineZoneRules(zone) {
    defineRule("thermostat_" + zone.id + "_sensor", {
        whenChanged: zone.sensor,
        then: function () {
            evaluateZone(zone, false);
        }
    });

    defineRule("thermostat_" + zone.id + "_target", {
        whenChanged: zone.deviceId + "/target_temperature",
        then: function () {
            logUserSetting(zone, zone.sensorKind === "floor" ? "Уставка пола" : "Уставка воздуха");
            evaluateZone(zone, true);
        }
    });

    defineRule("thermostat_" + zone.id + "_state", {
        whenChanged: zone.deviceId + "/target_state",
        then: function () {
            logUserSetting(zone, "Термостат");
            evaluateZone(zone, true);
        }
    });
}

function init() {
    var i;
    for (i = 0; i < ZONES.length; i++) {
        defineThermostat(ZONES[i]);
        defineZoneRules(ZONES[i]);
    }

    writeLog(null, "info", "СКРИПТ", "Скрипт загружен", { зон: ZONES.length });

    setTimeout(function () {
        evaluateAll(true);
        writeLog(null, "info", "СКРИПТ", "Стартовая инициализация завершена", { зон: ZONES.length });
    }, START_DELAY_MS);
}

init();

defineRule("thermostats_620_periodic_sync", {
    when: cron(PERIODIC_SYNC_CRON),
    then: function () {
        evaluateAll(true);
    }
});
