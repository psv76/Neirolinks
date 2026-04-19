// Vilpe_control_v1.js
// Объект: 05_16_Iset
// wb-rules (ECMAScript 5)

// ============================================================
// 1. КОНФИГ
// ============================================================

var VILPE_CFG = {
  ids: {
    vdev: "vilpe_control_v1",
    vdevTitle: "Vilpe control v.1"
  },

  breezart: {
    setpoint: "breezart_lux_sb_115/setpoint_fan_performance",
    actual: "breezart_lux_sb_115/fan_performance"
  },

  vilpe: {
    enableSwitch: "wb-mao4_220/Channel 2 Switch",
    speed: "wb-mao4_220/Channel 2 Dimming Level"
  },

  humiditySensors: [
    { id: "wb-msw-v4_116/Humidity", name: "Гостиная" },
    { id: "wb-msw-v4_47/Humidity", name: "Мастер-спальня" },
    { id: "wb-msw-v4_22/Humidity", name: "Кабинет" },
    { id: "wb-msw-v4_64/Humidity", name: "Душевая сауны" },
    { id: "wb-msw-v4_53/Humidity", name: "Коридор у сауны" }
  ],

  saunaCurrents: {
    l1: "wb-map12e_35/Ch 2 Irms L1",
    l2: "wb-map12e_35/Ch 2 Irms L2",
    l3: "wb-map12e_35/Ch 2 Irms L3"
  },

  dryingChannels: {
    ch200_1: "wb-mao4_200/Channel 1 Dimming Level",
    ch200_2: "wb-mao4_200/Channel 2 Dimming Level",
    ch200_3: "wb-mao4_200/Channel 3 Dimming Level",
    ch200_4: "wb-mao4_200/Channel 4 Dimming Level",
    ch220_1: "wb-mao4_220/Channel 1 Dimming Level",
    ch220_2: "wb-mao4_220/Channel 2 Dimming Level"
  },

  defaults: {
    humidityHighThreshold: 50,
    humidityVeryHighThreshold: 60,

    normalLag: 10,
    highHumidityLag: 5,

    veryHighSetpoint: 70,
    dryingSetpoint: 90,

    dryingDurationMin: 30,

    saunaOnCurrentA: 13,
    saunaL1OffA: 2,

    dryingConfirmSec: 60,

    tickSec: 5,

    minHumiditySensorsForReliable: 2
  }
};

// ============================================================
// 2. СОСТОЯНИЕ
// ============================================================

var vilpeState = {
  startupDone: false,

  saunaWasOn: false,
  dryingActive: false,
  dryingStartedTs: 0,
  dryingUntilTs: 0,
  dryingConditionSinceTs: 0,
  dryingStopReason: "",

  lastAppliedVilpeSetpoint: null,
  lastValidBreezartSetpoint: null,

  savedLevels: {},

  lastErrorText: "",
  lastDiagText: ""
};

// ============================================================
// 3. ФУНКЦИИ ЧТЕНИЯ / НОРМАЛИЗАЦИИ / ВАЛИДАЦИИ
// ============================================================

function vcNow() {
  return new Date().getTime();
}

function vcToNumber(v) {
  if (v === undefined || v === null || v === "") return null;
  var n = Number(v);
  if (isNaN(n)) return null;
  return n;
}

function vcRound1(v) {
  return Math.round(v * 10) / 10;
}

function vcClamp(v, min, max) {
  if (v < min) return min;
  if (v > max) return max;
  return v;
}

function vcSafeText(v) {
  if (v === undefined || v === null) return "";
  return String(v);
}

function vcReadRaw(cellId) {
  return dev[cellId];
}

function vcReadNumber(cellId) {
  return vcToNumber(vcReadRaw(cellId));
}

function vcWrite(cellId, value) {
  dev[cellId] = value;
}

function vcIsPercentValid(n) {
  return n !== null && n >= 0 && n <= 100;
}

function vcReadPercent(cellId) {
  var n = vcReadNumber(cellId);
  if (n === null) return null;
  if (n < 0) return null;
  return vcClamp(n, 0, 100);
}

