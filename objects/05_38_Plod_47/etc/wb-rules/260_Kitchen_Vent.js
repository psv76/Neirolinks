// 260_Kitchen_Vent.js
// Управление вытяжкой кухни.
// Система: вентиляция.
// Логика:
// - 4 дискретных входа выбирают скорость;
// - если все входы выключены, работает общеобменный режим 16%;
// - если активны несколько входов, приоритет у максимальной скорости.
// Физические каналы, которые пишет скрипт:
// - A16/Channel 1 Switch
// - A16/Channel 1 Dimming Level

var KITCHEN_HOOD_CFG = {
    enabled: true,                  // главный флаг логики
    applyOnStart: true,             // применять состояние после загрузки правил
    startDelayMs: 1000,             // задержка после старта wb-rules
    forceSwitchOn: true,            // всегда держать канал включённым
    enableLog: true,                // логировать действия в журнал

    inputs: {
        speed1: "wb-mcm8_50/Input 1",   // Скорость 1
        speed2: "wb-mcm8_50/Input 2",   // Скорость 2
        speed3: "wb-mcm8_50/Input 3",   // Скорость 3
        speed4: "wb-mcm8_50/Input 4"    // Скорость 4
    },

    output: {
        switchControl: "A16/Channel 1 Switch",
        levelControl: "A16/Channel 1 Dimming Level"
    },

    levels: {
        background: 16, // общеобменная вентиляция
        speed1: 25,
        speed2: 50,
        speed3: 75,
        speed4: 100
    }
};

var KITCHEN_HOOD_LOG_SYSTEM = "вентиляция";
var KITCHEN_HOOD_LOG_SCRIPT = "260_Kitchen_Vent";
var KITCHEN_HOOD_LOG_CONTEXT = "кухня";

var KITCHEN_HOOD_STATE = {
    lastDisabledLog: false,
    lastSwitchCommand: null,
    lastLevelCommand: null
};

function kitchenHoodFormatParams(params) {
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

function kitchenHoodWriteJournal(level, message) {
    if (level === "error" && log.error) {
        log.error(message);
        return;
    }

    if (level === "warning" && log.warning) {
        log.warning(message);
        return;
    }

    if (log.info) {
        log.info(message);
        return;
    }

    log(message);
}

function kitchenHoodWriteLog(eventName, eventText, params) {
    var message;

    if (!KITCHEN_HOOD_CFG.enableLog) {
        return;
    }

    message = "[" + KITCHEN_HOOD_LOG_SYSTEM + "][" + KITCHEN_HOOD_LOG_SCRIPT + "][" + KITCHEN_HOOD_LOG_CONTEXT + "]; " +
        eventName + "=" + eventText + kitchenHoodFormatParams(params);

    if (eventName === "АВАРИЯ" || eventName === "WATCHDOG") {
        kitchenHoodWriteJournal("error", message);
        return;
    }

    if (eventName === "ОШИБКА") {
        kitchenHoodWriteJournal("warning", message);
        return;
    }

    kitchenHoodWriteJournal("info", message);
}

function kitchenHoodLog(message) {
    kitchenHoodWriteLog("СОСТОЯНИЕ", message, null);
}

function getBool(cell) {
    return !!dev[cell];
}

function isKitchenHoodControlAvailable(cell) {
    return cell && dev[cell] !== null && dev[cell] !== undefined;
}

function getKitchenHoodLevel(cell, fallback) {
    var raw;
    var value;

    if (!cell) {
        return fallback;
    }

    raw = dev[cell];

    if (raw === null || raw === undefined || raw === "") {
        return fallback;
    }

    value = Number(raw);

    if (!isFinite(value)) {
        return fallback;
    }

    return value;
}

function getTargetLevel() {
    var in1 = getBool(KITCHEN_HOOD_CFG.inputs.speed1);
    var in2 = getBool(KITCHEN_HOOD_CFG.inputs.speed2);
    var in3 = getBool(KITCHEN_HOOD_CFG.inputs.speed3);
    var in4 = getBool(KITCHEN_HOOD_CFG.inputs.speed4);

    // Приоритет максимальной скорости
    if (in4) {
        return KITCHEN_HOOD_CFG.levels.speed4;
    }

    if (in3) {
        return KITCHEN_HOOD_CFG.levels.speed3;
    }

    if (in2) {
        return KITCHEN_HOOD_CFG.levels.speed2;
    }

    if (in1) {
        return KITCHEN_HOOD_CFG.levels.speed1;
    }

    return KITCHEN_HOOD_CFG.levels.background;
}

function getActiveInputsText() {
    var active = [];

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed1)) {
        active.push("S1");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed2)) {
        active.push("S2");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed3)) {
        active.push("S3");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed4)) {
        active.push("S4");
    }

    if (active.length === 0) {
        return "нет";
    }

    return active.join(",");
}

