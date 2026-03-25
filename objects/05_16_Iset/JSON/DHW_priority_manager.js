/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: 05 16 Исеть - DHW_priority_manager.js
 * -------------------------------------------------------------
 * Менеджер приоритета ГВС.
 *
 * НАЗНАЧЕНИЕ
 * -------------------------------------------------------------
 * Скрипт управляет нагревом бойлера косвенного нагрева и
 * приоритетом ГВС через:
 *   - насос бойлера
 *   - временное отключение отопительных насосов
 *   - временное повышение уставки котла
 *
 * АРХИТЕКТУРА
 * -------------------------------------------------------------
 * 1. Этот модуль отвечает ТОЛЬКО за контур ГВС.
 * 2. Boiler_room.js остаётся модулем мониторинга и аварий.
 * 3. Насосом ГВС должен управлять только этот сценарий.
 *
 * ЛОГИКА
 * -------------------------------------------------------------
 * Обычный режим:
 *   - уставка бойлера по умолчанию: 52 °C
 *   - гистерезис обычного режима: 3 °C
 *   - если температура <= 49 °C -> обычный нагрев
 *   - если температура >= 52 °C -> насос бойлера выключается
 *
 * Приоритетный режим ГВС:
 *   - если температура бойлера < 49 °C -> приоритет ГВС
 *   - сохраняется текущая уставка котла
 *   - котлу задаётся 80 °C
 *   - насосы отопления K2/K3/K4 временно отключаются
 *   - насос бойлера включается
 *   - при достижении 65 °C:
 *       насос бойлера выключается,
 *       уставка котла возвращается,
 *       через короткую задержку возвращаются насосы отопления
 *
 * ВАЖНО
 * -------------------------------------------------------------
 * Этот модуль должен быть единственным, кто пишет в:
 *   wb-mr6cu_37/K1
 *   wbe2-i-opentherm_11/Heating Setpoint
 *   wb-mr6cu_37/K2
 *   wb-mr6cu_37/K3
 *   wb-mr6cu_37/K4
 *
 * ПРИМЕЧАНИЕ ПО ПАНЕЛИ
 * -------------------------------------------------------------
 * Виртуальное устройство разделено по смыслу:
 *   - настройки, которые меняют редко
 *   - оперативные статусы, которые удобно читать в виджете
 *
 * Здесь оставлены только полезные эксплуатационные поля.
 * Технические unix-времена и дублирующие статусы убраны из UI.
 ***************************************************************/

var DHW_TEMP_SENSOR        = "wb-w1/28-00000fd7811a";
var BOILER_SETPOINT_CH     = "wbe2-i-opentherm_11/Heating Setpoint";

var PUMP_DHW               = "wb-mr6cu_37/K1";
var PUMP_FLOOR             = "wb-mr6cu_37/K2";
var PUMP_RAD_BASE          = "wb-mr6cu_37/K3";
var PUMP_RAD_LIVING        = "wb-mr6cu_37/K4";

var DEFAULT_ENABLED                = false;
var DEFAULT_NORMAL_SETPOINT_C      = 52;
var DEFAULT_NORMAL_HYST_C          = 3;
var DEFAULT_PRIORITY_TRIGGER_C     = 49;
var DEFAULT_PRIORITY_TARGET_C      = 65;
var DEFAULT_PRIORITY_BOILER_SP_C   = 80;
var DEFAULT_TICK_S                 = 15;
var DEFAULT_RESTORE_DELAY_S        = 30;
var DEFAULT_PRIORITY_TIMEOUT_MIN   = 50;