function vcGetSettings() {
  var s = {};

  s.humidityHighThreshold = vcReadNumber("vilpe_control_v1/humidity_high_threshold");
  if (s.humidityHighThreshold === null) s.humidityHighThreshold = VILPE_CFG.defaults.humidityHighThreshold;

  s.humidityVeryHighThreshold = vcReadNumber("vilpe_control_v1/humidity_very_high_threshold");
  if (s.humidityVeryHighThreshold === null) s.humidityVeryHighThreshold = VILPE_CFG.defaults.humidityVeryHighThreshold;

  s.normalLag = vcReadNumber("vilpe_control_v1/normal_lag");
  if (s.normalLag === null) s.normalLag = VILPE_CFG.defaults.normalLag;

  s.highHumidityLag = vcReadNumber("vilpe_control_v1/high_humidity_lag");
  if (s.highHumidityLag === null) s.highHumidityLag = VILPE_CFG.defaults.highHumidityLag;

  s.veryHighSetpoint = vcReadNumber("vilpe_control_v1/very_high_setpoint");
  if (s.veryHighSetpoint === null) s.veryHighSetpoint = VILPE_CFG.defaults.veryHighSetpoint;

  s.dryingSetpoint = vcReadNumber("vilpe_control_v1/drying_setpoint");
  if (s.dryingSetpoint === null) s.dryingSetpoint = VILPE_CFG.defaults.dryingSetpoint;

  s.dryingDurationMin = vcReadNumber("vilpe_control_v1/drying_duration_min");
  if (s.dryingDurationMin === null) s.dryingDurationMin = VILPE_CFG.defaults.dryingDurationMin;

  s.saunaOnCurrentA = vcReadNumber("vilpe_control_v1/sauna_on_current_a");
  if (s.saunaOnCurrentA === null) s.saunaOnCurrentA = VILPE_CFG.defaults.saunaOnCurrentA;

  s.saunaL1OffA = vcReadNumber("vilpe_control_v1/sauna_l1_off_a");
  if (s.saunaL1OffA === null) s.saunaL1OffA = VILPE_CFG.defaults.saunaL1OffA;

  s.dryingConfirmSec = vcReadNumber("vilpe_control_v1/drying_confirm_sec");
  if (s.dryingConfirmSec === null) s.dryingConfirmSec = VILPE_CFG.defaults.dryingConfirmSec;

  // валидация/ограничения настроек
  s.humidityHighThreshold = vcClamp(s.humidityHighThreshold, 0, 100);
  s.humidityVeryHighThreshold = vcClamp(s.humidityVeryHighThreshold, 0, 100);
  if (s.humidityVeryHighThreshold < s.humidityHighThreshold) {
    s.humidityVeryHighThreshold = s.humidityHighThreshold;
  }

  s.normalLag = vcClamp(s.normalLag, 0, 100);
  s.highHumidityLag = vcClamp(s.highHumidityLag, 0, 100);

  s.veryHighSetpoint = vcClamp(s.veryHighSetpoint, 0, 100);
  s.dryingSetpoint = vcClamp(s.dryingSetpoint, 0, 100);

  s.dryingDurationMin = vcClamp(s.dryingDurationMin, 1, 24 * 60);

  s.saunaOnCurrentA = vcClamp(s.saunaOnCurrentA, 1, 100);
  s.saunaL1OffA = vcClamp(s.saunaL1OffA, 0, 100);
  if (s.saunaL1OffA > s.saunaOnCurrentA) {
    s.saunaL1OffA = s.saunaOnCurrentA;
  }

  s.dryingConfirmSec = vcClamp(s.dryingConfirmSec, 1, 3600);

  return s;
}

function vcGetHumiditySnapshot() {
  var i;
  var sensors = [];
  var availableCount = 0;
  var unavailable = [];
  var maxHumidity = null;
  var maxHumiditySensor = "";

  for (i = 0; i < VILPE_CFG.humiditySensors.length; i++) {
    var ref = VILPE_CFG.humiditySensors[i];
    var v = vcReadNumber(ref.id);
    var ok = (v !== null && v >= 0 && v <= 100);

    sensors.push({
      id: ref.id,
      name: ref.name,
      value: v,
      ok: ok
    });

    if (ok) {
      availableCount += 1;
      if (maxHumidity === null || v > maxHumidity) {
        maxHumidity = v;
        maxHumiditySensor = ref.name;
      }
    } else {
      unavailable.push(ref.name);
    }
  }

  return {
    sensors: sensors,
    availableCount: availableCount,
    unavailable: unavailable,
    maxHumidity: maxHumidity,
    maxHumiditySensor: maxHumiditySensor
  };
}

