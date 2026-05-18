// 290__day_night.js
// Системный датчик "День / Ночь" для Wiren Board.
//
// Логика:
// - рассчитывает восход и закат по координатам объекта;
// - создаёт read-only виртуальное устройство для WB, Sprut.hub и других WB-скриптов;
// - is_night = true от заката до восхода;
// - is_day = true от восхода до заката;
// - is_evening_light_time = true от заката до указанного времени;
// - состояние пересчитывается при запуске и далее раз в минуту.

var SYSTEM_NAME = "освещение";
var SCRIPT_NAME = "290__day_night";
var CONTEXT_NAME = "день ночь";

var DEVICE_ID = "day_night";

// -------------------- НАСТРОЙКИ ОБЪЕКТА --------------------

// Координаты объекта.
var LATITUDE = 56.8389;
var LONGITUDE = 60.6057;

// true = использовать локальное время и часовой пояс контроллера.
var USE_CONTROLLER_TIMEZONE = true;

// Ручной часовой пояс используется только если USE_CONTROLLER_TIMEZONE = false.
var MANUAL_UTC_OFFSET_HOURS = 5;

// До какого времени держать признак "вечернее освещение".
var EVENING_LIGHT_END_TIME = "01:00";

// -------------------- ВИРТУАЛЬНОЕ УСТРОЙСТВО --------------------

defineVirtualDevice(DEVICE_ID, {
    title: "День / Ночь",
    cells: {
        current_time: {
            title: "Текущее время",
            type: "text",
            value: "",
            readonly: true,
            order: 10
        },
        sunrise_time: {
            title: "Восход",
            type: "text",
            value: "",
            readonly: true,
            order: 20
        },
        sunset_time: {
            title: "Закат",
            type: "text",
            value: "",
            readonly: true,
            order: 30
        },
        state_text: {
            title: "Состояние",
            type: "text",
            value: "Расчёт",
            readonly: true,
            order: 40
        },
        is_day: {
            title: "День",
            type: "switch",
            value: false,
            readonly: true,
            order: 50
        },
        is_night: {
            title: "Ночь",
            type: "switch",
            value: false,
            readonly: true,
            order: 60
        },
        is_evening_light_time: {
            title: "Вечернее освещение",
            type: "switch",
            value: false,
            readonly: true,
            order: 70
        },
        evening_light_window: {
            title: "Период вечернего освещения",
            type: "text",
            value: "",
            readonly: true,
            order: 80
        },
        calculation_ok: {
            title: "Расчёт выполнен",
            type: "switch",
            value: false,
            readonly: true,
            order: 90
        },
        last_update: {
            title: "Последнее обновление",
            type: "text",
            value: "",
            readonly: true,
            order: 100
        }
    }
});

// -------------------- СОСТОЯНИЕ --------------------

var STATE = {
    initialized: false,
    lastNight: null,
    lastEveningLightTime: null,
    lastCalculationError: ""
};

// -------------------- ОБЩИЕ ФУНКЦИИ --------------------

function pad2(value) {
    value = Number(value);
    return value < 10 ? "0" + value : "" + value;
}

function degToRad(deg) {
    return deg * Math.PI / 180;
}

function radToDeg(rad) {
    return rad * 180 / Math.PI;
}

function normalizeMinutes(minutes) {
    minutes = Math.round(minutes);

    while (minutes < 0) {
        minutes += 1440;
    }

    while (minutes >= 1440) {
        minutes -= 1440;
    }

    return minutes;
}

function formatMinutes(minutes) {
    minutes = normalizeMinutes(minutes);

    var hours = Math.floor(minutes / 60);
    var mins = minutes % 60;

    return pad2(hours) + ":" + pad2(mins);
}

function parseTimeToMinutes(timeText) {
    var match;
    var hours;
    var minutes;

    if (!timeText || typeof timeText !== "string") {
        return null;
    }

    match = timeText.match(/^([0-9]{1,2}):([0-9]{2})$/);

    if (!match) {
        return null;
    }

    hours = parseInt(match[1], 10);
    minutes = parseInt(match[2], 10);

    if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
        return null;
    }

    return hours * 60 + minutes;
}

function getSystemUtcOffsetHours(date) {
    return -date.getTimezoneOffset() / 60;
}

function getUsedUtcOffsetHours(date) {
    if (USE_CONTROLLER_TIMEZONE) {
        return getSystemUtcOffsetHours(date);
    }

    return MANUAL_UTC_OFFSET_HOURS;
}

function getLocalDayOfYear(date) {
    var start = new Date(date.getFullYear(), 0, 0);
    var diff = date.getTime() - start.getTime();

    return Math.floor(diff / 86400000);
}

