// Режим осушения сауны

var SAUNA_DRYING_CFG = {
  currents: {
    l1: "wb-map12e_35/Ch 2 Irms L1",
    l2: "wb-map12e_35/Ch 2 Irms L2",
    l3: "wb-map12e_35/Ch 2 Irms L3"
  },

  thresholds: {
    sauna_on_a: 13,
    l1_off_a: 2,
    confirm_ms: 60 * 1000
  },

  drying: {
    duration_ms: 30 * 60 * 1000,
    exhaust_open_pct: 100,
    fan_speed_pct: 100,
    other_valves_pct: 5
  },

  channels: {
    sauna_shower_exhaust: "wb-mao4_200/Channel 1 Dimming Level",
    master_bedroom_wc_exhaust: "wb-mao4_200/Channel 2 Dimming Level",
    living_exhaust: "wb-mao4_200/Channel 3 Dimming Level",
    guest_exhaust: "wb-mao4_200/Channel 4 Dimming Level",
    office_exhaust: "wb-mao4_220/Channel 1 Dimming Level",
    fan_speed: "wb-mao4_220/Channel 2 Dimming Level"
  },

  tick_sec: 5,
  vdev_name: "sauna_drying_mode",
  vdev_title: "Сауна / Осушение"
};

var saunaDryingState = {
  sauna_was_on: false,
  drying_active: false,
  condition_since_ms: 0,
  drying_started_ms: 0,
  drying_until_ms: 0,
  stop_reason: "",
  saved_levels: {}
};

defineVirtualDevice(SAUNA_DRYING_CFG.vdev_name, {
  title: SAUNA_DRYING_CFG.vdev_title,
  cells: {
    active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Осушение активно"
    },
    sauna_was_on: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Сауна была включена"
    },
    condition_active: {
      type: "switch",
      value: false,
      readonly: true,
      title: "Условие осушения активно"
    },
    timer_left_min: {
      type: "value",
      value: 0,
      readonly: true,
      title: "Осталось, мин"
    },
    l1: {
      type: "value",
      value: 0,
      readonly: true,
      title: "L1, A"
    },
    l2: {
      type: "value",
      value: 0,
      readonly: true,
      title: "L2, A"
    },
    l3: {
      type: "value",
      value: 0,
      readonly: true,
      title: "L3, A"
    },
    status: {
      type: "text",
      value: "",
      readonly: true,
      title: "Статус"
    },
    stop_reason: {
      type: "text",
      value: "",
      readonly: true,
      title: "Причина остановки"
    }
  }
});

function sdNow() {
  return new Date().getTime();
}

function sdToNumber(v) {
  if (v === undefined || v === null || v === "") return null;
  v = Number(v);
  if (isNaN(v)) return null;
  return v;
}

function sdRound1(v) {
  return Math.round(v * 10) / 10;
}

function sdRead(cell) {
  return sdToNumber(dev[cell]);
}

function sdWrite(cell, value) {
  dev[cell] = value;
}

function sdLog(msg) {
  log("sauna_drying: " + msg);
}

function sdGetCurrents() {
  return {
    l1: sdRead(SAUNA_DRYING_CFG.currents.l1),
    l2: sdRead(SAUNA_DRYING_CFG.currents.l2),
    l3: sdRead(SAUNA_DRYING_CFG.currents.l3)
  };
}

function sdIsSaunaOn(c) {
  return c.l1 !== null &&
         c.l2 !== null &&
         c.l3 !== null &&
         c.l1 >= SAUNA_DRYING_CFG.thresholds.sauna_on_a &&
         c.l2 >= SAUNA_DRYING_CFG.thresholds.sauna_on_a &&
         c.l3 >= SAUNA_DRYING_CFG.thresholds.sauna_on_a;
}

function sdIsDryingCondition(c) {
  return c.l1 !== null &&
         c.l2 !== null &&
         c.l3 !== null &&
         c.l1 <= SAUNA_DRYING_CFG.thresholds.l1_off_a &&
         c.l2 >= SAUNA_DRYING_CFG.thresholds.sauna_on_a &&
         c.l3 >= SAUNA_DRYING_CFG.thresholds.sauna_on_a;
}

function sdGetControlledChannels() {
  return [
    SAUNA_DRYING_CFG.channels.sauna_shower_exhaust,
    SAUNA_DRYING_CFG.channels.master_bedroom_wc_exhaust,
    SAUNA_DRYING_CFG.channels.living_exhaust,
    SAUNA_DRYING_CFG.channels.guest_exhaust,
    SAUNA_DRYING_CFG.channels.office_exhaust,
    SAUNA_DRYING_CFG.channels.fan_speed
  ];
}

function sdSaveLevels() {
  var arr = sdGetControlledChannels();
  var i;
  saunaDryingState.saved_levels = {};

  for (i = 0; i < arr.length; i++) {
    saunaDryingState.saved_levels[arr[i]] = sdRead(arr[i]);
  }
}

function sdRestoreLevels() {
  var key;
  for (key in saunaDryingState.saved_levels) {
    if (saunaDryingState.saved_levels.hasOwnProperty(key)) {
      if (saunaDryingState.saved_levels[key] !== null) {
        sdWrite(key, saunaDryingState.saved_levels[key]);
      }
    }
  }
}