function vcGetCurrentsSnapshot() {
  var l1 = vcReadNumber(VILPE_CFG.saunaCurrents.l1);
  var l2 = vcReadNumber(VILPE_CFG.saunaCurrents.l2);
  var l3 = vcReadNumber(VILPE_CFG.saunaCurrents.l3);

  var ok = (l1 !== null && l2 !== null && l3 !== null && l1 >= 0 && l2 >= 0 && l3 >= 0);

  return {
    l1: l1,
    l2: l2,
    l3: l3,
    ok: ok
  };
}

function vcGetBreezartSnapshot() {
  var setpoint = vcReadPercent(VILPE_CFG.breezart.setpoint);
  var actual = vcReadPercent(VILPE_CFG.breezart.actual);

  return {
    setpoint: setpoint,
    actual: actual,
    setpointOk: (setpoint !== null),
    actualOk: (actual !== null)
  };
}

function vcModeName(modeId) {
  if (modeId === "DRYING") return "Сушка сауны";
  if (modeId === "VERY_HIGH_HUMIDITY") return "Высокая влажность";
  if (modeId === "HIGH_HUMIDITY") return "Повышенная влажность";
  return "Нормальный";
}

// ============================================================
// 4. ФУНКЦИИ ДИАГНОСТИКИ
// ============================================================

function vcSetError(text) {
  vilpeState.lastErrorText = vcSafeText(text);
  vcWrite("vilpe_control_v1/last_error_text", vilpeState.lastErrorText);
}

function vcSetDiagnosticText(text) {
  vilpeState.lastDiagText = vcSafeText(text);
  vcWrite("vilpe_control_v1/diagnostic_status", vilpeState.lastDiagText);
}

function vcSetAlarm(active, text) {
  vcWrite("vilpe_control_v1/alarm_active", !!active);
  vcWrite("vilpe_control_v1/alarm_text", vcSafeText(text));
}

function vcUpdateInputAvailabilityText(hSnap, bSnap, cSnap) {
  var parts = [];
  parts.push("humidity_ok=" + hSnap.availableCount + "/" + VILPE_CFG.humiditySensors.length);
  parts.push("breezart_setpoint=" + (bSnap.setpointOk ? "ok" : "bad"));
  parts.push("breezart_actual=" + (bSnap.actualOk ? "ok" : "bad"));
  parts.push("sauna_currents=" + (cSnap.ok ? "ok" : "bad"));

  if (hSnap.unavailable.length > 0) {
    parts.push("humidity_unavailable=" + hSnap.unavailable.join(", "));
  }

  vcWrite("vilpe_control_v1/input_availability", parts.join("; "));
}

function vcApplyErrorFlags(flags) {
  vcWrite("vilpe_control_v1/input_data_error", !!flags.inputDataError);
  vcWrite("vilpe_control_v1/humidity_sensors_error", !!flags.humiditySensorsError);
  vcWrite("vilpe_control_v1/breezart_data_error", !!flags.breezartDataError);
  vcWrite("vilpe_control_v1/sauna_currents_error", !!flags.saunaCurrentsError);
  vcWrite("vilpe_control_v1/startup_diagnostics_error", !!flags.startupDiagnosticsError);
}

// ============================================================
// 5. ЛОГИКА ОПРЕДЕЛЕНИЯ РЕЖИМА
// ============================================================

function vcDetermineHumidityMode(hSnap, settings) {
  if (hSnap.availableCount === 0 || hSnap.maxHumidity === null) {
    return {
      modeId: "NORMAL",
      error: true,
      errorText: "Нет валидных данных влажности",
      maxHumidity: null,
      sourceName: ""
    };
  }

  var modeId = "NORMAL";
  if (hSnap.maxHumidity >= settings.humidityVeryHighThreshold) {
    modeId = "VERY_HIGH_HUMIDITY";
  } else if (hSnap.maxHumidity >= settings.humidityHighThreshold) {
    modeId = "HIGH_HUMIDITY";
  }

  return {
    modeId: modeId,
    error: false,
    errorText: "",
    maxHumidity: hSnap.maxHumidity,
    sourceName: hSnap.maxHumiditySensor
  };
}

