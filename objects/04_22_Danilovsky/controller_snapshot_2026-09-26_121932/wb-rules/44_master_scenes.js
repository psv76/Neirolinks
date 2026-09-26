// 44_master_scenes.js
// ============================================================================
// 1. НАЗНАЧЕНИЕ СКРИПТА
//
// Мастер-сцены квартиры «Я ушёл» и «Я пришёл».
//
// Кнопка 235, длинное нажатие:
// - работает только если квартира находится в состоянии HOME;
// - выключает всё известное освещение;
// - выключает все четыре кондиционера;
// - выключает вытяжные вентиляторы;
// - переводит квартиру в состояние AWAY.
//
// Кнопка 236, длинное нажатие:
// - работает только если квартира находится в состоянии AWAY;
// - по календарю восхода/заката определяет, светло сейчас или темно;
// - включает группы из ТЗ для светлого или тёмного времени;
// - включает все четыре кондиционера;
// - переводит квартиру в состояние HOME.
//
// Состояние HOME/AWAY хранится в постоянной памяти контроллера и не теряется
// после перезапуска wb-rules или контроллера.
//
// Для спальни режим DAY уже принят: 311 и 311.1 = 80%.
// Для кухонных LED-групп точные DAY-яркости и цветовая температура пока
// не согласованы, поэтому «Я пришёл» включает их с последними сохранёнными
// настройками яркости/цветовой температуры.
//
// ВАЖНО:
// - 236 и 221 физически приходят на один wb-mr6c_138/Input 1.
//   Мастер-сцена «Я пришёл» защищена флагом AWAY: когда квартира HOME,
//   этот long-сигнал не запускает «Я пришёл».
// ============================================================================


// ============================================================================
// 2. ФИЗИЧЕСКИЕ КАНАЛЫ
// ============================================================================

var BUTTON_235_LONG = "wb-mr6c_138/Input 3 Long Press Counter"; // Кнопка 235, «Я ушёл»
var BUTTON_236_LONG = "wb-mr6c_138/Input 1 Long Press Counter"; // Кнопка 236, «Я пришёл»


// --- Прихожая ---
var LIGHT_301 = "wb-mr6c_138/K1";       // Гр.301
var LIGHT_301_1 = "wb-mr6c_138/K2";     // Гр.301.1
var LIGHT_302 = "wb-mr6c_138/K3";       // Гр.302
var LIGHT_301_2 = "wb-led_11/CCT1";     // Гр.301.2

// --- Кухня-гостиная ---
var LIGHT_333_4 = "wb-mr6c_206/K1";         // Гр.333.4, бра
var LIGHT_305 = "wb-mr6c_206/K2";           // Гр.305
var LIGHT_308 = "wb-mr6c_206/K3";           // Гр.308
var LIGHT_307 = "wb-mr6c_206/K4";           // Гр.307
var FAN_304 = "wb-mr6c_206/K5";             // Вытяжной вентилятор гр.304
var LIGHT_333 = "wb-led_239/CCT2";          // Гр.333
var LIGHT_333_1 = "wb-led_40/CCT2";          // Гр.333.1
var LIGHT_333_2 = "wb-led_37/CCT2";          // Гр.333.2
var LIGHT_333_3 = "wb-led_52/Channels 1_2";  // Гр.333.3
var LIGHT_3333 = "wb-led_52/CCT2";           // Гр.3333

// --- Холл ---
var LIGHT_309 = "wb-mr6c_156/K5"; // Гр.309

// --- Душевая ---
var LIGHT_310 = "wb-mr6c_156/K6";            // Гр.310
var LIGHT_310_1 = "wb-mr6c_117/K1";          // Гр.310.1
var LIGHT_330 = "wb-led_42/Channels 3_4";     // Гр.330
var FAN_331 = "wb-mr6c_117/K2";               // Вентилятор гр.331

// --- Спальня ---
var LIGHT_312 = "wb-mr6c_156/K1";             // Гр.312
var LIGHT_329_1 = "wb-mr6c_156/K2";           // Гр.329.1
var LIGHT_329_2 = "wb-mr6c_156/K3";           // Гр.329.2
var LIGHT_338 = "wb-mr6c_156/K4";             // Гр.338
var LIGHT_311 = "wb-led_42/CCT1";             // Гр.311
var LIGHT_311_1 = "wb-led_23/CCT2";           // Гр.311.1
var BRIGHTNESS_311 = "wb-led_42/CCT1 Brightness";   // Яркость гр.311
var BRIGHTNESS_311_1 = "wb-led_23/CCT2 Brightness"; // Яркость гр.311.1

