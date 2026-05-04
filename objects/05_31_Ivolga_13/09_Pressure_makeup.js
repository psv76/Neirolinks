/*********************************************************************
 09_Pressure_makeup.js
 Подкачка давления
*********************************************************************/

var System = require("system");
var safeLog = System.safeLog;
var sendAlert = System.sendAlert;
var sendRestore = System.sendRestore;
var sendInfo = System.sendInfo;

/*********************************************************************
 КАНАЛЫ
*********************************************************************/

var CH = {
    valveMakeup:      "A04/K1",
    pressureBar:      "905.3/input_1_value",
    pressureCurrent:  "905.3/input_1_current",
    secBlock:         "power_monitor/secondary_alerts_blocked"
};

/*********************************************************************
 НАСТРОЙКИ ПО УМОЛЧАНИЮ
*********************************************************************/

var CFG = {
    currentBreakMa:      3.6,
    pressureMinBar:      1.20,
    pressureTargetBar:   1.50,
    pressureAlarmBar:    0.80,
    pulseOpenS:          3,
    pulsePauseS:         20,
    maxPulses:           5,
    filterSize:          3,
    pressureMinPhysBar:  0,
    pressureMaxPhysBar:  6
};

/*********************************************************************
 СОСТОЯНИЕ
*********************************************************************/

var STATE = {
    buffer: [],
    filteredPressureBar: null,

    active: false,
    waitingPause: false,
    pulseCount: 0,
    timer: null,

    sensorAlarm: false,
    lowPressureAlarm: false,
    makeupFailedAlarm: false,
    restoredAfterAlarm: false
};

/*********************************************************************
 ОБЩИЕ ФУНКЦИИ
*********************************************************************/

function readNum(path, fallback)
{
    var value = dev[path];

    if (value === undefined || value === null || value === "")
        return fallback;

    value = Number(value);

    if (isNaN(value))
        return fallback;

    return value;
}

function readNumOrNull(path)
{
    var value = dev[path];

    if (value === undefined || value === null || value === "")
        return null;

    value = Number(value);

    if (isNaN(value))
        return null;

    return value;
}

function readBool(path)
{
    return dev[path] === true || dev[path] === "true" || dev[path] === 1 || dev[path] === "1";
}

function setCellValue(cell, value)
{
    if (dev["pressure_makeup/" + cell] !== value)
        dev["pressure_makeup/" + cell] = value;
}

function clamp(value, minValue, maxValue)
{
    if (value < minValue)
        return minValue;

    if (value > maxValue)
        return maxValue;

    return value;
}

function round2(value)
{
    if (value === null || value === undefined || isNaN(Number(value)))
        return null;

    return Math.round(Number(value) * 100) / 100;
}

function fmtBar(value)
{
    if (value === null || value === undefined || isNaN(Number(value)))
        return "-";

    return String(round2(value)) + " бар";
}

function fmtMa(value)
{
    if (value === null || value === undefined || isNaN(Number(value)))
        return "-";

    return String(round2(value)) + " mA";
}

function secondaryAlertsBlocked()
{
    return readBool(CH.secBlock);
}

function cancelTimer()
{
    if (STATE.timer)
    {
        clearTimeout(STATE.timer);
        STATE.timer = null;
    }
}

function resetCycleState()
{
    cancelTimer();
    STATE.active = false;
    STATE.waitingPause = false;
    STATE.pulseCount = 0;

    if (readBool(CH.valveMakeup))
        dev[CH.valveMakeup] = false;
}

function filterPressure(value)
{
    var i;
    var sum = 0;

    if (value === null || value === undefined || isNaN(Number(value)))
        return null;

    value = Number(value);

    STATE.buffer.push(value);

    while (STATE.buffer.length > CFG.filterSize)
        STATE.buffer.shift();

    for (i = 0; i < STATE.buffer.length; i++)
        sum += STATE.buffer[i];

    return clamp(sum / STATE.buffer.length, CFG.pressureMinPhysBar, CFG.pressureMaxPhysBar);
}

function currentSensorBroken(currentMa)
{
    return currentMa !== null && currentMa < CFG.currentBreakMa;
}