function vcComputeVilpeTarget(modeId, settings, bSnap) {
  var target = null;
  var reason = "";

  if (modeId === "DRYING") {
    target = settings.dryingSetpoint;
  } else if (modeId === "VERY_HIGH_HUMIDITY") {
    target = settings.veryHighSetpoint;
  } else if (modeId === "HIGH_HUMIDITY") {
    if (!bSnap.setpointOk) {
      reason = "Нет валидной уставки Breezart для режима повышенной влажности";
      return { ok: false, target: null, reason: reason };
    }
    target = bSnap.setpoint - settings.highHumidityLag;
  } else {
    if (!bSnap.setpointOk) {
      reason = "Нет валидной уставки Breezart для нормального режима";
      return { ok: false, target: null, reason: reason };
    }
    target = bSnap.setpoint - settings.normalLag;
  }

  target = vcClamp(target, 0, 100);
  return { ok: true, target: target, reason: "" };
}

// ============================================================
// 6. ЛОГИКА СУШКИ САУНЫ
// ============================================================

function vcGetDryingManagedChannels() {
  return [
    VILPE_CFG.dryingChannels.ch200_1,
    VILPE_CFG.dryingChannels.ch200_2,
    VILPE_CFG.dryingChannels.ch200_3,
    VILPE_CFG.dryingChannels.ch200_4,
    VILPE_CFG.dryingChannels.ch220_1,
    VILPE_CFG.dryingChannels.ch220_2
  ];
}

function vcSerializeSavedLevels(levels) {
  try {
    return JSON.stringify(levels);
  } catch (e) {
    return "{}";
  }
}

function vcDeserializeSavedLevels(text) {
  if (!text) return {};
  try {
    var obj = JSON.parse(String(text));
    if (obj && typeof obj === "object") return obj;
    return {};
  } catch (e) {
    return {};
  }
}

function vcSaveLevelsBeforeDrying() {
  var arr = vcGetDryingManagedChannels();
  var i;
  var levels = {};

  for (i = 0; i < arr.length; i++) {
    var ch = arr[i];
    var val = vcReadPercent(ch);
    levels[ch] = val;
  }

  vilpeState.savedLevels = levels;
  vcWrite("vilpe_control_v1/state_saved_levels_json", vcSerializeSavedLevels(levels));
}

function vcRestoreLevelsAfterDrying() {
  var levels = vilpeState.savedLevels;
  var key;

  for (key in levels) {
    if (levels.hasOwnProperty(key)) {
      var val = vcToNumber(levels[key]);
      if (vcIsPercentValid(val)) {
        vcWrite(key, vcClamp(val, 0, 100));
      }
    }
  }
}

function vcApplyDryingLevels(settings) {
  vcWrite(VILPE_CFG.dryingChannels.ch200_1, 100);
  vcWrite(VILPE_CFG.dryingChannels.ch220_2, vcClamp(settings.dryingSetpoint, 0, 100));
  vcWrite(VILPE_CFG.dryingChannels.ch200_2, 5);
  vcWrite(VILPE_CFG.dryingChannels.ch200_3, 5);
  vcWrite(VILPE_CFG.dryingChannels.ch200_4, 5);
  vcWrite(VILPE_CFG.dryingChannels.ch220_1, 5);
}

function vcCurrentIsSaunaOn(cSnap, settings) {
  return cSnap.ok &&
    cSnap.l1 >= settings.saunaOnCurrentA &&
    cSnap.l2 >= settings.saunaOnCurrentA &&
    cSnap.l3 >= settings.saunaOnCurrentA;
}

function vcCurrentIsDryingCondition(cSnap, settings) {
  return cSnap.ok &&
    cSnap.l1 <= settings.saunaL1OffA &&
    cSnap.l2 >= settings.saunaOnCurrentA &&
    cSnap.l3 >= settings.saunaOnCurrentA;
}

function vcPersistState() {
  vcWrite("vilpe_control_v1/state_sauna_was_on", !!vilpeState.saunaWasOn);
  vcWrite("vilpe_control_v1/state_drying_active", !!vilpeState.dryingActive);
  vcWrite("vilpe_control_v1/state_drying_started_ts", vilpeState.dryingStartedTs);
  vcWrite("vilpe_control_v1/state_drying_until_ts", vilpeState.dryingUntilTs);
  vcWrite("vilpe_control_v1/state_drying_condition_since_ts", vilpeState.dryingConditionSinceTs);
}

