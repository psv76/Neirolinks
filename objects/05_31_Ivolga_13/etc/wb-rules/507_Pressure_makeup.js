var System = require("system");
var safeLog = System.safeLog;

var CH = {
    valveMakeup: "A04/K1",
    pressureBar: "905.3/input_1_value",
    pressureCurrent: "905.3/input_1_current",
    secBlock: "power_monitor/secondary_alerts_blocked"
};

var CFG = {
    currentBreakMa: 3.6,
    pressureMinBar: 1.2,
    pressureTargetBar: 1.5,
    pressureAlarmBar: 0.8,
    pulseOpenS: 3,
    pulsePauseS: 20,
    maxPulses: 5,
    watchdogS: 15,
    filterSize: 3
};

var STATE = {
    pressureBuffer: [],
    active: false,
    valveOpening: false,
    waitingPause: false,
    pulseCount: 0,
    sensorAlarm: false,
    lowPressureAlarm: false,
    makeupFailedAlarm: false,
    watchdogAlarm: false,
    lastEvent: "",
    valveCloseTimer: null,
    pauseTimer: null,
    watchdogTimer: null
};

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
    if (value < minValue)
        return minValue;
    if (value > maxValue)
        return maxValue;
    return value;
}

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

function getSettings()
{
    return {
        enabled: readBool(dev["pressure_makeup/enabled"]),
        autoMode: readBool(dev["pressure_makeup/auto_mode"]),
        pressureMinBar: readNumber("pressure_makeup/pressure_min_bar", CFG.pressureMinBar),
        pressureTargetBar: readNumber("pressure_makeup/pressure_target_bar", CFG.pressureTargetBar),
        pressureAlarmBar: readNumber("pressure_makeup/pressure_alarm_bar", CFG.pressureAlarmBar),
        currentBreakMa: readNumber("pressure_makeup/current_break_ma", CFG.currentBreakMa),
        pulseOpenS: readNumber("pressure_makeup/pulse_open_s", CFG.pulseOpenS),
        pulsePauseS: readNumber("pressure_makeup/pulse_pause_s", CFG.pulsePauseS),
        maxPulses: readNumber("pressure_makeup/max_pulses", CFG.maxPulses),
        watchdogS: readNumber("pressure_makeup/watchdog_s", CFG.watchdogS),
        smsAllowed: !readBool(dev[CH.secBlock])
    };
}

function sendAlertIfAllowed(settings, eventText, detailsText, recommendationText)
{
    if (!settings.smsAllowed)
        return;
    System.sendAlert("Котельная", eventText, detailsText, recommendationText);
}

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
    STATE.sensorAlarm = false;
    STATE.lowPressureAlarm = false;
    STATE.makeupFailedAlarm = false;
    STATE.watchdogAlarm = false;
    STATE.pulseCount = 0;
}