function getSettings()
{
    return {
        enabled: !!dev["pressure_makeup/enabled"],
        autoMode: !!dev["pressure_makeup/auto_mode"],
        pressureMinBar: readNum("pressure_makeup/pressure_min_bar", CFG.pressureMinBar),
        pressureTargetBar: readNum("pressure_makeup/pressure_target_bar", CFG.pressureTargetBar),
        pressureAlarmBar: readNum("pressure_makeup/pressure_alarm_bar", CFG.pressureAlarmBar),
        currentBreakMa: readNum("pressure_makeup/current_break_ma", CFG.currentBreakMa),
        pulseOpenS: readNum("pressure_makeup/pulse_open_s", CFG.pulseOpenS),
        pulsePauseS: readNum("pressure_makeup/pulse_pause_s", CFG.pulsePauseS),
        maxPulses: readNum("pressure_makeup/max_pulses", CFG.maxPulses)
    };
}

/*********************************************************************
 УВЕДОМЛЕНИЯ
*********************************************************************/

function sendSensorAlarm(pressureBar, currentMa)
{
    if (STATE.sensorAlarm || secondaryAlertsBlocked())
        return;

    sendAlert(
        "Котельная",
        "Ошибка датчика давления отопления.",
        "Давление = " + fmtBar(pressureBar) + ".\n" +
        "Ток датчика = " + fmtMa(currentMa) + ".\n" +
        "Ток ниже порога " + fmtMa(readNum("pressure_makeup/current_break_ma", CFG.currentBreakMa)) + ".",
        "Проверьте датчик давления, питание датчика и подключение к модулю."
    );

    STATE.sensorAlarm = true;
    STATE.restoredAfterAlarm = false;
}

function sendSensorRestore(pressureBar, currentMa)
{
    if (!STATE.sensorAlarm)
        return;

    sendRestore(
        "Котельная",
        "Датчик давления отопления восстановлен.",
        "Давление = " + fmtBar(pressureBar) + ".\n" +
        "Ток датчика = " + fmtMa(currentMa) + ".",
        ""
    );

    STATE.sensorAlarm = false;
    STATE.restoredAfterAlarm = true;
}

function sendLowPressureAlarm(pressureBar)
{
    if (STATE.lowPressureAlarm || secondaryAlertsBlocked())
        return;

    sendAlert(
        "Котельная",
        "Давление в системе отопления ниже допустимого.",
        "Текущее давление = " + fmtBar(pressureBar) + ".",
        "Проверьте систему отопления на утечку и работу подпитки."
    );

    STATE.lowPressureAlarm = true;
    STATE.restoredAfterAlarm = false;
}

function sendLowPressureRestore(pressureBar)
{
    if (!STATE.lowPressureAlarm)
        return;

    sendRestore(
        "Котельная",
        "Давление в системе отопления восстановлено.",
        "Текущее давление = " + fmtBar(pressureBar) + ".",
        ""
    );

    STATE.lowPressureAlarm = false;
    STATE.restoredAfterAlarm = true;
}

function sendMakeupStarted(pressureBar)
{
    if (secondaryAlertsBlocked())
        return;

    sendInfo(
        "Котельная",
        "Запущена автоматическая подпитка системы отопления.",
        "Стартовое давление = " + fmtBar(pressureBar) + ".",
        ""
    );
}

function sendMakeupSuccess(pressureBar, pulseCount)
{
    if (secondaryAlertsBlocked())
        return;

    sendRestore(
        "Котельная",
        "Автоматическая подпитка системы отопления завершена.",
        "Давление восстановлено до " + fmtBar(pressureBar) + ".\n" +
        "Количество импульсов = " + pulseCount + ".",
        ""
    );
}

function sendMakeupFailed(pressureBar, pulseCount)
{
    if (STATE.makeupFailedAlarm || secondaryAlertsBlocked())
        return;

    sendAlert(
        "Котельная",
        "Автоматическая подпитка системы отопления не дала результата.",
        "Текущее давление = " + fmtBar(pressureBar) + ".\n" +
        "Количество импульсов = " + pulseCount + ".",
        "Проверьте наличие воды, клапан подпитки и систему отопления на утечку."
    );

    STATE.makeupFailedAlarm = true;
    STATE.restoredAfterAlarm = false;
}

