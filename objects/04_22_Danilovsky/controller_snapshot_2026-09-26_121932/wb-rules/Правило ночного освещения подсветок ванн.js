// При включении света в ванной или душевой устанавливает яркость:
// с 00:00 до 07:00 — 10%, с 07:00 до 00:00 — 50%.
// При выключении ничего не меняет.
// Уже включённый свет в 00:00 и 07:00 яркость не меняет.
// Ручная регулировка сохраняется до следующего включения.
// При загрузке правил начальное true также может задать яркость.

// НАСТРОЙКИ
var SCENARIO_NAME = "light_brightness_by_time";
var NIGHT_START_HOUR = 0;
var NIGHT_END_HOUR = 7;
var NIGHT_BRIGHTNESS_PCT = 10;
var DAY_BRIGHTNESS_PCT = 50;

// ГРУППЫ СВЕТА
var LIGHTS = [
  // ВАННАЯ — ГР.327
  {
    key: "bathroom",
    switchTopic: "wb-led_11/CCT2",
    brightnessTopic: "wb-led_11/CCT2 Brightness"
  },
  // ДУШЕВАЯ — ГР.330
  {
    key: "shower",
    switchTopic: "wb-led_42/Channels 3_4",
    brightnessTopic: "wb-led_42/Channels 3_4 Brightness"
  }
];

// ПРАВИЛА
LIGHTS.forEach(function (light) {
  defineRule(SCENARIO_NAME + "_" + light.key, {
    whenChanged: light.switchTopic,
    then: function (newValue) {
      if (newValue !== true) return;

      var hour = new Date().getHours();
      var night = hour >= NIGHT_START_HOUR && hour < NIGHT_END_HOUR;
      var brightness = night ? NIGHT_BRIGHTNESS_PCT : DAY_BRIGHTNESS_PCT;
      var current = dev[light.brightnessTopic];

      if (typeof current !== "number" || !isFinite(current)) return;

      if (current !== brightness) {
        dev[light.brightnessTopic] = brightness;
      }
    }
  });
});