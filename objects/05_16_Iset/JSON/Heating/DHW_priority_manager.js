/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: DHW_priority_manager.js
 * -------------------------------------------------------------
 * Менеджер приоритета ГВС.
 *
 * ЗОНА ОТВЕТСТВЕННОСТИ
 * -------------------------------------------------------------
 * Этот модуль является единственным писателем только в:
 *   - wb-mr6cu_37/K1
 *   - wbe2-i-opentherm_11/Heating Setpoint
 *
 * В насосы отопления K2/K3/K4 модуль НЕ пишет.
 *
 * Для отопительных модулей публикуется прозрачный статус:
 *   - dhw_priority_mgr/heating_pause_mode
 *   - dhw_priority_mgr/heating_pause_active
 *
 * Ключевое требование безопасности:
 * при disable/alarm/выходе из приоритета уставка котла
 * должна восстанавливаться в предсказуемое состояние.
 ***************************************************************/

var DHW_TEMP_SENSOR = "wb-w1/28-00000fd7811a";
var BOILER_SETPOINT_CH = "wbe2-i-opentherm_11/Heating Setpoint";
var PUMP_DHW = "wb-mr6cu_37/K1";

var DEFAULT_ENABLED = false;
var DEFAULT_NORMAL_SETPOINT_C = 52;
var DEFAULT_NORMAL_HYST_C = 3;
var DEFAULT_PRIORITY_TRIGGER_C = 49;
var DEFAULT_PRIORITY_TARGET_C = 65;
var DEFAULT_PRIORITY_BOILER_SP_C = 80;
var DEFAULT_TICK_S = 15;
var DEFAULT_RESTORE_DELAY_S = 30;
var DEFAULT_PRIORITY_TIMEOUT_MIN = 50;

function dhwNowSec() { return Math.floor(Date.now() / 1000); }
function dhwRound1(v) { return Math.round(v * 10) / 10; }

function dhwToBool(v) {
  if (v === true || v === 1 || v === "1") return true;
  if (v === false || v === 0 || v === "0" || v === null || v === undefined) return false;
  return !!v;
}

function dhwReadNum(path) {
  try {
    var v = parseFloat(dev[path]);
    return isNaN(v) ? null : v;
  } catch (e) {
    return null;
  }
}

