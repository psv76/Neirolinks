var System = require("system");
var safeLog = System.safeLog;

// Каналы объекта 507 (Иволга)
// Читается: pressureBar, pressureCurrent, secBlock
// Пишется: valveMakeup
var CH = {
    valveMakeup:     "A04/K1",
    pressureBar:     "905.3/input_1_value",
    pressureCurrent: "905.3/input_1_current",
    secBlock:        "power_monitor/secondary_alerts_blocked"
};

// Настройки — менять здесь, не в интерфейсе
var CFG = {
    currentBreakMa:   3.6,   // мА — минимальный ток датчика (ниже = обрыв)
    pressureMinBar:   1.2,   // бар — старт подпитки ниже этого порога
    pressureTargetBar: 1.5,  // бар — стоп подпитки при достижении
    pressureAlarmBar: 1.0,   // бар — аварийный порог (отображается в интерфейсе)
    pulseOpenS:       3,     // с  — время открытия клапана за один импульс
    pulsePauseS:      20,    // с  — пауза между импульсами
    maxPulses:        5,     // шт — максимум импульсов за один цикл
    watchdogS:        15,    // с  — таймаут watchdog (клапан завис)
    filterSize:       3      // шт — размер буфера фильтра давления
};

var STATE = {
    pressureBuffer:    [],
    active:            false,
    valveOpening:      false,
    waitingPause:      false,
    pulseCount:        0,
    sensorAlarm:       false,
    lowPressureAlarm:  false,
    makeupFailedAlarm: false,
    watchdogAlarm:     false,
    lastEvent:         "",
    valveCloseTimer:   null,
    pauseTimer:        null,
    watchdogTimer:     null
};

// --- Утилиты ---

function readBool(value)
{
    return value === true || value === 1 || value === "1" || value === "true";
}

function readNumber(path, fallback)
{
    var value = Number(dev[path]);
    if (isNaN(value))
        return fallback;
    return value;
}

function round2(value)
{
    if (value === null)
        return null;
    return Math.round(value * 100) / 100;
}

function setCell(name, value)
{
    if (dev["pressure_makeup/" + name] !== value)
        dev["pressure_makeup/" + name] = value;
}

function setEvent(text)
{
    STATE.lastEvent = text;
    setCell("last_event", text);
    safeLog("[507_Pressure_makeup] " + text);
}

function clearTimer(timerName)
{
    if (STATE[timerName])
    {
        clearTimeout(STATE[timerName]);
        STATE[timerName] = null;
    }
}

function clamp(value, minValue, maxValue)
{
    if (value < minValue) return minValue;
    if (value > maxValue) return maxValue;
    return value;
}

// --- Фильтрация ---

function filterPressure(rawValue)
{
    var i;
    var sum = 0;

    if (rawValue === null)
        return null;

    STATE.pressureBuffer.push(rawValue);
    while (STATE.pressureBuffer.length > CFG.filterSize)
        STATE.pressureBuffer.shift();

    for (i = 0; i < STATE.pressureBuffer.length; i++)
        sum += STATE.pressureBuffer[i];

    return clamp(sum / STATE.pressureBuffer.length, 0, 6);
}

// --- Настройки (читаются из CFG, не из интерфейса) ---

function getSettings()
{
    return {
        pressureMinBar:    CFG.pressureMinBar,
        pressureTargetBar: CFG.pressureTargetBar,
        pressureAlarmBar:  CFG.pressureAlarmBar,
        currentBreakMa:    CFG.currentBreakMa,
        pulseOpenS:        CFG.pulseOpenS,
        pulsePauseS:       CFG.pulsePauseS,
        maxPulses:         CFG.maxPulses,
        watchdogS:         CFG.watchdogS,
        enabled:           readBool(dev["pressure_makeup/enabled"]),
        autoMode:          readBool(dev["pressure_makeup/auto_mode"]),
        smsAllowed:        !readBool(dev[CH.secBlock])
    };
}

// --- Алерты ---

function sendAlertIfAllowed(settings, eventText, detailsText, recommendationText)
{
    if (!settings.smsAllowed)
        return;
    System.sendAlert("Котельная", eventText, detailsText, recommendationText);
}

// --- Управление клапаном ---

function closeValve(reason)
{
    if (readBool(dev[CH.valveMakeup]))
        dev[CH.valveMakeup] = false;

    clearTimer("valveCloseTimer");
    clearTimer("watchdogTimer");
    STATE.valveOpening = false;

    if (reason)
        setEvent(reason);
}

