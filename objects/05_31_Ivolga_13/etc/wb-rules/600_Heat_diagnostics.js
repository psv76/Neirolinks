var CH = {
    tBoilerSupply: "wb-m1w2_170/External Sensor 1",
    tBoilerReturn: "wb-m1w2_170/External Sensor 2",
    tTpDomSupply: "wb-m1w2_141/External Sensor 1",
    tTpDomReturn: "wb-m1w2_141/External Sensor 2",
    tGpDomSupply: "wb-m1w2_167/External Sensor 1",
    tGpDomReturn: "wb-m1w2_167/External Sensor 2",
    tRadDomReturn: "wb-m1w2_121/External Sensor 1",
    tGpBesSupply: "wb-m1w2_173/External Sensor 1",
    tGpBesReturn: "wb-m1w2_173/External Sensor 2",
    tRadHozReturn: "wb-m1w2_166/External Sensor 1",
    tpDomZones: ["A08/K1", "A08/K2", "A08/K3", "A08/K4", "A08/K5"],
    gpDomZones: ["A13/K1", "A13/K2", "A13/K3", "A13/K4", "A13/K5", "A13/K6", "A14/K1", "A14/K2", "A14/K3", "A14/K4"],
    radDomZones: ["A09/K1", "A09/K2", "A09/K3", "A09/K4", "A09/K5"]
};

var CFG = {
    sensorMinC: -40,
    sensorMaxC: 120
};

var SENSOR_META = [
    { path: CH.tBoilerSupply, title: "Подача котлового контура" },
    { path: CH.tBoilerReturn, title: "Обратка котлового контура" },
    { path: CH.tTpDomSupply, title: "Подача ТП дом" },
    { path: CH.tTpDomReturn, title: "Обратка ТП дом" },
    { path: CH.tGpDomSupply, title: "Подача ГП дом" },
    { path: CH.tGpDomReturn, title: "Обратка ГП дом" },
    { path: CH.tRadDomReturn, title: "Обратка радиаторов дома" },
    { path: CH.tGpBesSupply, title: "Подача ГП беседка" },
    { path: CH.tGpBesReturn, title: "Обратка ГП беседка" },
    { path: CH.tRadHozReturn, title: "Обратка радиаторов хозблока" }
];

function readNumberOrNull(path)
{
    var value = Number(dev[path]);
    if (isNaN(value))
        return null;
    return value;
}

function readBool(value)
{
    return value === true || value === 1 || value === "1" || value === "true";
}

function countActiveZones(paths)
{
    var i;
    var count = 0;

    for (i = 0; i < paths.length; i++)
    {
        if (readBool(dev[paths[i]]))
            count++;
    }

    return count;
}

function delta(supply, ret)
{
    if (supply === null || ret === null)
        return null;

    return Math.round((supply - ret) * 10) / 10;
}

function sensorInvalid(value)
{
    return value === null || value < CFG.sensorMinC || value > CFG.sensorMaxC;
}

function setCell(name, value)
{
    if (dev["heat_diagnostics/" + name] !== value)
        dev["heat_diagnostics/" + name] = value;
}

function buildStatusText(invalidSensors)
{
    if (!invalidSensors.length)
        return "Диагностика в норме";

    return "Ошибка датчиков: " + invalidSensors.join(", ");
}

function evaluateDiagnostics()
{
    var values = {};
    var invalidSensors = [];
    var i;

    for (i = 0; i < SENSOR_META.length; i++)
    {
        values[SENSOR_META[i].path] = readNumberOrNull(SENSOR_META[i].path);

        if (sensorInvalid(values[SENSOR_META[i].path]))
            invalidSensors.push(SENSOR_META[i].title);
    }

    setCell("d_boiler", delta(values[CH.tBoilerSupply], values[CH.tBoilerReturn]));
    setCell("d_tp_dom", delta(values[CH.tTpDomSupply], values[CH.tTpDomReturn]));
    setCell("d_gp_dom", delta(values[CH.tGpDomSupply], values[CH.tGpDomReturn]));
    setCell("d_gp_besedka", delta(values[CH.tGpBesSupply], values[CH.tGpBesReturn]));

    setCell("tp_dom_demand_count", countActiveZones(CH.tpDomZones));
    setCell("gp_dom_demand_count", countActiveZones(CH.gpDomZones));
    setCell("rad_dom_demand_count", countActiveZones(CH.radDomZones));
    setCell("status_text", buildStatusText(invalidSensors));
}

defineVirtualDevice("heat_diagnostics", {
    title: "Диагностика отопления",
    cells: {
        status_text: { type: "text", title: "Состояние", value: "", readonly: true },
        d_boiler: { type: "value", title: "ΔT котлового контура", value: 0, readonly: true },
        d_tp_dom: { type: "value", title: "ΔT ТП дом", value: 0, readonly: true },
        d_gp_dom: { type: "value", title: "ΔT ГП дом", value: 0, readonly: true },
        d_gp_besedka: { type: "value", title: "ΔT ГП беседка", value: 0, readonly: true },
        tp_dom_demand_count: { type: "value", title: "Открытых контуров в ТП дом", value: 0, readonly: true },
        gp_dom_demand_count: { type: "value", title: "Открытых контуров в ГП дом", value: 0, readonly: true },
        rad_dom_demand_count: { type: "value", title: "Открытых контуров радиаторов дома", value: 0, readonly: true }
    }
});

defineRule("heat_diagnostics_evaluate", {
    whenChanged: [
        CH.tBoilerSupply,
        CH.tBoilerReturn,
        CH.tTpDomSupply,
        CH.tTpDomReturn,
        CH.tGpDomSupply,
        CH.tGpDomReturn,
        CH.tRadDomReturn,
        CH.tGpBesSupply,
        CH.tGpBesReturn,
        CH.tRadHozReturn
    ].concat(CH.tpDomZones).concat(CH.gpDomZones).concat(CH.radDomZones),
    then: function () {
        evaluateDiagnostics();
    }
});

setTimeout(function () {
    evaluateDiagnostics();
}, 3000);
