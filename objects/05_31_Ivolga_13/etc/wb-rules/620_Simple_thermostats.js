// 620_Simple_thermostats.js
// Объект: 05 31 Иволга 13
//
// Простые зональные термостаты:
//   1 датчик температуры -> 1 физический релейный выход.
// Логика и ownership находятся в Wiren Board.
// Sprut.hub после проверки шаблона NL_simple_thermostat используется только как UI.
//
// ВАЖНО:
// - target_state новых виртуальных устройств по умолчанию OFF.
// - Это безопасный режим первого ввода в эксплуатацию.
// - После проверки конкретной зоны термостат включается пользователем.
// - Гостевая спальня / кабинет временно привязаны по текущему WebUI.
// - 602 "Мастер тамбур" и 611 "Коридор" используют ближайшие доступные датчики;
//   эти две привязки требуется подтвердить на объекте.

var SYSTEM_NAME = "отопление";
var SCRIPT_NAME = "620_Simple_thermostats";

var TARGET_MIN = 15;
var TARGET_MAX = 30;
var SENSOR_VALID_MIN = -20;
var SENSOR_VALID_MAX = 70;
var TEMP_PUBLISH_MIN_DELTA = 0.1;
var TEMP_PUBLISH_MIN_INTERVAL_MS = 60000;

