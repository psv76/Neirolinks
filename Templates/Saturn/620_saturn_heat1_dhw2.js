var SCRIPT_ID = "620_saturn_heat1_dhw2";

var SATURN_CONTROLLERS = [
  { rawDevice: "saturn_lower_raw", titleSuffix: "нижних этажей", contextTag: "нижние", heatingDevice: "saturn_lower_heating", dhwDevice: "saturn_lower_dhw" },
  { rawDevice: "saturn_upper_raw", titleSuffix: "верхних этажей", contextTag: "верхние", heatingDevice: "saturn_upper_heating", dhwDevice: "saturn_upper_dhw" }
];

function logLine(level, systemTag, contextTag, eventType, message, params) {
  var line = "[" + systemTag + "][" + SCRIPT_ID + "][" + contextTag + "]; " + eventType + "=" + message;
  var k;
  if (params) for (k in params) if (params.hasOwnProperty(k)) line += "; " + k + "=" + params[k];
  if (level === "error") log.error(line); else if (level === "warning") log.warning(line); else log.info(line);
}

function pumpStateText(v) {
  if (v === 0) return "Запрещена работа";
  if (v === 1) return "Остановлен";
  if (v === 2) return "Включен";
  if (v === 3) return "Авария по перепаду/времени";
  if (v === 4) return "Авария по внешнему сигналу";
  return "Неизвестно(" + v + ")";
}

function defineSyncRule(cfg, rawControl, virtDevice, virtControl) {
  defineRule("saturn_sync_" + cfg.rawDevice + "_" + rawControl + "_" + virtDevice, {
    whenChanged: cfg.rawDevice + "/" + rawControl,
    then: function (newValue) { dev[virtDevice + "/" + virtControl] = newValue; }
  });
}

