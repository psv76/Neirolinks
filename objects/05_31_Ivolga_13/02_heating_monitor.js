/*********************************************************************
 02_heating_monitor.js
 Мониторинг отопления
*********************************************************************/

var System = require("system");
var SYS = System.SYS;
var safeLog = System.safeLog;
var sendAlert = System.sendAlert;
var sendRestore = System.sendRestore;

/*********************************************************************
 КАНАЛЫ
*********************************************************************/

var CH = {
    pumpTpDom:         "A03/K1",
    pumpGpDom:         "A03/K2",
    pumpRadDom:        "A03/K3",
    pumpGpBesedka:     "A03/K4",
    pumpRadHozblock:   "A03/K5",
    pumpRecirculation: "A03/K6",

    valveTpDomPower:   "A05/Channel 1 Switch",
    valveTpDomPos:     "A05/Channel 1 Dimming Level",
    valveGpDomPower:   "A05/Channel 2 Switch",
    valveGpDomPos:     "A05/Channel 2 Dimming Level",
    valveGpBesPower:   "A05/Channel 3 Switch",
    valveGpBesPos:     "A05/Channel 3 Dimming Level",

    tBoilerSupply:     "wb-m1w2_170/External Sensor 1",
    tBoilerReturn:     "wb-m1w2_170/External Sensor 2",
    tTpDomSupply:      "wb-m1w2_141/External Sensor 1",
    tTpDomReturn:      "wb-m1w2_141/External Sensor 2",
    tGpDomSupply:      "wb-m1w2_167/External Sensor 1",
    tGpDomReturn:      "wb-m1w2_167/External Sensor 2",
    tRadDomReturn:     "wb-m1w2_121/External Sensor 1",
    tGpBesSupply:      "wb-m1w2_173/External Sensor 1",
    tGpBesReturn:      "wb-m1w2_173/External Sensor 2",
    tRadHozReturn:     "wb-m1w2_166/External Sensor 1",

    secBlock:          "power_monitor/secondary_alerts_blocked",

    tpDomZones: [
        "A08/K1",
        "A08/K2",
        "A08/K3",
        "A08/K4",
        "A08/K5"
    ],

    gpDomZones: [
        "A13/K1",
        "A13/K2",
        "A13/K3",
        "A13/K4",
        "A13/K5",
        "A13/K6",
        "A14/K1",
        "A14/K2",
        "A14/K3",
        "A14/K4"
    ],

    radDomZones: [
        "A09/K1",
        "A09/K2",
        "A09/K3",
        "A09/K4",
        "A09/K5"
    ]
};

/*********************************************************************
 НАСТРОЙКИ
*********************************************************************/

var CFG = {
    sensorMinC: -40,
    sensorMaxC: 120,
    sensorAlarmDelayS: 30
};

/*********************************************************************
 СОСТОЯНИЕ
*********************************************************************/

var STATE = {
    sensorTimers: {},
    sensorAlarm: {}
};

/*********************************************************************
 СПРАВОЧНИК ДАТЧИКОВ
*********************************************************************/

var SENSORS = [
    { key: "t_boiler_supply", path: CH.tBoilerSupply, title: "Подача от котла" },
    { key: "t_boiler_return", path: CH.tBoilerReturn, title: "Обратка в котёл" },
    { key: "t_tp_dom_supply", path: CH.tTpDomSupply, title: "Подача ТП дом" },
    { key: "t_tp_dom_return", path: CH.tTpDomReturn, title: "Обратка ТП дом" },
    { key: "t_gp_dom_supply", path: CH.tGpDomSupply, title: "Подача ГП дом" },
    { key: "t_gp_dom_return", path: CH.tGpDomReturn, title: "Обратка ГП дом" },
    { key: "t_rad_dom_return", path: CH.tRadDomReturn, title: "Обратка радиаторы дом" },
    { key: "t_gp_bes_supply", path: CH.tGpBesSupply, title: "Подача ГП беседка" },
    { key: "t_gp_bes_return", path: CH.tGpBesReturn, title: "Обратка ГП беседка" },
    { key: "t_rad_hoz_return", path: CH.tRadHozReturn, title: "Обратка радиаторы хозблок" }
];

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

