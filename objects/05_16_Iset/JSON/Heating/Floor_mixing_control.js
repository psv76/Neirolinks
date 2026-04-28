/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: Floor_mixing_control.js
 * -------------------------------------------------------------
 * Регулятор узла подмеса тёплого пола для Wiren Board.
 *
 * НАЗНАЧЕНИЕ
 * -------------------------------------------------------------
 * Этот файл управляет только узлом подмеса тёплого пола.
 *
 * ВАЖНО ПО ТЕРМИНОЛОГИИ
 * -------------------------------------------------------------
 * На объекте датчик wb-w1/28-00000ff8a3d5 стоит на подаче
 * после узла подмеса в коллектор тёплого пола.
 *
 * То есть фактически регулятор держит не "температуру пола
 * в стяжке", а температуру подачи в контур тёплого пола.
 *
 * Для совместимости с уже существующим объектом и панелями
 * идентификаторы каналов floor_mixing_ctrl/* сохранены.
 *
 * ОСОБЕННОСТИ
 * -------------------------------------------------------------
 * - ES5 / wb-rules
 * - step-hold логика
 * - FAST / TRIM
 * - фильтр 3 измерения
 * - плавная погодная уставка
 * - паузы после движения
 * - выдержка после движения
 * - запрет частого разворота
 * - защита от пилы
 * - без рекурсии
 *
 * ЕДИНСТВЕННЫЙ ПИСАТЕЛЬ
 * -------------------------------------------------------------
 * Этот модуль должен быть единственным, кто пишет в:
 *   wb-mao4_131/Channel 1 Switch
 *   wb-mao4_131/Channel 1 Dimming Level
 ***************************************************************/


/***************************************************************
 * 1. ПРИВЯЗКА К УСТРОЙСТВАМ
 ***************************************************************/

var FM_TEMP_SUPPLY  = "wb-w1/28-00000ff8a3d5";
var FM_TEMP_OUTDOOR = "wb-w1/28-00000fd6a9ad";
var FM_PUMP_FLOOR   = "wb-mr6cu_37/K2";
var FM_VALVE_ENABLE = "wb-mao4_131/Channel 1 Switch";
var FM_VALVE_POS    = "wb-mao4_131/Channel 1 Dimming Level";


/***************************************************************
 * 2. НАСТРОЙКИ ПО УМОЛЧАНИЮ
 ***************************************************************/

var FM_DEFAULT_ENABLED = true;
var FM_DEFAULT_SETPOINT_MODE = "weather";
var FM_DEFAULT_PHASE_MODE = "auto";

var FM_DEFAULT_SETPOINT = 34;
var FM_DEFAULT_SENSOR_OFFSET = 0.0;

var FM_DEFAULT_BAND_C = 1.0;
var FM_DEFAULT_BIAS_C = 0.0;
var FM_DEFAULT_FAR_ERR_C = 2.5;

var FM_DEFAULT_FAST_HOLD_COLD_S = 90;
var FM_DEFAULT_FAST_HOLD_HOT_S  = 120;
var FM_DEFAULT_FAST_MIN_STEP = 2;
var FM_DEFAULT_FAST_MAX_STEP = 5;

var FM_DEFAULT_TRIM_HOLD_COLD_S = 180;
var FM_DEFAULT_TRIM_HOLD_HOT_S  = 240;
var FM_DEFAULT_TRIM_MIN_STEP = 1;
var FM_DEFAULT_TRIM_MAX_STEP = 2;

var FM_DEFAULT_PCT_PER_C_COLD = 2.0;
var FM_DEFAULT_PCT_PER_C_HOT  = 1.5;

var FM_DEFAULT_REVERSE_LOCK_S = 420;
var FM_DEFAULT_TREND_OK = 0.35;
var FM_DEFAULT_TREND_SLOW = 0.12;
var FM_DEFAULT_STAGNATION_S = 600;

var FM_DEFAULT_POST_MOVE_SETTLE_S = 90;

var FM_DEFAULT_MIN_POS = 0;
var FM_DEFAULT_MAX_POS = 80;
var FM_DEFAULT_HARD_MAX_C = 45;
var FM_DEFAULT_PERIOD_S = 15;
var FM_DEFAULT_WRITE_EPS_PCT = 0.5;
var FM_DEFAULT_ENABLE_RETRY_S = 60;


/***************************************************************
 * 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
 ***************************************************************/

function fmClamp(x, a, b) {
  x = Number(x);
  if (isNaN(x)) x = a;
  if (x < a) return a;
  if (x > b) return b;
  return x;
}

function fmNowSec() {
  return Math.floor(Date.now() / 1000);
}

function fmToBool(v) {
  if (v === true || v === 1 || v === "1") return true;
  if (v === false || v === 0 || v === "0" || v === null || v === undefined) return false;
  return !!v;
}

function fmReadNum(path) {
  try {
    var v = parseFloat(dev[path]);
    return isNaN(v) ? null : v;
  } catch (e) {
    return null;
  }
}

