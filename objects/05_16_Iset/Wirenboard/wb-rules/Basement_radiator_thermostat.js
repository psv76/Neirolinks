/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: Basement_radiator_thermostat.js (ВРЕМЕННЫЙ)
 * -------------------------------------------------------------
 * Временный комнатный термостат цоколя.
 *
 * ЕДИНСТВЕННЫЙ ПИСАТЕЛЬ:
 *   wb-mr6cu_37/K3 (насос радиаторов цоколя)
 *
 * ИСТОЧНИКИ ТЕМПЕРАТУРЫ ЦОКОЛЯ (подтверждены по конфигурации):
 *   wb-msw-v4_45/Temperature
 *   wb-msw-v4_61/Temperature
 *   wb-msw-v4_202/Temperature
 *   wb-msw-v4_209/Temperature
 *
 * Логика:
 * 1) Если dhw_priority_mgr/heating_pause_mode = priority_heat или restore,
 *    насос K3 принудительно выключается.
 * 2) Иначе работает простой общий термостат с гистерезисом:
 *    - если хотя бы один датчик ниже нижней границы -> K3 = 1
 *    - если все датчики выше верхней границы -> K3 = 0
 ***************************************************************/

var BRT_PUMP_BASEMENT = "wb-mr6cu_37/K3";
var BRT_DHW_PAUSE_MODE = "dhw_priority_mgr/heating_pause_mode";

var BRT_TEMP_SENSORS = [
  "wb-msw-v4_45/Temperature",
  "wb-msw-v4_61/Temperature",
  "wb-msw-v4_202/Temperature",
  "wb-msw-v4_209/Temperature"
];

var BRT_DEFAULT_ENABLED = true;
var BRT_DEFAULT_SETPOINT = 21.0;
var BRT_DEFAULT_HYST = 0.7;

function brtToBool(v) {
  if (v === true || v === 1 || v === "1") return true;
  if (v === false || v === 0 || v === "0" || v === null || v === undefined) return false;
  return !!v;
}