function anyOn(paths)
{
    var i;

    for (i = 0; i < paths.length; i++)
    {
        if (readBool(paths[i]))
            return true;
    }

    return false;
}

function countOn(paths)
{
    var i;
    var count = 0;

    for (i = 0; i < paths.length; i++)
    {
        if (readBool(paths[i]))
            count++;
    }

    return count;
}

function round1(value)
{
    if (value === null || value === undefined || isNaN(Number(value)))
        return null;

    return Math.round(Number(value) * 10) / 10;
}

function calcDelta(supply, ret)
{
    if (supply === null || ret === null)
        return null;

    return round1(supply - ret);
}

function setCellValue(cell, value)
{
    if (dev["heating_monitor/" + cell] !== value)
        dev["heating_monitor/" + cell] = value;
}

function boolText(value)
{
    return value ? "вкл" : "выкл";
}

function fmtTemp(value)
{
    if (value === null || value === undefined)
        return "-";

    return String(round1(value)) + " °C";
}

function sensorInvalid(value)
{
    return value === null || value < CFG.sensorMinC || value > CFG.sensorMaxC;
}

function secondaryAlertsBlocked()
{
    return readBool(CH.secBlock);
}

function clearSensorTimer(key)
{
    if (STATE.sensorTimers[key])
    {
        clearTimeout(STATE.sensorTimers[key]);
        STATE.sensorTimers[key] = null;
    }
}

function sendSensorAlarm(sensor)
{
    if (secondaryAlertsBlocked())
        return;

    if (STATE.sensorAlarm[sensor.key])
        return;

    sendAlert(
        "Котельная",
        "Ошибка датчика температуры: " + sensor.title + ".",
        "Показание отсутствует или вышло за допустимый диапазон.\n" +
        "Канал: " + sensor.path + ".",
        "Проверьте датчик, подключение и модуль WB-M1W2."
    );

    STATE.sensorAlarm[sensor.key] = true;
}

function sendSensorRestore(sensor, value)
{
    if (!STATE.sensorAlarm[sensor.key])
        return;

    sendRestore(
        "Котельная",
        "Датчик температуры восстановлен: " + sensor.title + ".",
        "Текущее значение: " + fmtTemp(value) + ".\n" +
        "Канал: " + sensor.path + ".",
        ""
    );

    STATE.sensorAlarm[sensor.key] = false;
}

function checkSensor(sensor)
{
    var value = readNumOrNull(sensor.path);

    if (sensorInvalid(value))
    {
        if (!STATE.sensorTimers[sensor.key])
        {
            STATE.sensorTimers[sensor.key] = setTimeout(function () {
                STATE.sensorTimers[sensor.key] = null;

                if (sensorInvalid(readNumOrNull(sensor.path)))
                    sendSensorAlarm(sensor);
            }, CFG.sensorAlarmDelayS * 1000);
        }

        return;
    }

    clearSensorTimer(sensor.key);
    sendSensorRestore(sensor, value);
}

function evaluateSensors()
{
    var i;

    for (i = 0; i < SENSORS.length; i++)
        checkSensor(SENSORS[i]);
}

