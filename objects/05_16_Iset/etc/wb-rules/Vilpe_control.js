// ============================================================
// 1. КОНФИГ
// ============================================================

var VC2_CFG = {
  ids: {
    userVdev: "vilpe_control_v3",
    userTitle: "Управление вытяжкой Vilpe v.3",
    serviceVdev: "vilpe_control_v3_service",
    serviceTitle: "Сервис Vilpe / HA и диагностика"
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

  // Координируемые каналы сушки.
  // По умолчанию скрипт работает как координатор сценария сушки для всех вытяжных линий ниже.
  dryingChannels: {
    ch200_1: "wb-mao4_200/Channel 1 Dimming Level",
    ch200_2: "wb-mao4_200/Channel 2 Dimming Level",
    ch200_3: "wb-mao4_200/Channel 3 Dimming Level",
    ch200_4: "wb-mao4_200/Channel 4 Dimming Level",
    ch220_1: "wb-mao4_220/Channel 1 Dimming Level",
    ch220_2: "wb-mao4_220/Channel 2 Dimming Level"
  },

  defaults: {
    humidityHighEnter: 50,
    humidityHighExitDelta: 2,
    humidityVeryHighEnter: 60,
    humidityVeryHighExitDelta: 2,

    normalLag: 10,
    highHumidityLag: 5,

    veryHighSetpoint: 70,
    dryingSetpoint: 90,

    dryingDurationMin: 30,

    saunaOnCurrentA: 13,
    saunaL1OffA: 2,
    dryingConfirmSec: 60,

    // Допуск по отсутствию токов: краткие провалы не останавливают сушку.
    currentsLossGraceSec: 180,

    tickSec: 5,
    minHumiditySensorsForReliable: 2,

    // Координация дополнительных каналов сушки (кроме канала Vilpe).
    coordinatorEnabled: true
  }
};

// ============================================================
// 2. СОСТОЯНИЕ
// ============================================================

var vc2State = {
  startupDone: false,

  humidityModeStable: "NORMAL",

  saunaWasOn: false,
  dryingActive: false,
  dryingStartedTs: 0,
  dryingUntilTs: 0,
  dryingConditionSinceTs: 0,
  dryingStopReason: "",
  currentsMissingSinceTs: 0,

  lastAppliedVilpeSetpoint: null,
  lastValidBreezartSetpoint: null,

  savedLevels: {},

  lastErrorText: "",
  lastDiagText: "",
  startupDiagnosticsError: false
};

// ============================================================
// 3. ФУНКЦИИ ЧТЕНИЯ / НОРМАЛИЗАЦИИ / ВАЛИДАЦИИ
// ============================================================

function vc2Now() {
  return new Date().getTime();
}

function vc2ToNumber(v) {
  if (v === undefined || v === null || v === "") return null;
  var n = Number(v);
  if (isNaN(n)) return null;
  return n;
}

function vc2Round1(v) {
  return Math.round(v * 10) / 10;
}

function vc2Clamp(v, min, max) {
  if (v < min) return min;
  if (v > max) return max;
  return v;
}

function vc2SafeText(v) {
  if (v === undefined || v === null) return "";
  return String(v);
}

function vc2ReadRaw(cellId) {
  return dev[cellId];
}

function vc2ReadNumber(cellId) {
  return vc2ToNumber(vc2ReadRaw(cellId));
}

function vc2Write(cellId, value) {
  dev[cellId] = value;
}

function vc2ReadPercent(cellId) {
  var n = vc2ReadNumber(cellId);
  if (n === null || n < 0) return null;
  return vc2Clamp(n, 0, 100);
}

function vc2IsPercentValid(v) {
  return v !== null && v >= 0 && v <= 100;
}

function vc2ModeName(modeId) {
  if (modeId === "DRYING") return "Сушка сауны";
  if (modeId === "VERY_HIGH_HUMIDITY") return "Высокая влажность";
  if (modeId === "HIGH_HUMIDITY") return "Повышенная влажность";
  return "Нормальный";
}

function vc2ServiceCell(name) {
  return VC2_CFG.ids.serviceVdev + "/" + name;
}

function vc2UserCell(name) {
  return VC2_CFG.ids.userVdev + "/" + name;
}

function vc2GetSettings() {
  var s = {};

  s.humidityHighEnter = vc2ReadNumber(vc2UserCell("humidity_high_enter"));
  if (s.humidityHighEnter === null) s.humidityHighEnter = VC2_CFG.defaults.humidityHighEnter;

  s.humidityHighExitDelta = vc2ReadNumber(vc2UserCell("humidity_high_exit_delta"));
  if (s.humidityHighExitDelta === null) s.humidityHighExitDelta = VC2_CFG.defaults.humidityHighExitDelta;

  s.humidityVeryHighEnter = vc2ReadNumber(vc2UserCell("humidity_very_high_enter"));
  if (s.humidityVeryHighEnter === null) s.humidityVeryHighEnter = VC2_CFG.defaults.humidityVeryHighEnter;

  s.humidityVeryHighExitDelta = vc2ReadNumber(vc2UserCell("humidity_very_high_exit_delta"));
  if (s.humidityVeryHighExitDelta === null) s.humidityVeryHighExitDelta = VC2_CFG.defaults.humidityVeryHighExitDelta;

  s.normalLag = vc2ReadNumber(vc2UserCell("normal_lag"));
  if (s.normalLag === null) s.normalLag = VC2_CFG.defaults.normalLag;

  s.highHumidityLag = vc2ReadNumber(vc2UserCell("high_humidity_lag"));
  if (s.highHumidityLag === null) s.highHumidityLag = VC2_CFG.defaults.highHumidityLag;

  s.veryHighSetpoint = vc2ReadNumber(vc2UserCell("very_high_setpoint"));
  if (s.veryHighSetpoint === null) s.veryHighSetpoint = VC2_CFG.defaults.veryHighSetpoint;

  s.dryingSetpoint = vc2ReadNumber(vc2UserCell("drying_setpoint"));
  if (s.dryingSetpoint === null) s.dryingSetpoint = VC2_CFG.defaults.dryingSetpoint;

  s.dryingDurationMin = vc2ReadNumber(vc2UserCell("drying_duration_min"));
  if (s.dryingDurationMin === null) s.dryingDurationMin = VC2_CFG.defaults.dryingDurationMin;

  s.saunaOnCurrentA = vc2ReadNumber(vc2UserCell("sauna_on_current_a"));
  if (s.saunaOnCurrentA === null) s.saunaOnCurrentA = VC2_CFG.defaults.saunaOnCurrentA;

  s.saunaL1OffA = vc2ReadNumber(vc2UserCell("sauna_l1_off_a"));
  if (s.saunaL1OffA === null) s.saunaL1OffA = VC2_CFG.defaults.saunaL1OffA;

  s.dryingConfirmSec = vc2ReadNumber(vc2UserCell("drying_confirm_sec"));
  if (s.dryingConfirmSec === null) s.dryingConfirmSec = VC2_CFG.defaults.dryingConfirmSec;

  s.currentsLossGraceSec = vc2ReadNumber(vc2UserCell("currents_loss_grace_sec"));
  if (s.currentsLossGraceSec === null) s.currentsLossGraceSec = VC2_CFG.defaults.currentsLossGraceSec;

  s.coordinatorEnabled = !!vc2ReadRaw(vc2UserCell("coordinator_enabled"));

  s.humidityHighEnter = vc2Clamp(s.humidityHighEnter, 0, 100);
  s.humidityHighExitDelta = vc2Clamp(s.humidityHighExitDelta, 0, 20);

  s.humidityVeryHighEnter = vc2Clamp(s.humidityVeryHighEnter, 0, 100);
  s.humidityVeryHighExitDelta = vc2Clamp(s.humidityVeryHighExitDelta, 0, 20);

  if (s.humidityVeryHighEnter < s.humidityHighEnter) s.humidityVeryHighEnter = s.humidityHighEnter;

  s.normalLag = vc2Clamp(s.normalLag, 0, 100);
  s.highHumidityLag = vc2Clamp(s.highHumidityLag, 0, 100);

  s.veryHighSetpoint = vc2Clamp(s.veryHighSetpoint, 0, 100);
  s.dryingSetpoint = vc2Clamp(s.dryingSetpoint, 0, 100);

  s.dryingDurationMin = vc2Clamp(s.dryingDurationMin, 1, 24 * 60);

  s.saunaOnCurrentA = vc2Clamp(s.saunaOnCurrentA, 1, 100);
  s.saunaL1OffA = vc2Clamp(s.saunaL1OffA, 0, 100);
  if (s.saunaL1OffA > s.saunaOnCurrentA) s.saunaL1OffA = s.saunaOnCurrentA;

  s.dryingConfirmSec = vc2Clamp(s.dryingConfirmSec, 1, 3600);
  s.currentsLossGraceSec = vc2Clamp(s.currentsLossGraceSec, 0, 3600);

  s.humidityHighExit = vc2Clamp(s.humidityHighEnter - s.humidityHighExitDelta, 0, 100);
  s.humidityVeryHighExit = vc2Clamp(s.humidityVeryHighEnter - s.humidityVeryHighExitDelta, 0, 100);

  if (s.humidityVeryHighExit < s.humidityHighExit) {
    s.humidityVeryHighExit = s.humidityHighExit;
  }

  return s;
}

function vc2GetHumiditySnapshot() {
  var sensors = [];
  var unavailable = [];
  var availableCount = 0;
  var maxHumidity = null;
  var maxHumiditySensor = "";
  var i;

  for (i = 0; i < VC2_CFG.humiditySensors.length; i++) {
    var ref = VC2_CFG.humiditySensors[i];
    var value = vc2ReadNumber(ref.id);
    var ok = (value !== null && value >= 0 && value <= 100);

    sensors.push({ id: ref.id, name: ref.name, value: value, ok: ok });

    if (ok) {
      availableCount += 1;
      if (maxHumidity === null || value > maxHumidity) {
        maxHumidity = value;
        maxHumiditySensor = ref.name;
      }
    } else {
      unavailable.push(ref.name);
    }
  }

  return {
    sensors: sensors,
    unavailable: unavailable,
    availableCount: availableCount,
    maxHumidity: maxHumidity,
    maxHumiditySensor: maxHumiditySensor
  };
}

function vc2GetCurrentsSnapshot() {
  var l1 = vc2ReadNumber(VC2_CFG.saunaCurrents.l1);
  var l2 = vc2ReadNumber(VC2_CFG.saunaCurrents.l2);
  var l3 = vc2ReadNumber(VC2_CFG.saunaCurrents.l3);

  var ok = (l1 !== null && l2 !== null && l3 !== null && l1 >= 0 && l2 >= 0 && l3 >= 0);

  return {
    l1: l1,
    l2: l2,
    l3: l3,
    ok: ok
  };
}

function vc2GetBreezartSnapshot() {
  var setpoint = vc2ReadPercent(VC2_CFG.breezart.setpoint);
  var actual = vc2ReadPercent(VC2_CFG.breezart.actual);

  return {
    setpoint: setpoint,
    actual: actual,
    setpointOk: setpoint !== null,
    actualOk: actual !== null
  };
}

// ============================================================
// 4. ФУНКЦИИ ОПРЕДЕЛЕНИЯ РЕЖИМА (влажность + антидребезг)
// ============================================================

function vc2DetermineHumidityMode(hSnap, settings) {
  if (hSnap.availableCount === 0 || hSnap.maxHumidity === null) {
    return {
      modeId: vc2State.humidityModeStable,
      reliable: false,
      sourceName: "",
      maxHumidity: null
    };
  }

  var prev = vc2State.humidityModeStable;
  var maxH = hSnap.maxHumidity;
  var next = prev;

  if (prev === "VERY_HIGH_HUMIDITY") {
    if (maxH < settings.humidityVeryHighExit) {
      if (maxH >= settings.humidityHighEnter) {
        next = "HIGH_HUMIDITY";
      } else {
        next = "NORMAL";
      }
    }
  } else if (prev === "HIGH_HUMIDITY") {
    if (maxH >= settings.humidityVeryHighEnter) {
      next = "VERY_HIGH_HUMIDITY";
    } else if (maxH < settings.humidityHighExit) {
      next = "NORMAL";
    }
  } else {
    if (maxH >= settings.humidityVeryHighEnter) {
      next = "VERY_HIGH_HUMIDITY";
    } else if (maxH >= settings.humidityHighEnter) {
      next = "HIGH_HUMIDITY";
    } else {
      next = "NORMAL";
    }
  }

  vc2State.humidityModeStable = next;

  return {
    modeId: next,
    reliable: true,
    sourceName: hSnap.maxHumiditySensor,
    maxHumidity: maxH
  };
}

function vc2ComputeVilpeTarget(activeMode, settings, bSnap) {
  var target = null;
  var reason = "";

  if (activeMode === "DRYING") {
    target = settings.dryingSetpoint;
  } else if (activeMode === "VERY_HIGH_HUMIDITY") {
    target = settings.veryHighSetpoint;
  } else if (activeMode === "HIGH_HUMIDITY") {
    if (!bSnap.setpointOk) {
      reason = "Нет уставки Breezart для режима повышенной влажности";
      return { ok: false, target: null, reason: reason };
    }
    target = bSnap.setpoint - settings.highHumidityLag;
  } else {
    if (!bSnap.setpointOk) {
      reason = "Нет уставки Breezart для нормального режима";
      return { ok: false, target: null, reason: reason };
    }
    target = bSnap.setpoint - settings.normalLag;
  }

  return {
    ok: true,
    target: vc2Clamp(target, 0, 100),
    reason: ""
  };
}

// ============================================================
// 5. ЛОГИКА СУШКИ САУНЫ
// ============================================================

function vc2CurrentIsSaunaOn(cSnap, settings) {
  return cSnap.ok &&
    cSnap.l1 >= settings.saunaOnCurrentA &&
    cSnap.l2 >= settings.saunaOnCurrentA &&
    cSnap.l3 >= settings.saunaOnCurrentA;
}

function vc2CurrentIsDryingCondition(cSnap, settings) {
  return cSnap.ok &&
    cSnap.l1 <= settings.saunaL1OffA &&
    cSnap.l2 >= settings.saunaOnCurrentA &&
    cSnap.l3 >= settings.saunaOnCurrentA;
}

function vc2GetManagedChannels(settings) {
  var arr = [VC2_CFG.vilpe.speed];

  if (!settings.coordinatorEnabled) {
    return arr;
  }

  arr.push(VC2_CFG.dryingChannels.ch200_1);
  arr.push(VC2_CFG.dryingChannels.ch200_2);
  arr.push(VC2_CFG.dryingChannels.ch200_3);
  arr.push(VC2_CFG.dryingChannels.ch200_4);
  arr.push(VC2_CFG.dryingChannels.ch220_1);

  return arr;
}

function vc2SerializeSavedLevels(levels) {
  try {
    return JSON.stringify(levels);
  } catch (e) {
    return "{}";
  }
}

function vc2DeserializeSavedLevels(text) {
  if (!text) return {};
  try {
    var obj = JSON.parse(String(text));
    if (obj && typeof obj === "object") return obj;
    return {};
  } catch (e) {
    return {};
  }
}

function vc2SaveLevelsBeforeDrying(settings) {
  var channels = vc2GetManagedChannels(settings);
  var i;
  var levels = {};

  for (i = 0; i < channels.length; i++) {
    levels[channels[i]] = vc2ReadPercent(channels[i]);
  }

  vc2State.savedLevels = levels;
  vc2Write(vc2ServiceCell("state_saved_levels_json"), vc2SerializeSavedLevels(levels));
}

function vc2RestoreLevelsAfterDrying() {
  var key;
  for (key in vc2State.savedLevels) {
    if (vc2State.savedLevels.hasOwnProperty(key)) {
      var v = vc2ToNumber(vc2State.savedLevels[key]);
      if (vc2IsPercentValid(v)) {
        vc2Write(key, vc2Clamp(v, 0, 100));
      }
    }
  }
}

function vc2ApplyDryingLevels(settings) {
  vc2Write(VC2_CFG.vilpe.speed, vc2Clamp(settings.dryingSetpoint, 0, 100));
  vc2Write(VC2_CFG.vilpe.enableSwitch, settings.dryingSetpoint > 0);

  if (!settings.coordinatorEnabled) {
    return;
  }

  vc2Write(VC2_CFG.dryingChannels.ch200_1, 100);
  vc2Write(VC2_CFG.dryingChannels.ch200_2, 5);
  vc2Write(VC2_CFG.dryingChannels.ch200_3, 5);
  vc2Write(VC2_CFG.dryingChannels.ch200_4, 5);
  vc2Write(VC2_CFG.dryingChannels.ch220_1, 5);
}

function vc2PersistState() {
  vc2Write(vc2ServiceCell("state_sauna_was_on"), !!vc2State.saunaWasOn);
  vc2Write(vc2ServiceCell("state_drying_active"), !!vc2State.dryingActive);
  vc2Write(vc2ServiceCell("state_drying_started_ts"), vc2State.dryingStartedTs);
  vc2Write(vc2ServiceCell("state_drying_until_ts"), vc2State.dryingUntilTs);
  vc2Write(vc2ServiceCell("state_drying_condition_since_ts"), vc2State.dryingConditionSinceTs);
  vc2Write(vc2ServiceCell("state_currents_missing_since_ts"), vc2State.currentsMissingSinceTs);
  vc2Write(vc2ServiceCell("state_humidity_mode_stable"), vc2State.humidityModeStable);
  vc2Write(vc2ServiceCell("state_last_applied_vilpe_setpoint"), vc2State.lastAppliedVilpeSetpoint === null ? -1 : vc2State.lastAppliedVilpeSetpoint);
}

function vc2StartDrying(reasonText, settings) {
  if (vc2State.dryingActive) return;

  vc2SaveLevelsBeforeDrying(settings);
  vc2ApplyDryingLevels(settings);

  var now = vc2Now();
  vc2State.dryingActive = true;
  vc2State.dryingStartedTs = now;
  vc2State.dryingUntilTs = now + settings.dryingDurationMin * 60 * 1000;
  vc2State.dryingStopReason = "";
  vc2State.currentsMissingSinceTs = 0;

  vc2Write(vc2UserCell("drying_status"), "Активна");
  vc2Write(vc2UserCell("drying_stop_reason"), "");
  vc2Write(vc2ServiceCell("event_text"), "Запущена сушка: " + vc2SafeText(reasonText));

  vc2PersistState();
}

function vc2StopDrying(reasonText) {
  if (!vc2State.dryingActive) return;

  vc2RestoreLevelsAfterDrying();

  vc2State.dryingActive = false;
  vc2State.dryingStartedTs = 0;
  vc2State.dryingUntilTs = 0;
  vc2State.dryingConditionSinceTs = 0;
  vc2State.saunaWasOn = false;
  vc2State.currentsMissingSinceTs = 0;
  vc2State.dryingStopReason = vc2SafeText(reasonText);
  vc2State.savedLevels = {};

  vc2Write(vc2ServiceCell("state_saved_levels_json"), "{}");
  vc2Write(vc2UserCell("drying_status"), "Не активна");
  vc2Write(vc2UserCell("drying_stop_reason"), vc2State.dryingStopReason);
  vc2Write(vc2ServiceCell("event_text"), "Сушка остановлена: " + vc2State.dryingStopReason);

  vc2PersistState();
}

function vc2UpdateDryingState(cSnap, settings) {
  var now = vc2Now();

  if (cSnap.ok) {
    vc2State.currentsMissingSinceTs = 0;

    if (vc2CurrentIsSaunaOn(cSnap, settings)) {
      vc2State.saunaWasOn = true;
    }

    var cond = vc2CurrentIsDryingCondition(cSnap, settings);
    if (cond) {
      if (vc2State.dryingConditionSinceTs === 0) {
        vc2State.dryingConditionSinceTs = now;
      }
    } else {
      vc2State.dryingConditionSinceTs = 0;
    }

    if (!vc2State.dryingActive && vc2State.saunaWasOn && cond) {
      var elapsed = now - vc2State.dryingConditionSinceTs;
      if (elapsed >= settings.dryingConfirmSec * 1000) {
        vc2StartDrying("Подтверждена остановка печи сауны", settings);
      }
    }

    if (vc2State.dryingActive) {
      if (!cond) {
        vc2StopDrying("Условие сушки пропало");
        return;
      }

      if (now >= vc2State.dryingUntilTs) {
        vc2StopDrying("Завершение по таймеру");
        return;
      }
    }

    vc2PersistState();
    return;
  }

  // Данные токов недоступны.
  if (!vc2State.dryingActive) {
    // Если сушка не активна, просто ждем восстановления данных.
    vc2State.dryingConditionSinceTs = 0;
    vc2PersistState();
    return;
  }

  if (vc2State.currentsMissingSinceTs === 0) {
    vc2State.currentsMissingSinceTs = now;
    vc2Write(vc2ServiceCell("event_text"), "Потеря токов во время сушки: ожидание восстановления");
    vc2PersistState();
    return;
  }

  var missingSec = Math.floor((now - vc2State.currentsMissingSinceTs) / 1000);
  if (missingSec >= settings.currentsLossGraceSec) {
    vc2StopDrying("Токи сауны недоступны дольше допустимого времени");
    return;
  }

  // В пределах grace-периода продолжаем сушку до таймера без изменения состояния.
  if (now >= vc2State.dryingUntilTs) {
    vc2StopDrying("Завершение по таймеру при недоступных токах");
    return;
  }

  vc2PersistState();
}

// ============================================================
// 6. SAFE BEHAVIOR
// ============================================================

function vc2ApplyVilpeSetpoint(target) {
  var t = vc2Clamp(target, 0, 100);
  vc2Write(VC2_CFG.vilpe.speed, t);
  vc2Write(VC2_CFG.vilpe.enableSwitch, t > 0);
  vc2State.lastAppliedVilpeSetpoint = t;
  vc2Write(vc2UserCell("target_vilpe_setpoint"), t);
  vc2PersistState();
}

function vc2SelectSafeSetpoint(bSnap) {
  if (vc2State.lastAppliedVilpeSetpoint !== null) {
    return vc2State.lastAppliedVilpeSetpoint;
  }

  if (vc2State.lastValidBreezartSetpoint !== null) {
    return vc2State.lastValidBreezartSetpoint;
  }

  if (bSnap.setpointOk) {
    return bSnap.setpoint;
  }

  if (bSnap.actualOk) {
    return bSnap.actual;
  }

  // Явный запасной минимум, если полностью нет данных.
  return 15;
}

function vc2ApplySafeBehavior(reasonText, bSnap) {
  var safeSetpoint = vc2SelectSafeSetpoint(bSnap);
  vc2ApplyVilpeSetpoint(safeSetpoint);
  vc2State.lastErrorText = vc2SafeText(reasonText);
  vc2State.lastDiagText = "SAFE: удержание безопасной уставки";

  vc2Write(vc2UserCell("last_error_text"), vc2State.lastErrorText);
  vc2Write(vc2UserCell("diagnostic_status"), vc2State.lastDiagText);
  vc2Write(vc2ServiceCell("event_text"), "SAFE-режим: " + vc2SafeText(reasonText));
}

// ============================================================
// 7. ДИАГНОСТИКА И ФЛАГИ
// ============================================================

function vc2UpdateTimerLeft() {
  var leftSec = 0;
  if (vc2State.dryingActive) {
    leftSec = Math.floor((vc2State.dryingUntilTs - vc2Now()) / 1000);
    if (leftSec < 0) leftSec = 0;
  }
  vc2Write(vc2UserCell("drying_timer_left_sec"), leftSec);
}

function vc2UpdateInputAvailabilityText(hSnap, bSnap, cSnap) {
  var parts = [];
  parts.push("влажность=" + hSnap.availableCount + "/" + VC2_CFG.humiditySensors.length);
  parts.push("уставка_Breezart=" + (bSnap.setpointOk ? "ok" : "нет"));
  parts.push("факт_Breezart=" + (bSnap.actualOk ? "ok" : "нет"));
  parts.push("токи_сауны=" + (cSnap.ok ? "ok" : "нет"));
  if (hSnap.unavailable.length > 0) {
    parts.push("нет_датчиков=" + hSnap.unavailable.join(", "));
  }
  vc2Write(vc2ServiceCell("input_availability"), parts.join("; "));
}

function vc2ApplyFlags(flags, alarmText) {
  vc2Write(vc2ServiceCell("alarm_active"), !!flags.alarmActive);
  vc2Write(vc2ServiceCell("alarm_text"), vc2SafeText(alarmText));
  vc2Write(vc2ServiceCell("input_data_error"), !!flags.inputDataError);
  vc2Write(vc2ServiceCell("humidity_sensors_error"), !!flags.humiditySensorsError);
  vc2Write(vc2ServiceCell("breezart_data_error"), !!flags.breezartDataError);
  vc2Write(vc2ServiceCell("sauna_currents_error"), !!flags.saunaCurrentsError);
  vc2Write(vc2ServiceCell("startup_diagnostics_error"), !!vc2State.startupDiagnosticsError);
  vc2Write(vc2ServiceCell("drying_currents_missing"), !!flags.dryingCurrentsMissing);
  vc2Write(vc2ServiceCell("safe_mode_active"), !!flags.safeModeActive);
}

// ============================================================
// 8. ПРИМЕНЕНИЕ УСТАВОК
// ============================================================

function vc2EvaluateAndApply() {
  var settings = vc2GetSettings();
  var hSnap = vc2GetHumiditySnapshot();
  var cSnap = vc2GetCurrentsSnapshot();
  var bSnap = vc2GetBreezartSnapshot();

  var flags = {
    alarmActive: false,
    inputDataError: false,
    humiditySensorsError: false,
    breezartDataError: false,
    saunaCurrentsError: false,
    dryingCurrentsMissing: false,
    safeModeActive: false
  };

  vc2UpdateDryingState(cSnap, settings);

  if (!bSnap.setpointOk) {
    flags.breezartDataError = true;
  } else {
    vc2State.lastValidBreezartSetpoint = bSnap.setpoint;
  }

  if (!cSnap.ok) {
    flags.saunaCurrentsError = true;
    if (vc2State.dryingActive) {
      flags.dryingCurrentsMissing = true;
    }
  }

  if (hSnap.unavailable.length > 0) {
    flags.humiditySensorsError = true;
  }

  var humidityReliable = hSnap.availableCount >= VC2_CFG.defaults.minHumiditySensorsForReliable;
  var humidityMode = vc2DetermineHumidityMode(hSnap, settings);

  var activeMode = "NORMAL";
  if (vc2State.dryingActive) {
    activeMode = "DRYING";
  } else {
    activeMode = humidityMode.modeId;
  }

  if (!humidityReliable && !vc2State.dryingActive) {
    flags.inputDataError = true;
    flags.safeModeActive = true;
    flags.alarmActive = true;
    vc2ApplySafeBehavior("Недостаточно валидных датчиков влажности", bSnap);
  } else {
    var target = vc2ComputeVilpeTarget(activeMode, settings, bSnap);
    if (target.ok) {
      vc2ApplyVilpeSetpoint(target.target);
      vc2State.lastErrorText = "";
      vc2State.lastDiagText = "Режим: " + vc2ModeName(activeMode);
      vc2Write(vc2UserCell("last_error_text"), "");
      vc2Write(vc2UserCell("diagnostic_status"), vc2State.lastDiagText);
    } else {
      flags.inputDataError = true;
      flags.breezartDataError = true;
      flags.safeModeActive = true;
      flags.alarmActive = true;
      vc2ApplySafeBehavior(target.reason, bSnap);
    }
  }


  if (flags.breezartDataError && !flags.safeModeActive) {
    flags.alarmActive = true;
  }

  if (flags.saunaCurrentsError && !vc2State.dryingActive) {
    // Потеря токов вне сушки не критична для управления Vilpe, оставляем только сервисный флаг.
  }

  vc2Write(vc2UserCell("active_mode"), vc2ModeName(activeMode));
  vc2Write(vc2UserCell("breezart_setpoint"), bSnap.setpointOk ? bSnap.setpoint : -1);
  vc2Write(vc2UserCell("breezart_actual"), bSnap.actualOk ? bSnap.actual : -1);

  if (humidityMode.maxHumidity === null) {
    vc2Write(vc2UserCell("max_humidity"), -1);
    vc2Write(vc2UserCell("max_humidity_sensor"), "");
  } else {
    vc2Write(vc2UserCell("max_humidity"), vc2Round1(humidityMode.maxHumidity));
    vc2Write(vc2UserCell("max_humidity_sensor"), humidityMode.sourceName);
  }

  vc2Write(vc2UserCell("drying_status"), vc2State.dryingActive ? "Активна" : "Не активна");
  vc2Write(vc2UserCell("drying_stop_reason"), vc2State.dryingStopReason);

  vc2Write(vc2ServiceCell("current_l1"), cSnap.l1 !== null ? vc2Round1(cSnap.l1) : -1);
  vc2Write(vc2ServiceCell("current_l2"), cSnap.l2 !== null ? vc2Round1(cSnap.l2) : -1);
  vc2Write(vc2ServiceCell("current_l3"), cSnap.l3 !== null ? vc2Round1(cSnap.l3) : -1);

  vc2UpdateInputAvailabilityText(hSnap, bSnap, cSnap);

  var alarmText = "";
  if (flags.safeModeActive) {
    alarmText = vc2State.lastErrorText;
  } else if (flags.breezartDataError) {
    alarmText = "Недоступны данные Breezart";
  }

  vc2ApplyFlags(flags, alarmText);
  vc2UpdateTimerLeft();
}

// ============================================================
// 9. VIRTUAL DEVICES
// ============================================================

defineVirtualDevice(VC2_CFG.ids.userVdev, {
  title: VC2_CFG.ids.userTitle,
  cells: {
    // Настройки (пользовательские)
    humidity_high_enter: {
      type: "range",
      value: VC2_CFG.defaults.humidityHighEnter,
      min: 0,
      max: 100,
      title: "Порог входа: повышенная влажность, %",
      order: 1
    },
    humidity_high_exit_delta: {
      type: "range",
      value: VC2_CFG.defaults.humidityHighExitDelta,
      min: 0,
      max: 20,
      title: "Гистерезис выхода из повышенной влажности, %",
      order: 2
    },
    humidity_very_high_enter: {
      type: "range",
      value: VC2_CFG.defaults.humidityVeryHighEnter,
      min: 0,
      max: 100,
      title: "Порог входа: высокая влажность, %",
      order: 3
    },
    humidity_very_high_exit_delta: {
      type: "range",
      value: VC2_CFG.defaults.humidityVeryHighExitDelta,
      min: 0,
      max: 20,
      title: "Гистерезис выхода из высокой влажности, %",
      order: 4
    },
    normal_lag: {
      type: "range",
      value: VC2_CFG.defaults.normalLag,
      min: 0,
      max: 100,
      title: "Отставание Vilpe в норме, %",
      order: 5
    },
    high_humidity_lag: {
      type: "range",
      value: VC2_CFG.defaults.highHumidityLag,
      min: 0,
      max: 100,
      title: "Отставание Vilpe при повышенной влажности, %",
      order: 6
    },
    very_high_setpoint: {
      type: "range",
      value: VC2_CFG.defaults.veryHighSetpoint,
      min: 0,
      max: 100,
      title: "Уставка при высокой влажности, %",
      order: 7
    },
    drying_setpoint: {
      type: "range",
      value: VC2_CFG.defaults.dryingSetpoint,
      min: 0,
      max: 100,
      title: "Уставка при сушке, %",
      order: 8
    },
    drying_duration_min: {
      type: "value",
      value: VC2_CFG.defaults.dryingDurationMin,
      title: "Длительность сушки, мин",
      order: 9
    },
    sauna_on_current_a: {
      type: "value",
      value: VC2_CFG.defaults.saunaOnCurrentA,
      title: "Порог \"сауна включена\", А",
      order: 10
    },
    sauna_l1_off_a: {
      type: "value",
      value: VC2_CFG.defaults.saunaL1OffA,
      title: "Порог L1 для старта сушки, А",
      order: 11
    },
    drying_confirm_sec: {
      type: "value",
      value: VC2_CFG.defaults.dryingConfirmSec,
      title: "Подтверждение запуска сушки, сек",
      order: 12
    },
    currents_loss_grace_sec: {
      type: "value",
      value: VC2_CFG.defaults.currentsLossGraceSec,
      title: "Допуск потери токов при сушке, сек",
      order: 13
    },
    coordinator_enabled: {
      type: "switch",
      value: VC2_CFG.defaults.coordinatorEnabled,
      title: "Координировать доп. каналы сушки",
      order: 14
    },

    // Пользовательские статусы
    active_mode: {
      type: "text",
      value: "",
      readonly: true,
      title: "Активный режим",
      order: 30
    },
    target_vilpe_setpoint: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Итоговая уставка Vilpe, %",
      order: 31
    },
    breezart_setpoint: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Уставка Breezart, %",
      order: 32
    },
    breezart_actual: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Факт Breezart, %",
      order: 33
    },
    max_humidity: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Максимальная влажность, %",
      order: 34
    },
    max_humidity_sensor: {
      type: "text",
      value: "",
      readonly: true,
      title: "Датчик максимальной влажности",
      order: 35
    },
    drying_status: {
      type: "text",
      value: "Не активна",
      readonly: true,
      title: "Сушка сауны",
      order: 36
    },
    drying_timer_left_sec: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Остаток таймера сушки, сек",
      order: 37
    },
    drying_stop_reason: {
      type: "text",
      value: "",
      readonly: true,
      title: "Причина остановки сушки",
      order: 38
    },
    diagnostic_status: {
      type: "text",
      value: "",
      readonly: true,
      title: "Диагностический статус",
      order: 39
    },
    last_error_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "Текст последней ошибки",
      order: 40
    }
  }
});

