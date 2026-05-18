// 550_Pressure_makeup.js
// 05 38 Плодоовощ 47.
// Автоматическая импульсная подпитка давления отопления.
// Защита: клапан не открывается, если давление ХВС недостаточно выше давления отопления.
// Защита: клапан не открывается при ошибке тока датчиков давления 4-20 мА.
// Защита: автоподпитка блокируется при слишком частых циклах подпитки.
// Физический канал, который пишет скрипт: wb-mr6cu_219/K5

var System = null;

try {
    System = require("system");
} catch (e) {
    System = null;
}

var LOG_SYSTEM_NAME = "отопление";
var LOG_SCRIPT_NAME = "550_Pressure_makeup";
var LOG_CONTEXT_NAME = "давление";

var HOUR_MS = 60 * 60 * 1000;
var DAY_MS = 24 * HOUR_MS;

var CH = {
    valveMakeup: "wb-mr6cu_219/K5",                       // 550 Клапан подпитки отопления
    heatPressureBar: "wb-mai2-mini_210/input_1_value",     // Давление отопления, бар × 1000
    heatPressureCurrent: "wb-mai2-mini_210/input_1_current", // Ток датчика давления отопления, мА
    coldPressureBar: "wb-mai2-mini_210/input_2_value",     // Давление ХВС, бар × 1000
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
    pressureClampMaxBar: 6,

    minRiseBar: 0,             // 0 = контроль роста давления отключен
    autoStartBlockMs: 60000,    // блокировка автоматической подпитки после старта wb-rules

    maxCycles1h: 3,             // максимум автоматических циклов подпитки за 1 час; 0 = контроль отключен
    maxCycles24h: 6             // максимум автоматических циклов подпитки за 24 часа; 0 = контроль отключен
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
    frequentMakeupAlarm: false,

    autoStartBlocked: true,

    makeupCycleTimestamps: [],
    makeupCycles1h: 0,
    makeupCycles24h: 0,

    cycleStartPressureBar: null,
    lastEvent: "",
    lastLoggedEvent: "",

    alarmLogState: {},

    valveCloseTimer: null,
    pauseTimer: null,
    watchdogTimer: null,
    autoStartBlockTimer: null
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

function writeJournal(level, message)
{
    if (level === "error" && log.error)
    {
        log.error(message);
        return;
    }

    if (level === "warning" && log.warning)
    {
        log.warning(message);
        return;
    }

    if (log.info)
    {
        log.info(message);
        return;
    }

    safeLog(message);
}

function formatParams(params)
{
    var list = [];
    var k;

    if (!params)
        return "";

    for (k in params)
    {
        if (params.hasOwnProperty(k))
        {
            if (params[k] !== undefined && params[k] !== null && params[k] !== "")
                list.push(k + "=" + params[k]);
        }
    }

    if (list.length === 0)
        return "";

    return "; " + list.join("; ");
}

function writeLog(eventName, eventText, params)
{
    var message = "[" + LOG_SYSTEM_NAME + "][" + LOG_SCRIPT_NAME + "][" + LOG_CONTEXT_NAME + "]; " +
        eventName + "=" + eventText + formatParams(params);

    if (eventName === "АВАРИЯ" || eventName === "WATCHDOG")
    {
        writeJournal("error", message);
        return;
    }

    if (eventName === "ОШИБКА")
    {
        writeJournal("warning", message);
        return;
    }

    writeJournal("info", message);
}

function readBool(value)
{
    return value === true || value === 1 || value === "1" || value === "true";
}

function readNumber(path, fallback)
{
    var raw;
    var value;

    if (!path)
        return fallback;

    raw = dev[path];

    if (raw === null || raw === undefined || raw === "")
        return fallback;

    value = Number(raw);

    if (!isFinite(value))
        return fallback;

    return value;
}

function setCell(name, value)
{
    if (dev["pressure_makeup/" + name] !== value)
        dev["pressure_makeup/" + name] = value;
}

function formatNumber(value)
{
    if (value === null || value === undefined || !isFinite(Number(value)))
        return "нет данных";

    return String(value);
}

function makePressureParams(settings, pressureState, reason)
{
    var params = {
        "причина": reason,
        "отопление": pressureState ? formatNumber(pressureState.heatPressureBar) : "нет данных",
        "хвс": pressureState ? formatNumber(pressureState.coldPressureBar) : "нет данных",
        "запас_хвс": pressureState ? formatNumber(pressureState.pressureDeltaBar) : "нет данных",
        "ток_отопление": pressureState ? formatNumber(pressureState.heatCurrentMa) : "нет данных",
        "ток_хвс": pressureState ? formatNumber(pressureState.coldCurrentMa) : "нет данных",
        "клапан": readBool(dev[CH.valveMakeup]) ? "ON" : "OFF",
        "импульсы": STATE.pulseCount,
        "канал": CH.valveMakeup
    };

    if (settings)
    {
        params["старт"] = settings.pressureMinBar;
        params["цель"] = settings.pressureTargetBar;
        params["мин_хвс"] = settings.coldMinAbsBar;
        params["мин_запас_хвс"] = settings.coldMinDeltaBar;
        params["лимит_циклов_1ч"] = settings.maxCycles1h;
        params["лимит_циклов_24ч"] = settings.maxCycles24h;
    }

    params["циклов_1ч"] = STATE.makeupCycles1h;
    params["циклов_24ч"] = STATE.makeupCycles24h;

    return params;
}

function setEvent(text, eventName, params, forceLog)
{
    STATE.lastEvent = text;
    setCell("last_event", text);

    if (!eventName)
        eventName = "СОСТОЯНИЕ";

    if (forceLog || STATE.lastLoggedEvent !== eventName + ":" + text)
    {
        STATE.lastLoggedEvent = eventName + ":" + text;
        writeLog(eventName, text, params);
    }
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

function round2(value)
{
    if (value === null)
        return null;

    return Math.round(value * 100) / 100;
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
        maxCycles1h: readNumber("pressure_makeup/max_cycles_1h", CFG.maxCycles1h),
        maxCycles24h: readNumber("pressure_makeup/max_cycles_24h", CFG.maxCycles24h),

        smsAllowed: CH.secBlock ? !readBool(dev[CH.secBlock]) : true
    };
}

function readPressureState()
{
    var heatRaw = readNumber(CH.heatPressureBar, null);
    var coldRaw = readNumber(CH.coldPressureBar, null);
    var heatRawBar = heatRaw === null ? null : heatRaw / 1000;
    var coldRawBar = coldRaw === null ? null : coldRaw / 1000;
    var heatCurrentMa = readNumber(CH.heatPressureCurrent, null);
    var coldCurrentMa = readNumber(CH.coldPressureCurrent, null);
    var heatPressureBar = round2(filterValue(heatRawBar, STATE.heatPressureBuffer));
    var coldPressureBar = round2(filterValue(coldRawBar, STATE.coldPressureBuffer));
    var pressureDeltaBar = null;

    if (heatPressureBar !== null && coldPressureBar !== null)
        pressureDeltaBar = round2(coldPressureBar - heatPressureBar);

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

    writeLog("ОШИБКА", "Уведомление не отправлено через system.js", {
        "событие": eventText,
        "детали": detailsText,
        "рекомендация": recommendationText
    });
}

function isControlAvailable(topic)
{
    return topic && dev[topic] !== null && dev[topic] !== undefined;
}

function writeValve(value, eventText, settings, pressureState, reason)
{
    var params = makePressureParams(settings, pressureState, reason);

    params["канал"] = CH.valveMakeup;
    params["значение в канал"] = value ? "ON" : "OFF";

    if (!isControlAvailable(CH.valveMakeup))
    {
        setEvent("Канал клапана подпитки недоступен", "ОШИБКА", params, true);
        return false;
    }

    if (readBool(dev[CH.valveMakeup]) !== value)
        dev[CH.valveMakeup] = value;

    setEvent(eventText, "КОМАНДА", params, true);
    return true;
}

function closeValve(reason)
{
    var settings = getSettings();
    var pressureState = readPressureState();
    var wasOpen = readBool(dev[CH.valveMakeup]);

    if (wasOpen)
        writeValve(false, "Закрыть клапан подпитки", settings, pressureState, reason || "закрытие клапана");
    else if (!isControlAvailable(CH.valveMakeup))
        setEvent("Канал клапана подпитки недоступен", "ОШИБКА", makePressureParams(settings, pressureState, reason || "закрытие клапана"), false);

    clearTimer("valveCloseTimer");
    clearTimer("watchdogTimer");

    STATE.valveOpening = false;

    if (reason)
        setEvent(reason, classifyEvent(reason), makePressureParams(settings, pressureState, reason), false);
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

function classifyEvent(text)
{
    if (text.indexOf("Watchdog") >= 0)
        return "WATCHDOG";

    if (text.indexOf("Неуспешное") >= 0 || text.indexOf("не растёт") >= 0)
        return "АВАРИЯ";

    if (text.indexOf("Ошибка") >= 0 || text.indexOf("отклонен") >= 0 || text.indexOf("недостаточно") >= 0)
        return "ОШИБКА";

    return "СОСТОЯНИЕ";
}

function rejectPulse(reason, stopActiveCycle)
{
    var settings = getSettings();
    var pressureState = readPressureState();

    if (stopActiveCycle)
    {
        stopCycle(reason);
        return;
    }

    setEvent(reason, "ОШИБКА", makePressureParams(settings, pressureState, reason), false);
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
    STATE.frequentMakeupAlarm = false;

    STATE.pulseCount = 0;
    STATE.heatPressureBuffer = [];
    STATE.coldPressureBuffer = [];
    STATE.makeupCycleTimestamps = [];
    STATE.makeupCycles1h = 0;
    STATE.makeupCycles24h = 0;
    STATE.alarmLogState = {};
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

function logAlarmFlag(name, active, eventText, settings, pressureState)
{
    var previous = STATE.alarmLogState[name];
    var params;

    if (previous === active)
        return;

    STATE.alarmLogState[name] = active;
    params = makePressureParams(settings, pressureState, active ? "активна" : "восстановление");

    if (active)
        writeLog(name === "lowPressureAlarm" ? "АВАРИЯ" : "ОШИБКА", eventText, params);
    else
        writeLog("РЕЗУЛЬТАТ", eventText + " снята", params);
}

function logSafetyAlarms(settings, pressureState)
{
    logAlarmFlag("heatCurrentAlarm", STATE.heatCurrentAlarm, "Ток датчика давления отопления ниже порога", settings, pressureState);
    logAlarmFlag("coldCurrentAlarm", STATE.coldCurrentAlarm, "Ток датчика давления ХВС ниже порога", settings, pressureState);
    logAlarmFlag("heatPressureSensorAlarm", STATE.heatPressureSensorAlarm, "Нет корректного давления отопления", settings, pressureState);
    logAlarmFlag("coldPressureSensorAlarm", STATE.coldPressureSensorAlarm, "Нет корректного давления ХВС", settings, pressureState);
    logAlarmFlag("coldPressureAlarm", STATE.coldPressureAlarm, "Давление ХВС недостаточно для подпитки", settings, pressureState);
    logAlarmFlag("lowPressureAlarm", STATE.lowPressureAlarm, "Аварийно низкое давление отопления", settings, pressureState);
    logAlarmFlag("frequentMakeupAlarm", STATE.frequentMakeupAlarm, "Слишком частая подпитка отопления", settings, pressureState);
}


function updateMakeupCycleStats()
{
    var now = nowMs();
    var i;
    var fresh = [];
    var cycles1h = 0;
    var cycles24h = 0;

    for (i = 0; i < STATE.makeupCycleTimestamps.length; i++)
    {
        if (now - STATE.makeupCycleTimestamps[i] <= DAY_MS)
        {
            fresh.push(STATE.makeupCycleTimestamps[i]);

            if (now - STATE.makeupCycleTimestamps[i] <= HOUR_MS)
                cycles1h = cycles1h + 1;

            cycles24h = cycles24h + 1;
        }
    }

    STATE.makeupCycleTimestamps = fresh;
    STATE.makeupCycles1h = cycles1h;
    STATE.makeupCycles24h = cycles24h;
}

function checkFrequentMakeupLimit(settings, pressureState)
{
    var over1h = settings.maxCycles1h > 0 && STATE.makeupCycles1h > settings.maxCycles1h;
    var over24h = settings.maxCycles24h > 0 && STATE.makeupCycles24h > settings.maxCycles24h;
    var params;

    if (!over1h && !over24h)
        return false;

    STATE.frequentMakeupAlarm = true;

    params = makePressureParams(settings, pressureState, over1h ? "превышен лимит циклов за 1 час" : "превышен лимит циклов за 24 часа");
    writeLog("АВАРИЯ", "Слишком частая подпитка отопления", params);

    sendAlertIfAllowed(
        settings,
        "Слишком частая подпитка отопления",
        "Автоподпитка заблокирована: циклов за 1 час=" + STATE.makeupCycles1h + ", за 24 часа=" + STATE.makeupCycles24h + ".",
        "Проверьте протечки, расширительный бак, предохранительный клапан и давление в системе."
    );

    return true;
}

function registerMakeupCycleStart(settings, pressureState)
{
    updateMakeupCycleStats();
    STATE.makeupCycleTimestamps.push(nowMs());
    updateMakeupCycleStats();

    setCell("makeup_cycles_1h", STATE.makeupCycles1h);
    setCell("makeup_cycles_24h", STATE.makeupCycles24h);

    if (checkFrequentMakeupLimit(settings, pressureState))
        return false;

    return true;
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
    updateMakeupCycleStats();
    setCell("auto_start_blocked", STATE.autoStartBlocked);
    setCell("makeup_cycles_1h", STATE.makeupCycles1h);
    setCell("makeup_cycles_24h", STATE.makeupCycles24h);

    setCell("heat_pressure_sensor_alarm", STATE.heatPressureSensorAlarm);
    setCell("cold_pressure_sensor_alarm", STATE.coldPressureSensorAlarm);
    setCell("heat_current_alarm", STATE.heatCurrentAlarm);
    setCell("cold_current_alarm", STATE.coldCurrentAlarm);
    setCell("cold_pressure_alarm", STATE.coldPressureAlarm);
    setCell("low_pressure_alarm", STATE.lowPressureAlarm);
    setCell("makeup_failed_alarm", STATE.makeupFailedAlarm);
    setCell("no_rise_alarm", STATE.noRiseAlarm);
    setCell("watchdog_alarm", STATE.watchdogAlarm);
    setCell("frequent_makeup_alarm", STATE.frequentMakeupAlarm);

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

function canStartPulse(settings, pressureState, manualMode)
{
    if (!manualMode && !settings.enabled)
        return "Импульс отклонен: подпитка отключена";

    if (!manualMode && !settings.autoMode)
        return "Импульс отклонен: автоматический режим отключен";

    if (!manualMode && STATE.autoStartBlocked)
        return "Импульс отклонен: автоподпитка заблокирована после запуска скрипта";

    if (!isControlAvailable(CH.valveMakeup))
        return "Импульс отклонен: канал клапана подпитки недоступен";

    if (STATE.watchdogAlarm)
        return "Импульс отклонен: активна авария watchdog";

    if (STATE.frequentMakeupAlarm)
        return "Импульс отклонен: слишком частая подпитка, автоподпитка заблокирована";

    if (settings.minRiseBar > 0 && STATE.noRiseAlarm)
        return "Импульс отклонен: активна авария отсутствия роста давления";

    if (STATE.makeupFailedAlarm || STATE.pulseCount >= settings.maxPulses)
        return "Импульс отклонен: превышено количество импульсов";

    if (STATE.heatCurrentAlarm || STATE.coldCurrentAlarm)
        return "Импульс отклонен: ток датчика давления ниже порога";

    if (STATE.heatPressureSensorAlarm || STATE.coldPressureSensorAlarm)
        return "Импульс отклонен: ошибка значения давления";

    if (STATE.coldPressureAlarm)
        return "Импульс отклонен: давление ХВС недостаточно";

    if (STATE.valveOpening || STATE.waitingPause || readBool(dev[CH.valveMakeup]))
        return "Импульс отклонен: клапан уже открыт или цикл ещё не завершён";

    if (pressureState.heatPressureBar !== null && pressureState.heatPressureBar >= settings.pressureTargetBar)
        return "Импульс отклонен: уже достигнуто целевое давление";

    return "";
}

function openPulse(settings, manualMode)
{
    var pressureState = readPressureState();
    var rejectReason = "";
    var stopActiveCycle = false;

    updateSafetyAlarms(settings, pressureState);
    updateMakeupCycleStats();
    logSafetyAlarms(settings, pressureState);

    rejectReason = canStartPulse(settings, pressureState, manualMode);
    if (rejectReason)
    {
        stopActiveCycle = STATE.watchdogAlarm ||
            STATE.frequentMakeupAlarm ||
            (settings.minRiseBar > 0 && STATE.noRiseAlarm) ||
            STATE.makeupFailedAlarm ||
            STATE.pulseCount >= settings.maxPulses ||
            STATE.heatCurrentAlarm ||
            STATE.coldCurrentAlarm ||
            STATE.heatPressureSensorAlarm ||
            STATE.coldPressureSensorAlarm ||
            STATE.coldPressureAlarm;

        rejectPulse(rejectReason, stopActiveCycle);
        updateVirtualState(pressureState);
        return;
    }

    STATE.active = true;
    STATE.valveOpening = true;
    STATE.pulseCount = STATE.pulseCount + 1;

    if (!writeValve(true, manualMode ? "Открыть клапан подпитки: ручной импульс" : "Открыть клапан подпитки", settings, pressureState, manualMode ? "ручной импульс" : "автоматический импульс"))
    {
        STATE.valveOpening = false;
        updateVirtualState(pressureState);
        return;
    }

    STATE.valveCloseTimer = setTimeout(function () {
        closeValve("Закрытие клапана после импульса");

        STATE.waitingPause = true;
        setEvent("Начало паузы после импульса", "СОСТОЯНИЕ", makePressureParams(settings, readPressureState(), "пауза после импульса"), true);

        STATE.pauseTimer = setTimeout(function () {
            STATE.waitingPause = false;
            setEvent("Окончание паузы после импульса", "СОСТОЯНИЕ", makePressureParams(settings, readPressureState(), "окончание паузы"), true);
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
    updateMakeupCycleStats();
    logSafetyAlarms(settings, pressureState);

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
    else if (STATE.frequentMakeupAlarm)
    {
        if (STATE.active || readBool(dev[CH.valveMakeup]))
            stopCycle("Подпитка остановлена: слишком частые срабатывания");
        else
            setEvent("Автоподпитка заблокирована: слишком частые срабатывания", "АВАРИЯ", makePressureParams(settings, pressureState, "превышен лимит циклов подпитки"), false);
    }
    else if (!settings.enabled || !settings.autoMode)
    {
        if (STATE.active || readBool(dev[CH.valveMakeup]))
            stopCycle("Подпитка отключена");
        else
            setEvent("Подпитка отключена", "СОСТОЯНИЕ", makePressureParams(settings, pressureState, "enabled=false или auto_mode=false"), false);
    }
    else if (STATE.autoStartBlocked)
    {
        setEvent("Автоподпитка заблокирована после запуска скрипта", "СОСТОЯНИЕ", makePressureParams(settings, pressureState, "стартовая блокировка"), false);
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
                if (!registerMakeupCycleStart(settings, pressureState))
                {
                    stopCycle("Подпитка остановлена: слишком частые срабатывания");
                    updateVirtualState(pressureState);
                    return;
                }

                STATE.active = true;
                STATE.pulseCount = 0;
                STATE.cycleStartPressureBar = pressureState.heatPressureBar;
                setEvent("Старт цикла подпитки", "СОСТОЯНИЕ", makePressureParams(settings, pressureState, "давление отопления ниже порога старта"), true);
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
                    logSafetyAlarms(settings, pressureState);
                }
            }
        }
    }

    updateVirtualState(pressureState);
}

defineVirtualDevice("pressure_makeup", {
    title: "550 Подпитка давления отопления",
    cells: {
        enabled: { type: "switch", value: true, order: 1, title: "Подпитка разрешена" },
        auto_mode: { type: "switch", value: true, order: 2, title: "Автоматический режим" },
        manual_pulse: { type: "pushbutton", order: 3, title: "Ручной импульс" },
        manual_close: { type: "pushbutton", order: 4, title: "Закрыть клапан" },
        reset_alarm: { type: "pushbutton", order: 5, title: "Сбросить аварии" },

        heat_pressure_bar: { type: "value", readonly: true, value: 0, order: 10, title: "Давление отопления, бар" },
        heat_pressure_current_ma: { type: "value", readonly: true, value: 0, order: 11, title: "Ток датчика отопления, мА" },
        cold_pressure_bar: { type: "value", readonly: true, value: 0, order: 12, title: "Давление ХВС, бар" },
        cold_pressure_current_ma: { type: "value", readonly: true, value: 0, order: 13, title: "Ток датчика ХВС, мА" },
        pressure_delta_bar: { type: "value", readonly: true, value: 0, order: 14, title: "Запас давления ХВС, бар" },
        valve_open: { type: "switch", readonly: true, value: false, order: 15, title: "Клапан подпитки открыт" },
        active: { type: "switch", readonly: true, value: false, order: 16, title: "Цикл подпитки активен" },
        valve_opening: { type: "switch", readonly: true, value: false, order: 17, title: "Идёт импульс открытия" },
        waiting_pause: { type: "switch", readonly: true, value: false, order: 18, title: "Пауза после импульса" },
        pulse_count: { type: "value", readonly: true, value: 0, order: 19, title: "Импульсов в цикле" },
        auto_start_blocked: { type: "switch", readonly: true, value: true, order: 20, title: "Блокировка автоподпитки после запуска" },
        makeup_cycles_1h: { type: "value", readonly: true, value: 0, order: 21, title: "Циклов подпитки за 1 час" },
        makeup_cycles_24h: { type: "value", readonly: true, value: 0, order: 22, title: "Циклов подпитки за 24 часа" },

        heat_pressure_sensor_alarm: { type: "switch", readonly: true, value: false, order: 30, title: "Ошибка давления отопления" },
        cold_pressure_sensor_alarm: { type: "switch", readonly: true, value: false, order: 31, title: "Ошибка давления ХВС" },
        heat_current_alarm: { type: "switch", readonly: true, value: false, order: 32, title: "Обрыв датчика отопления" },
        cold_current_alarm: { type: "switch", readonly: true, value: false, order: 33, title: "Обрыв датчика ХВС" },
        cold_pressure_alarm: { type: "switch", readonly: true, value: false, order: 34, title: "Недостаточное давление ХВС" },
        low_pressure_alarm: { type: "switch", readonly: true, value: false, order: 35, title: "Аварийно низкое давление отопления" },
        makeup_failed_alarm: { type: "switch", readonly: true, value: false, order: 36, title: "Подпитка не дала результата" },
        no_rise_alarm: { type: "switch", readonly: true, value: false, order: 37, title: "Давление не растёт" },
        watchdog_alarm: { type: "switch", readonly: true, value: false, order: 38, title: "Watchdog клапана" },
        frequent_makeup_alarm: { type: "switch", readonly: true, value: false, order: 39, title: "Слишком частая подпитка" },

        last_event: { type: "text", readonly: true, value: "", order: 60, title: "Последнее событие" },
        status_line1: { type: "text", readonly: true, value: "", order: 61, title: "Статус 1" },
        status_line2: { type: "text", readonly: true, value: "", order: 62, title: "Статус 2" },
        status_line3: { type: "text", readonly: true, value: "", order: 63, title: "Статус 3" },
        status_line4: { type: "text", readonly: true, value: "", order: 64, title: "Статус 4" },
        status_line5: { type: "text", readonly: true, value: "", order: 65, title: "Статус 5" },
        status_text: { type: "text", readonly: true, value: "", order: 66, title: "Текущий статус" },

        pressure_min_bar: { type: "value", value: CFG.pressureMinBar, order: 100, title: "Старт подпитки, бар" },
        pressure_target_bar: { type: "value", value: CFG.pressureTargetBar, order: 101, title: "Целевое давление, бар" },
        pressure_alarm_bar: { type: "value", value: CFG.pressureAlarmBar, order: 102, title: "Аварийный минимум, бар" },
        cold_min_delta_bar: { type: "value", value: CFG.coldMinDeltaBar, order: 103, title: "Минимальный запас ХВС, бар" },
        cold_min_abs_bar: { type: "value", value: CFG.coldMinAbsBar, order: 104, title: "Минимальное давление ХВС, бар" },
        pulse_open_s: { type: "value", value: CFG.pulseOpenS, order: 105, title: "Открытие клапана, сек" },
        pulse_pause_s: { type: "value", value: CFG.pulsePauseS, order: 106, title: "Пауза после импульса, сек" },
        max_pulses: { type: "value", value: CFG.maxPulses, order: 107, title: "Максимум импульсов" },
        watchdog_s: { type: "value", value: CFG.watchdogS, order: 108, title: "Watchdog открытия, сек" },
        current_break_ma: { type: "value", value: CFG.currentBreakMa, order: 109, title: "Порог обрыва датчика, мА" },
        min_rise_bar: { type: "value", value: CFG.minRiseBar, order: 110, title: "Минимальный рост давления, бар" },
        max_cycles_1h: { type: "value", value: CFG.maxCycles1h, order: 111, title: "Максимум циклов за 1 час" },
        max_cycles_24h: { type: "value", value: CFG.maxCycles24h, order: 112, title: "Максимум циклов за 24 часа" }
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
        "pressure_makeup/min_rise_bar",
        "pressure_makeup/max_cycles_1h",
        "pressure_makeup/max_cycles_24h"
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
        var pressureState;

        if (!newValue)
            return;

        settings = getSettings();
        pressureState = readPressureState();

        if (readBool(dev[CH.valveMakeup]))
        {
            setEvent("Ручной импульс отклонен: клапан уже открыт", "ОШИБКА", makePressureParams(settings, pressureState, "ручной импульс"), true);
            evaluate();
            return;
        }

        openPulse(settings, true);
        evaluate();
    }
});

writeLog("СКРИПТ", "Скрипт загружен", {
    "канал_клапана": CH.valveMakeup,
    "давление_отопления": CH.heatPressureBar,
    "давление_хвс": CH.coldPressureBar
});

setTimeout(function () {
    var settings = getSettings();
    var pressureState = readPressureState();

    writeValve(false, "Принудительно выключить канал клапана на старте", settings, pressureState, "старт скрипта");
    setEvent("Стартовая инициализация", "СКРИПТ", makePressureParams(settings, pressureState, "старт скрипта"), true);
    evaluate();
}, 3000);

STATE.autoStartBlockTimer = setTimeout(function () {
    STATE.autoStartBlocked = false;
    setCell("auto_start_blocked", false);
    setEvent("Блокировка автоподпитки после запуска снята", "СОСТОЯНИЕ", makePressureParams(getSettings(), readPressureState(), "таймер стартовой блокировки"), true);
    evaluate();
}, CFG.autoStartBlockMs);
