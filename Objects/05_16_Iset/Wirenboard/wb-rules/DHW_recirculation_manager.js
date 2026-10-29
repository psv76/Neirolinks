/***************************************************************
 * PROJECT: 05 16 Исеть
 * SCRIPT: DHW_recirculation_manager.js
 * -------------------------------------------------------------
 * Управление насосом рециркуляции ГВС K5.
 *
 * Логика v1:
 *   HOME -> K5 ON
 *   AWAY -> K5 OFF
 *
 * Источник режима присутствия:
 *   house_mode/away
 *
 * Пишет:
 *   wb-mr6cu_12/K5
 ***************************************************************/

var DRM_PUMP = "wb-mr6cu_12/K5";
var DRM_HOUSE_AWAY = "house_mode/away";
var DRM_TICK_MS = 15000;

function drmToBool(v) {
  return (v === true || v === 1 || v === "1");
}

function drmReadBool(path) {
  try {
    return drmToBool(dev[path]);
  } catch (e) {
    return false;
  }
}

function drmWritePump(target, reason) {
  var current = drmReadBool(DRM_PUMP);

  if (current === target) {
    return;
  }

  dev[DRM_PUMP] = target;

  log.info(
    "[гвс][dhw_recirculation_manager][рециркуляция]; КОМАНДА=" +
    (target ? "Включить насос" : "Выключить насос") +
    "; причина=" + reason +
    "; канал=" + DRM_PUMP +
    "; значение в канал=" + (target ? "ON" : "OFF")
  );
}

defineVirtualDevice("dhw_recirculation_mgr", {
  title: "ГВС / Рециркуляция",
  cells: {
    mode: {
      type: "text",
      value: "HOME",
      readonly: true,
      title: "Режим объекта",
      order: 1
    },
    requested_on: {
      type: "switch",
      value: true,
      readonly: true,
      title: "Требуется работа насоса",
      order: 2
    },
    status: {
      type: "text",
      value: "Инициализация",
      readonly: true,
      title: "Статус",
      order: 3
    }
  }
});

function drmStep() {
  var away = drmReadBool(DRM_HOUSE_AWAY);
  var requested = !away;

  dev["dhw_recirculation_mgr/mode"] = away ? "AWAY" : "HOME";
  dev["dhw_recirculation_mgr/requested_on"] = requested;

  drmWritePump(requested, away ? "режим AWAY" : "режим HOME");

  dev["dhw_recirculation_mgr/status"] = away ?
    "AWAY: команда K5 OFF" :
    "HOME: команда K5 ON";
}

defineRule("dhw_recirculation_on_house_mode", {
  whenChanged: DRM_HOUSE_AWAY,
  then: function () {
    drmStep();
  }
});

drmStep();
setInterval(drmStep, DRM_TICK_MS);

log.info(
  "[гвс][dhw_recirculation_manager][рециркуляция]; СКРИПТ=Запущен; " +
  "логика=HOME ON / AWAY OFF; канал=" + DRM_PUMP
);