// --- Кладовая ---
var LIGHT_315 = "wb-mr6c_138/K6";         // Гр.315
var LIGHT_315_1 = "wb-led_26/CCT2";       // Гр.315.1
var FAN_328 = "wb-mr6c_218/K1";           // Вентилятор гр.328

// --- Ванная ---
var LIGHT_316 = "wb-mr6c_218/K2";         // Гр.316
var LIGHT_336 = "wb-mr6c_218/K3";         // Гр.336
var LIGHT_327 = "wb-led_11/CCT2";         // Гр.327
var FAN_326 = "wb-mr6c_218/K4";           // Вентилятор гр.326

// --- Детская девочки ---
var LIGHT_317 = "wb-mr6c_203/K1";         // Гр.317
var LIGHT_320 = "wb-mr6c_203/K2";         // Гр.320
var LIGHT_319 = "wb-led_58/RGB Strip";     // Гр.319
var LIGHT_319_WHITE = "wb-led_58/Channel 4"; // Белый канал гр.319
var LIGHT_320_1 = "wb-led_13/RGB Strip";   // Гр.320.1
var LIGHT_320_1_WHITE = "wb-led_13/Channel 4"; // Белый канал гр.320.1
var LIGHT_104_2 = "wb-mr6c_203/K3"; //Гр.104.2

// --- Детская мальчика ---
var LIGHT_321 = "wb-mr6c_203/K4";         // Гр.321
var LIGHT_337 = "wb-mr6c_203/K5";         // Гр.337
var LIGHT_325_1 = "wb-led_245/RGB Strip"; // Гр.325.1
var LIGHT_325_2 = "wb-led_51/RGB Strip";  // Гр.325.2
var LIGHT_324 = "wb-led_224/RGB Strip";   // Гр.324
var LIGHT_122_2 = "wb-mr6c_203/K6";   // Гр.122.2

// --- Гардероб ---
var LIGHT_314 = "wb-mr6c_138/K4";         // Гр.314
var LIGHT_334 = "wb-led_26/CCT1";         // Гр.334
var FAN_335 = "wb-mr6c_138/K5";           // Вентилятор гр.335

// --- Кондиционеры ---
var AC_GIRLS = "ONOKOM-AIR-GR-1-MB-B_2/Active";   // Детская девочки
var AC_KITCHEN = "ONOKOM-AIR-GR-1-MB-B_3/Active"; // Кухня-гостиная
var AC_BEDROOM = "ONOKOM-AIR-GR-1-MB-B_4/Active"; // Спальня
var AC_BOYS = "ONOKOM-AIR-GR-1-MB-B_5/Active";    // Детская мальчика


// ============================================================================
// 3. НАСТРОЙКИ
// ============================================================================

// Координаты ЖК «Даниловский», Екатеринбург.
// Используются только для расчёта восхода и заката.
var LATITUDE = 56.8633;
var LONGITUDE = 60.6526;

// Режим DAY спальни уже согласован.
var BEDROOM_DAY_BRIGHTNESS = 80;

// Защита от retained MQTT при запуске правил.
var STARTUP_IGNORE_MS = 3000;
var SCRIPT_STARTED_AT_MS = Date.now();

// Постоянный флаг HOME/AWAY.
var storage = new PersistentStorage("danilovsky_master_scenes", {global: true});

if (storage["home_state"] !== "HOME" && storage["home_state"] !== "AWAY") {
    storage["home_state"] = "HOME";
}


// ============================================================================
// 4. СПИСКИ УСТРОЙСТВ
// ============================================================================