function getUtcDayOfYear(date) {
    var start = Date.UTC(date.getUTCFullYear(), 0, 0);
    var now = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());

    return Math.floor((now - start) / 86400000);
}

function getLocalNowParts(date) {
    var shifted;

    if (USE_CONTROLLER_TIMEZONE) {
        return {
            year: date.getFullYear(),
            month: date.getMonth() + 1,
            day: date.getDate(),
            hours: date.getHours(),
            minutes: date.getMinutes(),
            seconds: date.getSeconds(),
            dayOfYear: getLocalDayOfYear(date)
        };
    }

    shifted = new Date(date.getTime() + MANUAL_UTC_OFFSET_HOURS * 60 * 60 * 1000);

    return {
        year: shifted.getUTCFullYear(),
        month: shifted.getUTCMonth() + 1,
        day: shifted.getUTCDate(),
        hours: shifted.getUTCHours(),
        minutes: shifted.getUTCMinutes(),
        seconds: shifted.getUTCSeconds(),
        dayOfYear: getUtcDayOfYear(shifted)
    };
}

function formatCurrentDateTime(date) {
    var p = getLocalNowParts(date);

    return pad2(p.day) + "." + pad2(p.month) + "." + p.year + " " + pad2(p.hours) + ":" + pad2(p.minutes);
}

function getCurrentLocalMinutes(date) {
    var p = getLocalNowParts(date);

    return p.hours * 60 + p.minutes;
}

function isTimeInWindow(nowMinutes, startMinutes, endMinutes) {
    nowMinutes = normalizeMinutes(nowMinutes);
    startMinutes = normalizeMinutes(startMinutes);
    endMinutes = normalizeMinutes(endMinutes);

    if (startMinutes === endMinutes) {
        return false;
    }

    if (startMinutes < endMinutes) {
        return nowMinutes >= startMinutes && nowMinutes < endMinutes;
    }

    return nowMinutes >= startMinutes || nowMinutes < endMinutes;
}

function setControl(controlName, value) {
    var topic = DEVICE_ID + "/" + controlName;

    if (dev[topic] !== value) {
        dev[topic] = value;
    }
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

function commonLogParams(now, sun, isEveningLightTime) {
    return {
        "текущее_время": formatCurrentDateTime(now),
        "восход": sun.sunriseText,
        "закат": sun.sunsetText,
        "вечернее_освещение": isEveningLightTime ? "да" : "нет",
        "окно_вечернего_освещения": sun.sunsetText + "-" + EVENING_LIGHT_END_TIME
    };
}

// -------------------- РАСЧЁТ ВОСХОДА И ЗАКАТА --------------------

function calculateSunTimes(date) {
    var latitude = Number(LATITUDE);
    var longitude = Number(LONGITUDE);
    var localParts;
    var dayOfYear;
    var utcOffsetHours;
    var zenith;
    var latRad;
    var declination;
    var b;
    var equationOfTime;
    var cosHourAngle;
    var hourAngleDeg;
    var sunriseUtcHours;
    var sunsetUtcHours;
    var sunriseLocalMinutes;
    var sunsetLocalMinutes;

    if (!isFinite(latitude) || !isFinite(longitude)) {
        return {
            ok: false,
            error: "Некорректные координаты"
        };
    }

    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        return {
            ok: false,
            error: "Координаты вне допустимого диапазона"
        };
    }

    localParts = getLocalNowParts(date);
    dayOfYear = localParts.dayOfYear;
    utcOffsetHours = getUsedUtcOffsetHours(date);

    zenith = 90.833;
    latRad = degToRad(latitude);

    declination = degToRad(23.45) * Math.sin(2 * Math.PI * (284 + dayOfYear) / 365);

    b = 2 * Math.PI * (dayOfYear - 81) / 365;
    equationOfTime = 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);

    cosHourAngle =
        (Math.cos(degToRad(zenith)) - Math.sin(latRad) * Math.sin(declination)) /
        (Math.cos(latRad) * Math.cos(declination));

    if (cosHourAngle > 1) {
        return {
            ok: false,
            error: "Восход не рассчитан"
        };
    }

    if (cosHourAngle < -1) {
        return {
            ok: false,
            error: "Закат не рассчитан"
        };
    }

    hourAngleDeg = radToDeg(Math.acos(cosHourAngle));

    sunriseUtcHours = 12 - hourAngleDeg / 15 - equationOfTime / 60 - longitude / 15;
    sunsetUtcHours = 12 + hourAngleDeg / 15 - equationOfTime / 60 - longitude / 15;

    sunriseLocalMinutes = normalizeMinutes((sunriseUtcHours + utcOffsetHours) * 60);
    sunsetLocalMinutes = normalizeMinutes((sunsetUtcHours + utcOffsetHours) * 60);

    return {
        ok: true,
        sunriseMinutes: sunriseLocalMinutes,
        sunsetMinutes: sunsetLocalMinutes,
        sunriseText: formatMinutes(sunriseLocalMinutes),
        sunsetText: formatMinutes(sunsetLocalMinutes),
        utcOffsetHours: utcOffsetHours
    };
}