var ZONES = [
    {
        id: "601",
        context: "мастер спальня",
        title: "Термостат мастер спальня",
        sensorTopic: "wb-m1w2_147/External Sensor 1",
        sensorTitle: "Пол мастер спальни",
        outputTopic: "A08/K1",
        outputTitle: "601 ТП Мастер спальня",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "602",
        context: "мастер тамбур",
        title: "Термостат мастер тамбур",
        sensorTopic: "wb-msw-v4_206/Temperature",
        sensorTitle: "Воздух мастер спальни (временно для тамбура)",
        outputTopic: "A08/K2",
        outputTitle: "602 ТП Мастер тамбур",
        defaultTarget: 22,
        hysteresis: 0.3,
        provisional: true
    },
    {
        id: "603",
        context: "мастер гардероб",
        title: "Термостат мастер гардероб",
        sensorTopic: "wb-msw-v4_117/Temperature",
        sensorTitle: "Воздух гардероб мастер спальни",
        outputTopic: "A08/K3",
        outputTitle: "603 ТП Мастер гардероб",
        defaultTarget: 22,
        hysteresis: 0.3
    },
    {
        id: "604",
        context: "гостевая спальня",
        title: "Термостат гостевая спальня пол",
        sensorTopic: "902.11_M1W2_TEMP_NONE/External Sensor 1",
        sensorTitle: "Пол гостевая спальня",
        outputTopic: "A08/K4",
        outputTitle: "604 ТП Гостевая спальня",
        defaultTarget: 25,
        hysteresis: 1.0,
        provisional: true
    },
    {
        id: "605",
        context: "кабинет",
        title: "Термостат кабинет пол",
        sensorTopic: "902.09_M1W2_TEMP_NONE/External Sensor 1",
        sensorTitle: "Пол кабинет",
        outputTopic: "A08/K5",
        outputTitle: "605 ТП кабинет",
        defaultTarget: 25,
        hysteresis: 1.0,
        provisional: true
    },
    {
        id: "606",
        context: "прихожая",
        title: "Термостат прихожая пол",
        sensorTopic: "902.06_M1W2_TEMP_NONE/External Sensor 1",
        sensorTitle: "Пол прихожая",
        outputTopic: "A13/K1",
        outputTitle: "606 ГП прихожая",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "607",
        context: "санузел прихожей",
        title: "Термостат санузел прихожей",
        sensorTopic: "902.04_M1W2_LEAK_TEMP/External Sensor 2",
        sensorTitle: "Пол санузел прихожей",
        outputTopic: "A13/K2",
        outputTitle: "607 ГП с/у гостевой",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "608",
        context: "гардероб прихожей",
        title: "Термостат гардероб прихожей",
        sensorTopic: "902.07_MSW_TH/Temperature",
        sensorTitle: "Воздух гардероб прихожей",
        outputTopic: "A13/K3",
        outputTitle: "608 ГП гардероб 1",
        defaultTarget: 22,
        hysteresis: 0.3
    },
    {
        id: "609",
        context: "ванная",
        title: "Термостат ванная",
        sensorTopic: "902.13_M1W2_LEAK_TEMP/External Sensor 2",
        sensorTitle: "Пол ванная",
        outputTopic: "A13/K4",
        outputTitle: "609 ГП ванная",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "610",
        context: "постирочная",
        title: "Термостат постирочная",
        sensorTopic: "902.14_MSW_TH/Temperature",
        sensorTitle: "Воздух постирочная",
        outputTopic: "A13/K5",
        outputTitle: "610 ГП постирочная",
        defaultTarget: 22,
        hysteresis: 0.3
    },
    {
        id: "611",
        context: "коридор",
        title: "Термостат коридор",
        sensorTopic: "902.05_MSW_THM/Temperature",
        sensorTitle: "Воздух прихожая (временно для коридора)",
        outputTopic: "A13/K6",
        outputTitle: "611 ГП коридор",
        defaultTarget: 22,
        hysteresis: 0.3,
        provisional: true
    },
    {
        id: "612",
        context: "гостиная",
        title: "Термостат гостиная пол",
        sensorTopic: "902.02_M1W2_TEMP_NONE/External Sensor 1",
        sensorTitle: "Пол гостиная",
        outputTopic: "A14/K1",
        outputTitle: "612 ГП гостиная",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "613",
        context: "кухня",
        title: "Термостат кухня пол",
        sensorTopic: "wb-m1w2_165/External Sensor 2",
        sensorTitle: "Пол кухня",
        outputTopic: "A14/K2",
        outputTitle: "613 ГП кухня",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "614",
        context: "мастер ванная",
        title: "Термостат мастер ванная",
        sensorTopic: "wb-m1w2_138/External Sensor 2",
        sensorTitle: "Пол мастер ванной",
        outputTopic: "A14/K3",
        outputTitle: "614 ГП Мастер ванная",
        defaultTarget: 25,
        hysteresis: 1.0
    },
    {
        id: "615",
        context: "кладовка",
        title: "Термостат кладовка",
        sensorTopic: "wb-msw-v4_140/Temperature",
        sensorTitle: "Воздух кладовка",
        outputTopic: "A14/K4",
        outputTitle: "615 ГП кладовка",
        defaultTarget: 22,
        hysteresis: 0.3
    },
    {
        id: "620",
        context: "прихожая радиатор",
        title: "Термостат радиатор прихожая",
        sensorTopic: "902.05_MSW_THM/Temperature",
        sensorTitle: "Воздух прихожая",
        outputTopic: "A09/K1",
        outputTitle: "620 Радиатор прихожая",
        defaultTarget: 22,
        hysteresis: 0.3
    },
    {
        id: "621",
        context: "гостевая спальня радиатор",
        title: "Термостат радиатор гостевая спальня",
        sensorTopic: "902.10_MSW_TH/Temperature",
        sensorTitle: "Воздух гостевая спальня",
        outputTopic: "A09/K2",
        outputTitle: "621 Радиатор гостевая спальня",
        defaultTarget: 22,
        hysteresis: 0.3,
        provisional: true
    }
];

function nowMs() {
    return new Date().getTime();
}

function round1(value) {
    return Math.round(Number(value) * 10) / 10;
}

function clamp(value, minValue, maxValue) {
    var n = Number(value);
    if (!isFinite(n)) return minValue;
    if (n < minValue) return minValue;
    if (n > maxValue) return maxValue;
    return n;
}