function dhwReadBool(path) {
  try {
    return dhwToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function dhwClamp(v, minV, maxV) {
  v = Number(v);
  if (isNaN(v)) v = minV;
  if (v < minV) return minV;
  if (v > maxV) return maxV;
  return v;
}

function dhwWriteBoolIfNeeded(path, value) {
  var target = !!value;
  if (dhwReadBool(path) !== target) dev[path] = target;
}

function dhwWriteNumIfNeeded(path, value, eps) {
  var cur = dhwReadNum(path);
  var e = eps || 0.1;
  if (cur === null || Math.abs(cur - value) > e) dev[path] = value;
}

function dhwJoinStatus(a, b, c) {
  var out = [];
  if (a) out.push(a);
  if (b) out.push(b);
  if (c) out.push(c);
  return out.join(" | ");
}

function dhwPauseActive() { return dhwReadBool("boiler_room_boiler/ch_pause_active"); }
function dhwPauseSetpoint() { return dhwClamp(dhwReadNum("boiler_room_boiler/ch_pause_setpoint"), 10, 25); }

function dhwApplyNormalSetpoint(cfg) {
  var target = dhwGetNormalSafeTarget(cfg);
  dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, target, 0.1);
}

function dhwGetNormalSafeTarget(cfg) {
  return dhwPauseActive() ? dhwPauseSetpoint() : cfg.normalSetpoint;
}

function dhwSetUi(mode, line1, line2, line3) {
  var pauseMode = "no_pause";
  var pauseActive = false;

  if (mode === "priority_heat") {
    pauseMode = "priority_heat";
    pauseActive = true;
  } else if (mode === "restore") {
    pauseMode = "restore";
    pauseActive = true;
  }

  dev["dhw_priority_mgr/mode"] = mode || "disabled";
  dev["dhw_priority_mgr/heating_pause_mode"] = pauseMode;
  dev["dhw_priority_mgr/heating_pause_active"] = pauseActive;
  dev["dhw_priority_mgr/status_line1"] = line1 || "";
  dev["dhw_priority_mgr/status_line2"] = line2 || "";
  dev["dhw_priority_mgr/status_line3"] = line3 || "";
  dev["dhw_priority_mgr/status_text"] = dhwJoinStatus(line1, line2, line3);
}

function dhwReadConfig() {
  return {
    enabled: dhwReadBool("dhw_priority_mgr/enabled"),
    normalSetpoint: dhwClamp(dev["dhw_priority_mgr/normal_setpoint"], 40, 70),
    normalHyst: dhwClamp(dev["dhw_priority_mgr/normal_hysteresis"], 1, 15),
    priorityTrigger: dhwClamp(dev["dhw_priority_mgr/priority_trigger"], 35, 70),
    priorityTarget: dhwClamp(dev["dhw_priority_mgr/priority_target"], 45, 85),
    priorityBoilerSp: dhwClamp(dev["dhw_priority_mgr/priority_boiler_setpoint"], 45, 85),
    tickS: dhwClamp(dev["dhw_priority_mgr/tick_s"], 5, 300),
    restoreDelayS: dhwClamp(dev["dhw_priority_mgr/restore_delay_s"], 0, 600),
    priorityTimeoutMin: dhwClamp(dev["dhw_priority_mgr/priority_timeout_min"], 5, 180)
  };
}

defineVirtualDevice("dhw_priority_mgr", {
  title: "ГВС / Приоритет бойлера",
  cells: {
    enabled: { type: "switch", value: DEFAULT_ENABLED, title: "Логика приоритета ГВС включена" },
    normal_setpoint: { type: "range", value: DEFAULT_NORMAL_SETPOINT_C, min: 40, max: 70, step: 1, title: "Обычная уставка бойлера, °C" },
    normal_hysteresis: { type: "range", value: DEFAULT_NORMAL_HYST_C, min: 1, max: 15, step: 1, title: "Гистерезис обычного режима, °C" },
    priority_trigger: { type: "range", value: DEFAULT_PRIORITY_TRIGGER_C, min: 35, max: 70, step: 1, title: "Порог входа в приоритет, °C" },
    priority_target: { type: "range", value: DEFAULT_PRIORITY_TARGET_C, min: 45, max: 85, step: 1, title: "Цель приоритета, °C" },
    priority_boiler_setpoint: { type: "range", value: DEFAULT_PRIORITY_BOILER_SP_C, min: 45, max: 85, step: 1, title: "Уставка котла в приоритете, °C" },
    tick_s: { type: "range", value: DEFAULT_TICK_S, min: 5, max: 300, step: 5, title: "Период проверки, с" },
    restore_delay_s: { type: "range", value: DEFAULT_RESTORE_DELAY_S, min: 0, max: 600, step: 5, title: "Задержка режима restore, с" },
    priority_timeout_min: { type: "range", value: DEFAULT_PRIORITY_TIMEOUT_MIN, min: 5, max: 180, step: 1, title: "Таймаут приоритета, мин" },

    boiler_temp: { type: "value", value: 0, readonly: true, title: "Температура бойлера, °C" },
    target_temp: { type: "value", value: 0, readonly: true, title: "Текущая цель бойлера, °C" },
    boiler_setpoint_now: { type: "value", value: 0, readonly: true, title: "Текущая уставка котла, °C" },
    saved_boiler_setpoint: { type: "value", value: 0, readonly: true, title: "Сохранённая уставка котла, °C" },
    pump_dhw: { type: "switch", value: false, readonly: true, title: "Насос бойлера" },

    heating_pause_active: { type: "switch", value: false, readonly: true, title: "Пауза отопления активна" },
    heating_pause_mode: {
      type: "text",
      value: "no_pause",
      readonly: true,
      title: "Режим паузы отопления (no_pause/priority_heat/restore)"
    },

    mode: { type: "text", value: "disabled", readonly: true, title: "Режим менеджера ГВС" },
    status_line1: { type: "text", value: "", readonly: true, title: "Статус 1" },
    status_line2: { type: "text", value: "", readonly: true, title: "Статус 2" },
    status_line3: { type: "text", value: "", readonly: true, title: "Статус 3" },
    status_text: { type: "text", value: "", readonly: true, title: "Краткий статус" },

    alarm_active: { type: "switch", value: false, readonly: true, title: "Авария менеджера ГВС" },
    alarm_text: { type: "text", value: "", readonly: true, title: "Текст аварии" }
  }
});

var mgr = {
  state: "disabled",
  savedBoilerSetpoint: null,
  priorityStartedTs: 0,
  restoreDeadlineTs: 0,
  lastAlarm: false,
  alarmText: "",
  loopTimer: null
};

function dhwSetSavedSetpoint(value) {
  var v = dhwClamp(value, 10, 90);
  mgr.savedBoilerSetpoint = v;
  dev["dhw_priority_mgr/saved_boiler_setpoint"] = dhwRound1(v);
}

function dhwGetSavedSetpoint() {
  var persisted;
  if (mgr.savedBoilerSetpoint !== null) return mgr.savedBoilerSetpoint;
  persisted = dhwReadNum("dhw_priority_mgr/saved_boiler_setpoint");
  if (persisted !== null && persisted > 0) {
    mgr.savedBoilerSetpoint = persisted;
    return persisted;
  }
  return null;
}

function dhwClearSavedSetpoint() {
  mgr.savedBoilerSetpoint = null;
  dev["dhw_priority_mgr/saved_boiler_setpoint"] = 0;
}

function dhwRememberBoilerSetpointForPriority(cfg) {
  var existing = dhwGetSavedSetpoint();
  var current;

  if (existing !== null) return;

  current = dhwReadNum(BOILER_SETPOINT_CH);

  if (current === null) {
    dhwSetSavedSetpoint(cfg.normalSetpoint);
    return;
  }

  /*
   * Если wb-rules перезапустился в момент уже активного приоритета,
   * на входе можем увидеть текущую уставку = priority_boiler_setpoint.
   * В этом случае нельзя сохранять её как "исходную".
   */
  if (Math.abs(current - cfg.priorityBoilerSp) <= 0.3) {
    dhwSetSavedSetpoint(cfg.normalSetpoint);
    return;
  }

  dhwSetSavedSetpoint(current);
}

function dhwGetFinalSafeSetpoint(cfg) {
  var saved;

  if (dhwPauseActive()) return dhwPauseSetpoint();

  saved = dhwGetSavedSetpoint();
  if (saved !== null) return saved;

  return cfg.normalSetpoint;
}

function dhwApplyFinalSafeSetpoint(cfg) {
  dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, dhwGetFinalSafeSetpoint(cfg), 0.1);
}

