// Подсветка лестницы для Wiren Board (wb-rules, ES5)
// Объект: 05_38_Plod_47

var STAIR_LIGHT_CHANNEL = "L04/K1";
var LOWER_SENSOR_CHANNEL = "wb-gpio/A1_IN";
var UPPER_SENSOR_CHANNEL = "wb-gpio/A2_IN";
var MOTION_LEVEL_CHANNEL = "wb-msw-v4_32/Current Motion";

var VDEV_NAME = "stair_light_control";
var VDEV_TITLE = "Подсветка лестницы";

var syncGuard = false;

var state = {
  sessionActive: false,
  entrySensor: "",
  exitSensor: "",
  exitSawFalse: false,
  offTimerId: null,
  countdownIntervalId: null,
  offDeadlineTs: 0,
  prevLower: null,
  prevUpper: null
};

function toBool(value) {
  return value === true || value === 1 || value === "1";
}

function toNumber(value, fallback) {
  var n = Number(value);
  return isNaN(n) ? fallback : n;
}

function isMotionPresent(level) {
  var threshold = toNumber(dev[VDEV_NAME + "/motion_threshold"], 1);
  var current = toNumber(level, 0);
  return current >= threshold;
}

function updateCountdown(seconds) {
  var sec = seconds;
  if (sec < 0) {
    sec = 0;
  }
  syncGuard = true;
  dev[VDEV_NAME + "/countdown_sec"] = sec;
  syncGuard = false;
}

function clearOffTimer() {
  if (state.offTimerId !== null) {
    clearTimeout(state.offTimerId);
    state.offTimerId = null;
  }
  if (state.countdownIntervalId !== null) {
    clearInterval(state.countdownIntervalId);
    state.countdownIntervalId = null;
  }
  state.offDeadlineTs = 0;
  updateCountdown(0);
}

function setLight(value) {
  var current = toBool(dev[STAIR_LIGHT_CHANNEL]);
  var target = toBool(value);

  if (current === target) {
    syncGuard = true;
    dev[VDEV_NAME + "/stair_light"] = target;
    syncGuard = false;
    return;
  }

  syncGuard = true;
  dev[STAIR_LIGHT_CHANNEL] = target;
  dev[VDEV_NAME + "/stair_light"] = target;
  syncGuard = false;
}

function resetSession() {
  state.sessionActive = false;
  state.entrySensor = "";
  state.exitSensor = "";
  state.exitSawFalse = false;
  clearOffTimer();
}

function finishSessionAndTurnOff() {
  setLight(false);
  resetSession();
}

function startOffTimer() {
  var timeoutSec = Math.max(0, toNumber(dev[VDEV_NAME + "/off_timeout_sec"], 20));

  clearOffTimer();

  if (timeoutSec === 0) {
    finishSessionAndTurnOff();
    return;
  }

  state.offDeadlineTs = Date.now() + timeoutSec * 1000;
  updateCountdown(timeoutSec);

  state.countdownIntervalId = setInterval(function () {
    var left = Math.ceil((state.offDeadlineTs - Date.now()) / 1000);
    updateCountdown(left);
  }, 1000);

  state.offTimerId = setTimeout(function () {
    finishSessionAndTurnOff();
  }, timeoutSec * 1000);
}

function ensureOffTimerRunning() {
  if (state.offTimerId !== null) {
    return;
  }
  startOffTimer();
}

function onMotionUpdate(level) {
  syncGuard = true;
  dev[VDEV_NAME + "/motion_level"] = toNumber(level, 0);
  syncGuard = false;

  if (!state.sessionActive) {
    clearOffTimer();
    return;
  }

  if (isMotionPresent(level)) {
    clearOffTimer();
  } else {
    ensureOffTimerRunning();
  }
}

function startSession(triggerSensor) {
  state.sessionActive = true;
  state.entrySensor = triggerSensor;
  state.exitSensor = triggerSensor === "lower" ? "upper" : "lower";
  state.exitSawFalse = false;

  setLight(true);

  if (isMotionPresent(dev[MOTION_LEVEL_CHANNEL])) {
    clearOffTimer();
  } else {
    startOffTimer();
  }
}

function processSensorEdge(sensorName, prev, curr) {
  var falling = prev === true && curr === false;
  var rising = prev === false && curr === true;

  if (falling && !state.sessionActive) {
    startSession(sensorName);
    return;
  }

  if (!state.sessionActive) {
    return;
  }

  if (sensorName !== state.exitSensor) {
    return;
  }

  if (falling) {
    state.exitSawFalse = true;
    clearOffTimer();
    return;
  }

  if (rising && state.exitSawFalse) {
    finishSessionAndTurnOff();
  }
}

