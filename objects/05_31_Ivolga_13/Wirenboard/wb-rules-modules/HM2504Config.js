/* Иволга 504, контракт v1.0. Только объектные параметры, не настройки Исети.
 * null — конкретные измерения 562, которые необходимо внести после ПНР.
 * Тайминги и tuning ниже — стартовые инженерные предложения для стенда/ПНР.
 */
exports.config = {
    periodMs: 5000, requestTtlS: 15,
    normalSupplyC: 35, maxSupplyC: 40, autonomousSupplyC: 30,
    supplyCloseC: 45, supplyStopC: 48, supplyImmediateStopC: 50,
    floorCloseC: 31, floorStopC: 33, floorTargetMaxC: 30,
    supplyHysteresisC: 3, floorHysteresisC: 2,
    closeObserveMs: 10000, coolStableMs: 120000, circulationCheckMs: 60000,
    postrunMs: 120000, responseMs: 900000, responseRiseC: 1,
    sourceMarginC: 5,
    // Measured Level at fully closed/open hot port; Switch needed to hold closed.
    valveClosedLevel: null, valveOpenLevel: null, valveClosedEnable: null,
    // Measured safe opening cap under hot source in floor-only mode, percent hot port.
    floorOnlyMaxPct: null,
    floorStepPct: 1, floorStepMs: 60000,
    tuning: {
        bandC: 0.5, biasC: 0, farErrorC: 4,
        fastHoldColdS: 60, fastHoldHotS: 30, fastMinStepPct: 1, fastMaxStepPct: 4,
        trimHoldColdS: 90, trimHoldHotS: 30, trimMinStepPct: 1, trimMaxStepPct: 2,
        pctPerCCold: 1, pctPerCHot: 2, reverseLockS: 60,
        trendOkCPerMin: 0.3, trendSlowCPerMin: 0.05, stagnationS: 600,
        postMoveSettleS: 30, minPosPct: 0, maxPosPct: 100,
        hardMaxC: 45, supplyValidMinC: -20, supplyValidMaxC: 110,
        sensorBadLimit: 1, sourceGuardEnabled: false, sourceMarginC: 0,
        sourceValidMinC: -20, sourceValidMaxC: 110,
        startupCapEnabled: true, startupDurationS: 300, startupMaxPosPct: 10,
        enableRetryS: 30, safeCloseOnDisable: true
    }
};