function brtReadBool(path) {
  try {
    return brtToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function brtReadNum(path) {
  try {
    var v = parseFloat(dev[path]);
    return isNaN(v) ? null : v;
  } catch (e) {
    return null;
  }
}

function brtClamp(v, minV, maxV) {
  v = Number(v);
  if (isNaN(v)) v = minV;
  if (v < minV) return minV;
  if (v > maxV) return maxV;
  return v;
}

function brtRound1(v) {
  return Math.round(v * 10) / 10;
}

function brtWriteBoolIfNeeded(path, value) {
  var target = !!value;
  if (brtReadBool(path) !== target) dev[path] = target;
}

function brtReadPauseMode() {
  try {
    var mode = String(dev[BRT_DHW_PAUSE_MODE]);
    if (!mode) return "no_pause";
    return mode;
  } catch (e) {
    return "no_pause";
  }
}

function brtReadTemps() {
  var out = [];
  var i;
  var t;
  for (i = 0; i < BRT_TEMP_SENSORS.length; i++) {
    t = brtReadNum(BRT_TEMP_SENSORS[i]);
    if (t !== null) out.push(t);
  }
  return out;
}

function brtNeedHeat(temps, lowBorder) {
  var i;
  for (i = 0; i < temps.length; i++) {
    if (temps[i] < lowBorder) return true;
  }
  return false;
}

function brtCanStopHeat(temps, highBorder) {
  var i;
  if (!temps.length) return false;
  for (i = 0; i < temps.length; i++) {
    if (temps[i] <= highBorder) return false;
  }
  return true;
}

function brtBuildTempsText() {
  var chunks = [];
  var i;
  var t;
  for (i = 0; i < BRT_TEMP_SENSORS.length; i++) {
    t = brtReadNum(BRT_TEMP_SENSORS[i]);
    chunks.push(BRT_TEMP_SENSORS[i] + "=" + (t === null ? "нет данных" : brtRound1(t) + "°C"));
  }
  return chunks.join("; ");
}

function brtApply() {
  var enabled = brtReadBool("basement_radiator_thermostat/enabled");
  var setpoint = brtClamp(dev["basement_radiator_thermostat/setpoint_c"], 10, 30);
  var hyst = brtClamp(dev["basement_radiator_thermostat/hysteresis_c"], 0.2, 5);
  var lowBorder = setpoint - hyst;
  var highBorder = setpoint + hyst;
  var pauseMode = brtReadPauseMode();
  var temps;
  var pumpState;
  var reason;

  dev["basement_radiator_thermostat/low_border_c"] = brtRound1(lowBorder);
  dev["basement_radiator_thermostat/high_border_c"] = brtRound1(highBorder);
  dev["basement_radiator_thermostat/dhw_pause_mode"] = pauseMode;
  dev["basement_radiator_thermostat/temps_text"] = brtBuildTempsText();

  if (!enabled) {
    brtWriteBoolIfNeeded(BRT_PUMP_BASEMENT, false);
    dev["basement_radiator_thermostat/heat_demand"] = false;
    dev["basement_radiator_thermostat/pump_state"] = brtReadBool(BRT_PUMP_BASEMENT);
    dev["basement_radiator_thermostat/status_text"] = "Термостат отключён пользователем";
    return;
  }

  if (pauseMode === "priority_heat" || pauseMode === "restore") {
    brtWriteBoolIfNeeded(BRT_PUMP_BASEMENT, false);
    dev["basement_radiator_thermostat/heat_demand"] = false;
    dev["basement_radiator_thermostat/pump_state"] = brtReadBool(BRT_PUMP_BASEMENT);
    dev["basement_radiator_thermostat/status_text"] = "Насос цоколя выключен: активен приоритет ГВС";
    return;
  }

  temps = brtReadTemps();
  if (!temps.length) {
    brtWriteBoolIfNeeded(BRT_PUMP_BASEMENT, false);
    dev["basement_radiator_thermostat/heat_demand"] = false;
    dev["basement_radiator_thermostat/pump_state"] = brtReadBool(BRT_PUMP_BASEMENT);
    dev["basement_radiator_thermostat/status_text"] = "Нет валидных температур цоколя, насос остановлен";
    return;
  }

  pumpState = brtReadBool(BRT_PUMP_BASEMENT);

  if (brtNeedHeat(temps, lowBorder)) {
    pumpState = true;
    reason = "Есть помещение ниже нижней границы";
  } else if (brtCanStopHeat(temps, highBorder)) {
    pumpState = false;
    reason = "Все помещения выше верхней границы";
  } else {
    reason = "Зона гистерезиса: сохраняем текущее состояние";
  }

  brtWriteBoolIfNeeded(BRT_PUMP_BASEMENT, pumpState);

  dev["basement_radiator_thermostat/heat_demand"] = pumpState;
  dev["basement_radiator_thermostat/pump_state"] = brtReadBool(BRT_PUMP_BASEMENT);
  dev["basement_radiator_thermostat/status_text"] = reason;
}

defineVirtualDevice("basement_radiator_thermostat", {
  title: "Цоколь: временный термостат радиаторов",
  cells: {
    enabled: { type: "switch", value: BRT_DEFAULT_ENABLED, title: "Включен временный термостат" },
    setpoint_c: { type: "value", value: BRT_DEFAULT_SETPOINT, title: "Общая уставка, °C" },
    hysteresis_c: { type: "value", value: BRT_DEFAULT_HYST, title: "Общий гистерезис, °C" },

    low_border_c: { type: "value", value: 0, readonly: true, title: "Нижняя граница, °C" },
    high_border_c: { type: "value", value: 0, readonly: true, title: "Верхняя граница, °C" },

    dhw_pause_mode: { type: "text", value: "no_pause", readonly: true, title: "Режим ГВС (no_pause/priority_heat/restore)" },
    heat_demand: { type: "switch", value: false, readonly: true, title: "Запрос на отопление цоколя" },
    pump_state: { type: "switch", value: false, readonly: true, title: "Состояние насоса K3" },

    temps_text: { type: "text", value: "", readonly: true, title: "Температуры помещений" },
    status_text: { type: "text", value: "", readonly: true, title: "Статус" }
  }
});

defineRule("basement_thermostat_on_settings", {
  whenChanged: [
    "basement_radiator_thermostat/enabled",
    "basement_radiator_thermostat/setpoint_c",
    "basement_radiator_thermostat/hysteresis_c"
  ],
  then: brtApply
});

defineRule("basement_thermostat_on_temps", {
  whenChanged: BRT_TEMP_SENSORS,
  then: brtApply
});

defineRule("basement_thermostat_on_dhw_mode", {
  whenChanged: BRT_DHW_PAUSE_MODE,
  then: brtApply
});

defineRule("basement_thermostat_periodic_safety", {
  when: cron("*/20 * * * * *"),
  then: brtApply
});

brtApply();