// -------------------- ОСНОВНАЯ ЛОГИКА --------------------

function publishCalculationError(errorText) {
    setControl("calculation_ok", false);
    setControl("state_text", "Ошибка расчёта");
    setControl("sunrise_time", errorText);
    setControl("sunset_time", errorText);
    setControl("is_day", false);
    setControl("is_night", false);
    setControl("is_evening_light_time", false);
    setControl("evening_light_window", "нет расчёта");

    if (STATE.lastCalculationError !== errorText) {
        writeLog("ОШИБКА", "Ошибка расчёта дня и ночи", {
            "причина": errorText
        });

        STATE.lastCalculationError = errorText;
    }
}

function publishConfigError(errorText) {
    setControl("calculation_ok", false);
    setControl("state_text", "Ошибка настройки");
    setControl("is_day", false);
    setControl("is_night", false);
    setControl("is_evening_light_time", false);
    setControl("evening_light_window", "ошибка времени");

    if (STATE.lastCalculationError !== errorText) {
        writeLog("АВАРИЯ", "Ошибка настройки дня и ночи", {
            "причина": errorText,
            "EVENING_LIGHT_END_TIME": EVENING_LIGHT_END_TIME
        });

        STATE.lastCalculationError = errorText;
    }
}

function logStateTransition(now, sun, isNight, isEveningLightTime) {
    var params;

    if (!STATE.initialized) {
        return;
    }

    if (STATE.lastNight === null || STATE.lastNight === isNight) {
        return;
    }

    params = commonLogParams(now, sun, isEveningLightTime);

    if (isNight) {
        params["причина"] = "текущее время после заката";
        writeLog("СОСТОЯНИЕ", "Ночь включена", params);
        return;
    }

    params["причина"] = "случился восход";
    writeLog("СОСТОЯНИЕ", "День включен", params);
}

function updateDayNight() {
    var now = new Date();
    var nowMinutes = getCurrentLocalMinutes(now);
    var sun = calculateSunTimes(now);
    var eveningEndMinutes;
    var isDay;
    var isNight;
    var isEveningLightTime;
    var stateText;
    var eveningWindowText;

    setControl("current_time", formatCurrentDateTime(now));
    setControl("last_update", formatCurrentDateTime(now));

    if (!sun.ok) {
        publishCalculationError(sun.error);
        return;
    }

    eveningEndMinutes = parseTimeToMinutes(EVENING_LIGHT_END_TIME);

    if (eveningEndMinutes === null) {
        publishConfigError("Некорректное значение времени окончания вечернего освещения");
        return;
    }

    STATE.lastCalculationError = "";

    isDay = isTimeInWindow(nowMinutes, sun.sunriseMinutes, sun.sunsetMinutes);
    isNight = !isDay;
    isEveningLightTime = isTimeInWindow(nowMinutes, sun.sunsetMinutes, eveningEndMinutes);
    stateText = isNight ? "Ночь" : "День";
    eveningWindowText = sun.sunsetText + " - " + EVENING_LIGHT_END_TIME;

    setControl("calculation_ok", true);
    setControl("sunrise_time", sun.sunriseText);
    setControl("sunset_time", sun.sunsetText);
    setControl("state_text", stateText);
    setControl("is_day", isDay);
    setControl("is_night", isNight);
    setControl("is_evening_light_time", isEveningLightTime);
    setControl("evening_light_window", eveningWindowText);

    logStateTransition(now, sun, isNight, isEveningLightTime);

    STATE.lastNight = isNight;
    STATE.lastEveningLightTime = isEveningLightTime;
}

// -------------------- ЗАПУСК --------------------

writeLog("СКРИПТ", "Скрипт загружен", {
    "устройство": DEVICE_ID
});

updateDayNight();

STATE.initialized = true;

writeLog("СКРИПТ", "Стартовая инициализация завершена", {
    "устройство": DEVICE_ID,
    "состояние": dev[DEVICE_ID + "/state_text"],
    "восход": dev[DEVICE_ID + "/sunrise_time"],
    "закат": dev[DEVICE_ID + "/sunset_time"],
    "вечернее_освещение": dev[DEVICE_ID + "/is_evening_light_time"] ? "да" : "нет"
});

defineRule("day_night_update_every_minute", {
    when: cron("*/1 * * * *"),
    then: function () {
        updateDayNight();
    }
});