function defineSaturn(cfg) {
  defineVirtualDevice(cfg.heatingDevice, { title: "Saturn Отопление " + cfg.titleSuffix, cells: {
    enabled: { title: "Разрешено управление", type: "switch", readonly: true, value: false },
    s1_id: { title: "ID схемы", type: "value", readonly: true, value: 0 },
    feed_t: { title: "Температура подачи", type: "value", units: "°C", readonly: true, value: 0 },
    outdoor_t: { title: "Температура наружная", type: "value", units: "°C", readonly: true, value: 0 },
    return_t: { title: "Температура обратки", type: "value", units: "°C", readonly: true, value: 0 },
    pressure: { title: "Давление подпитки", type: "value", units: "bar", readonly: true, value: 0 },
    t_correct: { title: "Коррекция уставки", type: "value", units: "°C", value: 0 },
    t_preset: { title: "Уставка подачи", type: "value", units: "°C", readonly: true, value: 0 },
    pump1_state: { title: "Насос 1", type: "text", readonly: true, value: "-" },
    pump2_state: { title: "Насос 2", type: "text", readonly: true, value: "-" },
    valve_percent: { title: "Клапан", type: "value", units: "%", readonly: true, value: 0 },
    remote_stop: { title: "Дистанционный стоп", type: "switch", value: false },
    t1_error: { title: "Ошибка датчика подачи", type: "switch", readonly: true, value: false },
    t2_error: { title: "Ошибка датчика наружного", type: "switch", readonly: true, value: false },
    t3_error: { title: "Ошибка датчика обратки", type: "switch", readonly: true, value: false },
    ai1_error: { title: "Ошибка датчика давления", type: "switch", readonly: true, value: false },
    feed_on_count: { title: "Включений подпитки", type: "value", readonly: true, value: 0 },
    feed_work_time: { title: "Время подпитки", type: "value", units: "мин", readonly: true, value: 0 }
  }});

  defineVirtualDevice(cfg.dhwDevice, { title: "Saturn ГВС " + cfg.titleSuffix, cells: {
    enabled: { title: "Разрешено управление", type: "switch", readonly: true, value: false },
    s2_id: { title: "ID схемы", type: "value", readonly: true, value: 0 },
    dhw_t: { title: "Температура ГВС", type: "value", units: "°C", readonly: true, value: 0 },
    dhw_t_preset: { title: "Уставка ГВС", type: "value", units: "°C", value: 55 },
    dhw_t_correct: { title: "Коррекция ГВС", type: "value", units: "°C", value: 0 },
    pump1_state: { title: "Насос ГВС 1", type: "text", readonly: true, value: "-" },
    pump2_state: { title: "Насос ГВС 2", type: "text", readonly: true, value: "-" },
    valve_percent: { title: "Клапан", type: "value", units: "%", readonly: true, value: 0 },
    remote_stop: { title: "Дистанционный стоп", type: "switch", value: false },
    t4_error: { title: "Ошибка датчика ГВС", type: "switch", readonly: true, value: false },
    prior_on: { title: "Приоритет ГВС", type: "switch", readonly: true, value: false },
    prior_value: { title: "Порог приоритета", type: "value", units: "°C", readonly: true, value: 0 },
    prior_time: { title: "Время приоритета", type: "value", units: "мин", readonly: true, value: 0 },
    battery_v: { title: "Батарея RTC", type: "value", units: "V", readonly: true, value: 0 }
  }});

  defineSyncRule(cfg, "S1_ID", cfg.heatingDevice, "s1_id");
  defineSyncRule(cfg, "T1", cfg.heatingDevice, "feed_t");
  defineSyncRule(cfg, "T2", cfg.heatingDevice, "outdoor_t");
  defineSyncRule(cfg, "T3", cfg.heatingDevice, "return_t");
  defineSyncRule(cfg, "AI1", cfg.heatingDevice, "pressure");
  defineSyncRule(cfg, "S1_T_correct", cfg.heatingDevice, "t_correct");
  defineSyncRule(cfg, "S1_T_preset", cfg.heatingDevice, "t_preset");
  defineSyncRule(cfg, "S1_ValvePercent", cfg.heatingDevice, "valve_percent");
  defineSyncRule(cfg, "S1_RemoteStop", cfg.heatingDevice, "remote_stop");
  defineSyncRule(cfg, "T1_error", cfg.heatingDevice, "t1_error");
  defineSyncRule(cfg, "T2_error", cfg.heatingDevice, "t2_error");
  defineSyncRule(cfg, "T3_error", cfg.heatingDevice, "t3_error");
  defineSyncRule(cfg, "AI1_error", cfg.heatingDevice, "ai1_error");
  defineSyncRule(cfg, "S1_HS_FeedOnCount", cfg.heatingDevice, "feed_on_count");
  defineSyncRule(cfg, "S1_HS_FeedWorkTime", cfg.heatingDevice, "feed_work_time");

  defineSyncRule(cfg, "S2_ID", cfg.dhwDevice, "s2_id");
  defineSyncRule(cfg, "T4", cfg.dhwDevice, "dhw_t");
  defineSyncRule(cfg, "S2_T_preset", cfg.dhwDevice, "dhw_t_preset");
  defineSyncRule(cfg, "S2_T_correct", cfg.dhwDevice, "dhw_t_correct");
  defineSyncRule(cfg, "S2_ValvePercent", cfg.dhwDevice, "valve_percent");
  defineSyncRule(cfg, "S2_RemoteStop", cfg.dhwDevice, "remote_stop");
  defineSyncRule(cfg, "T4_error", cfg.dhwDevice, "t4_error");
  defineSyncRule(cfg, "S2_Prior_On", cfg.dhwDevice, "prior_on");
  defineSyncRule(cfg, "S2_Prior_Value", cfg.dhwDevice, "prior_value");
  defineSyncRule(cfg, "S2_Prior_Time", cfg.dhwDevice, "prior_time");
  defineSyncRule(cfg, "V_battery", cfg.dhwDevice, "battery_v");

  defineRule("saturn_pumps_s1_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/S1_Pump1", then: function (v) {
    dev[cfg.heatingDevice + "/pump1_state"] = pumpStateText(v);
    if (v === 2) logLine("info", "отопление", cfg.contextTag, "СОСТОЯНИЕ", "Насос 1 включен", { канал: "S1_Pump1", значение: v });
    if (v === 3 || v === 4) logLine("error", "отопление", cfg.contextTag, "АВАРИЯ", "Насос 1 в аварии", { канал: "S1_Pump1", значение: v });
  }});
  defineRule("saturn_pumps_s1_2_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/S1_Pump2", then: function (v) { dev[cfg.heatingDevice + "/pump2_state"] = pumpStateText(v); }});
  defineRule("saturn_pumps_s2_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/S2_Pump1", then: function (v) { dev[cfg.dhwDevice + "/pump1_state"] = pumpStateText(v); }});
  defineRule("saturn_pumps_s2_2_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/S2_Pump2", then: function (v) { dev[cfg.dhwDevice + "/pump2_state"] = pumpStateText(v); }});

  defineRule("saturn_log_t1_err_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/T1_error", then: function (v) {
    if (v) logLine("error", "отопление", cfg.contextTag, "АВАРИЯ", "Неисправен датчик подачи", { канал: "T1_error", значение: v });
    else logLine("info", "отопление", cfg.contextTag, "СОСТОЯНИЕ", "Неисправность датчика подачи снята", { канал: "T1_error", значение: v });
  }});

  defineRule("saturn_log_t4_err_" + cfg.rawDevice, { whenChanged: cfg.rawDevice + "/T4_error", then: function (v) {
    if (v) logLine("error", "гвс", cfg.contextTag, "АВАРИЯ", "Неисправен датчик ГВС", { канал: "T4_error", значение: v });
    else logLine("info", "гвс", cfg.contextTag, "СОСТОЯНИЕ", "Неисправность датчика ГВС снята", { канал: "T4_error", значение: v });
  }});

  defineRule("saturn_write_s1_remote_" + cfg.rawDevice, { whenChanged: cfg.heatingDevice + "/remote_stop", then: function (v) {
    dev[cfg.rawDevice + "/S1_RemoteStop"] = v ? 1 : 0;
    logLine("info", "отопление", cfg.contextTag, "КОМАНДА", "Изменить дистанционный стоп отопления", { канал: "S1_RemoteStop", "значение в канал": v ? 1 : 0 });
  }});
  defineRule("saturn_write_s2_remote_" + cfg.rawDevice, { whenChanged: cfg.dhwDevice + "/remote_stop", then: function (v) {
    dev[cfg.rawDevice + "/S2_RemoteStop"] = v ? 1 : 0;
    logLine("info", "гвс", cfg.contextTag, "КОМАНДА", "Изменить дистанционный стоп ГВС", { канал: "S2_RemoteStop", "значение в канал": v ? 1 : 0 });
  }});

  logLine("info", "сатурн", cfg.contextTag, "СКРИПТ", "Запущен мониторинг Saturn", { raw_device: cfg.rawDevice, схема1: "отопление", схема2: "гвс" });
}

for (var i = 0; i < SATURN_CONTROLLERS.length; i++) defineSaturn(SATURN_CONTROLLERS[i]);
