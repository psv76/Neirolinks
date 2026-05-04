// 550_Pressure_makeup.js
// 05 38 Плодоовощ 47.
// Автоматическая импульсная подпитка давления отопления.
// Защита: клапан не открывается, если давление ХВС недостаточно выше давления отопления.
// Защита: клапан не открывается при ошибке тока датчиков давления 4-20 мА.

var System = null;

try {
    System = require("system");
} catch (e) {
    System = null;
}

var CH = {
    valveMakeup: "wb-mr6cu_219/K5",                       // 550 Клапан подпитки отопления
    heatPressureBar: "wb-mai2-mini_210/input_1_value",     // Давление в системе отопления, бар
    heatPressureCurrent: "wb-mai2-mini_210/input_1_current", // Ток датчика давления отопления, мА
    coldPressureBar: "wb-mai2-mini_210/input_2_value",     // Давление в системе ХВС, бар
    coldPressureCurrent: "wb-mai2-mini_210/input_2_current", // Ток датчика давления ХВС, мА
    secBlock: null                                         // Если есть power_monitor, можно указать канал блокировки уведомлений
};

var CFG = {
    currentBreakMa: 3.6,       // Порог обрыва датчика 4-20 мА

    pressureMinBar: 1.2,
    pressureTargetBar: 1.5,
    pressureAlarmBar: 0.8,

    coldMinDeltaBar: 0.2,      // ХВС должна быть выше отопления минимум на эту величину
    coldMinAbsBar: 0.5,        // Минимально допустимое абсолютное давление ХВС

    pulseOpenS: 3,
    pulsePauseS: 20,
    maxPulses: 5,
    watchdogS: 15,

    filterSize: 3,
    pressureClampMinBar: 0,
    pressureClampMaxBar: 10,

    minRiseBar: 0              // 0 = контроль роста давления отключен
};

var STATE = {
    heatPressureBuffer: [],
    coldPressureBuffer: [],

    active: false,
    valveOpening: false,
    waitingPause: false,
    pulseCount: 0,

    heatPressureSensorAlarm: false,
    coldPressureSensorAlarm: false,
    heatCurrentAlarm: false,
    coldCurrentAlarm: false,
    coldPressureAlarm: false,
    lowPressureAlarm: false,
    makeupFailedAlarm: false,
    noRiseAlarm: false,
    watchdogAlarm: false,

    cycleStartPressureBar: null,
    lastEvent: "",

    valveCloseTimer: null,
    pauseTimer: null,
    watchdogTimer: null
};

function safeLog(text)
{
    if (System && typeof System.safeLog === "function")
    {
        System.safeLog(text);
        return;
    }

    log(text);
}

function readBool(value)
{
    return value === true || value === 1 || value === "1" || value === "true";
}