function sendMakeupFailedRestore(pressureBar)
{
    if (!STATE.makeupFailedAlarm)
        return;

    sendRestore(
        "Котельная",
        "Состояние подпитки системы отопления восстановлено.",
        "Текущее давление = " + fmtBar(pressureBar) + ".",
        ""
    );

    STATE.makeupFailedAlarm = false;
    STATE.restoredAfterAlarm = true;
}

/*********************************************************************
 ОСНОВНАЯ ЛОГИКА
*********************************************************************/

function updateStatus(pressureBar, currentMa, settings)
{
    var statusLine1 = "";
    var statusLine2 = "";
    var statusLine3 = "";
    var statusText = "";

    statusLine1 = "Давление: " + fmtBar(pressureBar) + ", ток: " + fmtMa(currentMa);
    statusLine2 = "Подпитка: " + (STATE.active ? "активна" : "выкл") +
                  ", импульс: " + STATE.pulseCount + "/" + settings.maxPulses;
    statusLine3 = "Клапан: " + (readBool(CH.valveMakeup) ? "открыт" : "закрыт");

    if (STATE.sensorAlarm)
        statusText = "Ошибка датчика давления";
    else if (STATE.makeupFailedAlarm)
        statusText = "Подпитка не дала результата";
    else if (STATE.active)
        statusText = "Идёт автоматическая подпитка";
    else if (pressureBar !== null && pressureBar < settings.pressureMinBar)
        statusText = "Давление ниже рабочего";
    else
        statusText = "Подпитка в норме";

    setCellValue("pressure_bar", round2(pressureBar));
    setCellValue("pressure_current_ma", round2(currentMa));
    setCellValue("valve_open", readBool(CH.valveMakeup));
    setCellValue("active", STATE.active);
    setCellValue("pulse_count", STATE.pulseCount);
    setCellValue("sensor_alarm", STATE.sensorAlarm);
    setCellValue("low_pressure_alarm", STATE.lowPressureAlarm);
    setCellValue("makeup_failed_alarm", STATE.makeupFailedAlarm);
    setCellValue("status_line1", statusLine1);
    setCellValue("status_line2", statusLine2);
    setCellValue("status_line3", statusLine3);
    setCellValue("status_text", statusText);
}

function finishCycleSuccess(pressureBar)
{
    var pulses = STATE.pulseCount;

    resetCycleState();
    sendMakeupSuccess(pressureBar, pulses);
    sendMakeupFailedRestore(pressureBar);
}

function finishCycleFailed(pressureBar)
{
    var pulses = STATE.pulseCount;

    resetCycleState();
    sendMakeupFailed(pressureBar, pulses);
}

function openValveAndWait(settings)
{
    STATE.active = true;
    STATE.waitingPause = false;
    STATE.pulseCount++;

    dev[CH.valveMakeup] = true;

    STATE.timer = setTimeout(function () {
        dev[CH.valveMakeup] = false;
        STATE.timer = null;
        STATE.waitingPause = true;

        STATE.timer = setTimeout(function () {
            STATE.timer = null;
            STATE.waitingPause = false;
            evaluatePressureMakeup();
        }, settings.pulsePauseS * 1000);

    }, settings.pulseOpenS * 1000);
}

function startCycle(pressureBar, settings)
{
    if (STATE.active)
        return;

    sendMakeupStarted(pressureBar);
    sendMakeupFailedRestore(pressureBar);
    openValveAndWait(settings);
}