function kitchenHoodBaseParams(reason, activeInputsText, targetLevel) {
    return {
        "причина": reason,
        "входы": activeInputsText,
        "цель": targetLevel + "%"
    };
}

function writeKitchenHoodSwitch(value, reason, activeInputsText, targetLevel) {
    var topic = KITCHEN_HOOD_CFG.output.switchControl;
    var params = kitchenHoodBaseParams(reason, activeInputsText, targetLevel);

    params["канал"] = topic;
    params["значение в канал"] = value ? "ON" : "OFF";

    if (!isKitchenHoodControlAvailable(topic)) {
        kitchenHoodWriteLog("ОШИБКА", "Канал включения вытяжки недоступен", params);
        return false;
    }

    if (!!dev[topic] !== !!value) {
        dev[topic] = !!value;
        KITCHEN_HOOD_STATE.lastSwitchCommand = value;
        kitchenHoodWriteLog("КОМАНДА", value ? "Включить канал вытяжки" : "Выключить канал вытяжки", params);
    }

    return true;
}

function writeKitchenHoodLevel(value, reason, activeInputsText) {
    var topic = KITCHEN_HOOD_CFG.output.levelControl;
    var currentLevel = getKitchenHoodLevel(topic, null);
    var params = kitchenHoodBaseParams(reason, activeInputsText, value);

    params["канал"] = topic;
    params["значение в канал"] = value + "%";

    if (!isKitchenHoodControlAvailable(topic)) {
        kitchenHoodWriteLog("ОШИБКА", "Канал задания скорости вытяжки недоступен", params);
        return false;
    }

    if (currentLevel === null || currentLevel !== value) {
        dev[topic] = value;
        KITCHEN_HOOD_STATE.lastLevelCommand = value;
        kitchenHoodWriteLog("КОМАНДА", "Установить скорость вытяжки", params);
    }

    return true;
}

function applyKitchenHoodState(reason) {
    var targetLevel;
    var activeInputsText;

    if (!KITCHEN_HOOD_CFG.enabled) {
        if (!KITCHEN_HOOD_STATE.lastDisabledLog) {
            KITCHEN_HOOD_STATE.lastDisabledLog = true;
            kitchenHoodWriteLog("СОСТОЯНИЕ", "Сценарий отключён", {
                "причина": "enabled=false"
            });
        }
        return;
    }

    KITCHEN_HOOD_STATE.lastDisabledLog = false;

    targetLevel = getTargetLevel();
    activeInputsText = getActiveInputsText();

    if (KITCHEN_HOOD_CFG.forceSwitchOn) {
        writeKitchenHoodSwitch(true, reason, activeInputsText, targetLevel);
    }

    writeKitchenHoodLevel(targetLevel, reason, activeInputsText);
}

defineRule("kitchen_hood_apply_on_inputs_change", {
    whenChanged: [
        KITCHEN_HOOD_CFG.inputs.speed1,
        KITCHEN_HOOD_CFG.inputs.speed2,
        KITCHEN_HOOD_CFG.inputs.speed3,
        KITCHEN_HOOD_CFG.inputs.speed4
    ],
    then: function () {
        applyKitchenHoodState("изменение входов");
    }
});

kitchenHoodWriteLog("СКРИПТ", "Скрипт загружен", {
    "входы": KITCHEN_HOOD_CFG.inputs.speed1 + ", " + KITCHEN_HOOD_CFG.inputs.speed2 + ", " + KITCHEN_HOOD_CFG.inputs.speed3 + ", " + KITCHEN_HOOD_CFG.inputs.speed4,
    "канал_включения": KITCHEN_HOOD_CFG.output.switchControl,
    "канал_скорости": KITCHEN_HOOD_CFG.output.levelControl
});

if (KITCHEN_HOOD_CFG.applyOnStart) {
    setTimeout(function () {
        applyKitchenHoodState("старт скрипта");
    }, KITCHEN_HOOD_CFG.startDelayMs);
}