function dhwNowSec() { return Math.floor(Date.now() / 1000); }
function dhwRound1(v) { return Math.round(v * 10) / 10; }
function dhwToBool(v) {
  if (v === true || v === 1 || v === "1") return true;
  if (v === false || v === 0 || v === "0" || v === null || v === undefined) return false;
  return !!v;
}
function dhwReadNum(path) { try { var v = parseFloat(dev[path]); return isNaN(v) ? null : v; } catch (e) { return null; } }
function dhwReadBool(path) { try { return dhwToBool(dev[path]); } catch (e) { return false; } }
function dhwClamp(v, minV, maxV) { v = Number(v); if (isNaN(v)) v = minV; if (v < minV) return minV; if (v > maxV) return maxV; return v; }
function dhwWriteBoolIfNeeded(path, value) { var t = !!value; if (dhwReadBool(path) !== t) dev[path] = t; }
function dhwWriteNumIfNeeded(path, value, eps) { var c = dhwReadNum(path); if (c === null || Math.abs(c - value) > (eps || 0.1)) dev[path] = value; }
function dhwJoinStatus(a, b, c) { var out = []; if (a) out.push(a); if (b) out.push(b); if (c) out.push(c); return out.join(" | "); }
function dhwPauseActive() { return dhwReadBool("boiler_room_boiler/ch_pause_active"); }
function dhwPauseSetpoint() { return dhwClamp(dhwReadNum("boiler_room_boiler/ch_pause_setpoint"), 10, 25); }
function dhwApplyNormalSetpoint(cfg) {
  var target = dhwPauseActive() ? dhwPauseSetpoint() : cfg.normalSetpoint;
  dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, target, 0.1);
}
function dhwSetUi(mode, line1, line2, line3) {
  dev["dhw_priority_mgr/mode"] = mode || "";
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
    restore_delay_s: { type: "range", value: DEFAULT_RESTORE_DELAY_S, min: 0, max: 600, step: 5, title: "Задержка возврата отопления, с" },
    priority_timeout_min: { type: "range", value: DEFAULT_PRIORITY_TIMEOUT_MIN, min: 5, max: 180, step: 1, title: "Таймаут приоритета, мин" },
    boiler_temp: { type: "value", value: 0, readonly: true, title: "Температура бойлера, °C" },
    target_temp: { type: "value", value: 0, readonly: true, title: "Текущая цель бойлера, °C" },
    boiler_setpoint_now: { type: "value", value: 0, readonly: true, title: "Текущая уставка котла, °C" },
    saved_boiler_setpoint: { type: "value", value: 0, readonly: true, title: "Сохранённая уставка котла, °C" },
    pump_dhw: { type: "switch", value: false, readonly: true, title: "Насос бойлера" },
    pump_floor: { type: "switch", value: false, readonly: true, title: "Насос тёплого пола" },
    pump_rad_base: { type: "switch", value: false, readonly: true, title: "Насос радиаторов цоколь" },
    pump_rad_living: { type: "switch", value: false, readonly: true, title: "Насос радиаторов жилой этаж" },
    heating_paused: { type: "switch", value: false, readonly: true, title: "Отопление временно остановлено" },
    priority_active: { type: "switch", value: false, readonly: true, title: "Приоритет ГВС активен" },
    mode: { type: "text", value: "выключено", readonly: true, title: "Режим" },
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
  pumpsBeforePriority: { floor: false, radBase: false, radLiving: false },
  priorityStartedTs: 0,
  restoreDeadlineTs: 0,
  lastAlarm: false,
  alarmText: "",
  loopTimer: null
};