// Всё известное освещение квартиры.
// Управляемые розетки 104.2 и 122.2 сюда намеренно НЕ входят.
var ALL_LIGHTS = [
    LIGHT_301,
    LIGHT_301_1,
    LIGHT_302,
    LIGHT_301_2,
    LIGHT_104_2,
    LIGHT_122_2,

    LIGHT_333_4,
    LIGHT_305,
    LIGHT_308,
    LIGHT_307,
    LIGHT_333,
    LIGHT_333_1,
    LIGHT_333_2,
    LIGHT_333_3,
    LIGHT_3333,

    LIGHT_309,

    LIGHT_310,
    LIGHT_310_1,
    LIGHT_330,

    LIGHT_312,
    LIGHT_329_1,
    LIGHT_329_2,
    LIGHT_338,
    LIGHT_311,
    LIGHT_311_1,

    LIGHT_315,
    LIGHT_315_1,

    LIGHT_316,
    LIGHT_336,
    LIGHT_327,

    LIGHT_317,
    LIGHT_320,
    LIGHT_319,
    LIGHT_319_WHITE,
    LIGHT_320_1,
    LIGHT_320_1_WHITE,

    LIGHT_321,
    LIGHT_337,
    LIGHT_325_1,
    LIGHT_325_2,
    LIGHT_324,

    LIGHT_314,
    LIGHT_334
];

var ALL_FANS = [
    FAN_304,
    FAN_326,
    FAN_328,
    FAN_331,
    FAN_335
];

var ALL_AC = [
    AC_GIRLS,
    AC_KITCHEN,
    AC_BEDROOM,
    AC_BOYS
];

// Светлое время: группы строго по ТЗ.
var ARRIVE_LIGHTS_DAY = [
    LIGHT_333_4,
    LIGHT_301_2,
    LIGHT_333,
    LIGHT_333_2,
    LIGHT_3333,
    LIGHT_311,
    LIGHT_311_1
];

// Тёмное время: группы строго по ТЗ.
var ARRIVE_LIGHTS_NIGHT = [
    LIGHT_301,
    LIGHT_302,
    LIGHT_308,
    LIGHT_333_1,
    LIGHT_333_2,
    LIGHT_333_4,
    LIGHT_301_2,
    LIGHT_333,
    LIGHT_3333,
    LIGHT_311,
    LIGHT_311_1
];


// ============================================================================
// 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================================

function isStartupWindow() {
    return (Date.now() - SCRIPT_STARTED_AT_MS) < STARTUP_IGNORE_MS;
}

function setIfDifferent(channel, value) {
    if (dev[channel] !== value) {
        dev[channel] = value;
    }
}

function setMany(channels, value) {
    var i;

    for (i = 0; i < channels.length; i += 1) {
        setIfDifferent(channels[i], value);
    }
}

function pad2(value) {
    return value < 10 ? "0" + value : "" + value;
}

function formatTime(date) {
    return pad2(date.getHours()) + ":" + pad2(date.getMinutes());
}


// ============================================================================
// 6. РАСЧЁТ ВОСХОДА И ЗАКАТА
//
// Расчёт выполняется локально на контроллере по дате и координатам.
// Интернет для работы мастер-сцены не нужен.
// ============================================================================

var RAD = Math.PI / 180;
var DAY_MS = 86400000;
var J1970 = 2440588;
var J2000 = 2451545;
var J0 = 0.0009;

function toJulian(date) {
    return date.valueOf() / DAY_MS - 0.5 + J1970;
}

function fromJulian(j) {
    return new Date((j + 0.5 - J1970) * DAY_MS);
}

function toDays(date) {
    return toJulian(date) - J2000;
}

function solarMeanAnomaly(d) {
    return RAD * (357.5291 + 0.98560028 * d);
}

function eclipticLongitude(m) {
    var c = RAD * (
        1.9148 * Math.sin(m) +
        0.0200 * Math.sin(2 * m) +
        0.0003 * Math.sin(3 * m)
    );

    var p = RAD * 102.9372;

    return m + c + p + Math.PI;
}

function declination(l) {
    var e = RAD * 23.4397;

    return Math.asin(Math.sin(l) * Math.sin(e));
}

function julianCycle(d, lw) {
    return Math.round(d - J0 - lw / (2 * Math.PI));
}

function approxTransit(ht, lw, n) {
    return J0 + (ht + lw) / (2 * Math.PI) + n;
}

function solarTransitJ(ds, m, l) {
    return J2000 + ds + 0.0053 * Math.sin(m) - 0.0069 * Math.sin(2 * l);
}

function hourAngle(h, phi, dec) {
    return Math.acos(
        (Math.sin(h) - Math.sin(phi) * Math.sin(dec)) /
        (Math.cos(phi) * Math.cos(dec))
    );
}