function readBool(value) {
    return value === true || value === 1 || value === "1" || value === "true" || value === "ON";
}

function isValidTemperature(value) {
    var n = Number(value);
    return isFinite(n) && n >= SENSOR_VALID_MIN && n <= SENSOR_VALID_MAX;
}

function setIfChanged(topic, value) {
    if (dev[topic] !== value) dev[topic] = value;
}

function setNumberIfChanged(topic, value) {
    var oldValue = Number(dev[topic]);
    var newValue = Number(value);
    if (!isFinite(oldValue) || Math.abs(oldValue - newValue) > 0.001) dev[topic] = newValue;
}

function writeLog(zone, eventName, text, params) {
    var items = [];
    var key;
    var message;

    if (params) {
        for (key in params) {
            if (params.hasOwnProperty(key)) items.push(key + "=" + params[key]);
        }
    }

    message = "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "][" + zone.context + "]; " +
        eventName + "=" + text + (items.length ? "; " + items.join("; ") : "");

    if (eventName === "АВАРИЯ") log.error(message);
    else if (eventName === "ОШИБКА") log.warning(message);
    else log.info(message);
}

function defineThermostat(zone) {
    zone.vdevice = "NL_simple_thermostat_" + zone.id;

    defineVirtualDevice(zone.vdevice, {
        title: zone.title,
        cells: {
            target_state: { title: "Термостат", type: "switch", value: false, readonly: false, order: 10 },
            temperature: { title: "Температура", type: "temperature", value: 0, readonly: true, order: 20 },
            target_temperature: {
                title: "Уставка",
                type: "range",
                value: zone.defaultTarget,
                min: TARGET_MIN,
                max: TARGET_MAX,
                readonly: false,
                order: 30
            },
            current_state: {
                title: "Sprut: текущий режим",
                type: "switch",
                value: false,
                readonly: true,
                order: 800
            },
            sensor_valid: { title: "Датчик исправен", type: "switch", value: false, readonly: true, order: 810 },
            state: { title: "Состояние", type: "text", value: "Инициализация", readonly: true, order: 820 }
        }
    });

    zone.runtime = {
        initialized: false,
        heat: readBool(dev[zone.outputTopic]),
        sensorValid: null,
        lastTarget: null,
        lastEnabled: null,
        lastTemp: null,
        lastTempPublishTs: 0,
        lastCommand: null
    };
}

function shouldPublishTemperature(zone, value, force) {
    if (force || zone.runtime.lastTemp === null) return true;
    if (Math.abs(Number(zone.runtime.lastTemp) - Number(value)) >= TEMP_PUBLISH_MIN_DELTA) return true;
    return (nowMs() - zone.runtime.lastTempPublishTs) >= TEMP_PUBLISH_MIN_INTERVAL_MS;
}

function publishTemperature(zone, value, force) {
    if (!shouldPublishTemperature(zone, value, force)) return;
    setNumberIfChanged(zone.vdevice + "/temperature", round1(value));
    zone.runtime.lastTemp = round1(value);
    zone.runtime.lastTempPublishTs = nowMs();
}

function setOutput(zone, value, reason, temp, target) {
    var command = !!value;

    if (readBool(dev[zone.outputTopic]) !== command) dev[zone.outputTopic] = command;
    setIfChanged(zone.vdevice + "/current_state", command);

    if (zone.runtime.lastCommand !== command) {
        zone.runtime.lastCommand = command;
        writeLog(zone, "КОМАНДА", command ? "Открыть сервопривод" : "Закрыть сервопривод", {
            "причина": reason,
            "датчик": zone.sensorTitle,
            "температура": isFinite(Number(temp)) ? round1(temp) : "нет данных",
            "уставка": round1(target),
            "гистерезис": zone.hysteresis,
            "канал": zone.outputTopic,
            "назначение": zone.outputTitle
        });
    }
}