function fmReadBool(path) {
  try {
    return fmToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function fmRound1(v) {
  return Math.round(v * 10) / 10;
}

function fmRound2(v) {
  return Math.round(v * 100) / 100;
}

function fmNumOr(v, dflt) {
  v = Number(v);
  return isNaN(v) ? dflt : v;
}

function fmLinMap(x, x1, y1, x2, y2) {
  if (x <= x1) return y1;
  if (x >= x2) return y2;
  return y1 + (y2 - y1) * (x - x1) / (x2 - x1);
}


/***************************************************************
 * 4. ВИРТУАЛЬНОЕ УСТРОЙСТВО
 ***************************************************************/

defineVirtualDevice("floor_mixing_ctrl", {
  title: { ru: "Узел подмеса Тёплый пол" },
  cells: {
    enabled: {
      title: "Регулятор включен",
      type: "switch",
      value: FM_DEFAULT_ENABLED
    },

    t_floor_raw: {
      title: "Подача после подмеса raw, °C",
      type: "value",
      value: 0,
      readonly: true
    },

    sensor_offset: {
      title: "Поправка датчика, °C",
      type: "value",
      value: FM_DEFAULT_SENSOR_OFFSET
    },

    t_floor_corr: {
      title: "Подача после подмеса corr, °C",
      type: "value",
      value: 0,
      readonly: true
    },

    t_outdoor: {
      title: "Уличная температура, °C",
      type: "value",
      value: 0,
      readonly: true
    },

    pump_on: {
      title: "Насос пола",
      type: "switch",
      value: false,
      readonly: true
    },

    valve_enable: {
      title: "Питание клапана",
      type: "switch",
      value: false,
      readonly: true
    },

    valve_position: {
      title: "Положение клапана, %",
      type: "range",
      value: 0,
      max: 100,
      readonly: true
    },

    setpoint_mode: {
      title: "Режим уставки",
      type: "enum",
      value: FM_DEFAULT_SETPOINT_MODE,
      enum: {
        weather: "По улице",
        manual: "Ручная"
      }
    },

    setpoint_status: {
      title: "Статус уставки",
      type: "text",
      value: "Авто: по улице",
      readonly: true
    },

    setpoint_mode_weather: {
      title: "УСТАВКА ПО УЛИЦЕ",
      type: "pushbutton"
    },

    setpoint_mode_manual: {
      title: "УСТАВКА РУЧНАЯ",
      type: "pushbutton"
    },

    setpoint: {
      title: "Уставка подачи, °C",
      type: "range",
      value: FM_DEFAULT_SETPOINT,
      min: 20,
      max: 45,
      step: 1
    },

    band_c: {
      title: "Deadband ±°C",
      type: "range",
      value: FM_DEFAULT_BAND_C,
      min: 0.2,
      max: 5,
      step: 0.1
    },

    bias_c: {
      title: "Подстраховка при недогреве, °C",
      type: "value",
      value: FM_DEFAULT_BIAS_C
    },

    far_err_c: {
      title: "Порог FAST→TRIM, °C",
      type: "value",
      value: FM_DEFAULT_FAR_ERR_C
    },

    fast_hold_cold_s: {
      title: "FAST: пауза после закрытия, с",
      type: "range",
      value: FM_DEFAULT_FAST_HOLD_COLD_S,
      min: 5,
      max: 600,
      step: 5
    },

    fast_hold_hot_s: {
      title: "FAST: пауза после открытия, с",
      type: "range",
      value: FM_DEFAULT_FAST_HOLD_HOT_S,
      min: 5,
      max: 600,
      step: 5
    },

    fast_min_step_pct: {
      title: "FAST: мин. шаг, %",
      type: "range",
      value: FM_DEFAULT_FAST_MIN_STEP,
      min: 1,
      max: 30,
      step: 1
    },

    fast_max_step_pct: {
      title: "FAST: макс. шаг, %",
      type: "range",
      value: FM_DEFAULT_FAST_MAX_STEP,
      min: 1,
      max: 40,
      step: 1
    },

    trim_hold_cold_s: {
      title: "TRIM: пауза после закрытия, с",
      type: "range",
      value: FM_DEFAULT_TRIM_HOLD_COLD_S,
      min: 5,
      max: 900,
      step: 5
    },

    trim_hold_hot_s: {
      title: "TRIM: пауза после открытия, с",
      type: "range",
      value: FM_DEFAULT_TRIM_HOLD_HOT_S,
      min: 5,
      max: 900,
      step: 5
    },

    trim_min_step_pct: {
      title: "TRIM: мин. шаг, %",
      type: "range",
      value: FM_DEFAULT_TRIM_MIN_STEP,
      min: 1,
      max: 20,
      step: 1
    },

    trim_max_step_pct: {
      title: "TRIM: макс. шаг, %",
      type: "range",
      value: FM_DEFAULT_TRIM_MAX_STEP,
      min: 1,
      max: 20,
      step: 1
    },

    pct_per_c_cold: {
      title: "Недогрев: % на 1°C",
      type: "range",
      value: FM_DEFAULT_PCT_PER_C_COLD,
      min: 0.5,
      max: 20,
      step: 0.5
    },

    pct_per_c_hot: {
      title: "Перегрев: % на 1°C",
      type: "range",
      value: FM_DEFAULT_PCT_PER_C_HOT,
      min: 0.5,
      max: 20,
      step: 0.5
    },

    reverse_lock_s: {
      title: "Запрет разворота, с",
      type: "range",
      value: FM_DEFAULT_REVERSE_LOCK_S,
      min: 0,
      max: 900,
      step: 10
    },

    trend_ok_c_per_min: {
      title: "Тренд «достаточно», °C/мин",
      type: "value",
      value: FM_DEFAULT_TREND_OK
    },

    trend_slow_c_per_min: {
      title: "Тренд «слабый», °C/мин",
      type: "value",
      value: FM_DEFAULT_TREND_SLOW
    },

    stagnation_s: {
      title: "Застой (микрошаг), с",
      type: "range",
      value: FM_DEFAULT_STAGNATION_S,
      min: 0,
      max: 3600,
      step: 30
    },

    min_pos: {
      title: "Мин. положение, %",
      type: "range",
      value: FM_DEFAULT_MIN_POS,
      min: 0,
      max: 100,
      step: 1
    },

    max_pos: {
      title: "Макс. положение, %",
      type: "range",
      value: FM_DEFAULT_MAX_POS,
      min: 0,
      max: 100,
      step: 1
    },

    hard_max_c: {
      title: "Жёсткий максимум подачи, °C",
      type: "value",
      value: FM_DEFAULT_HARD_MAX_C
    },

    phase_mode: {
      title: "Фаза: авто/ручная",
      type: "enum",
      value: FM_DEFAULT_PHASE_MODE,
      enum: {
        auto: "Авто",
        fast: "FAST",
        trim: "TRIM"
      }
    },

    phase_auto: {
      title: "ФАЗА АВТО",
      type: "pushbutton"
    },

    phase_fast: {
      title: "ФАЗА FAST",
      type: "pushbutton"
    },

    phase_trim: {
      title: "ФАЗА TRIM",
      type: "pushbutton"
    },

    manual_valve: {
      title: "Клапан вручную, %",
      type: "range",
      value: 20,
      max: 100,
      step: 1
    },

    period_s: {
      title: "Период проверки, с",
      type: "range",
      value: FM_DEFAULT_PERIOD_S,
      min: 2,
      max: 180,
      step: 1
    },

    effective_setpoint: {
      title: "Эффективная уставка, °C",
      type: "value",
      value: 0,
      readonly: true
    },

    phase: {
      title: "Фактическая фаза",
      type: "text",
      value: "TRIM",
      readonly: true
    },

    dT_c_min: {
      title: "Тренд, °C/мин",
      type: "value",
      value: 0,
      readonly: true
    },

    stop_now: {
      title: "СТОП (заморозить выход)",
      type: "pushbutton"
    },

    status: {
      title: "Статус",
      type: "text",
      value: "init",
      readonly: true
    }
  }
});


/***************************************************************
 * 5. ВНУТРЕННЕЕ СОСТОЯНИЕ
 ***************************************************************/

var fmPosCmd = 20;
var fmFrozen = false;
var fmLastMoveTs = 0;
var fmLastDir = "";
var fmLastT = null;
var fmLastTs = 0;
var fmLastNonBandTs = 0;
var fmLastTWhenNonBand = null;
var fmPumpWasOn = null;
var fmSuppressSetpointAutoSwitch = false;
var fmLoopTimer = null;
var fmInControlStep = false;
var fmPendingImmediateReason = "";
var fmImmediateTimer = null;
var fmLastValveWritePct = null;
var fmLastValveEnableWriteTs = 0;
var fmFilterBuf = [];


/***************************************************************
 * 6. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ РЕГУЛЯТОРА
 ***************************************************************/

function fmSetSetpointStatus(mode) {
  if (mode === "manual") {
    dev["floor_mixing_ctrl/setpoint_status"] = "Ручная";
  } else {
    dev["floor_mixing_ctrl/setpoint_status"] = "Авто: по улице";
  }
}

function fmWriteValve(pct) {
  var minPos = fmClamp(dev["floor_mixing_ctrl/min_pos"], 0, 100);
  var maxPos = fmClamp(dev["floor_mixing_ctrl/max_pos"], 0, 100);
  var p;
  var aoNow;
  var eps;

  if (maxPos < minPos) maxPos = minPos;

  p = fmClamp(pct, minPos, maxPos);
  p = fmClamp(p, 0, 100);

  aoNow = fmReadNum(FM_VALVE_POS);
  eps = fmNumOr(FM_DEFAULT_WRITE_EPS_PCT, 0.5);

  if (aoNow === null || Math.abs(aoNow - p) >= eps) {
    dev[FM_VALVE_POS] = p;
    fmLastValveWritePct = p;
  }

  dev["floor_mixing_ctrl/valve_position"] = p;
}

function fmEnsureValveEnabled() {
  var isEnabled = fmReadBool(FM_VALVE_ENABLE);
  var ts = fmNowSec();
  var retryS = fmNumOr(FM_DEFAULT_ENABLE_RETRY_S, 60);

  if (!isEnabled && (fmLastValveEnableWriteTs === 0 || (ts - fmLastValveEnableWriteTs) >= retryS)) {
    dev[FM_VALVE_ENABLE] = true;
    fmLastValveEnableWriteTs = ts;
  }

  dev["floor_mixing_ctrl/valve_enable"] = fmReadBool(FM_VALVE_ENABLE);
}

function fmFilter3(v) {
  var i;
  var sum = 0;

  if (v === null) return null;

  fmFilterBuf.push(v);
  if (fmFilterBuf.length > 3) {
    fmFilterBuf.shift();
  }

  for (i = 0; i < fmFilterBuf.length; i++) {
    sum += fmFilterBuf[i];
  }

  return sum / fmFilterBuf.length;
}

function fmReadCorrectedSupplyTemp() {
  var raw = fmReadNum(FM_TEMP_SUPPLY);
  var offset = fmReadNum("floor_mixing_ctrl/sensor_offset");
  var corr;
  var filt;

  if (raw === null) {
    dev["floor_mixing_ctrl/t_floor_raw"] = 0;
    dev["floor_mixing_ctrl/t_floor_corr"] = 0;
    return null;
  }

  if (offset === null) offset = FM_DEFAULT_SENSOR_OFFSET;

  dev["floor_mixing_ctrl/t_floor_raw"] = fmRound1(raw);

  corr = raw + offset;
  filt = fmFilter3(corr);

  if (filt === null) return null;

  dev["floor_mixing_ctrl/t_floor_corr"] = fmRound1(filt);
  return filt;
}

function fmReadOutdoorTemp() {
  var t = fmReadNum(FM_TEMP_OUTDOOR);

  if (t === null) {
    dev["floor_mixing_ctrl/t_outdoor"] = 0;
    return null;
  }

  dev["floor_mixing_ctrl/t_outdoor"] = fmRound1(t);
  return t;
}

function fmSyncValvePosFromAO() {
  var ao = fmReadNum(FM_VALVE_POS);
  if (ao === null) return;

  fmPosCmd = fmClamp(ao, 0, 100);
  dev["floor_mixing_ctrl/valve_position"] = fmPosCmd;
}

function fmWeatherSetpoint() {
  var out = fmReadOutdoorTemp();
  var sp;

  if (out === null) {
    return fmClamp(dev["floor_mixing_ctrl/setpoint"], 20, 45);
  }

  if (out <= -25) return 42;
  if (out >= 10) return 30;

  if (out <= -10) {
    sp = fmLinMap(out, -25, 42, -10, 38);
  } else if (out <= 0) {
    sp = fmLinMap(out, -10, 38, 0, 35);
  } else {
    sp = fmLinMap(out, 0, 35, 10, 30);
  }

  return fmRound1(fmClamp(sp, 20, 45));
}

function fmApplyWeatherSetpoint() {
  var sp = fmWeatherSetpoint();

  fmSuppressSetpointAutoSwitch = true;
  dev["floor_mixing_ctrl/setpoint"] = sp;
  fmSuppressSetpointAutoSwitch = false;

  fmSetSetpointStatus("weather");
  return sp;
}

function fmActiveSetpoint() {
  var mode = dev["floor_mixing_ctrl/setpoint_mode"];
  var spManual;

  if (mode === "manual") {
    spManual = fmClamp(dev["floor_mixing_ctrl/setpoint"], 20, 45);

    fmSuppressSetpointAutoSwitch = true;
    dev["floor_mixing_ctrl/setpoint"] = spManual;
    fmSuppressSetpointAutoSwitch = false;

    fmSetSetpointStatus("manual");
    return spManual;
  }

  return fmApplyWeatherSetpoint();
}

function fmCurrentPhaseAuto(errAbs) {
  var thr = fmNumOr(dev["floor_mixing_ctrl/far_err_c"], FM_DEFAULT_FAR_ERR_C);

  if (errAbs >= thr) return "FAST";
  return "TRIM";
}

function fmChoosePhase(errAbs) {
  var pm = dev["floor_mixing_ctrl/phase_mode"];

  if (pm === "fast") return "FAST";
  if (pm === "trim") return "TRIM";
  return fmCurrentPhaseAuto(errAbs);
}

function fmHoldSeconds(phase, lastDirLocal) {
  if (phase === "FAST") {
    if (lastDirLocal === "hotter") return dev["floor_mixing_ctrl/fast_hold_hot_s"];
    if (lastDirLocal === "colder") return dev["floor_mixing_ctrl/fast_hold_cold_s"];
    return Math.max(dev["floor_mixing_ctrl/fast_hold_cold_s"], dev["floor_mixing_ctrl/fast_hold_hot_s"]);
  }

  if (lastDirLocal === "hotter") return dev["floor_mixing_ctrl/trim_hold_hot_s"];
  if (lastDirLocal === "colder") return dev["floor_mixing_ctrl/trim_hold_cold_s"];
  return Math.max(dev["floor_mixing_ctrl/trim_hold_cold_s"], dev["floor_mixing_ctrl/trim_hold_hot_s"]);
}

function fmStepLimits(phase) {
  if (phase === "FAST") {
    return {
      minStep: dev["floor_mixing_ctrl/fast_min_step_pct"],
      maxStep: dev["floor_mixing_ctrl/fast_max_step_pct"]
    };
  }

  return {
    minStep: dev["floor_mixing_ctrl/trim_min_step_pct"],
    maxStep: dev["floor_mixing_ctrl/trim_max_step_pct"]
  };
}

function fmResetMotionMemory() {
  fmLastMoveTs = 0;
  fmLastDir = "";
  fmLastNonBandTs = 0;
  fmLastTWhenNonBand = null;
}

function fmRequestImmediateRecalc(reason) {
  if (!dev["floor_mixing_ctrl/enabled"]) return;
  if (fmFrozen) return;
  if (!fmReadBool(FM_PUMP_FLOOR)) return;

  if (fmInControlStep) {
    fmPendingImmediateReason = reason || "отложенный пересчёт";
    return;
  }

  if (fmImmediateTimer) clearTimeout(fmImmediateTimer);

  fmImmediateTimer = setTimeout(function () {
    fmImmediateTimer = null;
    dev["floor_mixing_ctrl/status"] = "мгновенный пересчёт: " + (reason || "без причины");
    fmControlStep();
  }, 1);
}


/***************************************************************
 * 7. СОСТОЯНИЕ НАСОСА ПОЛА
 ***************************************************************/

function fmSyncPumpState() {
  var pumpOn = fmReadBool(FM_PUMP_FLOOR);
  var turnedOn = false;
  var turnedOff = false;

  dev["floor_mixing_ctrl/pump_on"] = pumpOn;

  if (fmPumpWasOn === null) {
    fmPumpWasOn = pumpOn;

    if (!pumpOn) {
      fmPosCmd = 0;
      fmWriteValve(0);
      fmFilterBuf = [];
      dev["floor_mixing_ctrl/status"] = "насос пола выключен: клапан закрыт 0%";
    }

    return {
      pumpOn: pumpOn,
      turnedOn: false,
      turnedOff: false
    };
  }

  if (!fmPumpWasOn && pumpOn) {
    turnedOn = true;
  }

  if (fmPumpWasOn && !pumpOn) {
    turnedOff = true;
    fmPosCmd = 0;
    fmWriteValve(0);
    fmFilterBuf = [];
    dev["floor_mixing_ctrl/status"] = "насос пола выключен: клапан закрыт 0%";
  }

  fmPumpWasOn = pumpOn;

  return {
    pumpOn: pumpOn,
    turnedOn: turnedOn,
    turnedOff: turnedOff
  };
}


/***************************************************************
 * 8. ОСНОВНАЯ ЛОГИКА
 ***************************************************************/

function fmControlStep() {
  var pumpState;
  var t;
  var ts;
  var dT_c_min = 0;
  var hardMax;
  var sp;
  var band;
  var bias;
  var effSp;
  var err;
  var phase;
  var holdS;
  var dir;
  var revLockS;
  var trendOk;
  var trendSlow;
  var movingRight;
  var movingWrong;
  var absTrend;
  var kCold;
  var kHot;
  var k;
  var lim;
  var minStep;
  var maxStep;
  var baseStep;
  var step;
  var stgS;
  var minPos;
  var maxPos;
  var delta;
  var newCmd;
  var postMoveSettleS;
  var sinceMove;
  var dt;

  if (fmInControlStep) return;
  fmInControlStep = true;

  try {
    pumpState = fmSyncPumpState();

    if (!dev["floor_mixing_ctrl/enabled"]) {
      return;
    }

    if (!pumpState.pumpOn) {
      dev["floor_mixing_ctrl/pump_on"] = false;
      dev["floor_mixing_ctrl/status"] = "насос пола выключен: клапан закрыт 0%";
      return;
    }

    dev["floor_mixing_ctrl/pump_on"] = true;

    t = fmReadCorrectedSupplyTemp();
    if (t === null) {
      dev["floor_mixing_ctrl/status"] = "нет данных датчика подачи";
      return;
    }

    fmReadOutdoorTemp();

    if (fmFrozen) {
      var holdPos = fmClamp(dev["floor_mixing_ctrl/manual_valve"], 0, 100);
      fmPosCmd = holdPos;
      fmWriteValve(fmPosCmd);
      dev["floor_mixing_ctrl/status"] = "СТОП: клапан удерживается вручную на " + fmPosCmd.toFixed(1) + "%";
      return;
    }

    fmEnsureValveEnabled();

    hardMax = fmNumOr(dev["floor_mixing_ctrl/hard_max_c"], FM_DEFAULT_HARD_MAX_C);
    if (t >= hardMax) {
      fmPosCmd = 0;
      fmWriteValve(0);
      dev["floor_mixing_ctrl/status"] =
        "защита: подача " + t.toFixed(1) + "°C >= " + hardMax.toFixed(1) + "°C, клапан закрыт";
      return;
    }

    ts = fmNowSec();

    if (fmLastT !== null && fmLastTs !== 0) {
      dt = ts - fmLastTs;
      if (dt > 0) {
        dT_c_min = (t - fmLastT) * 60.0 / dt;
      }
    }

    dev["floor_mixing_ctrl/dT_c_min"] = fmRound2(dT_c_min);

    fmLastT = t;
    fmLastTs = ts;

    sp = fmActiveSetpoint();
    band = fmNumOr(dev["floor_mixing_ctrl/band_c"], FM_DEFAULT_BAND_C);
    bias = fmNumOr(dev["floor_mixing_ctrl/bias_c"], FM_DEFAULT_BIAS_C);

    if (t < sp) {
      effSp = sp + bias;
    } else {
      effSp = sp;
    }

    dev["floor_mixing_ctrl/effective_setpoint"] = fmRound1(effSp);

    err = effSp - t;

    if (Math.abs(err) <= band) {
      dev["floor_mixing_ctrl/phase"] = "TRIM";
      dev["floor_mixing_ctrl/status"] =
        "в deadband; t=" + t.toFixed(1) + " sp=" + effSp.toFixed(1) + " cmd=" + fmPosCmd.toFixed(1) + "%";

      fmLastNonBandTs = 0;
      fmLastTWhenNonBand = null;

      fmWriteValve(fmPosCmd);
      return;
    }

    if (!fmLastNonBandTs) {
      fmLastNonBandTs = ts;
      fmLastTWhenNonBand = t;
    }

    phase = fmChoosePhase(Math.abs(err));

    if (phase === "FAST" && Math.abs(err) < 1.8) {
      phase = "TRIM";
    }

    dev["floor_mixing_ctrl/phase"] = phase;

    postMoveSettleS = fmNumOr(FM_DEFAULT_POST_MOVE_SETTLE_S, 90);
    sinceMove = fmLastMoveTs ? (ts - fmLastMoveTs) : 999999;

    if (sinceMove < postMoveSettleS) {
      dev["floor_mixing_ctrl/status"] =
        "выдержка после движения " + (postMoveSettleS - sinceMove) + "с; err=" + err.toFixed(2) + " [" + phase + "]";
      fmWriteValve(fmPosCmd);
      return;
    }

    holdS = fmNumOr(fmHoldSeconds(phase, fmLastDir), 30);

    if (fmLastMoveTs && (ts - fmLastMoveTs < holdS)) {
      dev["floor_mixing_ctrl/status"] =
        "пауза " + (holdS - (ts - fmLastMoveTs)) + "с; err=" + err.toFixed(2) + " [" + phase + "]";
      fmWriteValve(fmPosCmd);
      return;
    }

    dir = (err > 0) ? "hotter" : "colder";
    revLockS = fmNumOr(dev["floor_mixing_ctrl/reverse_lock_s"], FM_DEFAULT_REVERSE_LOCK_S);

    if (fmLastDir && dir !== fmLastDir && (ts - fmLastMoveTs < revLockS)) {
      dev["floor_mixing_ctrl/status"] =
        "запрет разворота " + (revLockS - (ts - fmLastMoveTs)) + "с; err=" + err.toFixed(2);
      fmWriteValve(fmPosCmd);
      return;
    }

    trendOk = fmNumOr(dev["floor_mixing_ctrl/trend_ok_c_per_min"], FM_DEFAULT_TREND_OK);
    trendSlow = fmNumOr(dev["floor_mixing_ctrl/trend_slow_c_per_min"], FM_DEFAULT_TREND_SLOW);

    movingRight = (err > 0 && dT_c_min > 0) || (err < 0 && dT_c_min < 0);
    movingWrong = (err > 0 && dT_c_min < 0) || (err < 0 && dT_c_min > 0);
    absTrend = Math.abs(dT_c_min);

    if (movingRight && absTrend >= trendOk) {
      dev["floor_mixing_ctrl/status"] =
        "тренд достаточный → ждём; err=" + err.toFixed(2) +
        " dT=" + dT_c_min.toFixed(2) + " [" + phase + "]";
      fmWriteValve(fmPosCmd);
      return;
    }

    kCold = fmNumOr(dev["floor_mixing_ctrl/pct_per_c_cold"], FM_DEFAULT_PCT_PER_C_COLD);
    kHot  = fmNumOr(dev["floor_mixing_ctrl/pct_per_c_hot"], FM_DEFAULT_PCT_PER_C_HOT);
    k = (dir === "hotter") ? kCold : kHot;

    lim = fmStepLimits(phase);
    minStep = fmNumOr(lim.minStep, 1);
    maxStep = fmNumOr(lim.maxStep, 5);

    baseStep = Math.abs(err) * k;

    if (movingRight && absTrend > trendSlow && absTrend < trendOk) {
      baseStep *= 0.45;
    }

    if (movingWrong && absTrend > trendSlow) {
      baseStep *= 1.15;
    }

    if (Math.abs(err) < 1.5) {
      baseStep *= 0.7;
    }

    stgS = fmNumOr(dev["floor_mixing_ctrl/stagnation_s"], FM_DEFAULT_STAGNATION_S);
    if (stgS > 0 && fmLastNonBandTs && (ts - fmLastNonBandTs >= stgS) && fmLastTWhenNonBand !== null) {
      if (Math.abs(t - fmLastTWhenNonBand) < 0.1) {
        baseStep = Math.max(baseStep, minStep);
        fmLastNonBandTs = ts;
        fmLastTWhenNonBand = t;
      } else {
        fmLastNonBandTs = ts;
        fmLastTWhenNonBand = t;
      }
    }

    step = fmClamp(baseStep, minStep, maxStep);

    minPos = fmClamp(dev["floor_mixing_ctrl/min_pos"], 0, 100);
    maxPos = fmClamp(dev["floor_mixing_ctrl/max_pos"], 0, 100);
    if (maxPos < minPos) maxPos = minPos;

    delta = (dir === "hotter") ? step : -step;

    newCmd = fmPosCmd + delta;
    newCmd = fmClamp(newCmd, minPos, maxPos);
    newCmd = fmClamp(newCmd, 0, 100);

    if (Math.abs(newCmd - fmPosCmd) < 0.001) {
      dev["floor_mixing_ctrl/status"] =
        "упор по положению; cmd=" + fmPosCmd.toFixed(1) + "%";
      fmWriteValve(fmPosCmd);
      return;
    }

    fmPosCmd = newCmd;
    fmWriteValve(fmPosCmd);

    fmLastDir = dir;
    fmLastMoveTs = ts;

    dev["floor_mixing_ctrl/status"] =
      "шаг " + (dir === "hotter" ? "ОТКРЫТЬ" : "ЗАКРЫТЬ") +
      " (" + step.toFixed(1) + "%) " +
      "t=" + t.toFixed(1) +
      " sp=" + effSp.toFixed(1) +
      " err=" + err.toFixed(2) +
      " dT=" + dT_c_min.toFixed(2) +
      " cmd=" + fmPosCmd.toFixed(1) +
      "% [" + phase + "]";

  } finally {
    fmInControlStep = false;

    if (fmPendingImmediateReason) {
      var reason = fmPendingImmediateReason;
      fmPendingImmediateReason = "";
      fmRequestImmediateRecalc(reason);
    }
  }
}


/***************************************************************
 * 9. КНОПКА СТОП
 ***************************************************************/

defineRule("floor_mixing_stop_now", {
  whenChanged: "floor_mixing_ctrl/stop_now",
  then: function () {
    fmFrozen = true;
    dev["floor_mixing_ctrl/status"] = "СТОП: выход заморожен";
  }
});


/***************************************************************
 * 10. ПЕРЕКЛЮЧЕНИЕ РЕЖИМА УСТАВКИ
 ***************************************************************/

defineRule("floor_mixing_setpoint_mode_weather", {
  whenChanged: "floor_mixing_ctrl/setpoint_mode_weather",
  then: function () {
    dev["floor_mixing_ctrl/setpoint_mode"] = "weather";
    fmApplyWeatherSetpoint();
    dev["floor_mixing_ctrl/status"] = "уставка: по улице";
    fmRequestImmediateRecalc("уставка по улице");
  }
});

defineRule("floor_mixing_setpoint_mode_manual", {
  whenChanged: "floor_mixing_ctrl/setpoint_mode_manual",
  then: function () {
    dev["floor_mixing_ctrl/setpoint_mode"] = "manual";
    fmSetSetpointStatus("manual");
    dev["floor_mixing_ctrl/status"] = "уставка: ручная";
    fmRequestImmediateRecalc("уставка ручная");
  }
});

defineRule("floor_mixing_setpoint_changed", {
  whenChanged: "floor_mixing_ctrl/setpoint",
  then: function () {
    if (fmSuppressSetpointAutoSwitch) return;

    fmSuppressSetpointAutoSwitch = true;
    dev["floor_mixing_ctrl/setpoint"] = fmClamp(dev["floor_mixing_ctrl/setpoint"], 20, 45);
    fmSuppressSetpointAutoSwitch = false;

    if (dev["floor_mixing_ctrl/setpoint_mode"] === "manual") {
      fmSetSetpointStatus("manual");
      dev["floor_mixing_ctrl/status"] = "изменена ручная уставка";
      fmRequestImmediateRecalc("изменение ручной уставки");
    } else {
      fmSetSetpointStatus("weather");
      dev["floor_mixing_ctrl/status"] = "обновлена расчётная уставка ПЗА";
    }
  }
});


/***************************************************************
 * 11. РУЧНОЕ УПРАВЛЕНИЕ ФАЗОЙ
 ***************************************************************/

defineRule("floor_mixing_phase_auto", {
  whenChanged: "floor_mixing_ctrl/phase_auto",
  then: function () {
    dev["floor_mixing_ctrl/phase_mode"] = "auto";
    dev["floor_mixing_ctrl/status"] = "фаза: Авто";
    fmRequestImmediateRecalc("фаза авто");
  }
});

defineRule("floor_mixing_phase_fast", {
  whenChanged: "floor_mixing_ctrl/phase_fast",
  then: function () {
    dev["floor_mixing_ctrl/phase_mode"] = "fast";
    dev["floor_mixing_ctrl/status"] = "фаза: FAST (ручная)";
    fmRequestImmediateRecalc("фаза fast");
  }
});

defineRule("floor_mixing_phase_trim", {
  whenChanged: "floor_mixing_ctrl/phase_trim",
  then: function () {
    dev["floor_mixing_ctrl/phase_mode"] = "trim";
    dev["floor_mixing_ctrl/status"] = "фаза: TRIM (ручная)";
    fmRequestImmediateRecalc("фаза trim");
  }
});


/***************************************************************
 * 12. ИЗМЕНЕНИЕ УЛИЧНОЙ ТЕМПЕРАТУРЫ
 ***************************************************************/

defineRule("floor_mixing_outdoor_watch", {
  whenChanged: FM_TEMP_OUTDOOR,
  then: function () {
    fmReadOutdoorTemp();

    if (dev["floor_mixing_ctrl/setpoint_mode"] === "weather") {
      fmApplyWeatherSetpoint();
      fmRequestImmediateRecalc("изменилась уличная температура");
    }
  }
});


/***************************************************************
 * 13. НАСОС ПОЛА
 ***************************************************************/

defineRule("floor_mixing_pump_watch", {
  whenChanged: FM_PUMP_FLOOR,
  then: function () {
    var pumpState = fmSyncPumpState();

    if (pumpState.turnedOn) {
      fmFilterBuf = [];
      fmResetMotionMemory();
      dev["floor_mixing_ctrl/status"] = "насос пола включён: регулирование восстановлено";
      fmRequestImmediateRecalc("насос пола включён");
    }

    if (pumpState.turnedOff) {
      dev["floor_mixing_ctrl/status"] = "насос пола выключен: клапан закрыт 0%";
    }
  }
});


/***************************************************************
 * 14. РЕАКЦИЯ НА ИЗМЕНЕНИЕ ПАРАМЕТРОВ
 ***************************************************************/

defineRule("floor_mixing_on_enabled_change", {
  whenChanged: "floor_mixing_ctrl/enabled",
  then: function () {
    if (dev["floor_mixing_ctrl/enabled"]) {
      fmFrozen = false;
      fmRequestImmediateRecalc("включено");
    }
  }
});

defineRule("floor_mixing_on_phase_mode_change", {
  whenChanged: "floor_mixing_ctrl/phase_mode",
  then: function () {
    fmRequestImmediateRecalc("смена phase_mode");
  }
});

defineRule("floor_mixing_on_sensor_offset_change", {
  whenChanged: "floor_mixing_ctrl/sensor_offset",
  then: function () {
    fmFilterBuf = [];
    fmRequestImmediateRecalc("изменение offset датчика");
  }
});


/***************************************************************
 * 15. ЦИКЛ
 ***************************************************************/

function fmStartLoop() {
  var periodS;

  if (fmLoopTimer) clearInterval(fmLoopTimer);

  periodS = fmNumOr(dev["floor_mixing_ctrl/period_s"], FM_DEFAULT_PERIOD_S);
  if (periodS < 2) periodS = FM_DEFAULT_PERIOD_S;

  fmLoopTimer = setInterval(function () {
    fmControlStep();
  }, Math.round(periodS * 1000));
}

defineRule("floor_mixing_restart_loop", {
  whenChanged: ["floor_mixing_ctrl/period_s", "floor_mixing_ctrl/enabled"],
  then: fmStartLoop
});


/***************************************************************
 * 16. ИНИЦИАЛИЗАЦИЯ
 ***************************************************************/

fmReadOutdoorTemp();
fmReadCorrectedSupplyTemp();

if (dev["floor_mixing_ctrl/setpoint_mode"] === "weather") {
  fmApplyWeatherSetpoint();
} else {
  fmSuppressSetpointAutoSwitch = true;
  dev["floor_mixing_ctrl/setpoint"] = fmClamp(dev["floor_mixing_ctrl/setpoint"], 20, 45);
  fmSuppressSetpointAutoSwitch = false;
  fmSetSetpointStatus("manual");
}

fmSyncValvePosFromAO();
fmSyncPumpState();
fmStartLoop();