function readNumber(path, fallback)
{
    var value;

    if (!path)
        return fallback;

    value = Number(dev[path]);

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
    safeLog("[550_Pressure_makeup] " + text);
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

function filterValue(rawValue, buffer)
{
    var i;
    var sum = 0;

    if (rawValue === null)
        return null;

    buffer.push(rawValue);

    while (buffer.length > CFG.filterSize)
        buffer.shift();

    for (i = 0; i < buffer.length; i++)
        sum += buffer[i];

    return clamp(
        sum / buffer.length,
        CFG.pressureClampMinBar,
        CFG.pressureClampMaxBar
    );
}

function getSettings()
{
    return {
        enabled: readBool(dev["pressure_makeup/enabled"]),
        autoMode: readBool(dev["pressure_makeup/auto_mode"]),

        currentBreakMa: readNumber("pressure_makeup/current_break_ma", CFG.currentBreakMa),

        pressureMinBar: readNumber("pressure_makeup/pressure_min_bar", CFG.pressureMinBar),
        pressureTargetBar: readNumber("pressure_makeup/pressure_target_bar", CFG.pressureTargetBar),
        pressureAlarmBar: readNumber("pressure_makeup/pressure_alarm_bar", CFG.pressureAlarmBar),

        coldMinDeltaBar: readNumber("pressure_makeup/cold_min_delta_bar", CFG.coldMinDeltaBar),
        coldMinAbsBar: readNumber("pressure_makeup/cold_min_abs_bar", CFG.coldMinAbsBar),

        pulseOpenS: readNumber("pressure_makeup/pulse_open_s", CFG.pulseOpenS),
        pulsePauseS: readNumber("pressure_makeup/pulse_pause_s", CFG.pulsePauseS),
        maxPulses: readNumber("pressure_makeup/max_pulses", CFG.maxPulses),
        watchdogS: readNumber("pressure_makeup/watchdog_s", CFG.watchdogS),

        minRiseBar: readNumber("pressure_makeup/min_rise_bar", CFG.minRiseBar),

        smsAllowed: CH.secBlock ? !readBool(dev[CH.secBlock]) : true
    };
}

function readPressureState()
{
    var heatRaw = readNumber(CH.heatPressureBar, null);
    var coldRaw = readNumber(CH.coldPressureBar, null);
    var heatCurrentMa = readNumber(CH.heatPressureCurrent, null);
    var coldCurrentMa = readNumber(CH.coldPressureCurrent, null);
    var heatPressureBar = filterValue(heatRaw, STATE.heatPressureBuffer);
    var coldPressureBar = filterValue(coldRaw, STATE.coldPressureBuffer);
    var pressureDeltaBar = null;

    if (heatPressureBar !== null && coldPressureBar !== null)
        pressureDeltaBar = coldPressureBar - heatPressureBar;

    return {
        heatPressureRaw: heatRaw,
        coldPressureRaw: coldRaw,
        heatCurrentMa: heatCurrentMa,
        coldCurrentMa: coldCurrentMa,
        heatPressureBar: heatPressureBar,
        coldPressureBar: coldPressureBar,
        pressureDeltaBar: pressureDeltaBar
    };
}

function sendAlertIfAllowed(settings, eventText, detailsText, recommendationText)
{
    if (!settings.smsAllowed)
        return;

    if (System && typeof System.sendAlert === "function")
    {
        System.sendAlert("Котельная", eventText, detailsText, recommendationText);
        return;
    }

    safeLog("[550_Pressure_makeup] ALERT: " + eventText + " " + detailsText + " " + recommendationText);
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
    STATE.valveOpening = false;
    STATE.waitingPause = false;
    STATE.cycleStartPressureBar = null;
}

function resetAllAlarmsAndCycle()
{
    stopCycle("Сброс аварийного состояния");

    STATE.heatPressureSensorAlarm = false;
    STATE.coldPressureSensorAlarm = false;
    STATE.heatCurrentAlarm = false;
    STATE.coldCurrentAlarm = false;
    STATE.coldPressureAlarm = false;
    STATE.lowPressureAlarm = false;
    STATE.makeupFailedAlarm = false;
    STATE.noRiseAlarm = false;
    STATE.watchdogAlarm = false;

    STATE.pulseCount = 0;
    STATE.heatPressureBuffer = [];
    STATE.coldPressureBuffer = [];
}

function isColdPressureAllowed(settings, pressureState)
{
    if (pressureState.coldPressureBar === null)
        return false;

    if (pressureState.heatPressureBar === null)
        return false;

    if (pressureState.coldPressureBar < settings.coldMinAbsBar)
        return false;

    if (pressureState.coldPressureBar <= pressureState.heatPressureBar + settings.coldMinDeltaBar)
        return false;

    return true;
}

function updateSafetyAlarms(settings, pressureState)
{
    STATE.heatCurrentAlarm = pressureState.heatCurrentMa === null || pressureState.heatCurrentMa < settings.currentBreakMa;
    STATE.coldCurrentAlarm = pressureState.coldCurrentMa === null || pressureState.coldCurrentMa < settings.currentBreakMa;

    STATE.heatPressureSensorAlarm = pressureState.heatPressureBar === null;
    STATE.coldPressureSensorAlarm = pressureState.coldPressureBar === null;

    if (pressureState.heatPressureBar !== null && pressureState.heatPressureBar < settings.pressureAlarmBar)
        STATE.lowPressureAlarm = true;

    if (pressureState.heatPressureBar !== null && pressureState.heatPressureBar >= settings.pressureMinBar)
        STATE.lowPressureAlarm = false;

    STATE.coldPressureAlarm = !isColdPressureAllowed(settings, pressureState);
}

function updateVirtualState(pressureState)
{
    setCell("heat_pressure_bar", pressureState.heatPressureBar);
    setCell("heat_pressure_current_ma", pressureState.heatCurrentMa);
    setCell("cold_pressure_bar", pressureState.coldPressureBar);
    setCell("cold_pressure_current_ma", pressureState.coldCurrentMa);
    setCell("pressure_delta_bar", pressureState.pressureDeltaBar);

    setCell("valve_open", readBool(dev[CH.valveMakeup]));
    setCell("active", STATE.active);
    setCell("valve_opening", STATE.valveOpening);
    setCell("waiting_pause", STATE.waitingPause);
    setCell("pulse_count", STATE.pulseCount);

    setCell("heat_pressure_sensor_alarm", STATE.heatPressureSensorAlarm);
    setCell("cold_pressure_sensor_alarm", STATE.coldPressureSensorAlarm);
    setCell("heat_current_alarm", STATE.heatCurrentAlarm);
    setCell("cold_current_alarm", STATE.coldCurrentAlarm);
    setCell("cold_pressure_alarm", STATE.coldPressureAlarm);
    setCell("low_pressure_alarm", STATE.lowPressureAlarm);
    setCell("makeup_failed_alarm", STATE.makeupFailedAlarm);
    setCell("no_rise_alarm", STATE.noRiseAlarm);
    setCell("watchdog_alarm", STATE.watchdogAlarm);

    setCell("status_line1", "Отопление: " + pressureState.heatPressureBar + " бар; " + pressureState.heatCurrentMa + " мА.");
    setCell("status_line2", "ХВС: " + pressureState.coldPressureBar + " бар; " + pressureState.coldCurrentMa + " мА.");
    setCell("status_line3", "Разница ХВС-отопление: " + pressureState.pressureDeltaBar + " бар.");
    setCell("status_line4", "Цикл: " + (STATE.active ? "активен" : "остановлен") + ", импульсы " + STATE.pulseCount + ".");
    setCell("status_line5", "Клапан: " + (readBool(dev[CH.valveMakeup]) ? "открыт" : "закрыт") + ".");
    setCell("status_text", STATE.lastEvent);
}

function checkPressureRise(settings, pressureState)
{
    if (!settings.minRiseBar || settings.minRiseBar <= 0)
        return;

    if (!STATE.active)
        return;

    if (STATE.pulseCount < 2)
        return;

    if (STATE.cycleStartPressureBar === null || pressureState.heatPressureBar === null)
        return;

    if (pressureState.heatPressureBar < STATE.cycleStartPressureBar + settings.minRiseBar)
    {
        STATE.noRiseAlarm = true;
        stopCycle("Подпитка остановлена: давление не растёт");
    }
}

function openPulse(settings, manualMode)
{
    var pressureState = readPressureState();

    updateSafetyAlarms(settings, pressureState);

    if (STATE.heatCurrentAlarm || STATE.coldCurrentAlarm)
    {
        stopCycle("Импульс отклонен: ток датчика давления ниже порога");
        updateVirtualState(pressureState);
        return;
    }

    if (STATE.heatPressureSensorAlarm || STATE.coldPressureSensorAlarm)
    {
        stopCycle("Импульс отклонен: ошибка значения давления");
        updateVirtualState(pressureState);
        return;
    }

    if (STATE.coldPressureAlarm)
    {
        stopCycle("Импульс отклонен: давление ХВС недостаточно");
        updateVirtualState(pressureState);
        return;
    }

    if (STATE.valveOpening || STATE.waitingPause || readBool(dev[CH.valveMakeup]))
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
                "Клапан подпитки был открыт дольше допустимого времени.",
                "Проверьте реле, клапан и логику подпитки."
            );
        }
    }, settings.watchdogS * 1000);
}

