// 300_outdoor_lighting.js
// 05 33 Верхнемакарово, здание: Гараж.
// Управление наружным освещением по системному датчику day_night.
// Ночь: забор ул. Дачная и забор ул. Колхозная включены от заката до восхода.
// Вечер: фасады, дорожки и гирлянда включены от заката до 01:00.
// Скрипт восстанавливает требуемые состояния при запуске и далее проверяет их раз в минуту.

var SYSTEM_NAME = "свет";
var SCRIPT_NAME = "300_outdoor_lighting";
var CONTEXT_NAME = "улица";

var DAY_NIGHT_DEVICE_ID = "day_night";

var CHECK_CRON = "*/1 * * * *";

var NIGHT_CHANNELS = [
    {
        channel: "A02/K1",
        title: "Забор ул. Дачная"
    },
    {
        channel: "A02/K3",
        title: "Забор ул. Колхозная"
    }
];

var EVENING_CHANNELS = [
    {
        channel: "A03/K1",
        title: "Фасад большого гаража"
    },
    {
        channel: "A03/K2",
        title: "Фасад Дом заказчика"
    },
    {
        channel: "A02/K2",
        title: "Дорожки"
    },
    {
        channel: "A01/K3",
        title: "Гирлянда большой гараж"
    }
];

var STATE = {
    initialized: false,
    lastNight: null,
    lastEvening: null,
    lastSourceError: "",
    lastMissingChannels: ""
};

// -------------------- ОБЩИЕ ФУНКЦИИ --------------------

function boolToText(value) {
    return value ? "да" : "нет";
}