defineVirtualDevice(VC2_CFG.ids.serviceVdev, {
  title: VC2_CFG.ids.serviceTitle,
  cells: {
    // Сервисные флаги для Home Assistant/уведомлений
    alarm_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Авария активна",
      order: 1
    },
    alarm_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "Текст аварии",
      order: 2
    },
    safe_mode_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "SAFE-режим активен",
      order: 3
    },
    input_data_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Ошибка входных данных",
      order: 4
    },
    humidity_sensors_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Ошибка датчиков влажности",
      order: 5
    },
    breezart_data_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Ошибка данных Breezart",
      order: 6
    },
    sauna_currents_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Ошибка токов сауны",
      order: 7
    },
    startup_diagnostics_error: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Ошибка диагностики старта",
      order: 8
    },
    drying_currents_missing: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Во время сушки нет токов",
      order: 9
    },

    // Сервисные диагностические значения
    input_availability: {
      type: "text",
      value: "",
      readonly: true,
      title: "Доступность входных данных",
      order: 20
    },
    event_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "Последнее сервисное событие",
      order: 21
    },
    current_l1: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L1, А",
      order: 22
    },
    current_l2: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L2, А",
      order: 23
    },
    current_l3: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Ток L3, А",
      order: 24
    },

    // Внутреннее состояние (скрыто из пользовательского устройства)
    state_sauna_was_on: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Служебно: сауна была включена",
      order: 90
    },
    state_drying_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Служебно: сушка активна",
      order: 91
    },
    state_drying_started_ts: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Служебно: старт сушки, timestamp",
      order: 92
    },
    state_drying_until_ts: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Служебно: сушка до, timestamp",
      order: 93
    },
    state_drying_condition_since_ts: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Служебно: условие сушки с, timestamp",
      order: 94
    },
    state_currents_missing_since_ts: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Служебно: токи пропали с, timestamp",
      order: 95
    },
    state_humidity_mode_stable: {
      type: "text",
      value: "NORMAL",
      readonly: true,
      title: "Служебно: устойчивый режим влажности",
      order: 96
    },
    state_last_applied_vilpe_setpoint: {
      type: "value",
      value: -1,
      readonly: true,
      title: "Служебно: последняя уставка Vilpe, %",
      order: 97
    },
    state_saved_levels_json: {
      type: "text",
      value: "{}",
      readonly: true,
      title: "Служебно: сохранённые уровни JSON",
      order: 98
    }
  }
});