function dhwSyncLiveValues() {
  var t = dhwReadNum(DHW_TEMP_SENSOR);
  var sp = dhwReadNum(BOILER_SETPOINT_CH);
  var cfg = dhwReadConfig();
  var target = (mgr.state === "priority_heat" || mgr.state === "restore") ? cfg.priorityTarget : cfg.normalSetpoint;

  dev["dhw_priority_mgr/boiler_temp"] = (t === null ? 0 : dhwRound1(t));
  dev["dhw_priority_mgr/target_temp"] = dhwRound1(target);
  dev["dhw_priority_mgr/boiler_setpoint_now"] = (sp === null ? 0 : dhwRound1(sp));
  dev["dhw_priority_mgr/saved_boiler_setpoint"] = (mgr.savedBoilerSetpoint === null ? 0 : dhwRound1(mgr.savedBoilerSetpoint));
  dev["dhw_priority_mgr/pump_dhw"] = dhwReadBool(PUMP_DHW);
  dev["dhw_priority_mgr/pump_floor"] = dhwReadBool(PUMP_FLOOR);
  dev["dhw_priority_mgr/pump_rad_base"] = dhwReadBool(PUMP_RAD_BASE);
  dev["dhw_priority_mgr/pump_rad_living"] = dhwReadBool(PUMP_RAD_LIVING);
  dev["dhw_priority_mgr/priority_active"] = (mgr.state === "priority_heat" || mgr.state === "restore");
  dev["dhw_priority_mgr/heating_paused"] = (mgr.state === "priority_heat" || mgr.state === "restore");
  dev["dhw_priority_mgr/alarm_active"] = mgr.lastAlarm;
  dev["dhw_priority_mgr/alarm_text"] = mgr.alarmText || "";
}
function dhwSetAlarm(text) { mgr.lastAlarm = true; mgr.alarmText = text || "неизвестная ошибка"; dev["dhw_priority_mgr/alarm_active"] = true; dev["dhw_priority_mgr/alarm_text"] = mgr.alarmText; }
function dhwClearAlarm() { mgr.lastAlarm = false; mgr.alarmText = ""; dev["dhw_priority_mgr/alarm_active"] = false; dev["dhw_priority_mgr/alarm_text"] = ""; }

function dhwRememberHeatingPumpsState() {
  mgr.pumpsBeforePriority.floor = dhwReadBool(PUMP_FLOOR);
  mgr.pumpsBeforePriority.radBase = dhwReadBool(PUMP_RAD_BASE);
  mgr.pumpsBeforePriority.radLiving = dhwReadBool(PUMP_RAD_LIVING);
}
function dhwDisableHeatingPumps() { dhwWriteBoolIfNeeded(PUMP_FLOOR, false); dhwWriteBoolIfNeeded(PUMP_RAD_BASE, false); dhwWriteBoolIfNeeded(PUMP_RAD_LIVING, false); }
function dhwRestoreHeatingPumps() { dhwWriteBoolIfNeeded(PUMP_FLOOR, mgr.pumpsBeforePriority.floor); dhwWriteBoolIfNeeded(PUMP_RAD_BASE, mgr.pumpsBeforePriority.radBase); dhwWriteBoolIfNeeded(PUMP_RAD_LIVING, mgr.pumpsBeforePriority.radLiving); }
function dhwSaveBoilerSetpointIfNeeded() { if (mgr.savedBoilerSetpoint !== null) return; var current = dhwReadNum(BOILER_SETPOINT_CH); mgr.savedBoilerSetpoint = (current === null ? 60 : current); dev["dhw_priority_mgr/saved_boiler_setpoint"] = dhwRound1(mgr.savedBoilerSetpoint); }
function dhwSetPriorityBoilerSetpoint(cfg) { dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, cfg.priorityBoilerSp, 0.1); }
function dhwRestoreBoilerSetpoint() { if (mgr.savedBoilerSetpoint === null) return; dhwWriteNumIfNeeded(BOILER_SETPOINT_CH, mgr.savedBoilerSetpoint, 0.1); }
function dhwEnableDhwPump() { dhwWriteBoolIfNeeded(PUMP_DHW, true); }
function dhwDisableDhwPump() { dhwWriteBoolIfNeeded(PUMP_DHW, false); }
function dhwSafeRestoreOutputs() { dhwDisableDhwPump(); dhwRestoreBoilerSetpoint(); dhwRestoreHeatingPumps(); }

