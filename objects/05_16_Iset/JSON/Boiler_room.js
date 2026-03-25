/***************************************************************
 * Boiler Room Monitor
 * -------------------------------------------------------------
 * Полный модуль мониторинга котельной для Wiren Board.
 *
 * Конкретно под эту систему:
 *   - котёл Ferroli Pegasus D45
 *   - OpenTherm через WBE2-I-OPENTHERM
 *   - гидрострелка
 *   - отдельные насосы контуров
 *   - бойлер косвенного нагрева
 *   - рециркуляция ГВС
 *   - тёплый пол через узел подмеса с 3-ходовым клапаном 0-10 В
 *   - температурные датчики 1-Wire
 *
 * Важно:
 *   - насос котлового контура управляется платой котла и напрямую WB не виден
 *   - датчик "Подача от котла" накладной, а не погружной
 *   - поэтому:
 *       OT Heating Temperature = температура воды в котле
 *       T_SUPPLY              = температура трубы/системы после гидрострелки
 *
 * Что делает модуль:
 *   1) собирает состояние котла по OpenTherm
 *   2) декодирует Boiler Status (ID 0)
 *   3) показывает насосы
 *   4) показывает температуры
 *   5) считает ΔT по контурам
 *   6) анализирует узел подмеса
 *   7) делает текстовую диагностику
 *   8) формирует аварийные флаги
 *   9) готовит основу для Telegram-уведомлений
 *
 * Статистика:
 *   - счётчики хранятся в памяти wb-rules
 *   - после рестарта wb-rules счётчики начнутся заново
 ***************************************************************/


/***************************************************************
 * 1. MQTT-УСТРОЙСТВА И КАНАЛЫ
 ***************************************************************/

/* OpenTherm адаптер */
var OT_DEVICE = "wbe2-i-opentherm_11";

/* Карта OpenTherm-каналов */
var OT = {
  boiler_status:        OT_DEVICE + "/Boiler Status",
  fault_indication:     OT_DEVICE + "/Boiler fault indication",
  ch_mode:              OT_DEVICE + "/Boiler CH mode",
  ch2_mode:             OT_DEVICE + "/Boiler CH2 mode",
  flame:                OT_DEVICE + "/Boiler Flame Status",
  master_ch_enable:     OT_DEVICE + "/Master CH enable",
  master_ch2_enable:    OT_DEVICE + "/Master CH2 enable",
  error_code:           OT_DEVICE + "/Error Code",
  invalid_connection:   OT_DEVICE + "/Invalid Connection",
  ch_min_value:         OT_DEVICE + "/CH Min Value",
  ch_max_value:         OT_DEVICE + "/CH Max Value",
  ch_gest:              OT_DEVICE + "/CH Gest",
  heating_temperature:  OT_DEVICE + "/Heating Temperature",
  water_pressure:       OT_DEVICE + "/Water Pressure",
  auto_temp_switch:     OT_DEVICE + "/Auto Temp Switch",
  season_reg:           OT_DEVICE + "/Season reg",
  ot_master_id:         OT_DEVICE + "/OT MasterID",
  fw_version:           OT_DEVICE + "/FW Version",
  temp_sensor_type:     OT_DEVICE + "/Temperature Sensor Type",
  heating_setpoint:     OT_DEVICE + "/Heating Setpoint"
};


/* Насосы */
var PUMP_GVS          = "wb-mr6cu_37/K1";
var PUMP_FLOOR        = "wb-mr6cu_37/K2";
var PUMP_RAD_BASE     = "wb-mr6cu_37/K3";
var PUMP_RAD_LIVING   = "wb-mr6cu_37/K4";
var PUMP_RECIRC       = "wb-mr6cu_37/K5";
var PUMP_VENT         = "wb-mr6cu_37/K6";


/* Температурные датчики 1-Wire */
var T_BOILER_DHW      = "wb-w1/28-00000fd7811a";
var T_RAD_BASE        = "wb-w1/28-00000fdeed15";
var T_OUTSIDE         = "wb-w1/28-00000fd6a9ad";
var T_FLOOR           = "wb-w1/28-00000ff8a3d5";
var T_RAD_LIVING      = "wb-w1/28-00000ff86391";
var T_SUPPLY          = "wb-w1/28-00000ff8446c";


/* Узел подмеса тёплого пола */
var FLOOR_VALVE_ENABLE = "wb-mao4_131/Channel 1 Switch";
var FLOOR_VALVE_POS    = "wb-mao4_131/Channel 1 Dimming Level";


/***************************************************************
 * 2. НАСТРОЕЧНЫЕ КОНСТАНТЫ
 ***************************************************************/

var PRESSURE_LOW_BAR            = 0.8;
var PRESSURE_WARN_BAR           = 1.0;
var PRESSURE_HIGH_BAR           = 3.0;

var BOILER_OVERHEAT_C           = 85;
var BOILER_HIGH_TEMP_WARN_C     = 80;

var DT_ARROW_WARN_C             = 8;
var DT_ARROW_ALARM_C            = 12;

var DT_RADIATOR_LOW_C           = 3;
var DT_RADIATOR_NORMAL_MAX_C    = 15;
var DT_RADIATOR_ALARM_C         = 25;

var DHW_HEAT_CHECK_SECONDS      = 15 * 60;
var DHW_MIN_RISE_C              = 1.0;

var FLOOR_VALVE_ACTIVE_POS      = 40;
var FLOOR_PUMP_CHECK_SECONDS    = 10 * 60;
var FLOOR_MIN_RISE_C            = 0.5;

var NO_HEAT_PICKUP_SECONDS      = 3 * 60;


/***************************************************************
 * 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
 ***************************************************************/

function nowSec() {
  return Math.floor(Date.now() / 1000);
}