function vcStartDrying(reasonText, settings) {
  if (vilpeState.dryingActive) return;

  vcSaveLevelsBeforeDrying();
  vcApplyDryingLevels(settings);

  var now = vcNow();
  vilpeState.dryingActive = true;
  vilpeState.dryingStartedTs = now;
  vilpeState.dryingUntilTs = now + settings.dryingDurationMin * 60 * 1000;
  vilpeState.dryingStopReason = "";

  vcWrite("vilpe_control_v1/drying_status", "Активна");
  vcWrite("vilpe_control_v1/drying_stop_reason", "");
  vcSetDiagnosticText("Запущена сушка сауны: " + vcSafeText(reasonText));

  vcPersistState();
}

function vcStopDrying(reasonText) {
  if (!vilpeState.dryingActive) return;

  vcRestoreLevelsAfterDrying();

  vilpeState.dryingActive = false;
  vilpeState.dryingStartedTs = 0;
  vilpeState.dryingUntilTs = 0;
  vilpeState.dryingConditionSinceTs = 0;
  vilpeState.saunaWasOn = false;
  vilpeState.dryingStopReason = vcSafeText(reasonText);
  vilpeState.savedLevels = {};

  vcWrite("vilpe_control_v1/state_saved_levels_json", "{}");
  vcWrite("vilpe_control_v1/drying_status", "Не активна");
  vcWrite("vilpe_control_v1/drying_stop_reason", vilpeState.dryingStopReason);

  vcPersistState();
}

function vcUpdateDryingState(cSnap, settings) {
  var now = vcNow();

  if (!cSnap.ok) {
    // Если токи пропали во время активной сушки — безопасно завершаем сушку.
    if (vilpeState.dryingActive) {
      vcStopDrying("Токи сауны недоступны во время сушки");
    }
    return;
  }

  if (vcCurrentIsSaunaOn(cSnap, settings)) {
    vilpeState.saunaWasOn = true;
  }

  var cond = vcCurrentIsDryingCondition(cSnap, settings);

  if (cond) {
    if (vilpeState.dryingConditionSinceTs === 0) {
      vilpeState.dryingConditionSinceTs = now;
    }
  } else {
    vilpeState.dryingConditionSinceTs = 0;
  }

  if (!vilpeState.dryingActive && vilpeState.saunaWasOn && cond) {
    var elapsed = now - vilpeState.dryingConditionSinceTs;
    if (elapsed >= settings.dryingConfirmSec * 1000) {
      vcStartDrying("Подтверждено условие остановки печи сауны", settings);
    }
  }

  if (vilpeState.dryingActive) {
    if (!cond) {
      vcStopDrying("Исчезло условие сушки");
      return;
    }

    if (now >= vilpeState.dryingUntilTs) {
      vcStopDrying("Завершение по таймеру");
      return;
    }
  }

  vcPersistState();
}

// ============================================================
// 7. ЛОГИКА ПРИМЕНЕНИЯ УСТАВОК
// ============================================================

function vcApplyVilpeSetpoint(target) {
  var t = vcClamp(target, 0, 100);
  vcWrite(VILPE_CFG.vilpe.speed, t);
  vcWrite(VILPE_CFG.vilpe.enableSwitch, t > 0);
  vilpeState.lastAppliedVilpeSetpoint = t;
  vcWrite("vilpe_control_v1/target_vilpe_setpoint", t);
}

function vcApplySafeBehavior() {
  if (vilpeState.lastAppliedVilpeSetpoint !== null) {
    vcApplyVilpeSetpoint(vilpeState.lastAppliedVilpeSetpoint);
  } else {
    vcApplyVilpeSetpoint(0);
  }
}

function vcUpdateTimerLeft() {
  var leftSec = 0;
  if (vilpeState.dryingActive) {
    leftSec = Math.floor((vilpeState.dryingUntilTs - vcNow()) / 1000);
    if (leftSec < 0) leftSec = 0;
  }
  vcWrite("vilpe_control_v1/drying_timer_left_sec", leftSec);
}