function buildStatus()
{
    var tBoilerSupply = readNumOrNull(CH.tBoilerSupply);
    var tBoilerReturn = readNumOrNull(CH.tBoilerReturn);
    var tTpDomSupply = readNumOrNull(CH.tTpDomSupply);
    var tTpDomReturn = readNumOrNull(CH.tTpDomReturn);
    var tGpDomSupply = readNumOrNull(CH.tGpDomSupply);
    var tGpDomReturn = readNumOrNull(CH.tGpDomReturn);
    var tRadDomReturn = readNumOrNull(CH.tRadDomReturn);
    var tGpBesSupply = readNumOrNull(CH.tGpBesSupply);
    var tGpBesReturn = readNumOrNull(CH.tGpBesReturn);
    var tRadHozReturn = readNumOrNull(CH.tRadHozReturn);

    var tpDomDemandCount = countOn(CH.tpDomZones);
    var gpDomDemandCount = countOn(CH.gpDomZones);
    var radDomDemandCount = countOn(CH.radDomZones);

    var tpDomDemand = tpDomDemandCount > 0;
    var gpDomDemand = gpDomDemandCount > 0;
    var radDomDemand = radDomDemandCount > 0;

    var pumpTpDom = readBool(CH.pumpTpDom);
    var pumpGpDom = readBool(CH.pumpGpDom);
    var pumpRadDom = readBool(CH.pumpRadDom);
    var pumpGpBesedka = readBool(CH.pumpGpBesedka);
    var pumpRadHozblock = readBool(CH.pumpRadHozblock);
    var pumpRecirculation = readBool(CH.pumpRecirculation);

    var valveTpDomPower = readBool(CH.valveTpDomPower);
    var valveGpDomPower = readBool(CH.valveGpDomPower);
    var valveGpBesPower = readBool(CH.valveGpBesPower);

    var valveTpDomPos = readNum(CH.valveTpDomPos, 0);
    var valveGpDomPos = readNum(CH.valveGpDomPos, 0);
    var valveGpBesPos = readNum(CH.valveGpBesPos, 0);

    var dBoiler = calcDelta(tBoilerSupply, tBoilerReturn);
    var dTpDom = calcDelta(tTpDomSupply, tTpDomReturn);
    var dGpDom = calcDelta(tGpDomSupply, tGpDomReturn);
    var dGpBes = calcDelta(tGpBesSupply, tGpBesReturn);

    var alarms = [];
    var statusLine1 = "";
    var statusLine2 = "";
    var statusLine3 = "";
    var statusText = "";

    if (sensorInvalid(tBoilerSupply) || sensorInvalid(tBoilerReturn))
        alarms.push("котловые датчики");

    if (sensorInvalid(tTpDomSupply) || sensorInvalid(tTpDomReturn))
        alarms.push("датчики ТП дом");

    if (sensorInvalid(tGpDomSupply) || sensorInvalid(tGpDomReturn))
        alarms.push("датчики ГП дом");

    if (sensorInvalid(tGpBesSupply) || sensorInvalid(tGpBesReturn))
        alarms.push("датчики ГП беседка");

    if (sensorInvalid(tRadDomReturn))
        alarms.push("датчик радиаторы дом");

    if (sensorInvalid(tRadHozReturn))
        alarms.push("датчик радиаторы хозблок");

    statusLine1 =
        "ТП дом " + tpDomDemandCount + "/" + CH.tpDomZones.length +
        ", ГП дом " + gpDomDemandCount + "/" + CH.gpDomZones.length +
        ", Радиаторы дом " + radDomDemandCount + "/" + CH.radDomZones.length;

    statusLine2 =
        "Насосы: ТП " + boolText(pumpTpDom) +
        ", ГП " + boolText(pumpGpDom) +
        ", Рад " + boolText(pumpRadDom) +
        ", Беседка " + boolText(pumpGpBesedka) +
        ", Хозблок " + boolText(pumpRadHozblock);

    statusLine3 =
        "ΔT: котёл " + (dBoiler === null ? "-" : dBoiler) +
        ", ТП " + (dTpDom === null ? "-" : dTpDom) +
        ", ГП " + (dGpDom === null ? "-" : dGpDom) +
        ", беседка " + (dGpBes === null ? "-" : dGpBes);

    if (alarms.length)
        statusText = "Есть проблемы: " + alarms.join(", ");
    else
        statusText = "Отопление в норме";

    return {
        tBoilerSupply: tBoilerSupply,
        tBoilerReturn: tBoilerReturn,
        tTpDomSupply: tTpDomSupply,
        tTpDomReturn: tTpDomReturn,
        tGpDomSupply: tGpDomSupply,
        tGpDomReturn: tGpDomReturn,
        tRadDomReturn: tRadDomReturn,
        tGpBesSupply: tGpBesSupply,
        tGpBesReturn: tGpBesReturn,
        tRadHozReturn: tRadHozReturn,

        tpDomDemandCount: tpDomDemandCount,
        gpDomDemandCount: gpDomDemandCount,
        radDomDemandCount: radDomDemandCount,

        tpDomDemand: tpDomDemand,
        gpDomDemand: gpDomDemand,
        radDomDemand: radDomDemand,

        pumpTpDom: pumpTpDom,
        pumpGpDom: pumpGpDom,
        pumpRadDom: pumpRadDom,
        pumpGpBesedka: pumpGpBesedka,
        pumpRadHozblock: pumpRadHozblock,
        pumpRecirculation: pumpRecirculation,

        valveTpDomPower: valveTpDomPower,
        valveGpDomPower: valveGpDomPower,
        valveGpBesPower: valveGpBesPower,

        valveTpDomPos: valveTpDomPos,
        valveGpDomPos: valveGpDomPos,
        valveGpBesPos: valveGpBesPos,

        dBoiler: dBoiler,
        dTpDom: dTpDom,
        dGpDom: dGpDom,
        dGpBes: dGpBes,

        statusLine1: statusLine1,
        statusLine2: statusLine2,
        statusLine3: statusLine3,
        statusText: statusText
    };
}