function updateSensorStates() {
  syncGuard = true;
  dev[VDEV_NAME + "/lower_sensor"] = toBool(dev[LOWER_SENSOR_CHANNEL]);
  dev[VDEV_NAME + "/upper_sensor"] = toBool(dev[UPPER_SENSOR_CHANNEL]);
  syncGuard = false;
}

defineVirtualDevice(VDEV_NAME, {
  title: VDEV_TITLE,
  cells: {
    stair_light: {
      title: "Переключатель подсветки",
      type: "switch",
      value: toBool(dev[STAIR_LIGHT_CHANNEL]),
      order: 1
    },
    lower_sensor: {
      title: "Нижний датчик",
      type: "switch",
      readonly: true,
      value: toBool(dev[LOWER_SENSOR_CHANNEL]),
      order: 2
    },
    motion_level: {
      title: "Движение на лестнице",
      type: "value",
      readonly: true,
      value: toNumber(dev[MOTION_LEVEL_CHANNEL], 0),
      order: 3
    },
    upper_sensor: {
      title: "Верхний датчик",
      type: "switch",
      readonly: true,
      value: toBool(dev[UPPER_SENSOR_CHANNEL]),
      order: 4
    },
    motion_threshold: {
      title: "Уровень \"есть движение\"",
      type: "range",
      min: 0,
      max: 5000,
      value: 300,
      order: 5
    },
    off_timeout_sec: {
      title: "Таймаут выключения, сек",
      type: "range",
      min: 0,
      max: 600,
      value: 30,
      order: 6
    },
    countdown_sec: {
      title: "Таймер обратного отсчета",
      type: "value",
      readonly: true,
      value: 0,
      order: 7
    }
  }
});

state.prevLower = toBool(dev[LOWER_SENSOR_CHANNEL]);
state.prevUpper = toBool(dev[UPPER_SENSOR_CHANNEL]);

updateSensorStates();
onMotionUpdate(dev[MOTION_LEVEL_CHANNEL]);

defineRule("stair_light_virtual_switch", {
  whenChanged: VDEV_NAME + "/stair_light",
  then: function (newValue) {
    if (syncGuard) {
      return;
    }

    var target = toBool(newValue);
    setLight(target);

    if (!target) {
      resetSession();
    }
  }
});

defineRule("stair_light_real_switch_sync", {
  whenChanged: STAIR_LIGHT_CHANNEL,
  then: function (newValue) {
    if (syncGuard) {
      return;
    }

    var realState = toBool(newValue);
    syncGuard = true;
    dev[VDEV_NAME + "/stair_light"] = realState;
    syncGuard = false;

    if (!realState) {
      resetSession();
    }
  }
});

defineRule("stair_light_lower_sensor", {
  whenChanged: LOWER_SENSOR_CHANNEL,
  then: function (newValue) {
    var curr = toBool(newValue);
    var prev = state.prevLower;
    state.prevLower = curr;

    syncGuard = true;
    dev[VDEV_NAME + "/lower_sensor"] = curr;
    syncGuard = false;

    processSensorEdge("lower", prev, curr);
  }
});

defineRule("stair_light_upper_sensor", {
  whenChanged: UPPER_SENSOR_CHANNEL,
  then: function (newValue) {
    var curr = toBool(newValue);
    var prev = state.prevUpper;
    state.prevUpper = curr;

    syncGuard = true;
    dev[VDEV_NAME + "/upper_sensor"] = curr;
    syncGuard = false;

    processSensorEdge("upper", prev, curr);
  }
});

defineRule("stair_light_motion_monitor", {
  whenChanged: MOTION_LEVEL_CHANNEL,
  then: function (newValue) {
    onMotionUpdate(newValue);
  }
});

defineRule("stair_light_timeout_changed", {
  whenChanged: VDEV_NAME + "/off_timeout_sec",
  then: function () {
    if (state.sessionActive && state.offTimerId !== null) {
      startOffTimer();
    }
  }
});

defineRule("stair_light_threshold_changed", {
  whenChanged: VDEV_NAME + "/motion_threshold",
  then: function () {
    onMotionUpdate(dev[MOTION_LEVEL_CHANNEL]);
  }
});