function evaluate()
{
    var settings = getSettings();
    var pressureState = readPressureState();

    updateSafetyAlarms(settings, pressureState);

    if (STATE.heatCurrentAlarm)
    {
        stopCycle("Ошибка датчика давления отопления: ток ниже порога");
    }
    else if (STATE.coldCurrentAlarm)
    {
        stopCycle("Ошибка датчика давления ХВС: ток ниже порога");
    }
    else if (STATE.heatPressureSensorAlarm)
    {
        stopCycle("Ошибка датчика давления отопления: нет значения давления");
    }
    else if (STATE.coldPressureSensorAlarm)
    {
        stopCycle("Ошибка датчика давления ХВС: нет значения давления");
    }
    else if (STATE.coldPressureAlarm)
    {
        if (STATE.active || readBool(dev[CH.valveMakeup]))
            stopCycle("Подпитка остановлена: давление ХВС недостаточно");
    }
    else if (!settings.enabled || !settings.autoMode)
    {
        stopCycle("Подпитка отключена");
    }
    else
    {
        if (pressureState.heatPressureBar !== null && pressureState.heatPressureBar >= settings.pressureTargetBar)
        {
            if (STATE.active)
                stopCycle("Успешное завершение: достигнуто целевое давление");

            STATE.active = false;
            STATE.pulseCount = 0;
            STATE.makeupFailedAlarm = false;
            STATE.noRiseAlarm = false;
            STATE.cycleStartPressureBar = null;
        }
        else if (!STATE.valveOpening && !STATE.waitingPause)
        {
            checkPressureRise(settings, pressureState);

            if (!STATE.active && pressureState.heatPressureBar !== null && pressureState.heatPressureBar < settings.pressureMinBar)
            {
                STATE.active = true;
                STATE.pulseCount = 0;
                STATE.cycleStartPressureBar = pressureState.heatPressureBar;
                setEvent("Старт цикла подпитки");
            }

            if (STATE.active && !STATE.noRiseAlarm)
            {
                if (STATE.pulseCount >= settings.maxPulses)
                {
                    STATE.makeupFailedAlarm = true;
                    stopCycle("Неуспешное завершение: превышено количество импульсов");

                    sendAlertIfAllowed(
                        settings,
                        "Подпитка не дала результата",
                        "Превышено допустимое количество импульсов.",
                        "Проверьте наличие воды, давление ХВС и клапан подпитки."
                    );
                }
                else if (pressureState.heatPressureBar !== null && pressureState.heatPressureBar < settings.pressureTargetBar)
                {
                    openPulse(settings, false);
                    pressureState = readPressureState();
                    updateSafetyAlarms(settings, pressureState);
                }
            }
        }
    }

    updateVirtualState(pressureState);
}