// ============================================================
// 10. RULES / TIMERS
// ============================================================

var vc2TrackedInputs = [
  VC2_CFG.breezart.setpoint,
  VC2_CFG.breezart.actual,

  VC2_CFG.saunaCurrents.l1,
  VC2_CFG.saunaCurrents.l2,
  VC2_CFG.saunaCurrents.l3,

  VC2_CFG.humiditySensors[0].id,
  VC2_CFG.humiditySensors[1].id,
  VC2_CFG.humiditySensors[2].id,
  VC2_CFG.humiditySensors[3].id,
  VC2_CFG.humiditySensors[4].id,

  vc2UserCell("humidity_high_enter"),
  vc2UserCell("humidity_high_exit_delta"),
  vc2UserCell("humidity_very_high_enter"),
  vc2UserCell("humidity_very_high_exit_delta"),
  vc2UserCell("normal_lag"),
  vc2UserCell("high_humidity_lag"),
  vc2UserCell("very_high_setpoint"),
  vc2UserCell("drying_setpoint"),
  vc2UserCell("drying_duration_min"),
  vc2UserCell("sauna_on_current_a"),
  vc2UserCell("sauna_l1_off_a"),
  vc2UserCell("drying_confirm_sec"),
  vc2UserCell("currents_loss_grace_sec"),
  vc2UserCell("coordinator_enabled")
];