function dhwSyncLiveValues() {
  var t = dhwReadNum(DHW_TEMP_SENSOR);
  var sp = dhwReadNum(BOILER_SETPOINT_CH);
  var cfg = dhwReadConfig();
  var target;

  if (mgr.state === "priority_heat") {
    target = cfg.priorityTarget;
  } else if (mgr.state === "restore") {
    target = dhwGetFinalSafeSetpoint(cfg);
  } else {
    target = dhwGetNormalSafeTarget(cfg);
  }

  dev["dhw_priority_mgr/boiler_temp"] = (t === null ? 0 : dhwRound1(t));
  dev["dhw_priority_mgr/target_temp"] = dhwRound1(target);
  dev["dhw_priority_mgr/boiler_setpoint_now"] = (sp === null ? 0 : dhwRound1(sp));
  dev["dhw_priority_mgr/saved_boiler_setpoint"] = (dhwGetSavedSetpoint() === null ? 0 : dhwRound1(dhwGetSavedSetpoint()));
  dev["dhw_priority_mgr/pump_dhw"] = dhwReadBool(PUMP_DHW);
  dev["dhw_priority_mgr/alarm_active"] = mgr.lastAlarm;
  dev["dhw_priority_mgr/alarm_text"] = mgr.alarmText || "";
}

function dhwSetAlarm(text) {
  mgr.lastAlarm = true;
  mgr.alarmText = text || "неизвестная ошибка";
  dev["dhw_priority_mgr/alarm_active"] = true;
  dev["dhw_priority_mgr/alarm_text"] = mgr.alarmText;
}

function dhwClearAlarm() {
  mgr.lastAlarm = false;
  mgr.alarmText = "";
  dev["dhw_priority_mgr/alarm_active"] = false;
  dev["dhw_priority_mgr/alarm_text"] = "";
}

function dhwEnableDhwPump() { dhwWriteBoolIfNeeded(PUMP_DHW, true); }
function dhwDisableDhwPump() { dhwWriteBoolIfNeeded(PUMP_DHW, false); }