defineVirtualDevice("pressure_makeup", {
    title: "550 Подпитка давления отопления",
    cells: {
        enabled: { type: "switch", value: true, order: 1 },
        auto_mode: { type: "switch", value: true, order: 2 },

        current_break_ma: { type: "value", value: CFG.currentBreakMa, order: 9 },
        pressure_min_bar: { type: "value", value: CFG.pressureMinBar, order: 10 },
        pressure_target_bar: { type: "value", value: CFG.pressureTargetBar, order: 11 },
        pressure_alarm_bar: { type: "value", value: CFG.pressureAlarmBar, order: 12 },

        cold_min_delta_bar: { type: "value", value: CFG.coldMinDeltaBar, order: 20 },
        cold_min_abs_bar: { type: "value", value: CFG.coldMinAbsBar, order: 21 },

        pulse_open_s: { type: "value", value: CFG.pulseOpenS, order: 30 },
        pulse_pause_s: { type: "value", value: CFG.pulsePauseS, order: 31 },
        max_pulses: { type: "value", value: CFG.maxPulses, order: 32 },
        watchdog_s: { type: "value", value: CFG.watchdogS, order: 33 },
        min_rise_bar: { type: "value", value: CFG.minRiseBar, order: 34 },

        manual_close: { type: "pushbutton", order: 40 },
        reset_alarm: { type: "pushbutton", order: 41 },
        manual_pulse: { type: "pushbutton", order: 42 },

        heat_pressure_bar: { type: "value", readonly: true, value: 0, order: 50 },
        heat_pressure_current_ma: { type: "value", readonly: true, value: 0, order: 51 },
        cold_pressure_bar: { type: "value", readonly: true, value: 0, order: 52 },
        cold_pressure_current_ma: { type: "value", readonly: true, value: 0, order: 53 },
        pressure_delta_bar: { type: "value", readonly: true, value: 0, order: 54 },

        valve_open: { type: "switch", readonly: true, value: false, order: 60 },
        active: { type: "switch", readonly: true, value: false, order: 61 },
        valve_opening: { type: "switch", readonly: true, value: false, order: 62 },
        waiting_pause: { type: "switch", readonly: true, value: false, order: 63 },
        pulse_count: { type: "value", readonly: true, value: 0, order: 64 },

        heat_pressure_sensor_alarm: { type: "switch", readonly: true, value: false, order: 70 },
        cold_pressure_sensor_alarm: { type: "switch", readonly: true, value: false, order: 71 },
        heat_current_alarm: { type: "switch", readonly: true, value: false, order: 72 },
        cold_current_alarm: { type: "switch", readonly: true, value: false, order: 73 },
        cold_pressure_alarm: { type: "switch", readonly: true, value: false, order: 74 },
        low_pressure_alarm: { type: "switch", readonly: true, value: false, order: 75 },
        makeup_failed_alarm: { type: "switch", readonly: true, value: false, order: 76 },
        no_rise_alarm: { type: "switch", readonly: true, value: false, order: 77 },
        watchdog_alarm: { type: "switch", readonly: true, value: false, order: 78 },

        last_event: { type: "text", readonly: true, value: "", order: 80 },
        status_line1: { type: "text", readonly: true, value: "", order: 81 },
        status_line2: { type: "text", readonly: true, value: "", order: 82 },
        status_line3: { type: "text", readonly: true, value: "", order: 83 },
        status_line4: { type: "text", readonly: true, value: "", order: 84 },
        status_line5: { type: "text", readonly: true, value: "", order: 85 },
        status_text: { type: "text", readonly: true, value: "", order: 86 }
    }
});