function round1(v) {
  return Math.round(v * 10) / 10;
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

function parseNum(v) {
  var x = parseFloat(v);
  return isNaN(x) ? null : x;
}

function parseInt10(v) {
  var x = parseInt(v, 10);
  return isNaN(x) ? null : x;
}

function readNum(path) {
  try {
    return parseNum(dev[path]);
  } catch (e) {
    return null;
  }
}

function readInt(path) {
  try {
    return parseInt10(dev[path]);
  } catch (e) {
    return null;
  }
}

function readBool(path) {
  try {
    return !!dev[path];
  } catch (e) {
    return false;
  }
}

function delta(a, b) {
  if (a === null || b === null) return null;
  return round1(a - b);
}

function bit(v, n) {
  return ((v >> n) & 1) === 1;
}

function hex2(v) {
  if (v === null || typeof v === "undefined") return "";
  var s = (v & 0xFF).toString(16).toUpperCase();
  return ("00" + s).slice(-2);
}

function hex4(v) {
  if (v === null || typeof v === "undefined") return "";
  var s = (v & 0xFFFF).toString(16).toUpperCase();
  return ("0000" + s).slice(-4);
}

function joinText(parts, emptyText) {
  var arr = [];
  var i;
  for (i = 0; i < parts.length; i++) {
    if (parts[i]) arr.push(parts[i]);
  }
  return arr.length ? arr.join("; ") : (emptyText || "нет");
}


/***************************************************************
 * 4. ПАМЯТЬ МОДУЛЯ
 ***************************************************************/

var mem = {
  lastFlame: null,
  lastUpdateTs: 0,
  burnerStartsTotal: 0,
  burnerRunSecondsTotal: 0,
  burnerRunSecondsToday: 0,

  dayKey: "",
  burnerStartsToday: 0,

  dhwPumpOnSince: 0,
  dhwStartTemp: null,
  dhwProblemLatched: false,

  floorMixingOnSince: 0,
  floorMixingStartTemp: null,
  floorMixingProblemLatched: false,

  noHeatPickupSince: 0,

  lastAlarmSignature: "",
  lastAlarmChangeTs: 0
};


/* Антициклирование котла */
var ANTICYCLE_DEFAULT_MIN_SUPPLY_C = 52;
var ANTICYCLE_BAND_C = 7;
var ANTICYCLE_MIN_PAUSE_S = 6 * 60;
var ANTICYCLE_PAUSE_SETPOINT_C = 15;

mem.antiCyclePauseActive = false;
mem.antiCyclePauseUntilTs = 0;

function getDayKey() {
  var d = new Date();
  return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
}

function resetDailyIfNeeded() {
  var dk = getDayKey();
  if (mem.dayKey !== dk) {
    mem.dayKey = dk;
    mem.burnerStartsToday = 0;
    mem.burnerRunSecondsToday = 0;
  }
}


/***************************************************************
 * 5. ДЕКОДЕР OPEN THERM STATUS
 ***************************************************************/

function decodeOpenThermStatus(rawValue) {
  var value = parseInt10(rawValue);

  if (value === null) {
    return {
      value: null,
      hex: "",
      masterByte: null,
      slaveByte: null,

      m_ch_enable: false,
      m_dhw_enable: false,
      m_cooling_enable: false,
      m_otc_active: false,
      m_ch2_enable: false,

      s_fault: false,
      s_ch_mode: false,
      s_dhw_mode: false,
      s_flame: false,
      s_cooling: false,
      s_ch2_mode: false,
      s_diag: false,

      masterFlagsText: "нет данных",
      slaveFlagsText: "нет данных",
      summaryText: "нет данных"
    };
  }

  value = value & 0xFFFF;

  var master = (value >> 8) & 0xFF;
  var slave = value & 0xFF;

  var d = {
    value: value,
    hex: "0x" + hex4(value),
    masterByte: master,
    slaveByte: slave,

    m_ch_enable: bit(master, 0),
    m_dhw_enable: bit(master, 1),
    m_cooling_enable: bit(master, 2),
    m_otc_active: bit(master, 3),
    m_ch2_enable: bit(master, 4),

    s_fault: bit(slave, 0),
    s_ch_mode: bit(slave, 1),
    s_dhw_mode: bit(slave, 2),
    s_flame: bit(slave, 3),
    s_cooling: bit(slave, 4),
    s_ch2_mode: bit(slave, 5),
    s_diag: bit(slave, 6)
  };

  var masterFlags = [];
  var slaveFlags = [];
  var summary = [];

  if (d.m_ch_enable)       masterFlags.push("контроллер разрешает отопление");
  if (d.m_dhw_enable)      masterFlags.push("контроллер разрешает ГВС");
  if (d.m_cooling_enable)  masterFlags.push("передан флаг охлаждения");
  if (d.m_otc_active)      masterFlags.push("активна погодозависимая регулировка");
  if (d.m_ch2_enable)      masterFlags.push("разрешён второй контур");

  if (d.s_fault)     slaveFlags.push("котёл сообщает об ошибке");
  if (d.s_ch_mode)   slaveFlags.push("котёл в режиме отопления");
  if (d.s_dhw_mode)  slaveFlags.push("котёл в режиме ГВС");
  if (d.s_flame)     slaveFlags.push("горелка сейчас включена");
  if (d.s_cooling)   slaveFlags.push("установлен флаг охлаждения");
  if (d.s_ch2_mode)  slaveFlags.push("активен второй контур");
  if (d.s_diag)      slaveFlags.push("есть диагностическое сообщение");

  summary.push(d.s_fault ? "есть ошибка" : "ошибок нет");
  summary.push(d.s_flame ? "горелка включена" : "горелка выключена");
  if (d.s_ch_mode) summary.push("идёт отопление");
  if (d.s_dhw_mode) summary.push("идёт нагрев ГВС");
  if (d.s_diag) summary.push("есть диагностическое сообщение");
  if (!d.s_fault && !d.s_flame && !d.s_ch_mode && !d.s_dhw_mode && !d.s_diag) {
    summary.push("котёл в ожидании");
  }

  d.masterFlagsText = masterFlags.length ? masterFlags.join(", ") : "нет активных команд";
  d.slaveFlagsText = slaveFlags.length ? slaveFlags.join(", ") : "нет активных состояний";
  d.summaryText = summary.join("; ");

  return d;
}


/***************************************************************
 * 6. ЧТЕНИЕ ВСЕХ ДАННЫХ
 ***************************************************************/

function readAll() {
  var data = {};

  data.ot_boiler_status_raw   = readInt(OT.boiler_status);
  data.ot_fault_indication    = readInt(OT.fault_indication);
  data.ot_ch_mode             = readInt(OT.ch_mode);
  data.ot_ch2_mode            = readInt(OT.ch2_mode);
  data.ot_flame               = readInt(OT.flame);
  data.ot_master_ch_enable    = readInt(OT.master_ch_enable);
  data.ot_master_ch2_enable   = readInt(OT.master_ch2_enable);
  data.ot_error_code          = readInt(OT.error_code);
  data.ot_invalid_connection  = readInt(OT.invalid_connection);
  data.ot_ch_min_value        = readNum(OT.ch_min_value);
  data.ot_ch_max_value        = readNum(OT.ch_max_value);
  data.ot_ch_gest             = readNum(OT.ch_gest);
  data.ot_heating_temperature = readNum(OT.heating_temperature);
  data.ot_water_pressure      = readNum(OT.water_pressure);
  data.ot_auto_temp_switch    = readInt(OT.auto_temp_switch);
  data.ot_season_reg          = readInt(OT.season_reg);
  data.ot_master_id           = readInt(OT.ot_master_id);
  data.ot_fw_version          = readNum(OT.fw_version);
  data.ot_temp_sensor_type    = readInt(OT.temp_sensor_type);
  data.ot_heating_setpoint    = readNum(OT.heating_setpoint);

  data.ot_decoded = decodeOpenThermStatus(data.ot_boiler_status_raw);

  data.pump_gvs        = readBool(PUMP_GVS);
  data.pump_floor      = readBool(PUMP_FLOOR);
  data.pump_rad_base   = readBool(PUMP_RAD_BASE);
  data.pump_rad_living = readBool(PUMP_RAD_LIVING);
  data.pump_recirc     = readBool(PUMP_RECIRC);
  data.pump_vent       = readBool(PUMP_VENT);

  data.t_boiler_dhw    = readNum(T_BOILER_DHW);
  data.t_rad_base      = readNum(T_RAD_BASE);
  data.t_outside       = readNum(T_OUTSIDE);
  data.t_floor         = readNum(T_FLOOR);
  data.t_rad_living    = readNum(T_RAD_LIVING);
  data.t_supply        = readNum(T_SUPPLY);

  data.floor_valve_enable = readBool(FLOOR_VALVE_ENABLE);
  data.floor_valve_pos    = readNum(FLOOR_VALVE_POS);

  data.dt_rad_base   = delta(data.t_supply, data.t_rad_base);
  data.dt_rad_living = delta(data.t_supply, data.t_rad_living);
  data.dt_floor      = delta(data.t_supply, data.t_floor);
  data.dt_arrow      = delta(data.ot_heating_temperature, data.t_supply);

  return data;
}

function updateAntiCycle(d) {
  var minSp = readNum("boiler_room_boiler/min_supply_setpoint");
  if (minSp === null) minSp = ANTICYCLE_DEFAULT_MIN_SUPPLY_C;
  minSp = Math.max(40, Math.min(60, Math.round(minSp)));

  var supply = d.t_supply;
  var now = nowSec();
  var resumeThreshold = round1(minSp - ANTICYCLE_BAND_C);

  if (mem.antiCyclePauseActive) {
    var canResumeByTime = now >= mem.antiCyclePauseUntilTs;
    var canResumeByTemp = (supply !== null && supply <= resumeThreshold);
    if (canResumeByTime && canResumeByTemp) {
      mem.antiCyclePauseActive = false;
      mem.antiCyclePauseUntilTs = 0;
    }
  } else {
    if (supply !== null && supply >= minSp) {
      mem.antiCyclePauseActive = true;
      mem.antiCyclePauseUntilTs = now + ANTICYCLE_MIN_PAUSE_S;
    }
  }

  d.anti_min_supply_setpoint = minSp;
  d.anti_pause_active = mem.antiCyclePauseActive;
  d.anti_pause_setpoint = ANTICYCLE_PAUSE_SETPOINT_C;
  d.anti_resume_threshold = resumeThreshold;
  d.anti_pause_remaining_s = mem.antiCyclePauseActive ? Math.max(0, mem.antiCyclePauseUntilTs - now) : 0;

  try {
    if (readNum("dhw_priority_mgr/normal_setpoint") !== minSp) dev["dhw_priority_mgr/normal_setpoint"] = minSp;
  } catch (e) {}
}


/***************************************************************
 * 7. СТАТИСТИКА
 ***************************************************************/

function updateStatistics(d) {
  resetDailyIfNeeded();

  var ts = nowSec();
  var flame = d.ot_flame === 1;

  if (mem.lastUpdateTs === 0) {
    mem.lastUpdateTs = ts;
    mem.lastFlame = flame;
    return;
  }

  var dt = ts - mem.lastUpdateTs;
  if (dt < 0 || dt > 3600) dt = 0;

  if (mem.lastFlame === true) {
    mem.burnerRunSecondsTotal += dt;
    mem.burnerRunSecondsToday += dt;
  }

  if (mem.lastFlame === false && flame === true) {
    mem.burnerStartsTotal += 1;
    mem.burnerStartsToday += 1;
  }

  mem.lastFlame = flame;
  mem.lastUpdateTs = ts;
}


/***************************************************************
 * 8. НАГРЕВ БОЙЛЕРА
 ***************************************************************/

function updateDhwHeatingWatch(d) {
  var ts = nowSec();

  if (d.pump_gvs) {
    if (mem.dhwPumpOnSince === 0) {
      mem.dhwPumpOnSince = ts;
      mem.dhwStartTemp = d.t_boiler_dhw;
      mem.dhwProblemLatched = false;
    } else {
      if (
        !mem.dhwProblemLatched &&
        mem.dhwStartTemp !== null &&
        d.t_boiler_dhw !== null &&
        (ts - mem.dhwPumpOnSince) >= DHW_HEAT_CHECK_SECONDS
      ) {
        var rise = d.t_boiler_dhw - mem.dhwStartTemp;
        if (rise < DHW_MIN_RISE_C) {
          mem.dhwProblemLatched = true;
        }
      }
    }
  } else {
    mem.dhwPumpOnSince = 0;
    mem.dhwStartTemp = null;
    mem.dhwProblemLatched = false;
  }
}


/***************************************************************
 * 9. УЗЕЛ ПОДМЕСА
 ***************************************************************/

function updateFloorMixingWatch(d) {
  var ts = nowSec();
  var active = d.pump_floor && d.floor_valve_enable && d.floor_valve_pos !== null && d.floor_valve_pos >= FLOOR_VALVE_ACTIVE_POS;

  if (active) {
    if (mem.floorMixingOnSince === 0) {
      mem.floorMixingOnSince = ts;
      mem.floorMixingStartTemp = d.t_floor;
      mem.floorMixingProblemLatched = false;
    } else {
      if (
        !mem.floorMixingProblemLatched &&
        mem.floorMixingStartTemp !== null &&
        d.t_floor !== null &&
        (ts - mem.floorMixingOnSince) >= FLOOR_PUMP_CHECK_SECONDS
      ) {
        var rise = d.t_floor - mem.floorMixingStartTemp;
        if (rise < FLOOR_MIN_RISE_C) {
          mem.floorMixingProblemLatched = true;
        }
      }
    }
  } else {
    mem.floorMixingOnSince = 0;
    mem.floorMixingStartTemp = null;
    mem.floorMixingProblemLatched = false;
  }
}


/***************************************************************
 * 10. НЕТ ТЕПЛООТБОРА
 ***************************************************************/

function updateNoHeatPickupWatch(d) {
  var ts = nowSec();
  var flame = d.ot_flame === 1;
  var anyUsefulPump = d.pump_rad_base || d.pump_rad_living || d.pump_floor || d.pump_gvs;

  if (flame && !anyUsefulPump) {
    if (mem.noHeatPickupSince === 0) {
      mem.noHeatPickupSince = ts;
    }
  } else {
    mem.noHeatPickupSince = 0;
  }
}


/***************************************************************
 * 11. ТЕКСТОВАЯ ДИАГНОСТИКА
 ***************************************************************/

function buildBoilerStateText(d) {
  if (d.ot_invalid_connection === 1) {
    return "нет корректной связи с котлом";
  }

  if (d.ot_error_code !== null && d.ot_error_code > 0) {
    return "ошибка котла (код " + d.ot_error_code + ")";
  }

  if (d.ot_fault_indication === 1 || d.ot_decoded.s_fault) {
    return "котёл сообщает об ошибке";
  }

  if (d.ot_flame === 1 && d.ot_ch_mode === 1) {
    return "горелка включена, идёт нагрев отопления";
  }

  if (d.ot_flame === 1 && d.ot_decoded.s_dhw_mode) {
    return "горелка включена, идёт нагрев ГВС";
  }

  if (d.ot_flame === 1) {
    return "горелка включена";
  }

  if (d.ot_ch_mode === 1) {
    return "режим отопления активен, горелка сейчас выключена";
  }

  if (d.ot_master_ch_enable === 1 || d.ot_decoded.m_ch_enable) {
    return "отопление разрешено, котёл в ожидании";
  }

  return "отопление не активно";
}

function classifyPressureText(pressure) {
  if (pressure === null) return "нет данных";

  if (pressure < PRESSURE_LOW_BAR) return "давление низкое";
  if (pressure < PRESSURE_WARN_BAR) return "давление ниже желательного";
  if (pressure <= 2.5) return "давление в норме";
  if (pressure <= PRESSURE_HIGH_BAR) return "давление повышенное";
  return "давление слишком высокое";
}

function classifyDeltaRadiatorText(dtValue) {
  if (dtValue === null) return "нет данных";
  if (dtValue < DT_RADIATOR_LOW_C) return "слишком маленькая ΔT";
  if (dtValue <= DT_RADIATOR_NORMAL_MAX_C) return "ΔT в норме";
  if (dtValue < DT_RADIATOR_ALARM_C) return "ΔT повышена";
  return "ΔT аварийно высокая";
}

function classifyArrowDeltaText(dtValue) {
  if (dtValue === null) return "нет данных";
  if (dtValue <= DT_ARROW_WARN_C) return "разница котёл/система нормальная";
  if (dtValue < DT_ARROW_ALARM_C) return "котёл греет быстрее, чем система забирает тепло";
  return "система плохо забирает тепло";
}

function buildCirculationText(d) {
  var flame = d.ot_flame === 1;
  var anyHeatingPump = d.pump_rad_base || d.pump_rad_living || d.pump_floor;
  var anyUsefulPump = anyHeatingPump || d.pump_gvs;

  if (d.ot_invalid_connection === 1) {
    return "невозможно оценить из-за ошибки связи";
  }

  if (!flame && !anyUsefulPump) {
    return "активного теплоотбора сейчас нет";
  }

  if (flame && !anyUsefulPump) {
    return "котёл греет, но контуры и бойлер не забирают тепло";
  }

  if (flame && d.dt_arrow !== null && d.dt_arrow >= DT_ARROW_ALARM_C) {
    return "котёл греет, но система забирает тепло плохо";
  }

  if (flame && anyUsefulPump) {
    return "циркуляция выглядит нормальной";
  }

  if (!flame && anyUsefulPump) {
    return "контуры работают на выбег/перенос остаточного тепла";
  }

  return "нет явных признаков проблемы";
}

function buildDhwText(d) {
  if (d.pump_gvs) {
    if (mem.dhwProblemLatched) {
      return "насос бойлера работает, но бойлер греется плохо";
    }
    return "идёт нагрев бойлера";
  }

  if (d.pump_recirc) {
    return "работает рециркуляция ГВС";
  }

  return "контур бойлера сейчас не активен";
}

function buildFloorMixingText(d) {
  var parts = [];

  parts.push(d.pump_floor ? "насос пола включён" : "насос пола выключен");
  parts.push(d.floor_valve_enable ? "клапан подмеса разрешён" : "клапан подмеса выключен");

  if (d.floor_valve_pos !== null) {
    parts.push("положение клапана " + round1(d.floor_valve_pos) + "%");
  }

  if (mem.floorMixingProblemLatched) {
    parts.push("возможна проблема подмеса или циркуляции");
  }

  return parts.join("; ");
}

function buildSystemNotes(d) {
  var notes = [];

  if (d.ot_invalid_connection === 1) {
    notes.push("адаптер OpenTherm сообщает о некорректной связи с котлом");
  }

  if (d.ot_error_code !== null && d.ot_error_code > 0) {
    notes.push("котёл выдал код ошибки " + d.ot_error_code);
  }

  if (d.ot_water_pressure !== null) {
    if (d.ot_water_pressure < PRESSURE_LOW_BAR) {
      notes.push("давление системы низкое");
    } else if (d.ot_water_pressure < PRESSURE_WARN_BAR) {
      notes.push("давление ниже желательного");
    } else if (d.ot_water_pressure > PRESSURE_HIGH_BAR) {
      notes.push("давление слишком высокое");
    }
  }

  if (d.dt_arrow !== null && d.dt_arrow >= DT_ARROW_WARN_C) {
    notes.push("заметная разница между температурой в котле и температурой трубы подачи");
  }

  if (d.dt_rad_base !== null && d.dt_rad_base >= DT_RADIATOR_ALARM_C) {
    notes.push("контур радиаторов цоколя забирает тепло слабо");
  }

  if (d.dt_rad_living !== null && d.dt_rad_living >= DT_RADIATOR_ALARM_C) {
    notes.push("контур радиаторов жилого этажа забирает тепло слабо");
  }

  if (d.dt_rad_base !== null && d.dt_rad_base < DT_RADIATOR_LOW_C && d.pump_rad_base) {
    notes.push("в контуре цоколя слишком маленькая ΔT");
  }

  if (d.dt_rad_living !== null && d.dt_rad_living < DT_RADIATOR_LOW_C && d.pump_rad_living) {
    notes.push("в контуре жилого этажа слишком маленькая ΔT");
  }

  if (d.ot_decoded.m_cooling_enable || d.ot_decoded.s_cooling) {
    notes.push("в OpenTherm установлен флаг cooling, для этого котла он обычно не используется");
  }

  if (d.ot_decoded.m_dhw_enable) {
    notes.push("контроллер разрешает ГВС по OpenTherm");
  }

  if (d.ot_decoded.m_ch2_enable && !d.ot_decoded.s_ch2_mode) {
    notes.push("второй контур разрешён контроллером, но котлом не активирован");
  }

  if (d.ot_heating_temperature !== null && d.ot_heating_temperature >= BOILER_HIGH_TEMP_WARN_C) {
    notes.push("температура котла высокая");
  }

  return notes.length ? notes.join("; ") : "замечаний нет";
}


/***************************************************************
 * 12. АВАРИИ
 ***************************************************************/

function buildAlarms(d) {
  var ts = nowSec();

  var alarms = {
    boiler_fault: false,
    invalid_connection: false,
    low_pressure: false,
    overheat: false,
    no_heat_pickup: false,
    poor_circulation: false,
    dhw_problem: false,
    floor_mixing_problem: false,

    summary: "аварий нет",
    details: "аварий нет"
  };

  alarms.invalid_connection = (d.ot_invalid_connection === 1);
  alarms.boiler_fault = (
    (d.ot_error_code !== null && d.ot_error_code > 0) ||
    d.ot_fault_indication === 1 ||
    d.ot_decoded.s_fault
  );

  alarms.low_pressure = (d.ot_water_pressure !== null && d.ot_water_pressure < PRESSURE_LOW_BAR);
  alarms.overheat = (d.ot_heating_temperature !== null && d.ot_heating_temperature >= BOILER_OVERHEAT_C);

  if (mem.noHeatPickupSince > 0 && (ts - mem.noHeatPickupSince) >= NO_HEAT_PICKUP_SECONDS) {
    alarms.no_heat_pickup = true;
  }

  if (d.ot_flame === 1 && d.dt_arrow !== null && d.dt_arrow >= DT_ARROW_ALARM_C) {
    alarms.poor_circulation = true;
  }

  alarms.dhw_problem = mem.dhwProblemLatched;
  alarms.floor_mixing_problem = mem.floorMixingProblemLatched;

  var summary = [];
  var details = [];

  if (alarms.invalid_connection)  { summary.push("связь"); details.push("нет корректной связи OpenTherm"); }
  if (alarms.boiler_fault)        { summary.push("котёл"); details.push("котёл сообщает об ошибке"); }
  if (alarms.low_pressure)        { summary.push("давление"); details.push("давление системы ниже допустимого"); }
  if (alarms.overheat)            { summary.push("перегрев"); details.push("температура котла слишком высокая"); }
  if (alarms.no_heat_pickup)      { summary.push("нет теплоотбора"); details.push("котёл греет, но система не забирает тепло"); }
  if (alarms.poor_circulation)    { summary.push("циркуляция"); details.push("признаки плохой циркуляции или малого теплоотбора"); }
  if (alarms.dhw_problem)         { summary.push("бойлер"); details.push("насос бойлера работает, но бойлер почти не нагревается"); }
  if (alarms.floor_mixing_problem){ summary.push("подмес"); details.push("узел подмеса пола работает неэффективно"); }

  alarms.summary = summary.length ? summary.join(", ") : "аварий нет";
  alarms.details = details.length ? details.join("; ") : "аварий нет";

  return alarms;
}

function updateAlarmSignature(alarms) {
  var signature = [
    alarms.invalid_connection ? 1 : 0,
    alarms.boiler_fault ? 1 : 0,
    alarms.low_pressure ? 1 : 0,
    alarms.overheat ? 1 : 0,
    alarms.no_heat_pickup ? 1 : 0,
    alarms.poor_circulation ? 1 : 0,
    alarms.dhw_problem ? 1 : 0,
    alarms.floor_mixing_problem ? 1 : 0
  ].join("");

  if (signature !== mem.lastAlarmSignature) {
    mem.lastAlarmSignature = signature;
    mem.lastAlarmChangeTs = nowSec();
  }
}


/***************************************************************
 * 13. ВИРТУАЛЬНЫЕ УСТРОЙСТВА
 ***************************************************************/

defineVirtualDevice("boiler_room_boiler", {
  title: "Котельная / Котёл",
  cells: {
    state:          { type: "text",   value: "", readonly: true, title: "Состояние" },
    flame:          { type: "switch", value: false, readonly: true, title: "Горелка" },
    ch_mode:        { type: "switch", value: false, readonly: true, title: "Режим отопления" },
    fault:          { type: "switch", value: false, readonly: true, title: "Ошибка котла" },
    temperature:    { type: "value",  value: 0, readonly: true, title: "Температура котла, °C" },
    setpoint:       { type: "value",  value: 0, readonly: true, title: "Уставка отопления, °C" },
    pressure:       { type: "value",  value: 0, readonly: true, title: "Давление, bar" },
    error_code:     { type: "value",  value: 0, readonly: true, title: "Код ошибки" },
    pressure_state: { type: "text",   value: "", readonly: true, title: "Оценка давления" },
    min_supply_setpoint: { type: "range", value: ANTICYCLE_DEFAULT_MIN_SUPPLY_C, min: 40, max: 60, step: 1, title: "Минимальная уставка теплоносителя, °C" },
    ch_pause_active: { type: "switch", value: false, readonly: true, title: "Отопление на паузе" },
    ch_pause_setpoint: { type: "value", value: ANTICYCLE_PAUSE_SETPOINT_C, readonly: true, title: "Уставка во время паузы, °C" },
    anticycle_status: { type: "text", value: "", readonly: true, title: "Антициклирование" },
    notes:          { type: "text",   value: "", readonly: true, title: "Заметки по котлу" }
  }
});

defineVirtualDevice("boiler_room_opentherm", {
  title: "Котельная / OpenTherm",
  cells: {
    status_raw:   { type: "value",  value: 0, readonly: true, title: "Boiler Status (dec)" },
    status_hex:   { type: "text",   value: "", readonly: true, title: "Boiler Status (hex)" },
    master_hex:   { type: "text",   value: "", readonly: true, title: "Master byte" },
    slave_hex:    { type: "text",   value: "", readonly: true, title: "Slave byte" },

    master_flags: { type: "text",   value: "", readonly: true, title: "Команды контроллера" },
    slave_flags:  { type: "text",   value: "", readonly: true, title: "Состояние котла" },
    summary:      { type: "text",   value: "", readonly: true, title: "Краткая расшифровка" },

    m_ch:         { type: "switch", value: false, readonly: true, title: "Master CH enable" },
    m_dhw:        { type: "switch", value: false, readonly: true, title: "Master DHW enable" },
    m_otc:        { type: "switch", value: false, readonly: true, title: "Master OTC active" },
    m_ch2:        { type: "switch", value: false, readonly: true, title: "Master CH2 enable" },

    s_fault:      { type: "switch", value: false, readonly: true, title: "Slave fault" },
    s_ch:         { type: "switch", value: false, readonly: true, title: "Slave CH mode" },
    s_dhw:        { type: "switch", value: false, readonly: true, title: "Slave DHW mode" },
    s_flame:      { type: "switch", value: false, readonly: true, title: "Slave flame" },
    s_diag:       { type: "switch", value: false, readonly: true, title: "Slave diagnostic" }
  }
});

defineVirtualDevice("boiler_room_pumps", {
  title: "Котельная / Насосы",
  cells: {
    gvs:         { type: "switch", value: false, readonly: true, title: "Насос ГВС" },
    floor:       { type: "switch", value: false, readonly: true, title: "Насос тёплого пола" },
    rad_base:    { type: "switch", value: false, readonly: true, title: "Насос радиаторов цоколь" },
    rad_living:  { type: "switch", value: false, readonly: true, title: "Насос радиаторов жилой этаж" },
    recirc:      { type: "switch", value: false, readonly: true, title: "Насос рециркуляции ГВС" },
    vent:        { type: "switch", value: false, readonly: true, title: "Насос вентиляции" },
    useful_load: { type: "text",   value: "", readonly: true, title: "Полезный теплоотбор" },
    notes:       { type: "text",   value: "", readonly: true, title: "Заметки по насосам" }
  }
});

defineVirtualDevice("boiler_room_temperatures", {
  title: "Котельная / Температуры",
  cells: {
    boiler_ot:  { type: "value", value: 0, readonly: true, title: "Котёл по OpenTherm, °C" },
    supply:     { type: "value", value: 0, readonly: true, title: "Подача от котла, °C" },
    rad_base:   { type: "value", value: 0, readonly: true, title: "Радиаторы цоколь, °C" },
    rad_living: { type: "value", value: 0, readonly: true, title: "Радиаторы жилой этаж, °C" },
    floor:      { type: "value", value: 0, readonly: true, title: "Тёплый пол, °C" },
    dhw:        { type: "value", value: 0, readonly: true, title: "Бойлер, °C" },
    outside:    { type: "value", value: 0, readonly: true, title: "Улица, °C" },
    notes:      { type: "text",  value: "", readonly: true, title: "Заметки по температурам" }
  }
});

defineVirtualDevice("boiler_room_deltas", {
  title: "Котельная / ΔT",
  cells: {
    dt_arrow:      { type: "value", value: 0, readonly: true, title: "ΔT котёл/система, °C" },
    dt_rad_base:   { type: "value", value: 0, readonly: true, title: "ΔT радиаторы цоколь, °C" },
    dt_rad_living: { type: "value", value: 0, readonly: true, title: "ΔT радиаторы жилой этаж, °C" },
    dt_floor:      { type: "value", value: 0, readonly: true, title: "ΔT подача/тёплый пол, °C" },

    arrow_state:   { type: "text", value: "", readonly: true, title: "Оценка котёл/система" },
    base_state:    { type: "text", value: "", readonly: true, title: "Оценка цоколь" },
    living_state:  { type: "text", value: "", readonly: true, title: "Оценка жилой этаж" }
  }
});

defineVirtualDevice("boiler_room_mixing", {
  title: "Котельная / Подмес",
  cells: {
    valve_enable: { type: "switch", value: false, readonly: true, title: "Клапан включён" },
    valve_pos:    { type: "value",  value: 0, readonly: true, title: "Положение клапана, %" },
    floor_pump:   { type: "switch", value: false, readonly: true, title: "Насос пола" },
    floor_temp:   { type: "value",  value: 0, readonly: true, title: "Температура пола, °C" },
    state:        { type: "text",   value: "", readonly: true, title: "Состояние узла" },
    notes:        { type: "text",   value: "", readonly: true, title: "Заметки по подмесу" }
  }
});

defineVirtualDevice("boiler_room_diagnostics", {
  title: "Котельная / Диагностика",
  cells: {
    boiler_state:      { type: "text", value: "", readonly: true, title: "Состояние котла" },
    circulation:       { type: "text", value: "", readonly: true, title: "Циркуляция" },
    dhw_state:         { type: "text", value: "", readonly: true, title: "Бойлер / ГВС" },
    floor_mixing:      { type: "text", value: "", readonly: true, title: "Подмес тёплого пола" },
    system_notes:      { type: "text", value: "", readonly: true, title: "Общие замечания" },
    last_alarm_change: { type: "value", value: 0, readonly: true, title: "Последнее изменение тревог, unix" }
  }
});

defineVirtualDevice("boiler_room_alarms", {
  title: "Котельная / Аварии",
  cells: {
    invalid_connection:   { type: "switch", value: false, readonly: true, title: "Нет связи OpenTherm" },
    boiler_fault:         { type: "switch", value: false, readonly: true, title: "Ошибка котла" },
    low_pressure:         { type: "switch", value: false, readonly: true, title: "Низкое давление" },
    overheat:             { type: "switch", value: false, readonly: true, title: "Перегрев котла" },
    no_heat_pickup:       { type: "switch", value: false, readonly: true, title: "Нет теплоотбора" },
    poor_circulation:     { type: "switch", value: false, readonly: true, title: "Плохая циркуляция" },
    dhw_problem:          { type: "switch", value: false, readonly: true, title: "Бойлер не греется" },
    floor_mixing_problem: { type: "switch", value: false, readonly: true, title: "Проблема подмеса" },
    summary:              { type: "text",   value: "", readonly: true, title: "Кратко" },
    details:              { type: "text",   value: "", readonly: true, title: "Подробно" }
  }
});

defineVirtualDevice("boiler_room_statistics", {
  title: "Котельная / Статистика",
  cells: {
    burner_starts_total: { type: "value", value: 0, readonly: true, title: "Пусков горелки всего" },
    burner_hours_total:  { type: "value", value: 0, readonly: true, title: "Часы горелки всего" },
    burner_starts_today: { type: "value", value: 0, readonly: true, title: "Пусков горелки сегодня" },
    burner_hours_today:  { type: "value", value: 0, readonly: true, title: "Часы горелки сегодня" },
    fw_version:          { type: "value", value: 0, readonly: true, title: "FW Version OT" },
    ot_master_id:        { type: "value", value: 0, readonly: true, title: "OT MasterID" },
    ch_min_value:        { type: "value", value: 0, readonly: true, title: "CH Min Value" },
    ch_max_value:        { type: "value", value: 0, readonly: true, title: "CH Max Value" }
  }
});


/***************************************************************
 * 14. ПУБЛИКАЦИЯ В ПАНЕЛИ
 ***************************************************************/

function publishAll(d, alarms, boilerStateText, circulationText, dhwText, floorMixText, systemNotesText) {
  var anyUsefulPump = d.pump_rad_base || d.pump_rad_living || d.pump_floor || d.pump_gvs;
  var usefulLoadText = anyUsefulPump ? "есть активный теплоотбор" : "полезный теплоотбор не активен";

  var pumpNotes = [];
  if (d.pump_recirc) pumpNotes.push("рециркуляция ГВС включена");
  if (d.pump_vent) pumpNotes.push("вентиляция включена");
  if (!anyUsefulPump && d.ot_flame === 1) pumpNotes.push("котёл горит, а полезные контуры не активны");

  var boilerNotes = [];
  if (d.ot_decoded.m_otc_active) boilerNotes.push("активна погодозависимая регулировка");
  if (d.ot_auto_temp_switch === 1) boilerNotes.push("автопереключение температуры активно");
  if (d.ot_season_reg === 1) boilerNotes.push("сезонное регулирование активно");
  if (d.anti_pause_active) boilerNotes.push("антициклирование: отопление на паузе ещё " + Math.ceil(d.anti_pause_remaining_s / 60) + " мин");

  var tempNotes = [];
  if (d.dt_arrow !== null) {
    tempNotes.push("ΔT котёл/система = " + d.dt_arrow + " °C");
  }

  var mixingState = "";
  if (!d.pump_floor && !d.floor_valve_enable) {
    mixingState = "узел пола не активен";
  } else if (mem.floorMixingProblemLatched) {
    mixingState = "есть подозрение на проблему узла подмеса";
  } else if (d.pump_floor) {
    mixingState = "узел пола активен";
  } else {
    mixingState = "готов, но не качает";
  }

  dev["boiler_room_boiler/state"] = boilerStateText;
  dev["boiler_room_boiler/flame"] = d.ot_flame === 1;
  dev["boiler_room_boiler/ch_mode"] = d.ot_ch_mode === 1;
  dev["boiler_room_boiler/fault"] = alarms.boiler_fault;
  dev["boiler_room_boiler/temperature"] = d.ot_heating_temperature !== null ? round1(d.ot_heating_temperature) : 0;
  dev["boiler_room_boiler/setpoint"] = d.ot_heating_setpoint !== null ? round1(d.ot_heating_setpoint) : 0;
  dev["boiler_room_boiler/pressure"] = d.ot_water_pressure !== null ? round2(d.ot_water_pressure) : 0;
  dev["boiler_room_boiler/error_code"] = d.ot_error_code !== null ? d.ot_error_code : 0;
  dev["boiler_room_boiler/pressure_state"] = classifyPressureText(d.ot_water_pressure);
  dev["boiler_room_boiler/min_supply_setpoint"] = d.anti_min_supply_setpoint;
  dev["boiler_room_boiler/ch_pause_active"] = d.anti_pause_active;
  dev["boiler_room_boiler/ch_pause_setpoint"] = d.anti_pause_setpoint;
  dev["boiler_room_boiler/anticycle_status"] = d.anti_pause_active ? ("пауза, возобновление при ≤ " + d.anti_resume_threshold + " °C и не ранее чем через " + Math.ceil(d.anti_pause_remaining_s/60) + " мин") : ("активно, пауза при ≥ " + d.anti_min_supply_setpoint + " °C");
  dev["boiler_room_boiler/notes"] = joinText(boilerNotes, "замечаний нет");

  dev["boiler_room_opentherm/status_raw"] = d.ot_boiler_status_raw !== null ? d.ot_boiler_status_raw : 0;
  dev["boiler_room_opentherm/status_hex"] = d.ot_decoded.hex;
  dev["boiler_room_opentherm/master_hex"] = d.ot_decoded.masterByte !== null ? ("0x" + hex2(d.ot_decoded.masterByte)) : "";
  dev["boiler_room_opentherm/slave_hex"] = d.ot_decoded.slaveByte !== null ? ("0x" + hex2(d.ot_decoded.slaveByte)) : "";
  dev["boiler_room_opentherm/master_flags"] = d.ot_decoded.masterFlagsText;
  dev["boiler_room_opentherm/slave_flags"] = d.ot_decoded.slaveFlagsText;
  dev["boiler_room_opentherm/summary"] = d.ot_decoded.summaryText;
  dev["boiler_room_opentherm/m_ch"] = d.ot_decoded.m_ch_enable;
  dev["boiler_room_opentherm/m_dhw"] = d.ot_decoded.m_dhw_enable;
  dev["boiler_room_opentherm/m_otc"] = d.ot_decoded.m_otc_active;
  dev["boiler_room_opentherm/m_ch2"] = d.ot_decoded.m_ch2_enable;
  dev["boiler_room_opentherm/s_fault"] = d.ot_decoded.s_fault;
  dev["boiler_room_opentherm/s_ch"] = d.ot_decoded.s_ch_mode;
  dev["boiler_room_opentherm/s_dhw"] = d.ot_decoded.s_dhw_mode;
  dev["boiler_room_opentherm/s_flame"] = d.ot_decoded.s_flame;
  dev["boiler_room_opentherm/s_diag"] = d.ot_decoded.s_diag;

  dev["boiler_room_pumps/gvs"] = d.pump_gvs;
  dev["boiler_room_pumps/floor"] = d.pump_floor;
  dev["boiler_room_pumps/rad_base"] = d.pump_rad_base;
  dev["boiler_room_pumps/rad_living"] = d.pump_rad_living;
  dev["boiler_room_pumps/recirc"] = d.pump_recirc;
  dev["boiler_room_pumps/vent"] = d.pump_vent;
  dev["boiler_room_pumps/useful_load"] = usefulLoadText;
  dev["boiler_room_pumps/notes"] = joinText(pumpNotes, "замечаний нет");

  dev["boiler_room_temperatures/boiler_ot"] = d.ot_heating_temperature !== null ? round1(d.ot_heating_temperature) : 0;
  dev["boiler_room_temperatures/supply"] = d.t_supply !== null ? round1(d.t_supply) : 0;
  dev["boiler_room_temperatures/rad_base"] = d.t_rad_base !== null ? round1(d.t_rad_base) : 0;
  dev["boiler_room_temperatures/rad_living"] = d.t_rad_living !== null ? round1(d.t_rad_living) : 0;
  dev["boiler_room_temperatures/floor"] = d.t_floor !== null ? round1(d.t_floor) : 0;
  dev["boiler_room_temperatures/dhw"] = d.t_boiler_dhw !== null ? round1(d.t_boiler_dhw) : 0;
  dev["boiler_room_temperatures/outside"] = d.t_outside !== null ? round1(d.t_outside) : 0;
  dev["boiler_room_temperatures/notes"] = joinText(tempNotes, "замечаний нет");

  dev["boiler_room_deltas/dt_arrow"] = d.dt_arrow !== null ? d.dt_arrow : 0;
  dev["boiler_room_deltas/dt_rad_base"] = d.dt_rad_base !== null ? d.dt_rad_base : 0;
  dev["boiler_room_deltas/dt_rad_living"] = d.dt_rad_living !== null ? d.dt_rad_living : 0;
  dev["boiler_room_deltas/dt_floor"] = d.dt_floor !== null ? d.dt_floor : 0;
  dev["boiler_room_deltas/arrow_state"] = classifyArrowDeltaText(d.dt_arrow);
  dev["boiler_room_deltas/base_state"] = classifyDeltaRadiatorText(d.dt_rad_base);
  dev["boiler_room_deltas/living_state"] = classifyDeltaRadiatorText(d.dt_rad_living);

  dev["boiler_room_mixing/valve_enable"] = d.floor_valve_enable;
  dev["boiler_room_mixing/valve_pos"] = d.floor_valve_pos !== null ? round1(d.floor_valve_pos) : 0;
  dev["boiler_room_mixing/floor_pump"] = d.pump_floor;
  dev["boiler_room_mixing/floor_temp"] = d.t_floor !== null ? round1(d.t_floor) : 0;
  dev["boiler_room_mixing/state"] = mixingState;
  dev["boiler_room_mixing/notes"] = floorMixText;

  dev["boiler_room_diagnostics/boiler_state"] = boilerStateText;
  dev["boiler_room_diagnostics/circulation"] = circulationText;
  dev["boiler_room_diagnostics/dhw_state"] = dhwText;
  dev["boiler_room_diagnostics/floor_mixing"] = floorMixText;
  dev["boiler_room_diagnostics/system_notes"] = systemNotesText;
  dev["boiler_room_diagnostics/last_alarm_change"] = mem.lastAlarmChangeTs;

  dev["boiler_room_alarms/invalid_connection"] = alarms.invalid_connection;
  dev["boiler_room_alarms/boiler_fault"] = alarms.boiler_fault;
  dev["boiler_room_alarms/low_pressure"] = alarms.low_pressure;
  dev["boiler_room_alarms/overheat"] = alarms.overheat;
  dev["boiler_room_alarms/no_heat_pickup"] = alarms.no_heat_pickup;
  dev["boiler_room_alarms/poor_circulation"] = alarms.poor_circulation;
  dev["boiler_room_alarms/dhw_problem"] = alarms.dhw_problem;
  dev["boiler_room_alarms/floor_mixing_problem"] = alarms.floor_mixing_problem;
  dev["boiler_room_alarms/summary"] = alarms.summary;
  dev["boiler_room_alarms/details"] = alarms.details;

  dev["boiler_room_statistics/burner_starts_total"] = mem.burnerStartsTotal;
  dev["boiler_room_statistics/burner_hours_total"] = round2(mem.burnerRunSecondsTotal / 3600.0);
  dev["boiler_room_statistics/burner_starts_today"] = mem.burnerStartsToday;
  dev["boiler_room_statistics/burner_hours_today"] = round2(mem.burnerRunSecondsToday / 3600.0);
  dev["boiler_room_statistics/fw_version"] = d.ot_fw_version !== null ? d.ot_fw_version : 0;
  dev["boiler_room_statistics/ot_master_id"] = d.ot_master_id !== null ? d.ot_master_id : 0;
  dev["boiler_room_statistics/ch_min_value"] = d.ot_ch_min_value !== null ? d.ot_ch_min_value : 0;
  dev["boiler_room_statistics/ch_max_value"] = d.ot_ch_max_value !== null ? d.ot_ch_max_value : 0;
}


/***************************************************************
 * 15. ГЛАВНАЯ ФУНКЦИЯ
 ***************************************************************/

function updateAll() {
  var d = readAll();

  updateStatistics(d);
  updateDhwHeatingWatch(d);
  updateFloorMixingWatch(d);
  updateNoHeatPickupWatch(d);
  updateAntiCycle(d);

  var boilerStateText = buildBoilerStateText(d);
  var circulationText = buildCirculationText(d);
  var dhwText = buildDhwText(d);
  var floorMixText = buildFloorMixingText(d);
  var systemNotesText = buildSystemNotes(d);

  var alarms = buildAlarms(d);
  updateAlarmSignature(alarms);

  publishAll(d, alarms, boilerStateText, circulationText, dhwText, floorMixText, systemNotesText);
}


/***************************************************************
 * 16. ПРАВИЛА
 ***************************************************************/

function updateAllWrapper() {
  updateAll();
}

defineRule("boiler_room_update_on_ot_status", {
  whenChanged: OT.boiler_status,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_flame", {
  whenChanged: OT.flame,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_ch_mode", {
  whenChanged: OT.ch_mode,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_temp", {
  whenChanged: OT.heating_temperature,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_pressure", {
  whenChanged: OT.water_pressure,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_error", {
  whenChanged: OT.error_code,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_invalid", {
  whenChanged: OT.invalid_connection,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_ot_setpoint", {
  whenChanged: OT.heating_setpoint,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_gvs", {
  whenChanged: PUMP_GVS,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_floor", {
  whenChanged: PUMP_FLOOR,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_rad_base", {
  whenChanged: PUMP_RAD_BASE,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_rad_living", {
  whenChanged: PUMP_RAD_LIVING,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_recirc", {
  whenChanged: PUMP_RECIRC,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_pump_vent", {
  whenChanged: PUMP_VENT,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_dhw", {
  whenChanged: T_BOILER_DHW,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_rad_base", {
  whenChanged: T_RAD_BASE,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_outside", {
  whenChanged: T_OUTSIDE,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_floor", {
  whenChanged: T_FLOOR,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_rad_living", {
  whenChanged: T_RAD_LIVING,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_t_supply", {
  whenChanged: T_SUPPLY,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_floor_valve_enable", {
  whenChanged: FLOOR_VALVE_ENABLE,
  then: updateAllWrapper
});

defineRule("boiler_room_update_on_floor_valve_pos", {
  whenChanged: FLOOR_VALVE_POS,
  then: updateAllWrapper
});

/* Раз в минуту — для длительных состояний и статистики */
defineRule("boiler_room_periodic_update", {
  when: cron("0 * * * * *"),
  then: updateAllWrapper
});

/* Инициализация после старта */
//defineRule("boiler_room_init_on_boot", {
//  when: cron("@reboot"),
//  then: function () {
//    updateAll();
//  }
//});