function stopCycle(reason)
{
    closeValve(reason);
    clearTimer("pauseTimer");
    STATE.active = false;
    STATE.waitingPause = false;
}

function resetAllAlarmsAndCycle()
{
    stopCycle("Сброс аварийного состояния");
    STATE.sensorAlarm       = false;
    STATE.lowPressureAlarm  = false;
    STATE.makeupFailedAlarm = false;
    STATE.watchdogAlarm     = false;
    STATE.pulseCount        = 0;
}

function openPulse(settings, manualMode)
{
    if (STATE.sensorAlarm || STATE.valveOpening || STATE.waitingPause || readBool(dev[CH.valveMakeup]))
        return;

    STATE.active       = true;
    STATE.valveOpening = true;
    STATE.pulseCount   = STATE.pulseCount + 1;

    dev[CH.valveMakeup] = true;
    setEvent(manualMode ? "Открытие клапана: ручной импульс" : "Открытие клапана");

    STATE.valveCloseTimer = setTimeout(function () {
        closeValve("Закрытие клапана");
        STATE.waitingPause = true;
        setEvent("Пауза между импульсами");

        STATE.pauseTimer = setTimeout(function () {
            STATE.waitingPause = false;
            setEvent("Пауза завершена");
            evaluate();
        }, settings.pulsePauseS * 1000);
    }, settings.pulseOpenS * 1000);

    STATE.watchdogTimer = setTimeout(function () {
        if (readBool(dev[CH.valveMakeup]))
        {
            STATE.watchdogAlarm = true;
            stopCycle("Watchdog: аварийное закрытие клапана");
            sendAlertIfAllowed(
                settings,
                "Аварийное закрытие подпитки",
                "Клапан открыт дольше допустимого времени.",
                "Проверьте реле и логику подпитки."
            );
        }
    }, settings.watchdogS * 1000);
}

// --- Обновление интерфейса ---

function updateVirtualState(pressureBar, currentMa)
{
    // Показания
    setCell("pressure_bar",      round2(pressureBar));
    setCell("sensor_current_ma", round2(currentMa));
    setCell("valve_open",        readBool(dev[CH.valveMakeup]));
    setCell("pulse_count",       STATE.pulseCount);
    setCell("active",            STATE.active);
    setCell("last_event",        STATE.lastEvent);

    // Аварии
    setCell("sensor_alarm",        STATE.sensorAlarm);
    setCell("low_pressure_alarm",  STATE.lowPressureAlarm);
    setCell("makeup_failed_alarm", STATE.makeupFailedAlarm);
    setCell("watchdog_alarm",      STATE.watchdogAlarm);
}

// --- Основная логика ---

function evaluate()
{
    var settings    = getSettings();
    var currentMa   = readNumber(CH.pressureCurrent, null);
    var pressureRaw = readNumber(CH.pressureBar, null);
    var pressureBar = filterPressure(pressureRaw);

    // Проверка датчика
    if (currentMa === null || currentMa < settings.currentBreakMa)
    {
        STATE.sensorAlarm = true;
        stopCycle("Авария датчика: ток ниже порога или обрыв");
    }

    // Аварийный порог давления
    if (pressureBar !== null && pressureBar < settings.pressureAlarmBar)
        STATE.lowPressureAlarm = true;

    if (pressureBar !== null && pressureBar >= settings.pressureMinBar)
        STATE.lowPressureAlarm = false;

    // Основная логика
    if (!settings.enabled || !settings.autoMode)
    {
        stopCycle("Подпитка отключена");
    }
    else if (!STATE.sensorAlarm)
    {
        if (pressureBar !== null && pressureBar >= settings.pressureTargetBar)
        {
            if (STATE.active)
                stopCycle("Цикл завершён: давление достигнуто");

            STATE.active            = false;
            STATE.pulseCount        = 0;
            STATE.makeupFailedAlarm = false;
        }
        else if (!STATE.valveOpening && !STATE.waitingPause)
        {
            if (!STATE.active && pressureBar !== null && pressureBar < settings.pressureMinBar)
            {
                STATE.active     = true;
                STATE.pulseCount = 0;
                setEvent("Старт цикла подпитки");
            }

            if (STATE.active)
            {
                if (STATE.pulseCount >= settings.maxPulses)
                {
                    STATE.makeupFailedAlarm = true;
                    stopCycle("Цикл завершён: превышено количество импульсов");
                    sendAlertIfAllowed(
                        settings,
                        "Подпитка не дала результата",
                        "Превышено допустимое количество импульсов.",
                        "Проверьте наличие воды и клапан подпитки."
                    );
                }
                else if (pressureBar !== null && pressureBar < settings.pressureTargetBar)
                {
                    openPulse(settings, false);
                }
            }
        }
    }

    updateVirtualState(pressureBar, currentMa);
}

