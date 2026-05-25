/*
 * 620_saturn_heat1_dhw2.js
 * Создает виртуальные устройства «Отопление» и «ГВС» из RAW Saturn-PLC.
 */

var SCRIPT_ID = "620_saturn_heat1_dhw2";

var SATURN_CONTROLLERS = [
  {
    rawDevice: "saturn_lower_raw",
    titleSuffix: "нижних этажей",
    contextTag: "нижние",
    heatingDevice: "saturn_lower_heating",
    dhwDevice: "saturn_lower_dhw"
  },
  {
    rawDevice: "saturn_upper_raw",
    titleSuffix: "верхних этажей",
    contextTag: "верхние",
    heatingDevice: "saturn_upper_heating",
    dhwDevice: "saturn_upper_dhw"
  }
];

function logLine(level, systemTag, contextTag, eventType, message, params) {
  var line = "[" + systemTag + "][" + SCRIPT_ID + "][" + contextTag + "]; " + eventType + "=" + message;
  var key;
  if (params) {
    for (key in params) {
      if (params.hasOwnProperty(key)) line += "; " + key + "=" + params[key];
    }
  }
  if (level === "error") log.error(line);
  else if (level === "warning") log.warning(line);
  else log.info(line);
}

function mapRawToVirtual(rawDevice, virtualDevice, channels) {
  for (var i = 0; i < channels.length; i++) {
    var controlId = channels[i];
    dev[virtualDevice + "/" + controlId] = dev[rawDevice + "/" + controlId];
  }
}

function defineSaturnVirtuals(cfg) {
  defineVirtualDevice(cfg.heatingDevice, {
    title: "Saturn Отопление " + cfg.titleSuffix,
    cells: {
      T1: { title: "T1", type: "value", units: "°C", value: 0, readonly: true },
      T2: { title: "T2", type: "value", units: "°C", value: 0, readonly: true },
      T3: { title: "T3", type: "value", units: "°C", value: 0, readonly: true },
      AI1: { title: "Давление отопления", type: "value", units: "bar", value: 0, readonly: true },
      T1_error: { title: "Ошибка T1", type: "switch", value: false, readonly: true },
      T2_error: { title: "Ошибка T2", type: "switch", value: false, readonly: true },
      DI1: { title: "DI1", type: "switch", value: false, readonly: true },
      DI2: { title: "DI2", type: "switch", value: false, readonly: true },
      DO1: { title: "DO1", type: "switch", value: false, readonly: true },
      DO2: { title: "DO2", type: "switch", value: false, readonly: true },
      AO1: { title: "AO1", type: "value", units: "V", value: 0, readonly: true },
      S1_ID: { title: "ID схемы 1", type: "value", value: 0, readonly: true }
    }
  });

  defineVirtualDevice(cfg.dhwDevice, {
    title: "Saturn ГВС " + cfg.titleSuffix,
    cells: {
      T4: { title: "T4", type: "value", units: "°C", value: 0, readonly: true },
      T5: { title: "T5", type: "value", units: "°C", value: 0, readonly: true },
      AI2: { title: "Давление ГВС", type: "value", units: "bar", value: 0, readonly: true },
      T4_error: { title: "Ошибка T4", type: "switch", value: false, readonly: true },
      T5_error: { title: "Ошибка T5", type: "switch", value: false, readonly: true },
      DI3: { title: "DI3", type: "switch", value: false, readonly: true },
      DI4: { title: "DI4", type: "switch", value: false, readonly: true },
      DO3: { title: "DO3", type: "switch", value: false, readonly: true },
      DO4: { title: "DO4", type: "switch", value: false, readonly: true },
      AO2: { title: "AO2", type: "value", units: "V", value: 0, readonly: true },
      S2_ID: { title: "ID схемы 2", type: "value", value: 0, readonly: true },
      V_battery: { title: "Батарея", type: "value", units: "V", value: 0, readonly: true }
    }
  });

  defineRule("saturn_sync_" + cfg.rawDevice, {
    whenChanged: cfg.rawDevice + "/T1",
    then: function () {
      mapRawToVirtual(cfg.rawDevice, cfg.heatingDevice, ["T1", "T2", "T3", "AI1", "T1_error", "T2_error", "DI1", "DI2", "DO1", "DO2", "AO1", "S1_ID"]);
      mapRawToVirtual(cfg.rawDevice, cfg.dhwDevice, ["T4", "T5", "AI2", "T4_error", "T5_error", "DI3", "DI4", "DO3", "DO4", "AO2", "S2_ID", "V_battery"]);
    }
  });

  defineRule("saturn_sensor_alarm_" + cfg.rawDevice, {
    whenChanged: cfg.rawDevice + "/T1_error",
    then: function (newValue) {
      if (newValue) {
        logLine("error", "отопление", cfg.contextTag, "АВАРИЯ", "Неисправен датчик T1", { channel: "T1_error", value: newValue });
      } else {
        logLine("info", "отопление", cfg.contextTag, "СОСТОЯНИЕ", "Неисправность датчика T1 снята", { channel: "T1_error", value: newValue });
      }
    }
  });

  logLine("info", "сатурн", cfg.contextTag, "СКРИПТ", "Инициализация виртуальных устройств Saturn", {
    raw: cfg.rawDevice,
    heating: cfg.heatingDevice,
    dhw: cfg.dhwDevice
  });
}

for (var i = 0; i < SATURN_CONTROLLERS.length; i++) {
  defineSaturnVirtuals(SATURN_CONTROLLERS[i]);
}