function evaluateZone(zone, forceTemperaturePublish) {
    var rawTemp = dev[zone.sensorTopic];
    var sensorValid = isValidTemperature(rawTemp);
    var temp = sensorValid ? round1(rawTemp) : NaN;
    var enabled = readBool(dev[zone.vdevice + "/target_state"]);
    var target = round1(clamp(dev[zone.vdevice + "/target_temperature"], TARGET_MIN, TARGET_MAX));
    var stateText;

    setNumberIfChanged(zone.vdevice + "/target_temperature", target);
    setIfChanged(zone.vdevice + "/sensor_valid", sensorValid);
    if (sensorValid) publishTemperature(zone, temp, forceTemperaturePublish);

    if (zone.runtime.lastEnabled !== enabled) {
        zone.runtime.lastEnabled = enabled;
        writeLog(zone, "НАСТРОЙКА", enabled ? "Термостат включён" : "Термостат выключен", {
            "уставка": target,
            "канал": zone.outputTopic
        });
    }

    if (zone.runtime.lastTarget === null || Math.abs(Number(zone.runtime.lastTarget) - target) > 0.001) {
        zone.runtime.lastTarget = target;
        writeLog(zone, "НАСТРОЙКА", "Изменена уставка", { "уставка": target, "канал": zone.outputTopic });
    }

    if (zone.runtime.sensorValid !== sensorValid) {
        zone.runtime.sensorValid = sensorValid;
        if (sensorValid) {
            writeLog(zone, "СОСТОЯНИЕ", "Датчик температуры восстановлен", {
                "датчик": zone.sensorTopic,
                "температура": temp
            });
        } else {
            writeLog(zone, "АВАРИЯ", "Нет корректного значения температуры", {
                "датчик": zone.sensorTopic,
                "значение": rawTemp
            });
        }
    }

    if (!enabled) {
        zone.runtime.heat = false;
        stateText = "Выключен";
        setOutput(zone, false, "термостат выключен", temp, target);
        setIfChanged(zone.vdevice + "/state", stateText);
        zone.runtime.initialized = true;
        return;
    }

    if (!sensorValid) {
        zone.runtime.heat = false;
        stateText = "Ошибка датчика — сервопривод закрыт";
        setOutput(zone, false, "ошибка датчика", temp, target);
        setIfChanged(zone.vdevice + "/state", stateText);
        zone.runtime.initialized = true;
        return;
    }

    if (temp <= target - zone.hysteresis) zone.runtime.heat = true;
    if (temp >= target) zone.runtime.heat = false;

    if (zone.runtime.heat) {
        stateText = "Нагрев";
        setOutput(zone, true, "температура ниже уставки", temp, target);
    } else {
        stateText = "Температура в норме";
        setOutput(zone, false, "температура достигла уставки", temp, target);
    }

    setIfChanged(zone.vdevice + "/state", stateText);
    zone.runtime.initialized = true;
}

function createZoneRule(zone) {
    defineRule("simple_thermostat_" + zone.id, {
        whenChanged: [
            zone.sensorTopic,
            zone.outputTopic,
            zone.vdevice + "/target_state",
            zone.vdevice + "/target_temperature"
        ],
        then: function () {
            evaluateZone(zone, false);
        }
    });
}

function evaluateAll(forceTemperaturePublish) {
    var i;
    for (i = 0; i < ZONES.length; i++) evaluateZone(ZONES[i], forceTemperaturePublish);
}

(function () {
    var i;
    for (i = 0; i < ZONES.length; i++) {
        defineThermostat(ZONES[i]);
        createZoneRule(ZONES[i]);
    }
})();

setTimeout(function () {
    evaluateAll(true);
    log.info(
        "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "]; СТАРТ=Создано " + ZONES.length +
        " простых термостатов; новые target_state по умолчанию OFF"
    );
}, 5000);

setInterval(function () {
    evaluateAll(true);
}, TEMP_PUBLISH_MIN_INTERVAL_MS);