// --- Виртуальное устройство ---

defineVirtualDevice("pressure_makeup", {
    title: "Подпитка давления (507)",
    cells: {
        // Группа 1: Показания
        pressure_bar: {
            title:    "Давление СО, бар  [цель ≥" + CFG.pressureTargetBar + "]",
            type:     "value",
            readonly: true,
            value:    0,
            order:    1
        },
        sensor_current_ma: {
            title:    "Ток датчика, мА  [норма ≥" + CFG.currentBreakMa + "]",
            type:     "value",
            readonly: true,
            value:    0,
            order:    2
        },
        valve_open: {
            title:    "Клапан открыт",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    3
        },
        pulse_count: {
            title:    "Импульсов в цикле",
            type:     "value",
            readonly: true,
            value:    0,
            order:    4
        },
        active: {
            title:    "Цикл активен",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    5
        },
        last_event: {
            title:    "Последнее событие",
            type:     "text",
            readonly: true,
            value:    "",
            order:    6
        },

        // Группа 2: Аварии
        sensor_alarm: {
            title:    "Авария датчика давления",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    10
        },
        low_pressure_alarm: {
            title:    "Давление ниже аварийного  [<" + CFG.pressureAlarmBar + " бар]",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    11
        },
        makeup_failed_alarm: {
            title:    "Подпитка не дала результата",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    12
        },
        watchdog_alarm: {
            title:    "Watchdog: клапан завис",
            type:     "switch",
            readonly: true,
            value:    false,
            order:    13
        },

        // Группа 3: Управление
        enabled: {
            title: "Подпитка включена",
            type:  "switch",
            value: true,
            order: 20
        },
        auto_mode: {
            title: "Авторежим",
            type:  "switch",
            value: true,
            order: 21
        },
        manual_pulse: {
            title: "Ручной импульс",
            type:  "pushbutton",
            order: 22
        },
        manual_close: {
            title: "Закрыть клапан",
            type:  "pushbutton",
            order: 23
        },
        reset_alarm: {
            title: "Сбросить аварии",
            type:  "pushbutton",
            order: 24
        }
    }
});

// --- Правила ---

defineRule("pressure_makeup_eval_507", {
    whenChanged: [
        CH.pressureBar,
        CH.pressureCurrent,
        "pressure_makeup/enabled",
        "pressure_makeup/auto_mode",
        CH.secBlock
    ],
    then: function () {
        evaluate();
    }
});

defineRule("pressure_makeup_manual_close_507", {
    whenChanged: "pressure_makeup/manual_close",
    then: function (newValue) {
        if (!newValue)
            return;

        stopCycle("Ручное закрытие клапана");
        updateVirtualState(
            filterPressure(readNumber(CH.pressureBar, null)),
            readNumber(CH.pressureCurrent, null)
        );
    }
});

defineRule("pressure_makeup_reset_alarm_507", {
    whenChanged: "pressure_makeup/reset_alarm",
    then: function (newValue) {
        if (!newValue)
            return;

        resetAllAlarmsAndCycle();
        evaluate();
    }
});

defineRule("pressure_makeup_manual_pulse_507", {
    whenChanged: "pressure_makeup/manual_pulse",
    then: function (newValue) {
        var settings;

        if (!newValue)
            return;

        if (STATE.sensorAlarm || readBool(dev[CH.valveMakeup]))
        {
            setEvent("Ручной импульс отклонён: авария или клапан уже открыт");
            evaluate();
            return;
        }

        settings = getSettings();
        openPulse(settings, true);
        evaluate();
    }
});

// --- Старт ---

setTimeout(function () {
    safeLog("[507_Pressure_makeup] Запуск скрипта");
    dev[CH.valveMakeup] = false;
    setEvent("Инициализация: клапан закрыт");
    evaluate();
}, 3000);