function updateVirtualStatus(data)
{
    setCellValue("t_boiler_supply", round1(data.tBoilerSupply));
    setCellValue("t_boiler_return", round1(data.tBoilerReturn));
    setCellValue("t_tp_dom_supply", round1(data.tTpDomSupply));
    setCellValue("t_tp_dom_return", round1(data.tTpDomReturn));
    setCellValue("t_gp_dom_supply", round1(data.tGpDomSupply));
    setCellValue("t_gp_dom_return", round1(data.tGpDomReturn));
    setCellValue("t_rad_dom_return", round1(data.tRadDomReturn));
    setCellValue("t_gp_bes_supply", round1(data.tGpBesSupply));
    setCellValue("t_gp_bes_return", round1(data.tGpBesReturn));
    setCellValue("t_rad_hoz_return", round1(data.tRadHozReturn));

    setCellValue("d_boiler", data.dBoiler);
    setCellValue("d_tp_dom", data.dTpDom);
    setCellValue("d_gp_dom", data.dGpDom);
    setCellValue("d_gp_besedka", data.dGpBes);

    setCellValue("tp_dom_demand", data.tpDomDemand);
    setCellValue("gp_dom_demand", data.gpDomDemand);
    setCellValue("rad_dom_demand", data.radDomDemand);

    setCellValue("tp_dom_demand_count", data.tpDomDemandCount);
    setCellValue("gp_dom_demand_count", data.gpDomDemandCount);
    setCellValue("rad_dom_demand_count", data.radDomDemandCount);

    setCellValue("pump_tp_dom", data.pumpTpDom);
    setCellValue("pump_gp_dom", data.pumpGpDom);
    setCellValue("pump_rad_dom", data.pumpRadDom);
    setCellValue("pump_gp_besedka", data.pumpGpBesedka);
    setCellValue("pump_rad_hozblock", data.pumpRadHozblock);
    setCellValue("pump_recirculation", data.pumpRecirculation);

    setCellValue("valve_tp_dom_power", data.valveTpDomPower);
    setCellValue("valve_gp_dom_power", data.valveGpDomPower);
    setCellValue("valve_gp_bes_power", data.valveGpBesPower);

    setCellValue("valve_tp_dom_pos", round1(data.valveTpDomPos));
    setCellValue("valve_gp_dom_pos", round1(data.valveGpDomPos));
    setCellValue("valve_gp_bes_pos", round1(data.valveGpBesPos));

    setCellValue("status_line1", data.statusLine1);
    setCellValue("status_line2", data.statusLine2);
    setCellValue("status_line3", data.statusLine3);
    setCellValue("status_text", data.statusText);
}

function evaluateHeatingMonitor()
{
    var data = buildStatus();

    updateVirtualStatus(data);
    evaluateSensors();
}

/*********************************************************************
 ВИРТУАЛЬНОЕ УСТРОЙСТВО
*********************************************************************/

