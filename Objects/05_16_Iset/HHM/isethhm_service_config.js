/* 05 16 Iset — as-built service channels/settings, 18.10.2026.
 * Read-only copy of CONFIRMED HM2 contracts; NOT a live release.
 * Valve/mixer protection is NOT commissioned here.
 */
exports.objectId='05_16_Iset';
exports.channels={
    floorSupply:'wb-m1w2_67/External Sensor 1',
    outdoor:'wb-m1w2_65/External Sensor 2',
    common:'wb-m1w2_65/External Sensor 1',
    dhwTank:'wb-m1w2_67/External Sensor 2',
    basementSupply:'wb-m1w2_66/External Sensor 2',
    livingSupply:'wb-m1w2_66/External Sensor 1',
    otSetpoint:'wbe2-i-opentherm_11/Heating Setpoint',
    otConnectionInvalid:'wbe2-i-opentherm_11/Invalid Connection',
    otBoilerFault:'wbe2-i-opentherm_11/Boiler Fault Indication',
    otErrorCode:'wbe2-i-opentherm_11/Error Code',
    fire:'wb-mio-gpio_195:1/IN1'
};
exports.outputs={
    dhwPump:'wb-mr6cu_12/K1',
    floorPump:'wb-mr6cu_12/K2',
    basementPump:'wb-mr6cu_12/K3',
    livingPump:'wb-mr6cu_12/K4',
    ahuPump:'wb-mr6cu_12/K6',
    floorValveEnable:'wb-mao4_131/Channel 1 Switch',
    floorValveLevel:'wb-mao4_131/Channel 1 Dimming Level',
    floorLoops:[
        'wb-mio-gpio_195:2/K12','wb-mio-gpio_195:2/K13',
        'wb-mio-gpio_195:2/K14','wb-mio-gpio_195:2/K15',
        'wb-mio-gpio_195:2/K16'
    ]
};
exports.basement={
    sensors:['wb-msw-v4_45/Temperature','wb-msw-v4_61/Temperature',
        'wb-msw-v4_202/Temperature','wb-msw-v4_209/Temperature'],
    targetC:23,hysteresisC:0.7
};
exports.dhw={
    targetC:52,hysteresisC:3,marginC:15,
    priorityMarginC:20,triggerC:45,timeoutS:7200,
    reliefS:900,overrunS:180,policy:'CONDITIONAL',
    recoveryS:60
};
exports.source={
    offC:15,minC:40,maxC:82,offsetC:3,epsilonC:0.5,
    writeIntervalS:15,upCPerMin:3,downCPerMin:1,
    dhwUpCPerMin:10,releaseHoldS:120
};
// Real HM2 AHU is NOT commissioned; keep K6 reserved for separate owner.
exports.ahu={commissioned:false};
// floor mixer physical commissioning cannot be inferred from relay feedback.
exports.floor={commissioned:false,reason:'ISSUE_194_PNR_NOT_ACCEPTED'};