function dhwExitPriorityToSafeNormal(cfg) {
  var wasPriorityActive = (mgr.state === "priority_heat" || mgr.state === "restore");
  var saved = dhwGetSavedSetpoint();
  var finalSetpoint;

  if (dhwPauseActive()) {
    finalSetpoint = dhwPauseSetpoint();
  } else if (wasPriorityActive && saved !== null) {
    finalSetpoint = saved;
  } else {
    finalSetpoint = cfg.normalSetpoint;
  }

  dhwDisableDhwPump();

  /*
   * Сначала очищаем внутренний saved-state,
   * затем применяем уже заранее рассчитанную итоговую уставку.
   * Так stale saved значение не становится "актуальной целью"
   * при disable/alarm вне реального выхода из priority/restore.
   */
  dhwClearSavedSetpoint();
  dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, finalSetpoint, 0.1);

  mgr.priorityStartedTs = 0;
  mgr.restoreDeadlineTs = 0;
}

function dhwEnterDisabled(cfg) {
  mgr.state = "disabled";
  dhwExitPriorityToSafeNormal(cfg);
  dhwClearAlarm();
  dhwSetUi("disabled", "Логика приоритета ГВС выключена", "Уставка котла приведена к безопасному состоянию", "Скрипт не вмешивается в насосы отопления");
  dhwSyncLiveValues();
}

function dhwEnterIdle(t, cfg) {
  mgr.state = "idle";
  dhwClearAlarm();
  dhwDisableDhwPump();
  dhwApplyNormalSetpoint(cfg);
  dhwSetUi("idle", "Бойлер в обычном диапазоне", "Целевая уставка котла: " + dhwRound1(dhwGetNormalSafeTarget(cfg)) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Антициклирование не активно"));
  dhwSyncLiveValues();
}

function dhwEnterNormalHeat(t, cfg) {
  mgr.state = "normal_heat";
  dhwClearAlarm();
  dhwEnableDhwPump();
  dhwApplyNormalSetpoint(cfg);
  dhwSetUi("normal_heat", "Обычный нагрев бойлера", "Целевая уставка котла: " + dhwRound1(dhwGetNormalSafeTarget(cfg)) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Насос бойлера включён"));
  dhwSyncLiveValues();
}

function dhwEnterPriorityHeat(t, cfg) {
  mgr.state = "priority_heat";
  mgr.priorityStartedTs = dhwNowSec();
  mgr.restoreDeadlineTs = 0;
  dhwRememberBoilerSetpointForPriority(cfg);
  dhwEnableDhwPump();
  dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, cfg.priorityBoilerSp, 0.1);
  dhwClearAlarm();
  dhwSetUi("priority_heat", "Включён приоритет ГВС", "Отопление должно быть остановлено внешними модулями", "Цель бойлера: " + dhwRound1(cfg.priorityTarget) + " °C");
  dhwSyncLiveValues();
}

function dhwEnterRestore(t, cfg) {
  mgr.state = "restore";
  mgr.restoreDeadlineTs = dhwNowSec() + cfg.restoreDelayS;
  dhwDisableDhwPump();
  dhwApplyFinalSafeSetpoint(cfg);
  dhwSetUi("restore", "Цель приоритета достигнута", "Идёт безопасный возврат уставки котла", "До no_pause: " + cfg.restoreDelayS + " с");
  dhwSyncLiveValues();
}

function dhwFinishRestore(t, cfg) {
  dhwExitPriorityToSafeNormal(cfg);
  dhwEnterIdle(t, cfg);
}

function dhwEnterAlarm(cfg, reason) {
  mgr.state = "alarm";
  dhwExitPriorityToSafeNormal(cfg);
  dhwSetAlarm(reason);
  dhwSetUi("alarm", "Ошибка менеджера ГВС", reason, "Уставка котла и насос ГВС переведены в безопасное состояние");
  dhwSyncLiveValues();
}

function dhwCheckPriorityFaults(t, cfg) {
  var ts = dhwNowSec();
  if (t === null) return "нет температуры бойлера";
  if (!dhwReadBool(PUMP_DHW)) return "насос бойлера должен быть включён";
  if (mgr.priorityStartedTs > 0) {
    var elapsed = ts - mgr.priorityStartedTs;
    if (elapsed >= cfg.priorityTimeoutMin * 60) return "таймаут приоритетного нагрева бойлера";
  }
  return "";
}

function dhwManagerStep() {
  var cfg = dhwReadConfig();
  var t = dhwReadNum(DHW_TEMP_SENSOR);
  var normalOnThreshold;
  var faultText;

  dhwSyncLiveValues();

  if (!cfg.enabled) {
    dhwEnterDisabled(cfg);
    return;
  }

  if (t === null) {
    dhwEnterAlarm(cfg, "нет данных датчика температуры бойлера");
    return;
  }

  normalOnThreshold = cfg.normalSetpoint - cfg.normalHyst;

  if (mgr.state === "disabled") {
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t <= normalOnThreshold) { dhwEnterNormalHeat(t, cfg); return; }
    dhwEnterIdle(t, cfg);
    return;
  }

  if (mgr.state === "alarm") {
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t <= normalOnThreshold) { dhwEnterNormalHeat(t, cfg); return; }
    dhwEnterIdle(t, cfg);
    return;
  }

  if (mgr.state === "idle") {
    dhwDisableDhwPump();
    dhwApplyNormalSetpoint(cfg);
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t <= normalOnThreshold) { dhwEnterNormalHeat(t, cfg); return; }
    dhwSetUi("idle", "Бойлер в обычном диапазоне", "Целевая уставка котла: " + dhwRound1(dhwGetNormalSafeTarget(cfg)) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Антициклирование не активно"));
    dhwSyncLiveValues();
    return;
  }

  if (mgr.state === "normal_heat") {
    dhwEnableDhwPump();
    dhwApplyNormalSetpoint(cfg);
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t >= cfg.normalSetpoint) { dhwEnterIdle(t, cfg); return; }
    dhwSetUi("normal_heat", "Бойлер греется в обычном режиме", "Целевая уставка котла: " + dhwRound1(dhwGetNormalSafeTarget(cfg)) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Насос бойлера включён"));
    dhwSyncLiveValues();
    return;
  }

  if (mgr.state === "priority_heat") {
    dhwEnableDhwPump();
    dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, cfg.priorityBoilerSp, 0.1);
    faultText = dhwCheckPriorityFaults(t, cfg);
    if (faultText) { dhwEnterAlarm(cfg, faultText); return; }
    if (t >= cfg.priorityTarget) { dhwEnterRestore(t, cfg); return; }
    dhwSetUi("priority_heat", "Отопление в паузе из-за ГВС", "Котёл: " + dhwRound1(cfg.priorityBoilerSp) + " °C", "Текущая температура бойлера: " + dhwRound1(t) + " °C");
    dhwSyncLiveValues();
    return;
  }

  if (mgr.state === "restore") {
    dhwDisableDhwPump();
    dhwApplyFinalSafeSetpoint(cfg);
    if (dhwNowSec() >= mgr.restoreDeadlineTs) { dhwFinishRestore(t, cfg); return; }
    dhwSetUi("restore", "Ожидание завершения restore", "Уставка котла уже в финальном безопасном значении", "Осталось: " + Math.max(0, mgr.restoreDeadlineTs - dhwNowSec()) + " с");
    dhwSyncLiveValues();
    return;
  }

  dhwEnterAlarm(cfg, "неизвестное состояние менеджера ГВС");
}

