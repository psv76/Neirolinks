/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: AHU_preheat_pump_manager.js
 * -------------------------------------------------------------
 * Насос водяного преднагрева ПВУ K6.
 *
 * Логика v1 WINTER_SAFE:
 *   если есть любой достоверный признак работы/запуска Breezart
 *   -> K6 ON.
 *
 * Автоматическую команду K6 OFF этот скрипт НЕ выдаёт.
 * При остановке ПВУ или потере данных насос не отключается.
 *
 * Пишет:
 *   wb-mr6cu_12/K6
 *
 * Читает Breezart:
 *   air_handling_unit
 *   air_handling_unit_status
 *   ventilation_status
 *   fan_performance
 ***************************************************************/

var APM_PUMP = "wb-mr6cu_12/K6";

var APM_AHU_COMMAND =
  "breezart_lux_sb_115/air_handling_unit";

var APM_AHU_STATUS =
  "breezart_lux_sb_115/air_handling_unit_status";

var APM_VENT_STATUS =
  "breezart_lux_sb_115/ventilation_status";

var APM_FAN_PERFORMANCE =
  "breezart_lux_sb_115/fan_performance";

var APM_FAN_RUNNING_THRESHOLD = 0.5;
var APM_TICK_MS = 10000;

function apmToBool(v) {
  return (v === true || v === 1 || v === "1");
}

function apmReadBool(path) {
  try {
    return apmToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function apmReadNum(path) {
  try {
    var value = parseFloat(dev[path]);
    return isNaN(value) ? null : value;
  } catch (e) {
    return null;
  }
}

defineVirtualDevice("ahu_preheat_pump_mgr", {
  title: "Вентиляция / Насос преднагрева K6",
  cells: {
    mode: {
      type: "text",
      value: "WINTER_SAFE_ON_ONLY",
      readonly: true,
      title: "Режим",
      order: 1
    },
    ahu_running: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Есть признак работы ПВУ",
      order: 2
    },
    fan_performance: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Фактическая производительность, %",
      order: 3
    },
    status: {
      type: "text",
      value: "Инициализация",
      readonly: true,
      title: "Статус",
      order: 4
    }
  }
});

function apmStep() {
  var ahuCommand = apmReadBool(APM_AHU_COMMAND);
  var ahuStatus = apmReadBool(APM_AHU_STATUS);
  var ventilationStatus = apmReadBool(APM_VENT_STATUS);
  var fanPerformance = apmReadNum(APM_FAN_PERFORMANCE);

  var running =
    ahuCommand ||
    ahuStatus ||
    ventilationStatus ||
    (fanPerformance !== null &&
     fanPerformance > APM_FAN_RUNNING_THRESHOLD);

  dev["ahu_preheat_pump_mgr/ahu_running"] = running;
  dev["ahu_preheat_pump_mgr/fan_performance"] =
    fanPerformance === null ? 0 : fanPerformance;

  if (running) {
    if (!apmReadBool(APM_PUMP)) {
      dev[APM_PUMP] = true;

      log.info(
        "[вентиляция][ahu_preheat_pump_manager][преднагрев]; " +
        "КОМАНДА=Включить насос; причина=есть признак работы ПВУ; " +
        "канал=" + APM_PUMP + "; значение в канал=ON; " +
        "ahu_command=" + String(ahuCommand) + "; " +
        "ahu_status=" + String(ahuStatus) + "; " +
        "ventilation_status=" + String(ventilationStatus) + "; " +
        "fan_performance=" + String(fanPerformance)
      );
    }

    dev["ahu_preheat_pump_mgr/status"] =
      "ПВУ работает/запускается: K6 должен быть ON";
  } else if (fanPerformance === null) {
    dev["ahu_preheat_pump_mgr/status"] =
      "Нет подтверждения работы ПВУ: K6 не отключаю";
  } else {
    dev["ahu_preheat_pump_mgr/status"] =
      "ПВУ не работает: команда K6 OFF запрещена в WINTER_SAFE";
  }
}

defineRule("ahu_preheat_pump_on_breezart", {
  whenChanged: [
    APM_AHU_COMMAND,
    APM_AHU_STATUS,
    APM_VENT_STATUS,
    APM_FAN_PERFORMANCE
  ],
  then: function () {
    apmStep();
  }
});

apmStep();
setInterval(apmStep, APM_TICK_MS);

log.info(
  "[вентиляция][ahu_preheat_pump_manager][преднагрев]; СКРИПТ=Запущен; " +
  "режим=WINTER_SAFE_ON_ONLY; команда K6 OFF отсутствует"
);