function vcEvaluateAndApply() {
  var settings = vcGetSettings();
  var hSnap = vcGetHumiditySnapshot();
  var cSnap = vcGetCurrentsSnapshot();
  var bSnap = vcGetBreezartSnapshot();

  var flags = {
    inputDataError: false,
    humiditySensorsError: false,
    breezartDataError: false,
    saunaCurrentsError: false,
    startupDiagnosticsError: false
  };

  var alarmActive = false;
  var alarmText = "";

  vcUpdateDryingState(cSnap, settings);

  if (!cSnap.ok) {
    flags.saunaCurrentsError = true;
    alarmActive = true;
    alarmText = "Недоступны токи сауны";
  }

  var humidityReliable = hSnap.availableCount >= VILPE_CFG.defaults.minHumiditySensorsForReliable;
  if (hSnap.unavailable.length > 0) {
    flags.humiditySensorsError = true;
  }

  if (!humidityReliable) {
    flags.inputDataError = true;
    alarmActive = true;
    alarmText = "Недостаточно валидных датчиков влажности";
  }

  if (!bSnap.setpointOk) {
    flags.breezartDataError = true;
  } else {
    vilpeState.lastValidBreezartSetpoint = bSnap.setpoint;
  }

  var humidityMode = vcDetermineHumidityMode(hSnap, settings);

  var activeMode = "NORMAL";
  if (vilpeState.dryingActive) {
    activeMode = "DRYING";
  } else if (humidityMode.modeId === "VERY_HIGH_HUMIDITY") {
    activeMode = "VERY_HIGH_HUMIDITY";
  } else if (humidityMode.modeId === "HIGH_HUMIDITY") {
    activeMode = "HIGH_HUMIDITY";
  }

  // Если влажность невалидна и нет сушки — безопасное поведение
  if (!humidityReliable && !vilpeState.dryingActive) {
    vcApplySafeBehavior();
    vcSetError("Недостаточно валидных датчиков влажности для надежного режима");
    vcSetDiagnosticText("SAFE: удержание последней уставки Vilpe");
  } else {
    var targetResult = vcComputeVilpeTarget(activeMode, settings, bSnap);
    if (targetResult.ok) {
      vcApplyVilpeSetpoint(targetResult.target);
      vcSetError("");
      vcSetDiagnosticText("Режим: " + vcModeName(activeMode));
    } else {
      flags.inputDataError = true;
      flags.breezartDataError = true;
      alarmActive = true;
      alarmText = targetResult.reason;
      vcApplySafeBehavior();
      vcSetError(targetResult.reason);
      vcSetDiagnosticText("SAFE: удержание последней уставки Vilpe из-за Breezart");
    }
  }

  vcWrite("vilpe_control_v1/active_mode", vcModeName(activeMode));
  vcWrite("vilpe_control_v1/breezart_setpoint", bSnap.setpointOk ? bSnap.setpoint : -1);
  vcWrite("vilpe_control_v1/breezart_actual", bSnap.actualOk ? bSnap.actual : -1);

  if (humidityMode.maxHumidity === null) {
    vcWrite("vilpe_control_v1/max_humidity", -1);
    vcWrite("vilpe_control_v1/max_humidity_sensor", "");
  } else {
    vcWrite("vilpe_control_v1/max_humidity", vcRound1(humidityMode.maxHumidity));
    vcWrite("vilpe_control_v1/max_humidity_sensor", humidityMode.sourceName);
  }

  vcWrite("vilpe_control_v1/current_l1", cSnap.l1 !== null ? vcRound1(cSnap.l1) : -1);
  vcWrite("vilpe_control_v1/current_l2", cSnap.l2 !== null ? vcRound1(cSnap.l2) : -1);
  vcWrite("vilpe_control_v1/current_l3", cSnap.l3 !== null ? vcRound1(cSnap.l3) : -1);

  vcWrite("vilpe_control_v1/drying_status", vilpeState.dryingActive ? "Активна" : "Не активна");
  vcWrite("vilpe_control_v1/drying_stop_reason", vilpeState.dryingStopReason);

  vcUpdateInputAvailabilityText(hSnap, bSnap, cSnap);

  if (!vilpeState.startupDone) {
    flags.startupDiagnosticsError = true;
  }

  vcApplyErrorFlags(flags);

  if (!alarmActive) {
    vcSetAlarm(false, "");
  } else {
    vcSetAlarm(true, alarmText);
  }

  vcUpdateTimerLeft();
}

// ============================================================
// 8. VIRTUAL DEVICE
// ============================================================