defineRule("pressure_makeup_eval_550", {
    whenChanged: [
        CH.heatPressureBar,
        CH.heatPressureCurrent,
        CH.coldPressureBar,
        CH.coldPressureCurrent,
        "pressure_makeup/enabled",
        "pressure_makeup/auto_mode",
        "pressure_makeup/current_break_ma",
        "pressure_makeup/pressure_min_bar",
        "pressure_makeup/pressure_target_bar",
        "pressure_makeup/pressure_alarm_bar",
        "pressure_makeup/cold_min_delta_bar",
        "pressure_makeup/cold_min_abs_bar",
        "pressure_makeup/pulse_open_s",
        "pressure_makeup/pulse_pause_s",
        "pressure_makeup/max_pulses",
        "pressure_makeup/watchdog_s",
        "pressure_makeup/min_rise_bar"
    ],
    then: function () {
        evaluate();
    }
});

defineRule("pressure_makeup_manual_close_550", {
    whenChanged: "pressure_makeup/manual_close",
    then: function (newValue) {
        if (!newValue)
            return;

        stopCycle("Ручное закрытие");
        updateVirtualState(readPressureState());
    }
});

defineRule("pressure_makeup_reset_alarm_550", {
    whenChanged: "pressure_makeup/reset_alarm",
    then: function (newValue) {
        if (!newValue)
            return;

        resetAllAlarmsAndCycle();
        evaluate();
    }
});

defineRule("pressure_makeup_manual_pulse_550", {
    whenChanged: "pressure_makeup/manual_pulse",
    then: function (newValue) {
        var settings;

        if (!newValue)
            return;

        settings = getSettings();

        if (readBool(dev[CH.valveMakeup]))
        {
            setEvent("Ручной импульс отклонен: клапан уже открыт");
            evaluate();
            return;
        }

        openPulse(settings, true);
        evaluate();
    }
});

setTimeout(function () {
    safeLog("[550_Pressure_makeup] Запуск скрипта");
    dev[CH.valveMakeup] = false;
    setEvent("Принудительное закрытие клапана на старте");
    evaluate();
}, 3000);
