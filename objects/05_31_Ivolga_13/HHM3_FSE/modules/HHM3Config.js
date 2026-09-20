/* HHM 3.0 FSE — Иволга. Карта дома 09.09.2026 + Issue #59. */
exports.zones = [
    {
        "id": "601",
        "title": "ТП мастер спальня + ТП мастер гардероб",
        "sensor": "903.09_TEMP_NONE/External Sensor 1",
        "kind": "floor",
        "outputs": [
            "A08/K1",
            "A08/K4"
        ],
        "target": 26,
        "min": 18,
        "max": 26,
        "hysteresis": 1,
        "hardMax": 27,
        "circuit": "501"
    },
    {
        "id": "602",
        "title": "ТП гостевая спальня",
        "sensor": "902.11_M1W2_TEMP_NONE/External Sensor 1",
        "kind": "floor",
        "outputs": [
            "A08/K2"
        ],
        "target": 26,
        "min": 18,
        "max": 26,
        "hysteresis": 1,
        "hardMax": 27,
        "circuit": "501"
    },
    {
        "id": "603",
        "title": "ТП кабинет",
        "sensor": "902.09_M1W2_TEMP_NONE/External Sensor 1",
        "kind": "floor",
        "outputs": [
            "A08/K3"
        ],
        "target": 26,
        "min": 18,
        "max": 26,
        "hysteresis": 1,
        "hardMax": 27,
        "circuit": "501"
    },
    {
        "id": "005",
        "title": "Радиатор прихожая",
        "sensor": "902.05_MSW_THM/Temperature",
        "kind": "air",
        "outputs": [
            "A08/K5"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "006",
        "title": "Радиатор гостевая спальня",
        "sensor": "902.10_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A08/K6"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "007",
        "title": "Радиатор мастер санузел",
        "sensor": "903.05_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A09/K1"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "008",
        "title": "Радиатор кабинет",
        "sensor": "902.08_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A09/K2"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "009",
        "title": "Радиатор мастер спальня",
        "sensor": "903.08_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A09/K3"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "010",
        "title": "Радиаторы гостиная",
        "sensor": "902.01_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A09/K4",
            "A09/K5"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "503"
    },
    {
        "id": "606",
        "title": "ГП прихожая",
        "sensor": "902.06_M1W2_TEMP_NONE/External Sensor 1",
        "kind": "floor",
        "outputs": [
            "A13/K1"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "607",
        "title": "ГП санузел",
        "sensor": "902.04_M1W2_LEAK_TEMP/External Sensor 2",
        "kind": "floor",
        "outputs": [
            "A13/K2"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "608",
        "title": "ГП гардероб прихожей",
        "sensor": "902.07_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A13/K3"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "609",
        "title": "ГП ванная",
        "sensor": "902.13_M1W2_LEAK_TEMP/External Sensor 2",
        "kind": "floor",
        "outputs": [
            "A13/K4"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "610",
        "title": "ГП постирочная",
        "sensor": "902.14_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A13/K5"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "611",
        "title": "ГП гостиная",
        "sensor": "902.02_M1W2_TEMP_NONE/External Sensor 1",
        "kind": "floor",
        "outputs": [
            "A13/K6"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "612",
        "title": "ГП кухня",
        "sensor": "903.02_M1W2_LEAK_TEMP/External Sensor 2",
        "kind": "floor",
        "outputs": [
            "A14/K1"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "613",
        "title": "ГП мастер санузел",
        "sensor": "903.06_M1W2_LEAK_TEMP/External Sensor 2",
        "kind": "floor",
        "outputs": [
            "A14/K2"
        ],
        "target": 28,
        "min": 18,
        "max": 35,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "614",
        "title": "ГП кладовка",
        "sensor": "903.03_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [
            "A14/K3"
        ],
        "target": 22,
        "min": 15,
        "max": 28,
        "hysteresis": 0.3,
        "hardMax": 0,
        "circuit": "502"
    },
    {
        "id": "505",
        "title": "Радиаторы хозблока",
        "sensor": "901.01_MSW_TH/Temperature",
        "kind": "air",
        "outputs": [],
        "target": 20,
        "min": 15,
        "max": 28,
        "hysteresis": 1,
        "hardMax": 0,
        "circuit": "505"
    }
];

// Targets/timing for 501/502/503 are Ivolga starting values, to be checked at PNR.
// 562 mapping and floor-only cap are accepted by #59, not measured by this release.
var common = {
    periodMs:5000,requestTtlS:15,normalSupplyC:35,maxSupplyC:40,autonomousSupplyC:30,
    supplyCloseC:45,supplyStopC:48,supplyImmediateStopC:50,
    floorCloseC:31,floorStopC:33,floorTargetMaxC:30,supplyHysteresisC:3,floorHysteresisC:2,
    closeObserveMs:10000,coolStableMs:120000,circulationCheckMs:60000,postrunMs:120000,
    responseMs:900000,responseRiseC:1,sourceMarginC:5,
    commandTimeoutMs:10000,commandRetryMs:5000,
    floorStepPct:1,floorStepMs:60000,
    tuning:{bandC:0.5,biasC:0,farErrorC:4,fastHoldColdS:60,fastHoldHotS:30,
        fastMinStepPct:1,fastMaxStepPct:4,trimHoldColdS:90,trimHoldHotS:30,
        trimMinStepPct:1,trimMaxStepPct:2,pctPerCCold:1,pctPerCHot:2,reverseLockS:60,
        trendOkCPerMin:0.3,trendSlowCPerMin:0.05,stagnationS:600,postMoveSettleS:30,
        minPosPct:0,maxPosPct:100,hardMaxC:45,supplyValidMinC:-20,supplyValidMaxC:110,
        sensorBadLimit:1,sourceGuardEnabled:false,sourceMarginC:0,sourceValidMinC:-20,
        sourceValidMaxC:110,startupCapEnabled:true,startupDurationS:300,startupMaxPosPct:10,
        enableRetryS:30,safeCloseOnDisable:true}
};
function mixed(id, ch, supply, ret, extra) {
    var c=JSON.parse(JSON.stringify(common));
    c.id=id;c.pump='A03/K'+ch;c.level='A05/Channel '+ch+' Dimming Level';c.enable='A05/Channel '+ch+' Switch';
    c.supply=supply;c.ret=ret;c.kind='mixed';c.zoneDelayMs=id==='504'?0:180000;
    Object.keys(extra||{}).forEach(function(k){c[k]=extra[k];});return c;
}
exports.config={
    version:'3.0.0-FSE',minWbRules:'2.42.0',periodMs:5000,sensorTtlMs:120000,
    houseTopic:'/neiro/ivolga/hhm3/house/frame',houseSource:'ivolga-hhm3-house',
    eventTopic:'/neiro/ivolga/hhm3/events',requestTtlMs:15000,
    // Explicit tie ordering: incumbent house first, then gazebo/outbuilding.
    priority:['503','502','501','504','505'],
    source:{temperature:'wb-m1w2_170/External Sensor 1',setpoint:'wbe2-i-opentherm_11/Heating Setpoint',
        connection:'wbe2-i-opentherm_11/Invalid Connection',fault:'wbe2-i-opentherm_11/Boiler fault indication',
        minC:30,maxC:60,hardMaxC:75,recoverC:70,coolMs:120000,responseMs:900000,
        // unconfirmed: request remains 0, NO physical substitute setpoint.
        // After supervised PNR: setpoint_zero OR ch_enable (heating only, never DHW).
        noDemandMode:'unconfirmed',chEnable:'wbe2-i-opentherm_11/Master CH enable'},
    circuits:{
        '501':mixed('501',1,'wb-m1w2_141/External Sensor 1','wb-m1w2_141/External Sensor 2',
            {normalSupplyC:30,maxSupplyC:38,autonomousSupplyC:28,supplyCloseC:42,supplyStopC:45,supplyImmediateStopC:48,
             floorCloseC:27,floorStopC:29,floorTargetMaxC:26,floorOnlyMaxPct:0,
             valveClosedLevel:1,valveOpenLevel:100,valveClosedEnable:true,
             valveEvidence:'560: visually closed at 1/ON; hydraulic sealing not measured'}),
        '502':mixed('502',2,'wb-m1w2_167/External Sensor 1','wb-m1w2_167/External Sensor 2',
            {normalSupplyC:32,maxSupplyC:35,autonomousSupplyC:28,supplyCloseC:40,supplyStopC:43,supplyImmediateStopC:46,
             floorCloseC:38,floorStopC:40,floorTargetMaxC:35,floorOnlyMaxPct:0,
             valveClosedLevel:1,valveOpenLevel:100,valveClosedEnable:false,
             valveEvidence:'561: provisional 1/OFF; physical closure unmeasured'}),
        '503':{id:'503',kind:'direct',pump:'A03/K3',supply:'wb-m1w2_170/External Sensor 1',ret:'wb-m1w2_121/External Sensor 1',
            targetC:45,fallbackC:35,hardMaxC:75,recoverC:70,zoneDelayMs:180000},
        '504':mixed('504',3,'wb-m1w2_173/External Sensor 1','wb-m1w2_173/External Sensor 2',
            {valveClosedLevel:1,valveOpenLevel:100,valveClosedEnable:false,floorOnlyMaxPct:50,
             valveEvidence:'562: accepted 1/100/false/50; AUTO switching and physical closure require PNR'}),
        '505':{id:'505',kind:'direct',pump:'A03/K5',supply:'wb-m1w2_170/External Sensor 1',ret:'wb-m1w2_166/External Sensor 1',
            targetC:45,fallbackC:35,hardMaxC:75,recoverC:70,zoneDelayMs:0}
    }
};

exports.config.circuits['504'].pump='A03/K4';