function dhwRestartLoop() {
  if (mgr.loopTimer) {
    clearInterval(mgr.loopTimer);
    mgr.loopTimer = null;
  }
  mgr.loopTimer = setInterval(function () {
    dhwManagerStep();
  }, Math.round(dhwReadConfig().tickS * 1000));
}

defineRule("dhw_priority_on_temp_change", {
  whenChanged: DHW_TEMP_SENSOR,
  then: dhwManagerStep
});

defineRule("dhw_priority_on_enabled_change", {
  whenChanged: "dhw_priority_mgr/enabled",
  then: dhwManagerStep
});

defineRule("dhw_priority_on_config_change", {
  whenChanged: [
    "dhw_priority_mgr/normal_setpoint",
    "dhw_priority_mgr/normal_hysteresis",
    "dhw_priority_mgr/priority_trigger",
    "dhw_priority_mgr/priority_target",
    "dhw_priority_mgr/priority_boiler_setpoint",
    "dhw_priority_mgr/restore_delay_s",
    "dhw_priority_mgr/priority_timeout_min"
  ],
  then: dhwManagerStep
});

defineRule("dhw_priority_on_tick_change", {
  whenChanged: "dhw_priority_mgr/tick_s",
  then: dhwRestartLoop
});

defineRule("dhw_priority_periodic_safety", {
  when: cron("0 */1 * * * *"),
  then: dhwManagerStep
});

dhwRestartLoop();
dhwManagerStep();
