/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: Heating_pumps_manager.js
 * -------------------------------------------------------------
 * Единый менеджер насосов отопления для жилого этажа:
 *   - wb-mr6cu_37/K2 (тёплый пол)
 *   - wb-mr6cu_37/K4 (радиаторы жилого этажа)
 *
 * ВАЖНО
 * -------------------------------------------------------------
 * На этом объекте сервоприводы нормально открытые.
 *
 * Это значит:
 *   - 0 на канале сервопривода = контур открыт, тепло идёт
 *   - 1 на канале сервопривода = контур закрыт
 *
 * Логика приоритета:
 *   1) Если dhw_priority_mgr/heating_pause_mode = priority_heat или restore,
 *      то оба насоса отопления выключаются.
 *   2) Иначе насосы управляются по состоянию сервоприводов:
 *      - если хотя бы один сервопривод группы = 0, насос нужен
 *      - если все сервоприводы группы = 1, насос не нужен
 *
 * Совместимость: ES5 / wb-rules.
 ***************************************************************/

var HPM_PUMP_FLOOR = "wb-mr6cu_37/K2";
var HPM_PUMP_RAD_LIVING = "wb-mr6cu_37/K4";
var HPM_DHW_PAUSE_MODE = "dhw_priority_mgr/heating_pause_mode";

var HPM_FLOOR_ACTUATORS = [
  "wb-mio-gpio_195:2/K12",
  "wb-mio-gpio_195:2/K13",
  "wb-mio-gpio_195:2/K14",
  "wb-mio-gpio_195:2/K15",
  "wb-mio-gpio_195:2/K16"
];

var HPM_LIVING_RAD_ACTUATORS = [
  "wb-mio-gpio_195:2/K1",
  "wb-mio-gpio_195:2/K2",
  "wb-mio-gpio_195:2/K3",
  "wb-mio-gpio_195:2/K4",
  "wb-mio-gpio_195:2/K5",
  "wb-mio-gpio_195:2/K6",
  "wb-mio-gpio_195:2/K7",
  "wb-mio-gpio_195:2/K8",
  "wb-mio-gpio_195:2/K9",
  "wb-mio-gpio_195:2/K10",
  "wb-mio-gpio_195:2/K11"
];

function hpmToBool(v) {
  if (v === true || v === 1 || v === "1") return true;
  if (v === false || v === 0 || v === "0" || v === null || v === undefined) return false;
  return !!v;
}

function hpmReadBool(path) {
  try {
    return hpmToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function hpmWriteBoolIfNeeded(path, value) {
  var target = !!value;
  if (hpmReadBool(path) !== target) dev[path] = target;
}

function hpmReadPauseMode() {
  try {
    var mode = String(dev[HPM_DHW_PAUSE_MODE]);
    if (!mode) return "no_pause";
    return mode;
  } catch (e) {
    return "no_pause";
  }
}

function hpmHasHeatDemandNO(list) {
  var i;
  for (i = 0; i < list.length; i++) {
    if (!hpmReadBool(list[i])) return true;
  }
  return false;
}

function hpmAllActuatorsClosedNO(list) {
  var i;
  for (i = 0; i < list.length; i++) {
    if (!hpmReadBool(list[i])) return false;
  }
  return true;
}

function hpmSetStatus(mode, floorNeed, livingNeed, reason) {
  dev["heating_pumps_mgr/dhw_pause_mode"] = mode;
  dev["heating_pumps_mgr/dhw_pause_active"] = (mode === "priority_heat" || mode === "restore");
  dev["heating_pumps_mgr/floor_heat_demand"] = floorNeed;
  dev["heating_pumps_mgr/living_radiators_heat_demand"] = livingNeed;
  dev["heating_pumps_mgr/floor_all_closed"] = hpmAllActuatorsClosedNO(HPM_FLOOR_ACTUATORS);
  dev["heating_pumps_mgr/living_radiators_all_closed"] = hpmAllActuatorsClosedNO(HPM_LIVING_RAD_ACTUATORS);
  dev["heating_pumps_mgr/floor_pump_state"] = hpmReadBool(HPM_PUMP_FLOOR);
  dev["heating_pumps_mgr/living_radiators_pump_state"] = hpmReadBool(HPM_PUMP_RAD_LIVING);
  dev["heating_pumps_mgr/status_text"] = reason;
}

function hpmApply() {
  var pauseMode = hpmReadPauseMode();
  var floorNeed = false;
  var livingNeed = false;

  if (pauseMode === "priority_heat" || pauseMode === "restore") {
    hpmWriteBoolIfNeeded(HPM_PUMP_FLOOR, false);
    hpmWriteBoolIfNeeded(HPM_PUMP_RAD_LIVING, false);
    hpmSetStatus(pauseMode, false, false, "Насосы отключены: активен приоритет ГВС");
    return;
  }

  floorNeed = hpmHasHeatDemandNO(HPM_FLOOR_ACTUATORS);
  livingNeed = hpmHasHeatDemandNO(HPM_LIVING_RAD_ACTUATORS);

  hpmWriteBoolIfNeeded(HPM_PUMP_FLOOR, floorNeed);
  hpmWriteBoolIfNeeded(HPM_PUMP_RAD_LIVING, livingNeed);

  hpmSetStatus(pauseMode, floorNeed, livingNeed, "Насосы управляются от нормально открытых сервоприводов");
}

defineVirtualDevice("heating_pumps_mgr", {
  title: "Насосы отопления: жилой этаж",
  cells: {
    dhw_pause_mode: {
      type: "text",
      value: "no_pause",
      readonly: true,
      title: "Режим ГВС (no_pause/priority_heat/restore)"
    },

    dhw_pause_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Пауза отопления из-за ГВС"
    },

    floor_heat_demand: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Запрос ТП (хотя бы один NO-сервопривод открыт)"
    },

    living_radiators_heat_demand: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Запрос радиаторов (хотя бы один NO-сервопривод открыт)"
    },

    floor_all_closed: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Все сервоприводы ТП закрыты"
    },

    living_radiators_all_closed: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Все сервоприводы радиаторов закрыты"
    },

    floor_pump_state: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Состояние насоса тёплого пола K2"
    },

    living_radiators_pump_state: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Состояние насоса радиаторов K4"
    },

    status_text: {
      type: "text",
      value: "",
      readonly: true,
      title: "Статус"
    }
  }
});

defineRule("heating_pumps_on_dhw_mode", {
  whenChanged: HPM_DHW_PAUSE_MODE,
  then: hpmApply
});

defineRule("heating_pumps_on_floor_actuators", {
  whenChanged: HPM_FLOOR_ACTUATORS,
  then: hpmApply
});

defineRule("heating_pumps_on_living_actuators", {
  whenChanged: HPM_LIVING_RAD_ACTUATORS,
  then: hpmApply
});

defineRule("heating_pumps_periodic_safety", {
  when: cron("*/20 * * * * *"),
  then: hpmApply
});

hpmApply();