defineVirtualDevice(VILPE_CFG.ids.vdev, {
  title: VILPE_CFG.ids.vdevTitle,
  cells: {
    // Настройки
    humidity_high_threshold: {
      type: "range",
      value: VILPE_CFG.defaults.humidityHighThreshold,
      min: 0,
      max: 100,
      title: "Порог повышенной влажности, %",
      order: 1
    },
    humidity_very_high_threshold: {
      type: "range",
      value: VILPE_CFG.defaults.humidityVeryHighThreshold,
      min: 0,
      max: 100,
      title: "Порог высокой влажности, %",
      order: 2
    },
    normal_lag: {
      type: "range",
      value: VILPE_CFG.defaults.normalLag,
      min: 0,
      max: 100,
      title: "Отставание в норме, %",
      order: 3
    },
    high_humidity_lag: {
      type: "range",
      value: VILPE_CFG.defaults.highHumidityLag,
      min: 0,
      max: 100,
      title: "Отставание при повышенной влажности, %",
      order: 4
    },
    very_high_setpoint: {
      type: "range",
      value: VILPE_CFG.defaults.veryHighSetpoint,
      min: 0,
      max: 100,
      title: "Уставка при высокой влажности, %",
      order: 5
    },
    drying_setpoint: {
      type: "range",
      value: VILPE_CFG.defaults.dryingSetpoint,
      min: 0,
      max: 100,
      title: "Уставка при сушке, %",
      order: 6
    },
    drying_duration_min: {
      type: "value",
      value: VILPE_CFG.defaults.dryingDurationMin,
      title: "Длительность сушки, мин",
      order: 7
    },
    sauna_on_current_a: {
      type: "value",
      value: VILPE_CFG.defaults.saunaOnCurrentA,
      title: "Порог 'сауна включена', А",
      order: 8
    },
    sauna_l1_off_a: {
      type: "value",
      value: VILPE_CFG.defaults.saunaL1OffA,
      title: "Порог L1 для старта сушки, А",
      order: 9
    },
    drying_confirm_sec: {
      type: "value",
      value: VILPE_CFG.defaults.dryingConfirmSec,
      title: "Подтверждение запуска, сек",
      order: 10
    },

    // Статус
    active_mode: {
      type: "text",
      value: "",
      readonly: true,
      title: "Активный режим",
      order: 20
    },
    target_vilpe_setpoint: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Итоговая уставка Vilpe, %",
      order: 21
    },
    breezart_setpoint: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Уставка приточки Breezart, %",
      order: 22
    },
    breezart_actual: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Факт приточки Breezart, %",
      order: 23
    },
    max_humidity: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Максимальная влажность, %",
      order: 24
    },
    max_humidity_sensor: {
      type: "text",
      value: "",
      readonly: true,
      title: "Датчик, определивший режим",
      order: 25
    },
    drying_status: {
      type: "text",
      value: "Не активна",
      readonly: true,
      title: "Статус сушки сауны",
      order: 26
    },
    drying_stop_reason: {
      type: "text",
      value: "",
      readonly: true,
      title: "Причина остановки сушки",
      order: 27
    },
    diagnostic_status: {
      type: "text",
      value: "",
      readonly: true,
      title: "Диагностический статус",
      order: 28
    },
    last_error_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "Текст ошибки / последней ошибки",
      order: 29
    },
    input_availability: {
      type: "text",
      value: "",
      readonly: true,
      title: "Доступность входных данных",
      order: 30
    },
    current_l1: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L1, A",
      order: 31
    },
    current_l2: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L2, A",
      order: 32
    },
    current_l3: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L3, A",
      order: 33
    },
    drying_timer_left_sec: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Остаток таймера сушки, сек",
      order: 34
    },

    // Диагностические флаги
    alarm_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "alarm_active",
      order: 40
    },
    alarm_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "alarm_text",
      order: 41
    },
    input_data_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "input_data_error",
      order: 42
    },
    humidity_sensors_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "humidity_sensors_error",
      order: 43
    },
    breezart_data_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "breezart_data_error",
      order: 44
    },
    sauna_currents_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "sauna_currents_error",
      order: 45
    },
    startup_diagnostics_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "startup_diagnostics_error",
      order: 46
    },

    // Внутреннее состояние для восстановления после рестарта
    state_sauna_was_on: {
      type: "switch",
      value: false,
      title: "state_sauna_was_on",
      order: 90
    },
    state_drying_active: {
      type: "switch",
      value: false,
      title: "state_drying_active",
      order: 91
    },
    state_drying_started_ts: {
      type: "value",
      value: 0,
      title: "state_drying_started_ts",
      order: 92
    },
    state_drying_until_ts: {
      type: "value",
      value: 0,
      title: "state_drying_until_ts",
      order: 93
    },
    state_drying_condition_since_ts: {
      type: "value",
      value: 0,
      title: "state_drying_condition_since_ts",
      order: 94
    },
    state_saved_levels_json: {
      type: "text",
      value: "{}",
      title: "state_saved_levels_json",
      order: 95
    }
  }
});

