/* 05_16_Iset: подтверждённые привязки и параметры Heating Manager 2.0.
 * null = контракт не подтверждён.
 * Сервоприводы радиаторов/конвекторов K1..K11 нормально открытые:
 *   0 = открыт, тепло идёт; 1 = закрыт.
 */
exports.outputsEnabled = true;
exports.otOffMethodCommissioned = true;
exports.runtime = { wbRules: "2.40.0-wb100" };

exports.ownershipMonitor = {
    commissioned: false,
    tolerance: null,
    settleSeconds: null,
    normalization: null,
    minimum: null,
    maximum: null
};

exports.allowedOutputs = {
    Heating_floor_manager: [
        "wb-mr6cu_37/K2",
        "wb-mao4_131/Channel 1 Switch",
        "wb-mao4_131/Channel 1 Dimming Level"
    ],
    Heating_basement_manager: ["wb-mr6cu_37/K3"],
    Heating_living_manager: [
        "wb-mr6cu_37/K4",
        "wb-mio-gpio_195:2/K1",
        "wb-mio-gpio_195:2/K2",
        "wb-mio-gpio_195:2/K3",
        "wb-mio-gpio_195:2/K4",
        "wb-mio-gpio_195:2/K5",
        "wb-mio-gpio_195:2/K6",
        "wb-mio-gpio_195:2/K7",
        "wb-mio-gpio_195:2/K8",
        "wb-mio-gpio_195:2/K9",
        "wb-mio-gpio_195:2/K10",
        "wb-mio-gpio_195:2/K11"
    ],
    Heating_dhw_manager: ["wb-mr6cu_37/K1"],
    Heating_ahu_manager: ["wb-mr6cu_37/K6"],
    Heating_source_manager: ["wbe2-i-opentherm_11/Heating Setpoint"]
};

exports.ttl = {
    input: 60, request: 60, outdoor: 3600, haHeartbeat: 60, startup: 60,
    recovery: 30, dhwRecovery: 60, otRecovery: 60, tick: 5, actuatorOpen: 180
};

exports.channels = {
    floor: "wb-w1/28-00000ff8a3d5",
    outdoor: "wb-w1/28-00000fd6a9ad",
    common: "wb-w1/28-00000ff8446c",
    dhw: "wb-w1/28-00000fd7811a",
    basement: "wb-w1/28-00000fdeed15",
    living: "wb-w1/28-00000ff86391",
    ot: "wbe2-i-opentherm_11/Heating Setpoint",
    connection: "wbe2-i-opentherm_11/Invalid Connection",
    fault: "wbe2-i-opentherm_11/Boiler Fault Indication",
    error: "wbe2-i-opentherm_11/Error Code",
    boiler: "wbe2-i-opentherm_11/Heating Temperature",
    pressure: "wbe2-i-opentherm_11/Water Pressure",
    flame: "wbe2-i-opentherm_11/Boiler Flame Status",
    breezartPerformance: "breezart_lux_sb_115/fan_performance",
    fire: "wb-mio-gpio_195:1/IN1"
};

exports.basementSensors = [
    "wb-msw-v4_45/Temperature",
    "wb-msw-v4_61/Temperature",
    "wb-msw-v4_202/Temperature",
    "wb-msw-v4_209/Temperature"
];

exports.basementTarget = 23;

/* HA публикует Unix timestamp каждые 20 секунд; WB TTL = 60 секунд. */
exports.haHeartbeat = "ha_heating_air/heartbeat";

/* ПВУ пока не передано под управление Heating Manager 2.0. */
exports.ahu = {
    commissioned: false,
    run: null,
    heatDemand: null,
    frost: null,
    normalSupply: null,
    frostSupply: null,
    localProtectionConfirmed: false,
    sourceUnavailablePump: null
};

exports.interlocks = {
    generator: null,
    leak: null
};

/* Тёплый пол к HA-термостатам воздуха НЕ подключён. */
exports.floorZones = [
    { water: "wb-mio-gpio_195:2/K12", demand: null },
    { water: "wb-mio-gpio_195:2/K13", demand: null },
    { water: "wb-mio-gpio_195:2/K14", demand: null },
    { water: "wb-mio-gpio_195:2/K15", demand: null },
    { water: "wb-mio-gpio_195:2/K16", demand: null }
];

/* Воздушные термостаты HA -> final demand -> NO-сервоприводы K1..K11. */
exports.livingMapConfirmed = true;

exports.livingZones = [
    {
        id: "office",
        title: "Кабинет",
        demand: "ha_heating_air/office_demand",
        outputs: ["wb-mio-gpio_195:2/K1"]
    },
    {
        id: "summer_kitchen",
        title: "Летняя кухня",
        demand: "ha_heating_air/summer_kitchen_demand",
        outputs: [
            "wb-mio-gpio_195:2/K2",
            "wb-mio-gpio_195:2/K3"
        ]
    },
    {
        id: "corridor",
        title: "Коридор",
        demand: "ha_heating_air/corridor_demand",
        outputs: ["wb-mio-gpio_195:2/K4"]
    },
    {
        id: "master_bathroom",
        title: "Мастер-санузел",
        demand: "ha_heating_air/master_bathroom_demand",
        outputs: ["wb-mio-gpio_195:2/K5"]
    },
    {
        id: "living_kitchen",
        title: "Гостиная + кухня",
        demand: "ha_heating_air/living_kitchen_demand",
        outputs: [
            "wb-mio-gpio_195:2/K6",
            "wb-mio-gpio_195:2/K7",
            "wb-mio-gpio_195:2/K9"
        ]
    },
    {
        id: "entrance",
        title: "Прихожая",
        demand: "ha_heating_air/entrance_demand",
        outputs: ["wb-mio-gpio_195:2/K8"]
    },
    {
        id: "guest_bathroom",
        title: "Гостевой санузел",
        demand: "ha_heating_air/guest_bathroom_demand",
        outputs: ["wb-mio-gpio_195:2/K10"]
    },
    {
        id: "master_bedroom",
        title: "Мастер-спальня",
        demand: "ha_heating_air/master_bedroom_demand",
        outputs: ["wb-mio-gpio_195:2/K11"]
    }
];

exports.source = {
    off: 15,
    min: 40,
    max: 82,
    frostMax: 85,
    offset: 3,
    epsilon: 0.5,
    writeInterval: 15,
    up: 3,
    down: 1,
    dhwUp: 10,
    releaseHold: 120
};

exports.dhw = {
    target: 52,
    hysteresis: 3,
    margin: 15,
    priorityMargin: 20,
    trigger: 45,
    timeout: 7200,
    relief: 900,
    overrun: 180,
    policy: "CONDITIONAL"
};

exports.response = {
    floorWindow: 600,
    floorRise: 0.5,
    dhwWindow: 900,
    dhwRise: 1,
    branchWindow: 600,
    branchRise: 2
};

/* Email_service/WBHelpers отсутствуют: сигнатуру доставки не угадываем. */
exports.emailAdapter = null;