function evaluatePressureMakeup()
{
    var settings = getSettings();
    var currentMa = readNumOrNull(CH.pressureCurrent);
    var pressureRaw = readNumOrNull(CH.pressureBar);
    var pressureBar;

    pressureBar = filterPressure(pressureRaw);
    STATE.filteredPressureBar = pressureBar;

    if (currentSensorBroken(currentMa))
    {
        resetCycleState();
        sendSensorAlarm(pressureBar, currentMa);
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    sendSensorRestore(pressureBar, currentMa);

    if (pressureBar !== null && pressureBar < settings.pressureAlarmBar)
        sendLowPressureAlarm(pressureBar);
    else if (pressureBar !== null && pressureBar >= settings.pressureMinBar)
        sendLowPressureRestore(pressureBar);

    if (!settings.enabled)
    {
        resetCycleState();
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (!settings.autoMode)
    {
        resetCycleState();
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (pressureBar === null)
    {
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (pressureBar >= settings.pressureTargetBar)
    {
        if (STATE.active)
            finishCycleSuccess(pressureBar);

        sendLowPressureRestore(pressureBar);
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (!STATE.active && pressureBar < settings.pressureMinBar)
    {
        startCycle(pressureBar, settings);
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (STATE.active && !STATE.waitingPause && !STATE.timer)
    {
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (!STATE.active)
    {
        updateStatus(pressureBar, currentMa, settings);
        return;
    }

    if (STATE.waitingPause)
    {
        if (pressureBar >= settings.pressureTargetBar)
        {
            finishCycleSuccess(pressureBar);
        }
        else if (STATE.pulseCount >= settings.maxPulses)
        {
            finishCycleFailed(pressureBar);
        }
        else
        {
            openValveAndWait(settings);
        }
    }

    updateStatus(pressureBar, currentMa, settings);
}

/*********************************************************************
 ВИРТУАЛЬНОЕ УСТРОЙСТВО
*********************************************************************/

defineVirtualDevice("pressure_makeup", {
    title: "pressure_makeup",
    cells: {
        enabled: {
            type: "switch",
            value: true
        },
        auto_mode: {
            type: "switch",
            value: true
        },
        pressure_min_bar: {
            type: "value",
            value: CFG.pressureMinBar
        },
        pressure_target_bar: {
            type: "value",
            value: CFG.pressureTargetBar
        },
        pressure_alarm_bar: {
            type: "value",
            value: CFG.pressureAlarmBar
        },
        current_break_ma: {
            type: "value",
            value: CFG.currentBreakMa
        },
        pulse_open_s: {
            type: "value",
            value: CFG.pulseOpenS
        },
        pulse_pause_s: {
            type: "value",
            value: CFG.pulsePauseS
        },
        max_pulses: {
            type: "value",
            value: CFG.maxPulses
        },

        pressure_bar: {
            type: "value",
            value: 0,
            readonly: true
        },
        pressure_current_ma: {
            type: "value",
            value: 0,
            readonly: true
        },
        valve_open: {
            type: "switch",
            value: false,
            readonly: true
        },
        active: {
            type: "switch",
            value: false,
            readonly: true
        },
        pulse_count: {
            type: "value",
            value: 0,
            readonly: true
        },
        sensor_alarm: {
            type: "switch",
            value: false,
            readonly: true
        },
        low_pressure_alarm: {
            type: "switch",
            value: false,
            readonly: true
        },
        makeup_failed_alarm: {
            type: "switch",
            value: false,
            readonly: true
        },
        status_line1: {
            type: "text",
            value: "",
            readonly: true
        },
        status_line2: {
            type: "text",
            value: "",
            readonly: true
        },
        status_line3: {
            type: "text",
            value: "",
            readonly: true
        },
        status_text: {
            type: "text",
            value: "",
            readonly: true
        }
    }
});

/*********************************************************************
 ПРАВИЛА
*********************************************************************/

defineRule("pressure_makeup_eval", {
    whenChanged: [
        CH.pressureBar,
        CH.pressureCurrent,
        "pressure_makeup/enabled",
        "pressure_makeup/auto_mode",
        "pressure_makeup/pressure_min_bar",
        "pressure_makeup/pressure_target_bar",
        "pressure_makeup/pressure_alarm_bar",
        "pressure_makeup/current_break_ma",
        "pressure_makeup/pulse_open_s",
        "pressure_makeup/pulse_pause_s",
        "pressure_makeup/max_pulses",
        CH.secBlock
    ],
    then: function () {
        evaluatePressureMakeup();
    }
});

/*********************************************************************
 СТАРТ
*********************************************************************/

setTimeout(function () {
    evaluatePressureMakeup();
    safeLog("[09_Pressure_makeup] started");
}, 3000);