function getSetJ(h, lw, phi, dec, n, m, l) {
    var w = hourAngle(h, phi, dec);
    var a = approxTransit(w, lw, n);

    return solarTransitJ(a, m, l);
}

function getSunTimes(now) {
    // Берём полдень текущей локальной даты, чтобы около полуночи
    // не перескочить на соседний календарный день.
    var date = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate(),
        12, 0, 0, 0
    );

    var lw = RAD * -LONGITUDE;
    var phi = RAD * LATITUDE;
    var d = toDays(date);
    var n = julianCycle(d, lw);
    var ds = approxTransit(0, lw, n);
    var m = solarMeanAnomaly(ds);
    var l = eclipticLongitude(m);
    var dec = declination(l);
    var jNoon = solarTransitJ(ds, m, l);

    // -0.833° — стандартная высота центра Солнца для восхода/заката.
    var jSet = getSetJ(RAD * -0.833, lw, phi, dec, n, m, l);
    var jRise = jNoon - (jSet - jNoon);

    return {
        sunrise: fromJulian(jRise),
        sunset: fromJulian(jSet)
    };
}

function isDaylight(now) {
    var sun = getSunTimes(now);

    return {
        daylight: now >= sun.sunrise && now < sun.sunset,
        sunrise: sun.sunrise,
        sunset: sun.sunset
    };
}


// ============================================================================
// 7. МАСТЕР-СЦЕНЫ
// ============================================================================

function leaveHome() {
    if (storage["home_state"] !== "HOME") {
        log.info("[освещение][44_master_scenes][квартира]; СОСТОЯНИЕ=Я ушёл не выполнено; причина=квартира уже AWAY");
        return;
    }

    setMany(ALL_LIGHTS, false);
    setMany(ALL_AC, false);
    setMany(ALL_FANS, false);

    storage["home_state"] = "AWAY";

    log.info("[освещение][44_master_scenes][квартира]; КОМАНДА=Я ушёл; " +
        "освещение=OFF; кондиционеры=OFF; вентиляторы=OFF; home_state=AWAY");
}

function arriveHome() {
    if (storage["home_state"] !== "AWAY") {
        log.info("[освещение][44_master_scenes][квартира]; СОСТОЯНИЕ=Я пришёл не выполнено; причина=квартира уже HOME");
        return;
    }

    var now = new Date();
    var sun = isDaylight(now);

    // Для спальни режим DAY уже определён — 80%.
    setIfDifferent(BRIGHTNESS_311, BEDROOM_DAY_BRIGHTNESS);
    setIfDifferent(BRIGHTNESS_311_1, BEDROOM_DAY_BRIGHTNESS);

    if (sun.daylight) {
        setMany(ARRIVE_LIGHTS_DAY, true);
    } else {
        setMany(ARRIVE_LIGHTS_NIGHT, true);
    }

    // Уставки кондиционеров не меняем — просто включаем их обратно.
    setMany(ALL_AC, true);

    storage["home_state"] = "HOME";

    log.info("[освещение][44_master_scenes][квартира]; КОМАНДА=Я пришёл; " +
        "режим=" + (sun.daylight ? "СВЕТЛО" : "ТЕМНО") +
        "; восход=" + formatTime(sun.sunrise) +
        "; закат=" + formatTime(sun.sunset) +
        "; кондиционеры=ON; home_state=HOME");

    log.info("[освещение][44_master_scenes][квартира]; НАСТРОЙКА=кухонные LED включены " +
        "с последними яркостью и цветовой температурой; точные значения режима DAY пока не согласованы");
}


// ============================================================================
// 8. ПРАВИЛА КНОПОК
// ============================================================================

// Кнопка 235, длинное нажатие — «Я ушёл».
defineRule("master_235_long_leave_home", {
    whenChanged: BUTTON_235_LONG,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        leaveHome();
    }
});


// Кнопка 236, длинное нажатие — «Я пришёл».
//
// Физически этот же Input 1 используется кнопкой 221.
// Защита от случайного запуска мастер-сцены — обязательный флаг AWAY:
// пока квартира HOME, событие ничего не включает.
defineRule("master_236_long_arrive_home", {
    whenChanged: BUTTON_236_LONG,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        arriveHome();
    }
});