defineRule("vilpe_control_v2_on_change", {
  whenChanged: vc2TrackedInputs,
  then: function () {
    vc2EvaluateAndApply();
  }
});

setInterval(function () {
  vc2EvaluateAndApply();
}, VC2_CFG.defaults.tickSec * 1000);

// ============================================================
// 11. ИНИЦИАЛИЗАЦИЯ И ВОССТАНОВЛЕНИЕ ПОСЛЕ СТАРТА
// ============================================================

function vc2RestoreStateOnStartup() {
  var now = vc2Now();

  vc2State.saunaWasOn = !!vc2ReadRaw(vc2ServiceCell("state_sauna_was_on"));
  vc2State.dryingActive = !!vc2ReadRaw(vc2ServiceCell("state_drying_active"));
  vc2State.dryingStartedTs = vc2ToNumber(vc2ReadRaw(vc2ServiceCell("state_drying_started_ts"))) || 0;
  vc2State.dryingUntilTs = vc2ToNumber(vc2ReadRaw(vc2ServiceCell("state_drying_until_ts"))) || 0;
  vc2State.dryingConditionSinceTs = vc2ToNumber(vc2ReadRaw(vc2ServiceCell("state_drying_condition_since_ts"))) || 0;
  vc2State.currentsMissingSinceTs = vc2ToNumber(vc2ReadRaw(vc2ServiceCell("state_currents_missing_since_ts"))) || 0;
  vc2State.savedLevels = vc2DeserializeSavedLevels(vc2ReadRaw(vc2ServiceCell("state_saved_levels_json")));

  var stableMode = vc2SafeText(vc2ReadRaw(vc2ServiceCell("state_humidity_mode_stable")));
  if (stableMode === "HIGH_HUMIDITY" || stableMode === "VERY_HIGH_HUMIDITY" || stableMode === "NORMAL") {
    vc2State.humidityModeStable = stableMode;
  }

  var persistedSetpoint = vc2ToNumber(vc2ReadRaw(vc2ServiceCell("state_last_applied_vilpe_setpoint")));
  if (persistedSetpoint !== null && persistedSetpoint >= 0 && persistedSetpoint <= 100) {
    vc2State.lastAppliedVilpeSetpoint = persistedSetpoint;
  }

  if (vc2State.dryingActive) {
    if (vc2State.dryingUntilTs <= now) {
      vc2State.dryingActive = false;
      vc2State.dryingStopReason = "Сушка сброшена при старте: таймер уже истек";
      vc2Write(vc2UserCell("drying_stop_reason"), vc2State.dryingStopReason);
    } else {
      vc2ApplyDryingLevels(vc2GetSettings());
      vc2Write(vc2UserCell("drying_status"), "Активна");
      vc2Write(vc2ServiceCell("event_text"), "После рестарта восстановлена активная сушка");
    }
  }

  vc2PersistState();
}