function openPulse(settings, manualMode)
{
    if (STATE.sensorAlarm || STATE.valveOpening || STATE.waitingPause || readBool(dev[CH.valveMakeup]))
        return;

    STATE.active = true;
    STATE.valveOpening = true;
    STATE.pulseCount = STATE.pulseCount + 1;

    dev[CH.valveMakeup] = true;
    setEvent(manualMode ? "Открытие клапана: ручной импульс" : "Открытие клапана");

    STATE.valveCloseTimer = setTimeout(function () {
        closeValve("Закрытие клапана");
        STATE.waitingPause = true;
        setEvent("Начало паузы");

        STATE.pauseTimer = setTimeout(function () {
            STATE.waitingPause = false;
            setEvent("Окончание паузы");
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

function updateVirtualState(stateData)
{
    setCell("pressure_bar", stateData.pressureBar);
    setCell("pressure_current_ma", stateData.currentMa);
    setCell("valve_open", readBool(dev[CH.valveMakeup]));
    setCell("active", STATE.active);
    setCell("valve_opening", STATE.valveOpening);
    setCell("waiting_pause", STATE.waitingPause);
    setCell("pulse_count", STATE.pulseCount);
    setCell("sensor_alarm", STATE.sensorAlarm);
    setCell("low_pressure_alarm", STATE.lowPressureAlarm);
    setCell("makeup_failed_alarm", STATE.makeupFailedAlarm);
    setCell("watchdog_alarm", STATE.watchdogAlarm);
    setCell("status_line1", "Давление: " + stateData.pressureBar + " бар; ток: " + stateData.currentMa + " mA");
    setCell("status_line2", "Цикл: " + (STATE.active ? "активен" : "остановлен") + ", импульсы " + STATE.pulseCount + ".");
    setCell("status_line3", "Клапан: " + (readBool(dev[CH.valveMakeup]) ? "открыт" : "закрыт") + ".");
    setCell("status_text", STATE.lastEvent);
}

function evaluate()
{
    var settings = getSettings();
    var currentMa = readNumber(CH.pressureCurrent, null);
    var pressureRaw = readNumber(CH.pressureBar, null);
    var pressureBar = filterPressure(pressureRaw);

    if (currentMa !== null && currentMa < settings.currentBreakMa)
    {
        STATE.sensorAlarm = true;
        stopCycle("Ошибка датчика: ток ниже порога");
    }

    if (pressureBar !== null && pressureBar < settings.pressureAlarmBar)
        STATE.lowPressureAlarm = true;

    if (pressureBar !== null && pressureBar >= settings.pressureMinBar)
        STATE.lowPressureAlarm = false;

    if (!settings.enabled || !settings.autoMode)
    {
        stopCycle("Подпитка отключена");
    }
    else if (!STATE.sensorAlarm)
    {
        if (STATE.valveOpening || STATE.waitingPause)
        {
            if (pressureBar !== null && pressureBar >= settings.pressureTargetBar)
            {
                stopCycle("Успешное завершение: достигнуто целевое давление");
                STATE.pulseCount = 0;
                STATE.makeupFailedAlarm = false;
            }
        }
        else if (pressureBar !== null && pressureBar >= settings.pressureTargetBar)
        {
            if (STATE.active)
                stopCycle("Успешное завершение");

            STATE.active = false;
            STATE.pulseCount = 0;
            STATE.makeupFailedAlarm = false;
        }
        else if (pressureBar !== null && pressureBar < settings.pressureMinBar)
        {
            if (!STATE.active)
            {
                STATE.pulseCount = 0;
                setEvent("Старт цикла подпитки");
            }

            if (STATE.pulseCount >= settings.maxPulses)
            {
                STATE.makeupFailedAlarm = true;
                stopCycle("Неуспешное завершение: превышено количество импульсов");
                sendAlertIfAllowed(
                    settings,
                    "Подпитка не дала результата",
                    "Превышено допустимое количество импульсов.",
                    "Проверьте наличие воды и клапан подпитки."
                );
            }
            else
            {
                openPulse(settings, false);
            }
        }
    }

    updateVirtualState({
        pressureBar: pressureBar,
        currentMa: currentMa
    });
}

defineVirtualDevice("pressure_makeup", {
    title: "Подпитка давления",
    cells: {
        enabled: { type: "switch", value: true },
        auto_mode: { type: "switch", value: true },
        pressure_min_bar: { type: "value", value: CFG.pressureMinBar },
        pressure_target_bar: { type: "value", value: CFG.pressureTargetBar },
        pressure_alarm_bar: { type: "value", value: CFG.pressureAlarmBar },
        current_break_ma: { type: "value", value: CFG.currentBreakMa },
        pulse_open_s: { type: "value", value: CFG.pulseOpenS },
        pulse_pause_s: { type: "value", value: CFG.pulsePauseS },
        max_pulses: { type: "value", value: CFG.maxPulses },
        watchdog_s: { type: "value", value: CFG.watchdogS },
        manual_close: { type: "pushbutton" },
        reset_alarm: { type: "pushbutton" },
        manual_pulse: { type: "pushbutton" },
        pressure_bar: { type: "value", readonly: true, value: 0 },
        pressure_current_ma: { type: "value", readonly: true, value: 0 },
        valve_open: { type: "switch", readonly: true, value: false },
        active: { type: "switch", readonly: true, value: false },
        valve_opening: { type: "switch", readonly: true, value: false },
        waiting_pause: { type: "switch", readonly: true, value: false },
        pulse_count: { type: "value", readonly: true, value: 0 },
        sensor_alarm: { type: "switch", readonly: true, value: false },
        low_pressure_alarm: { type: "switch", readonly: true, value: false },
        makeup_failed_alarm: { type: "switch", readonly: true, value: false },
        watchdog_alarm: { type: "switch", readonly: true, value: false },
        last_event: { type: "text", readonly: true, value: "" },
        status_line1: { type: "text", readonly: true, value: "" },
        status_line2: { type: "text", readonly: true, value: "" },
        status_line3: { type: "text", readonly: true, value: "" },
        status_text: { type: "text", readonly: true, value: "" }
    }
});

defineRule("pressure_makeup_eval_507", {
    whenChanged: [
        CH.pressureBar,
        CH.pressureCurrent,
        "pressure_makeup/enabled",
        "pressure_makeup/auto_mode",
        "pressure_makeup/pressure_min_bar",
        "pressure_makeup/pressure_target_bar",
        "pressure_makeup/current_break_ma",
        "pressure_makeup/pulse_open_s",
        "pressure_makeup/pulse_pause_s",
        "pressure_makeup/max_pulses",
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

        stopCycle("Ручное закрытие");
        updateVirtualState({
            pressureBar: filterPressure(readNumber(CH.pressureBar, null)),
            currentMa: readNumber(CH.pressureCurrent, null)
        });
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
            setEvent("Ручной импульс отклонен");
            evaluate();
            return;
        }

        settings = getSettings();
        openPulse(settings, true);
        evaluate();
    }
});

setTimeout(function () {
    safeLog("[507_Pressure_makeup] Запуск скрипта");
    dev[CH.valveMakeup] = false;
    setEvent("Принудительное закрытие клапана на старте");
    evaluate();
}, 3000);