function valueToBool(value) {
    return value === true || value === 1 || value === "1" || value === "true" || value === "ON";
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

function joinChannelNames(items) {
    var result = [];
    var i;

    for (i = 0; i < items.length; i++) {
        result.push(items[i].channel);
    }

    return result.join(", ");
}

function joinMissingChannels(items) {
    var result = [];
    var i;

    for (i = 0; i < items.length; i++) {
        result.push(items[i]);
    }

    return result.join(", ");
}

// -------------------- СИСТЕМНЫЙ ЖУРНАЛ --------------------

function writeLog(eventName, eventText, params) {
    var message = "[" + SYSTEM_NAME + "][" + SCRIPT_NAME + "][" + CONTEXT_NAME + "]; " +
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

function logSourceError(errorText) {
    if (STATE.lastSourceError === errorText) {
        return;
    }

    writeLog("ОШИБКА", "Нет корректного источника день/ночь", {
        "причина": errorText,
        "источник": DAY_NIGHT_DEVICE_ID
    });

    STATE.lastSourceError = errorText;
}

function clearSourceError() {
    if (STATE.lastSourceError === "") {
        return;
    }

    writeLog("СОСТОЯНИЕ", "Источник день/ночь восстановлен", {
        "источник": DAY_NIGHT_DEVICE_ID
    });

    STATE.lastSourceError = "";
}

function logMissingChannels(missingChannels) {
    var key;

    if (missingChannels.length === 0) {
        if (STATE.lastMissingChannels !== "") {
            writeLog("СОСТОЯНИЕ", "Все каналы наружного освещения доступны", {});
            STATE.lastMissingChannels = "";
        }
        return;
    }

    key = joinMissingChannels(missingChannels);

    if (STATE.lastMissingChannels === key) {
        return;
    }

    writeLog("ОШИБКА", "Недоступны каналы наружного освещения", {
        "канал": key
    });

    STATE.lastMissingChannels = key;
}

// -------------------- ЧТЕНИЕ ИСТОЧНИКА --------------------

function readBoolControl(controlName) {
    var topic = DAY_NIGHT_DEVICE_ID + "/" + controlName;

    if (typeof dev[topic] === "undefined") {
        return null;
    }

    return valueToBool(dev[topic]);
}

function readSourceState() {
    var calculationOk = readBoolControl("calculation_ok");
    var isNight = readBoolControl("is_night");
    var isEvening = readBoolControl("is_evening_light_time");

    if (calculationOk === null) {
        return {
            ok: false,
            error: "нет канала day_night/calculation_ok"
        };
    }

    if (!calculationOk) {
        return {
            ok: false,
            error: "day_night/calculation_ok=false"
        };
    }

    if (isNight === null) {
        return {
            ok: false,
            error: "нет канала day_night/is_night"
        };
    }

    if (isEvening === null) {
        return {
            ok: false,
            error: "нет канала day_night/is_evening_light_time"
        };
    }

    return {
        ok: true,
        isNight: isNight,
        isEvening: isEvening
    };
}

// -------------------- УПРАВЛЕНИЕ КАНАЛАМИ --------------------

function setOutputChannel(channel, targetValue, changedChannels, missingChannels) {
    if (typeof dev[channel] === "undefined") {
        missingChannels.push(channel);
        return;
    }

    if (valueToBool(dev[channel]) === targetValue) {
        return;
    }

    dev[channel] = targetValue;
    changedChannels.push(channel);
}

function applyGroup(groupName, groupTitle, channels, targetValue, reasonText, missingChannels) {
    var changedChannels = [];
    var i;
    var commandText;

    for (i = 0; i < channels.length; i++) {
        setOutputChannel(channels[i].channel, targetValue, changedChannels, missingChannels);
    }

    if (changedChannels.length === 0) {
        return;
    }

    commandText = targetValue ? "Включить " + groupTitle : "Выключить " + groupTitle;

    writeLog("КОМАНДА", commandText, {
        "группа": groupName,
        "причина": reasonText,
        "канал": changedChannels.join(", "),
        "значение в канал": targetValue ? "ON" : "OFF"
    });
}

function logModeIfChanged(source) {
    if (!STATE.initialized) {
        return;
    }

    if (STATE.lastNight === source.isNight && STATE.lastEvening === source.isEvening) {
        return;
    }

    writeLog("СОСТОЯНИЕ", "Режим наружного освещения изменён", {
        "ночь": boolToText(source.isNight),
        "вечер": boolToText(source.isEvening)
    });
}

function applyOutdoorLighting(reasonText) {
    var source = readSourceState();
    var missingChannels = [];

    if (!source.ok) {
        logSourceError(source.error);
        return;
    }

    clearSourceError();
    logModeIfChanged(source);

    applyGroup(
        "night",
        "ночное освещение",
        NIGHT_CHANNELS,
        source.isNight,
        source.isNight ? "day_night/is_night=true" : "day_night/is_night=false",
        missingChannels
    );

    applyGroup(
        "evening",
        "вечернее освещение",
        EVENING_CHANNELS,
        source.isEvening,
        source.isEvening ? "day_night/is_evening_light_time=true" : "day_night/is_evening_light_time=false",
        missingChannels
    );

    logMissingChannels(missingChannels);

    STATE.lastNight = source.isNight;
    STATE.lastEvening = source.isEvening;
}

// -------------------- ЗАПУСК --------------------

writeLog("СКРИПТ", "Скрипт загружен", {
    "источник": DAY_NIGHT_DEVICE_ID,
    "ночные_каналы": joinChannelNames(NIGHT_CHANNELS),
    "вечерние_каналы": joinChannelNames(EVENING_CHANNELS)
});

applyOutdoorLighting("старт скрипта");

STATE.initialized = true;

writeLog("СКРИПТ", "Стартовая инициализация завершена", {
    "источник": DAY_NIGHT_DEVICE_ID
});

defineRule("outdoor_lighting_night_changed", {
    whenChanged: DAY_NIGHT_DEVICE_ID + "/is_night",
    then: function () {
        applyOutdoorLighting("изменение признака ночь");
    }
});

defineRule("outdoor_lighting_evening_changed", {
    whenChanged: DAY_NIGHT_DEVICE_ID + "/is_evening_light_time",
    then: function () {
        applyOutdoorLighting("изменение признака вечер");
    }
});

defineRule("outdoor_lighting_calculation_changed", {
    whenChanged: DAY_NIGHT_DEVICE_ID + "/calculation_ok",
    then: function () {
        applyOutdoorLighting("изменение статуса расчёта день/ночь");
    }
});

defineRule("outdoor_lighting_periodic_restore", {
    when: cron(CHECK_CRON),
    then: function () {
        applyOutdoorLighting("периодическое восстановление состояния");
    }
});