function vc2StartupDiagnostics() {
  var hSnap = vc2GetHumiditySnapshot();
  var cSnap = vc2GetCurrentsSnapshot();
  var bSnap = vc2GetBreezartSnapshot();
  var errors = [];

  if (!bSnap.setpointOk) {
    errors.push("Недоступна уставка Breezart");
  }

  if (hSnap.availableCount < VC2_CFG.defaults.minHumiditySensorsForReliable) {
    errors.push("Недостаточно валидных датчиков влажности");
  }

  if (!cSnap.ok) {
    errors.push("Недоступны токи сауны");
  }

  if (errors.length > 0) {
    vc2State.startupDiagnosticsError = true;
    vc2Write(vc2UserCell("last_error_text"), errors.join("; "));
    vc2Write(vc2UserCell("diagnostic_status"), "Стартовая диагностика: есть замечания");
    vc2Write(vc2ServiceCell("event_text"), "Стартовая диагностика: " + errors[0]);
  } else {
    vc2State.startupDiagnosticsError = false;
    vc2Write(vc2UserCell("diagnostic_status"), "Стартовая диагностика: OK");
  }

  vc2Write(vc2ServiceCell("startup_diagnostics_error"), !!vc2State.startupDiagnosticsError);
}

setTimeout(function () {
  vc2RestoreStateOnStartup();
  vc2StartupDiagnostics();
  vc2State.startupDone = true;
  vc2EvaluateAndApply();
}, 1500);