function sdApplyDryingLevels() {
  sdWrite(
    SAUNA_DRYING_CFG.channels.sauna_shower_exhaust,
    SAUNA_DRYING_CFG.drying.exhaust_open_pct
  );

  sdWrite(
    SAUNA_DRYING_CFG.channels.fan_speed,
    SAUNA_DRYING_CFG.drying.fan_speed_pct
  );

  sdWrite(
    SAUNA_DRYING_CFG.channels.master_bedroom_wc_exhaust,
    SAUNA_DRYING_CFG.drying.other_valves_pct
  );

  sdWrite(
    SAUNA_DRYING_CFG.channels.living_exhaust,
    SAUNA_DRYING_CFG.drying.other_valves_pct
  );

  sdWrite(
    SAUNA_DRYING_CFG.channels.guest_exhaust,
    SAUNA_DRYING_CFG.drying.other_valves_pct
  );

  sdWrite(
    SAUNA_DRYING_CFG.channels.office_exhaust,
    SAUNA_DRYING_CFG.drying.other_valves_pct
  );
}

function sdStartDrying() {
  var now = sdNow();

  if (saunaDryingState.drying_active) return;

  sdSaveLevels();
  sdApplyDryingLevels();

  saunaDryingState.drying_active = true;
  saunaDryingState.drying_started_ms = now;
  saunaDryingState.drying_until_ms = now + SAUNA_DRYING_CFG.drying.duration_ms;
  saunaDryingState.stop_reason = "";

  sdLog("drying started");
}

function sdStopDrying(reason) {
  if (!saunaDryingState.drying_active) return;

  sdRestoreLevels();

  saunaDryingState.drying_active = false;
  saunaDryingState.drying_started_ms = 0;
  saunaDryingState.drying_until_ms = 0;
  saunaDryingState.condition_since_ms = 0;
  saunaDryingState.sauna_was_on = false;
  saunaDryingState.stop_reason = reason || "";
  saunaDryingState.saved_levels = {};

  sdLog("drying stopped: " + saunaDryingState.stop_reason);
}

function sdUpdateVdev(c, cond) {
  var left_ms = 0;
  var left_min = 0;
  var status = "";

  if (saunaDryingState.drying_active) {
    left_ms = saunaDryingState.drying_until_ms - sdNow();
    if (left_ms < 0) left_ms = 0;
    left_min = Math.ceil(left_ms / 60000);
    status = "осушение активно";
  } else {
    if (saunaDryingState.sauna_was_on) {
      if (cond) {
        status = "ожидание 1 мин перед запуском";
      } else {
        status = "сауна была включена, ждём условие осушения";
      }
    } else {
      status = "ожидание включения сауны";
    }
  }

  dev[SAUNA_DRYING_CFG.vdev_name + "/active"] = saunaDryingState.drying_active;
  dev[SAUNA_DRYING_CFG.vdev_name + "/sauna_was_on"] = saunaDryingState.sauna_was_on;
  dev[SAUNA_DRYING_CFG.vdev_name + "/condition_active"] = cond;
  dev[SAUNA_DRYING_CFG.vdev_name + "/timer_left_min"] = left_min;
  dev[SAUNA_DRYING_CFG.vdev_name + "/l1"] = (c.l1 === null ? 0 : sdRound1(c.l1));
  dev[SAUNA_DRYING_CFG.vdev_name + "/l2"] = (c.l2 === null ? 0 : sdRound1(c.l2));
  dev[SAUNA_DRYING_CFG.vdev_name + "/l3"] = (c.l3 === null ? 0 : sdRound1(c.l3));
  dev[SAUNA_DRYING_CFG.vdev_name + "/status"] = status;
  dev[SAUNA_DRYING_CFG.vdev_name + "/stop_reason"] = saunaDryingState.stop_reason;
}

function sdEvaluate() {
  var now = sdNow();
  var c = sdGetCurrents();
  var saunaOn = sdIsSaunaOn(c);
  var dryingCond = false;

  if (saunaOn) {
    saunaDryingState.sauna_was_on = true;
  }

  dryingCond = saunaDryingState.sauna_was_on && sdIsDryingCondition(c);

  if (!saunaDryingState.drying_active) {
    if (dryingCond) {
      if (!saunaDryingState.condition_since_ms) {
        saunaDryingState.condition_since_ms = now;
      }

      if ((now - saunaDryingState.condition_since_ms) >= SAUNA_DRYING_CFG.thresholds.confirm_ms) {
        sdStartDrying();
      }
    } else {
      saunaDryingState.condition_since_ms = 0;
    }
  } else {
    if (!dryingCond) {
      sdStopDrying("условие осушения исчезло");
    } else if (now >= saunaDryingState.drying_until_ms) {
      sdStopDrying("таймер завершён");
    }
  }

  sdUpdateVdev(c, dryingCond);
}

defineRule("sauna_drying_on_currents_change", {
  whenChanged: [
    SAUNA_DRYING_CFG.currents.l1,
    SAUNA_DRYING_CFG.currents.l2,
    SAUNA_DRYING_CFG.currents.l3
  ],
  then: function () {
    sdEvaluate();
  }
});

defineRule("sauna_drying_periodic_tick", {
  when: cron("*/" + SAUNA_DRYING_CFG.tick_sec + " * * * * *"),
  then: function () {
    sdEvaluate();
  }
});

sdEvaluate();