defineVirtualDevice("heating_monitor", {
    title: "heating_monitor",
    cells: {
        t_boiler_supply:      { type: "value", value: 0, readonly: true },
        t_boiler_return:      { type: "value", value: 0, readonly: true },
        t_tp_dom_supply:      { type: "value", value: 0, readonly: true },
        t_tp_dom_return:      { type: "value", value: 0, readonly: true },
        t_gp_dom_supply:      { type: "value", value: 0, readonly: true },
        t_gp_dom_return:      { type: "value", value: 0, readonly: true },
        t_rad_dom_return:     { type: "value", value: 0, readonly: true },
        t_gp_bes_supply:      { type: "value", value: 0, readonly: true },
        t_gp_bes_return:      { type: "value", value: 0, readonly: true },
        t_rad_hoz_return:     { type: "value", value: 0, readonly: true },

        d_boiler:             { type: "value", value: 0, readonly: true },
        d_tp_dom:             { type: "value", value: 0, readonly: true },
        d_gp_dom:             { type: "value", value: 0, readonly: true },
        d_gp_besedka:         { type: "value", value: 0, readonly: true },

        tp_dom_demand:        { type: "switch", value: false, readonly: true },
        gp_dom_demand:        { type: "switch", value: false, readonly: true },
        rad_dom_demand:       { type: "switch", value: false, readonly: true },

        tp_dom_demand_count:  { type: "value", value: 0, readonly: true },
        gp_dom_demand_count:  { type: "value", value: 0, readonly: true },
        rad_dom_demand_count: { type: "value", value: 0, readonly: true },

        pump_tp_dom:          { type: "switch", value: false, readonly: true },
        pump_gp_dom:          { type: "switch", value: false, readonly: true },
        pump_rad_dom:         { type: "switch", value: false, readonly: true },
        pump_gp_besedka:      { type: "switch", value: false, readonly: true },
        pump_rad_hozblock:    { type: "switch", value: false, readonly: true },
        pump_recirculation:   { type: "switch", value: false, readonly: true },

        valve_tp_dom_power:   { type: "switch", value: false, readonly: true },
        valve_gp_dom_power:   { type: "switch", value: false, readonly: true },
        valve_gp_bes_power:   { type: "switch", value: false, readonly: true },

        valve_tp_dom_pos:     { type: "value", value: 0, readonly: true },
        valve_gp_dom_pos:     { type: "value", value: 0, readonly: true },
        valve_gp_bes_pos:     { type: "value", value: 0, readonly: true },

        status_line1:         { type: "text", value: "", readonly: true },
        status_line2:         { type: "text", value: "", readonly: true },
        status_line3:         { type: "text", value: "", readonly: true },
        status_text:          { type: "text", value: "", readonly: true }
    }
});

/*********************************************************************
 ПРАВИЛА
*********************************************************************/

defineRule("heating_monitor_eval", {
    whenChanged: [
        CH.pumpTpDom,
        CH.pumpGpDom,
        CH.pumpRadDom,
        CH.pumpGpBesedka,
        CH.pumpRadHozblock,
        CH.pumpRecirculation,

        CH.valveTpDomPower,
        CH.valveTpDomPos,
        CH.valveGpDomPower,
        CH.valveGpDomPos,
        CH.valveGpBesPower,
        CH.valveGpBesPos,

        CH.tBoilerSupply,
        CH.tBoilerReturn,
        CH.tTpDomSupply,
        CH.tTpDomReturn,
        CH.tGpDomSupply,
        CH.tGpDomReturn,
        CH.tRadDomReturn,
        CH.tGpBesSupply,
        CH.tGpBesReturn,
        CH.tRadHozReturn,

        CH.tpDomZones[0],
        CH.tpDomZones[1],
        CH.tpDomZones[2],
        CH.tpDomZones[3],
        CH.tpDomZones[4],

        CH.gpDomZones[0],
        CH.gpDomZones[1],
        CH.gpDomZones[2],
        CH.gpDomZones[3],
        CH.gpDomZones[4],
        CH.gpDomZones[5],
        CH.gpDomZones[6],
        CH.gpDomZones[7],
        CH.gpDomZones[8],
        CH.gpDomZones[9],

        CH.radDomZones[0],
        CH.radDomZones[1],
        CH.radDomZones[2],
        CH.radDomZones[3],
        CH.radDomZones[4],

        CH.secBlock
    ],
    then: function () {
        evaluateHeatingMonitor();
    }
});

/*********************************************************************
 СТАРТ
*********************************************************************/

setTimeout(function () {
    evaluateHeatingMonitor();
    safeLog("[02_heating_monitor] started");
}, 3000);