// ============================================================
// 9. RULES / TIMERS
// ============================================================

var vcTrackedInputs = [
  VILPE_CFG.breezart.setpoint,
  VILPE_CFG.breezart.actual,

  VILPE_CFG.saunaCurrents.l1,
  VILPE_CFG.saunaCurrents.l2,
  VILPE_CFG.saunaCurrents.l3,

  VILPE_CFG.humiditySensors[0].id,
  VILPE_CFG.humiditySensors[1].id,
  VILPE_CFG.humiditySensors[2].id,
  VILPE_CFG.humiditySensors[3].id,
  VILPE_CFG.humiditySensors[4].id,

  "vilpe_control_v1/humidity_high_threshold",
  "vilpe_control_v1/humidity_very_high_threshold",
  "vilpe_control_v1/normal_lag",
  "vilpe_control_v1/high_humidity_lag",
  "vilpe_control_v1/very_high_setpoint",
  "vilpe_control_v1/drying_setpoint",
  "vilpe_control_v1/drying_duration_min",
  "vilpe_control_v1/sauna_on_current_a",
  "vilpe_control_v1/sauna_l1_off_a",
  "vilpe_control_v1/drying_confirm_sec"
];

defineRule("vilpe_control_v1_on_change", {
  whenChanged: vcTrackedInputs,
  then: function () {
    vcEvaluateAndApply();
  }
});

setInterval(function () {
  vcEvaluateAndApply();
}, VILPE_CFG.defaults.tickSec * 1000);

// ============================================================
// 10. ИНИЦИАЛИЗАЦИЯ И ДИАГНОСТИКА ПРИ СТАРТЕ
// ============================================================

function vcRestoreStateOnStartup() {
  var now = vcNow();

  vilpeState.saunaWasOn = !!dev["vilpe_control_v1/state_sauna_was_on"];
  vilpeState.dryingActive = !!dev["vilpe_control_v1/state_drying_active"];
  vilpeState.dryingStartedTs = vcToNumber(dev["vilpe_control_v1/state_drying_started_ts"]) || 0;
  vilpeState.dryingUntilTs = vcToNumber(dev["vilpe_control_v1/state_drying_until_ts"]) || 0;
  vilpeState.dryingConditionSinceTs = vcToNumber(dev["vilpe_control_v1/state_drying_condition_since_ts"]) || 0;
  vilpeState.savedLevels = vcDeserializeSavedLevels(dev["vilpe_control_v1/state_saved_levels_json"]);

  if (vilpeState.dryingActive) {
    if (vilpeState.dryingUntilTs <= now) {
      vilpeState.dryingActive = false;
      vilpeState.dryingStopReason = "Сушка сброшена при старте: таймер истек";
      vcWrite("vilpe_control_v1/drying_stop_reason", vilpeState.dryingStopReason);
    } else {
      vcWrite("vilpe_control_v1/drying_status", "Активна");
      vcApplyDryingLevels(vcGetSettings());
      vcSetDiagnosticText("Восстановлен активный режим сушки после рестарта");
    }
  }

  vcPersistState();
}

function vcStartupDiagnostics() {
  var hSnap = vcGetHumiditySnapshot();
  var cSnap = vcGetCurrentsSnapshot();
  var bSnap = vcGetBreezartSnapshot();

  var errors = [];

  if (!bSnap.setpointOk) {
    errors.push("Некорректна/недоступна уставка Breezart");
  }

  if (hSnap.availableCount < VILPE_CFG.defaults.minHumiditySensorsForReliable) {
    errors.push("Недостаточно валидных датчиков влажности при старте");
  }

  if (!cSnap.ok) {
    errors.push("Недоступны токи сауны при старте");
  }

  if (errors.length > 0) {
    vcWrite("vilpe_control_v1/startup_diagnostics_error", true);
    vcSetError(errors.join("; "));
    vcSetDiagnosticText("Ошибка стартовой диагностики");
    vcSetAlarm(true, "Стартовая диагностика: " + errors[0]);
  } else {
    vcWrite("vilpe_control_v1/startup_diagnostics_error", false);
    vcSetDiagnosticText("Стартовая диагностика: OK");
  }
}

setTimeout(function () {
  vcRestoreStateOnStartup();
  vcStartupDiagnostics();
  vilpeState.startupDone = true;
  vcEvaluateAndApply();
}, 1500);