function dhwEnterDisabled() { mgr.state = "disabled"; dhwSetUi("выключено", "Логика приоритета ГВС выключена", "Скрипт не вмешивается в работу контура", ""); dhwSyncLiveValues(); }
function dhwEnterIdle(t, cfg) { mgr.state = "idle"; dhwClearAlarm(); dhwApplyNormalSetpoint(cfg); dhwSetUi("норма", "Бойлер в обычном диапазоне", "Уставка: " + dhwRound1(cfg.normalSetpoint) + " °C, нижняя граница: " + dhwRound1(cfg.normalSetpoint - cfg.normalHyst) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Текущая температура: " + (t === null ? "нет данных" : dhwRound1(t) + " °C"))); dhwSyncLiveValues(); }
function dhwEnterNormalHeat(t, cfg) { mgr.state = "normal_heat"; dhwClearAlarm(); dhwEnableDhwPump(); dhwApplyNormalSetpoint(cfg); dhwSetUi("обычный нагрев", "Бойлер ниже обычной уставки", "Насос бойлера включён до " + dhwRound1(cfg.normalSetpoint) + " °C", "Текущая температура: " + (t === null ? "нет данных" : dhwRound1(t) + " °C")); dhwSyncLiveValues(); }
function dhwEnterPriorityHeat(t, cfg) {
  var ts = dhwNowSec();
  dhwSaveBoilerSetpointIfNeeded();
  dhwRememberHeatingPumpsState();
  mgr.state = "priority_heat";
  mgr.priorityStartedTs = ts;
  mgr.restoreDeadlineTs = 0;
  dhwDisableHeatingPumps();
  dhwEnableDhwPump();
  dhwSetPriorityBoilerSetpoint(cfg);
  dhwClearAlarm();
  dhwSetUi("приоритет ГВС", "Обнаружен сильный разбор горячей воды", "Котёл переведён на " + dhwRound1(cfg.priorityBoilerSp) + " °C, отопление временно отключено", "Греем бойлер до " + dhwRound1(cfg.priorityTarget) + " °C");
  dhwSyncLiveValues();
}
function dhwEnterRestore(t, cfg) { mgr.state = "restore"; mgr.restoreDeadlineTs = dhwNowSec() + cfg.restoreDelayS; dhwDisableDhwPump(); dhwRestoreBoilerSetpoint(); dhwSetUi("возврат в норму", "Цель приоритета достигнута", "Насос бойлера выключен, уставка котла возвращается", "Отопление будет восстановлено через " + cfg.restoreDelayS + " с"); dhwSyncLiveValues(); }
function dhwFinishRestore(t) { dhwRestoreHeatingPumps(); mgr.savedBoilerSetpoint = null; mgr.priorityStartedTs = 0; mgr.restoreDeadlineTs = 0; mgr.state = "idle"; dhwSetUi("норма", "Приоритет ГВС завершён", "Котловая уставка и отопительные насосы восстановлены", "Текущая температура бойлера: " + (t === null ? "нет данных" : dhwRound1(t) + " °C")); dhwSyncLiveValues(); }
function dhwEnterAlarm(t, reason) { dhwSafeRestoreOutputs(); mgr.state = "alarm"; mgr.restoreDeadlineTs = 0; mgr.priorityStartedTs = 0; mgr.savedBoilerSetpoint = null; dhwSetAlarm(reason); dhwSetUi("авария", "Ошибка менеджера ГВС", reason, "Приоритет снят, система возвращена в безопасное состояние"); dhwSyncLiveValues(); }

function dhwCheckPriorityFaults(t, cfg) {
  var ts = dhwNowSec();
  if (t === null) return "нет температуры бойлера";
  if (!dhwReadBool(PUMP_DHW)) return "насос бойлера должен быть включён, но остаётся выключенным";
  if (mgr.priorityStartedTs > 0) {
    var elapsed = ts - mgr.priorityStartedTs;
    if (elapsed >= cfg.priorityTimeoutMin * 60) return "таймаут приоритетного нагрева бойлера";
  }
  return "";
}

function dhwManagerStep() {
  var cfg = dhwReadConfig();
  var t = dhwReadNum(DHW_TEMP_SENSOR);
  dhwSyncLiveValues();

  if (!cfg.enabled) { dhwEnterDisabled(); return; }
  if (t === null) { dhwEnterAlarm(t, "нет данных датчика температуры бойлера"); return; }

  var normalOnThreshold = cfg.normalSetpoint - cfg.normalHyst;

  if (mgr.state === "disabled") {
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t <= normalOnThreshold) { dhwEnterNormalHeat(t, cfg); return; }
    dhwEnterIdle(t, cfg); return;
  }

  if (mgr.state === "alarm") { if (t >= normalOnThreshold) dhwEnterIdle(t, cfg); else dhwEnterNormalHeat(t, cfg); return; }

  if (mgr.state === "idle") {
    dhwDisableDhwPump();
    dhwApplyNormalSetpoint(cfg);
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t <= normalOnThreshold) { dhwEnterNormalHeat(t, cfg); return; }
    dhwSetUi("норма", "Бойлер в обычном диапазоне", "Уставка: " + dhwRound1(cfg.normalSetpoint) + " °C, нижняя граница: " + dhwRound1(normalOnThreshold) + " °C", (dhwPauseActive() ? "Антициклирование активно" : "Текущая температура: " + dhwRound1(t) + " °C"));
    dhwSyncLiveValues(); return;
  }

  if (mgr.state === "normal_heat") {
    dhwEnableDhwPump();
    dhwApplyNormalSetpoint(cfg);
    if (t < cfg.priorityTrigger) { dhwEnterPriorityHeat(t, cfg); return; }
    if (t >= cfg.normalSetpoint) { dhwDisableDhwPump(); dhwEnterIdle(t, cfg); return; }
    dhwSetUi("обычный нагрев", "Бойлер греется в обычном режиме", "Насос бойлера включён до " + dhwRound1(cfg.normalSetpoint) + " °C", "Текущая температура: " + dhwRound1(t) + " °C");
    dhwSyncLiveValues(); return;
  }

  if (mgr.state === "priority_heat") {
    dhwDisableHeatingPumps();
    dhwEnableDhwPump();
    dhwSetPriorityBoilerSetpoint(cfg);
    var faultText = dhwCheckPriorityFaults(t, cfg);
    if (faultText) { dhwEnterAlarm(t, faultText); return; }
    if (t >= cfg.priorityTarget) { dhwEnterRestore(t, cfg); return; }
    var elapsedMin = 0; if (mgr.priorityStartedTs > 0) elapsedMin = Math.floor((dhwNowSec() - mgr.priorityStartedTs) / 60);
    dhwSetUi("приоритет ГВС", "Отопление временно отключено, бойлер греется в приоритете", "Котёл: " + dhwRound1(cfg.priorityBoilerSp) + " °C, цель бойлера: " + dhwRound1(cfg.priorityTarget) + " °C", "Текущая температура: " + dhwRound1(t) + " °C, время в режиме: " + elapsedMin + " мин");
    dhwSyncLiveValues(); return;
  }

  if (mgr.state === "restore") {
    dhwDisableDhwPump();
    dhwRestoreBoilerSetpoint();
    if (dhwNowSec() >= mgr.restoreDeadlineTs) { dhwFinishRestore(t); return; }
    dhwSetUi("возврат в норму", "Ожидание восстановления отопительных насосов", "Уставка котла уже возвращена к исходной", "До возврата насосов осталось " + Math.max(0, mgr.restoreDeadlineTs - dhwNowSec()) + " с");
    dhwSyncLiveValues(); return;
  }

  dhwEnterAlarm(t, "неизвестное состояние менеджера ГВС");
}

function dhwRestartLoop() {
  if (mgr.loopTimer) { clearInterval(mgr.loopTimer); mgr.loopTimer = null; }
  var tickS = dhwReadConfig().tickS;
  mgr.loopTimer = setInterval(function () { dhwManagerStep(); }, Math.round(tickS * 1000));
}

defineRule("dhw_priority_on_temp_change", { whenChanged: DHW_TEMP_SENSOR, then: dhwManagerStep });
defineRule("dhw_priority_on_enabled_change", {
  whenChanged: "dhw_priority_mgr/enabled",
  then: function () {
    if (!dhwReadBool("dhw_priority_mgr/enabled")) {
      dhwSafeRestoreOutputs();
      mgr.savedBoilerSetpoint = null;
      mgr.priorityStartedTs = 0;
      mgr.restoreDeadlineTs = 0;
      dhwClearAlarm();
      mgr.state = "disabled";
    }
    dhwManagerStep();
  }
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
defineRule("dhw_priority_on_tick_change", { whenChanged: "dhw_priority_mgr/tick_s", then: dhwRestartLoop });
defineRule("dhw_priority_periodic_safety", { when: cron("0 */1 * * * *"), then: dhwManagerStep });

dhwRestartLoop();
dhwManagerStep();
