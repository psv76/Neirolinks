var System = require("system");
var safeLog = System.safeLog;

var CH = {
    u1: "A01/Urms L1",
    u2: "A01/Urms L2",
    u3: "A01/Urms L3",
    cross: "wb-gpio/EXT1_IN1",
    qf1: "wb-gpio/EXT1_IN2",
    qf2: "wb-gpio/EXT1_IN3",
    qf3: "wb-gpio/EXT1_IN4",
    upsStatus: "UPS1/battery_status",
    upsInputV: "UPS1/input_voltage"
};

var CFG = {
    minPhaseVoltage: 170,
    crossDelayS: 20,
    restoreDelayS: 180
};

var STATE = {
    mainPowerLost: false,
    secondaryBlocked: false,
    crossLossTimer: null,
    restoreTimer: null,
    upsAlarmActive: false
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
    if (dev["power_monitor/" + name] !== value)
        dev["power_monitor/" + name] = value;
}

function hasVillagePower()
{
    return readNumber(CH.u1, 0) >= CFG.minPhaseVoltage ||
           readNumber(CH.u2, 0) >= CFG.minPhaseVoltage ||
           readNumber(CH.u3, 0) >= CFG.minPhaseVoltage;
}

function setSecondaryBlocked(blocked)
{
    STATE.secondaryBlocked = blocked;
    setCell("secondary_alerts_blocked", blocked);
}

function cancelRestoreTimer()
{
    if (STATE.restoreTimer)
    {
        clearTimeout(STATE.restoreTimer);
        STATE.restoreTimer = null;
    }
}

function handlePowerLost(reasonText)
{
    if (STATE.mainPowerLost)
        return;

    STATE.mainPowerLost = true;
    cancelRestoreTimer();
    setSecondaryBlocked(true);

    System.sendAlert(
        "Котельная",
        "Отключено основное питание",
        reasonText,
        "Проверьте вводное питание и реле напряжения."
    );
}

function handlePowerRestore()
{
    if (!STATE.mainPowerLost)
        return;

    STATE.mainPowerLost = false;

    System.sendRestore(
        "Котельная",
        "Основное питание восстановлено",
        "Блокировка вторичных тревог будет снята после задержки.",
        ""
    );

    cancelRestoreTimer();
    STATE.restoreTimer = setTimeout(function () {
        STATE.restoreTimer = null;
        setSecondaryBlocked(false);
        safeLog("[100_power_monitor] Снята блокировка secondary_alerts_blocked");
    }, CFG.restoreDelayS * 1000);
}

function evaluateUpsStatus()
{
    var upsStatus = readNumber(CH.upsStatus, 0);

    if (upsStatus >= 2)
    {
        if (!STATE.upsAlarmActive)
        {
            STATE.upsAlarmActive = true;
            System.sendAlert(
                "Котельная",
                "Аварийный статус UPS1",
                "battery_status = " + upsStatus + ".",
                "Проверьте ИБП."
            );
        }
    }
    else if (STATE.upsAlarmActive)
    {
        STATE.upsAlarmActive = false;
        System.sendRestore(
            "Котельная",
            "UPS1 вернулся в нормальный режим",
            "battery_status = " + upsStatus + ".",
            ""
        );
    }
}

function evaluatePowerState()
{
    var mainsPresent = hasVillagePower();
    var crossPresent = readBool(dev[CH.cross]);

    if (mainsPresent && !crossPresent)
    {
        if (!STATE.crossLossTimer)
        {
            STATE.crossLossTimer = setTimeout(function () {
                STATE.crossLossTimer = null;

                if (hasVillagePower() && !readBool(dev[CH.cross]))
                    handlePowerLost("Напряжение по фазам есть, но после KV1 его нет.");

                updateStatus();
            }, CFG.crossDelayS * 1000);
        }

        return;
    }

    if (STATE.crossLossTimer)
    {
        clearTimeout(STATE.crossLossTimer);
        STATE.crossLossTimer = null;
    }

    if (!mainsPresent)
        handlePowerLost("Нет напряжения сети посёлка по фазам A01.");
    else if (!crossPresent)
        handlePowerLost("Нет напряжения на кросс-модуле после KV1.");
    else
        handlePowerRestore();
}

function updateStatus()
{
    setCell("mains_present", hasVillagePower());
    setCell("cross_present", readBool(dev[CH.cross]));
    setCell("qf1_present", readBool(dev[CH.qf1]));
    setCell("qf2_present", readBool(dev[CH.qf2]));
    setCell("qf3_present", readBool(dev[CH.qf3]));
    setCell("ups_battery_status", readNumber(CH.upsStatus, 0));
    setCell("ups_input_voltage", readNumber(CH.upsInputV, 0));
}

function evaluate()
{
    evaluatePowerState();
    evaluateUpsStatus();
    updateStatus();
}

defineVirtualDevice("power_monitor", {
    title: "Монитор питания",
    cells: {
        secondary_alerts_blocked: { type: "switch", value: false },
        mains_present: { type: "switch", value: false, readonly: true },
        cross_present: { type: "switch", value: false, readonly: true },
        qf1_present: { type: "switch", value: false, readonly: true },
        qf2_present: { type: "switch", value: false, readonly: true },
        qf3_present: { type: "switch", value: false, readonly: true },
        ups_battery_status: { type: "value", value: 0, readonly: true },
        ups_input_voltage: { type: "value", value: 0, readonly: true }
    }
});

defineRule("power_monitor_evaluate", {
    whenChanged: [
        CH.u1,
        CH.u2,
        CH.u3,
        CH.cross,
        CH.qf1,
        CH.qf2,
        CH.qf3,
        CH.upsStatus,
        CH.upsInputV
    ],
    then: function () {
        evaluate();
    }
});

setTimeout(function () {
    evaluate();
    safeLog("[100_power_monitor] Запуск");
}, 3000);
