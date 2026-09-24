// ============================================================================
// 1. НАЗНАЧЕНИЕ СКРИПТА
//
// Спальня, кнопки 209-212.
//
// Локальные аппаратные функции WB сохраняются:
// - 209 short: WB-LED23 + WB-LED42 локально переключают гр.311.1 + 311;
// - 210 short/long: WB-MR6C156 локально переключает гр.312;
// - 211 short: WB-MR6C156 локально переключает гр.329.2.
//
// Этот скрипт добавляет только то, чего нет в локальной логике:
// - 209 long: переключает режим DAY/NIGHT для гр.311 + 311.1;
// - 210 short: синхронизирует гр.311 + 311.1 с гр.312, задаёт DAY=80%
//              и при включении дополнительно включает гр.338, но не выключает ее при OFF;
// - 211 long: переключает гр.311 + 311.1 по фактическому состоянию;
// - 212 short: выключает гр.311 + 311.1;
// - 212 long: переключает режим DAY/NIGHT для гр.311 + 311.1.
//
// Режимы спальни:
// - DAY = 80%;
// - NIGHT = 10%.
// Режим DAY/NIGHT здесь ручной, по длинным нажатиям 209/212, без расписания.
//
// В WB-MR6C156 включён опрос счётчиков коротких и длинных нажатий.
//
// ВАЖНО ПЕРЕД УСТАНОВКОЙ:
// В старом "Правило света с различных кнопок.js" надо отключить спальню:
//    switch_control_lamps1 (212 short) и switch_control_lamps2 (211 long),
//    иначе два скрипта будут одновременно писать в гр.311/311.1.
// ============================================================================


// ============================================================================
// 2. ФИЗИЧЕСКИЕ КАНАЛЫ
// ============================================================================

var BUTTON_209_RAW = "wb-led_42/Input 1";                           // Кнопка 209, физический вход; используем для определения long
var BUTTON_210_SHORT = "wb-mr6c_156/Input 1 Single Press Counter";  // Кнопка 210, короткое нажатие
var BUTTON_211_LONG = "wb-mr6c_156/Input 3 Long Press Counter";     // Кнопка 211, длинное нажатие
var BUTTON_212_SHORT = "wb-mr6c_156/Input 0 Single Press Counter";  // Кнопка 212, короткое нажатие
var BUTTON_212_LONG = "wb-mr6c_156/Input 0 Long Press Counter";     // Кнопка 212, длинное нажатие

var LIGHT_312 = "wb-mr6c_156/K1";              // Основной свет спальни, гр.312
var LIGHT_329_2 = "wb-mr6c_156/K3";            // Подвесной светильник, гр.329.2
var LIGHT_338 = "wb-mr6c_156/K4";              // Настенный светильник, гр.338
var LIGHT_311 = "wb-led_42/CCT1";              // Подсветка потолка и мебели, гр.311
var LIGHT_311_1 = "wb-led_23/CCT2";            // Вертикальная подсветка, гр.311.1
var BRIGHTNESS_311 = "wb-led_42/CCT1 Brightness";     // Яркость гр.311
var BRIGHTNESS_311_1 = "wb-led_23/CCT2 Brightness";   // Яркость гр.311.1


// ============================================================================
// 3. НАСТРОЙКИ
// ============================================================================

// После короткого нажатия 210 даем локальной mapping-матрице MR6C время
// переключить K1, затем читаем уже фактическое состояние гр.312.
var LOCAL_MAPPING_SETTLE_MS = 150;

// Защита от ложных действий на retained MQTT при запуске wb-rules.
var STARTUP_IGNORE_MS = 3000;
var SCRIPT_STARTED_AT_MS = Date.now();

// Ручные режимы освещения спальни.
var DAY_BRIGHTNESS_311 = 80;       // Режим DAY, гр.311, %
var DAY_BRIGHTNESS_311_1 = 80;     // Режим DAY, гр.311.1, %
var NIGHT_BRIGHTNESS_311 = 10;     // Режим NIGHT, гр.311, %
var NIGHT_BRIGHTNESS_311_1 = 10;   // Режим NIGHT, гр.311.1, %

// Для кнопки 209 long используем сырой физический вход WB-LED42.
// Short у 209 остаётся полностью локальным в WB-LED23/WB-LED42.
var BUTTON_209_LONG_PRESS_MS = 1000;

var button209Pressed = false;
var button209PressId = 0;


// ============================================================================
// 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ============================================================================

function isStartupWindow() {
    return (Date.now() - SCRIPT_STARTED_AT_MS) < STARTUP_IGNORE_MS;
}

function setIfDifferent(channel, value) {
    if (dev[channel] !== value) {
        dev[channel] = value;
    }
}

function setDayBrightness() {
    setIfDifferent(BRIGHTNESS_311, DAY_BRIGHTNESS_311);
    setIfDifferent(BRIGHTNESS_311_1, DAY_BRIGHTNESS_311_1);
}

function setNightBrightness() {
    setIfDifferent(BRIGHTNESS_311, NIGHT_BRIGHTNESS_311);
    setIfDifferent(BRIGHTNESS_311_1, NIGHT_BRIGHTNESS_311_1);
}

function isNightBrightnessNow() {
    return dev[BRIGHTNESS_311] === NIGHT_BRIGHTNESS_311 &&
           dev[BRIGHTNESS_311_1] === NIGHT_BRIGHTNESS_311_1;
}

function toggleDayNightMode(source) {
    if (isNightBrightnessNow()) {
        setDayBrightness();
        log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=" + source +
            "; режим=DAY; гр.311=80%; гр.311.1=80%");
    } else {
        setNightBrightness();
        log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=" + source +
            "; режим=NIGHT; гр.311=10%; гр.311.1=10%");
    }
}

function setBedroomLeds(value) {
    setIfDifferent(LIGHT_311, value);
    setIfDifferent(LIGHT_311_1, value);
}

function toggleBedroomLeds() {
    // Если обе группы уже включены — выключаем обе.
    // Во всех остальных состояниях приводим пару к ON.
    var bothOn = dev[LIGHT_311] === true && dev[LIGHT_311_1] === true;
    var target = !bothOn;

    setBedroomLeds(target);

    log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=211 long; гр.311=" +
        (target ? "ON" : "OFF") + "; гр.311.1=" + (target ? "ON" : "OFF"));
}


// ============================================================================
// 5. ПРАВИЛА
// ============================================================================

// --------------------------------------------------------------------------
// Кнопка 209, длинное нажатие.
//
// Short у 209 уже обрабатывается локально двумя WB-LED и переключает
// гр.311 + 311.1, сохраняя последнюю выставленную яркость.
//
// Для long используем сырой вход wb-led_42/Input 1:
// - ON -> запускаем ожидание;
// - если кнопка остаётся нажатой 1 секунду -> переключаем DAY/NIGHT;
// - OFF раньше 1 секунды -> ничего не делаем, short остаётся локальным.
// --------------------------------------------------------------------------

defineRule("bedroom_209_raw_input", {
    whenChanged: BUTTON_209_RAW,
    then: function (newValue) {
        if (isStartupWindow()) {
            return;
        }

        if (newValue === true) {
            button209Pressed = true;
            button209PressId += 1;

            var thisPressId = button209PressId;

            setTimeout(function () {
                if (button209Pressed && button209PressId === thisPressId) {
                    toggleDayNightMode("209 long");
                }
            }, BUTTON_209_LONG_PRESS_MS);
        } else {
            button209Pressed = false;
        }
    }
});


// --------------------------------------------------------------------------
// Кнопка 210, короткое нажатие.
//
// Гр.312 уже переключается локально самим WB-MR6C156.
// JS не пишет повторно в K1.
//
// После короткого нажатия:
// - если гр.312 стала ON:
//      задаём режим DAY = 80%;
//      включаем 311 + 311.1;
//      включаем 338;
// - если гр.312 стала OFF:
//      выключаем 311 + 311.1;
//      338 НЕ выключаем по требованию ТЗ.
// --------------------------------------------------------------------------

defineRule("bedroom_210_short_additional_logic", {
    whenChanged: BUTTON_210_SHORT,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        setTimeout(function () {
            var mainLightOn = dev[LIGHT_312] === true;

            if (mainLightOn) {
                setDayBrightness();
                setBedroomLeds(true);
                setIfDifferent(LIGHT_338, true);

                log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=210 short; " +
                    "гр.312=ON локально; дополнительно гр.311=ON; гр.311.1=ON; гр.338=ON");
            } else {
                setBedroomLeds(false);

                log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=210 short; " +
                    "гр.312=OFF локально; дополнительно гр.311=OFF; гр.311.1=OFF; гр.338 без изменения");
            }
        }, LOCAL_MAPPING_SETTLE_MS);
    }
});


// --------------------------------------------------------------------------
// Кнопка 211, длинное нажатие.
//
// Короткое нажатие 211 локально переключает гр.329.2 и этим скриптом
// не обрабатывается.
//
// Long переключает гр.311 + 311.1 по фактическому состоянию, без pressCount.
// --------------------------------------------------------------------------

defineRule("bedroom_211_long_leds", {
    whenChanged: BUTTON_211_LONG,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        toggleBedroomLeds();
    }
});


// --------------------------------------------------------------------------
// Кнопка 212, короткое нажатие.
//
// Текущая локальная функция Input 0 WB-MR6C156 отдельно требует проверки.
// Этот скрипт не меняет mapping MR6C и только добавляет выключение LED-групп,
// как это делал старый объектовый скрипт.
//
// Гр.312 здесь повторно не пишем: локальная функция кнопки остается владельцем
// релейной части до отдельного решения по Input 0.
// --------------------------------------------------------------------------

defineRule("bedroom_212_short_leds_off", {
    whenChanged: BUTTON_212_SHORT,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        setBedroomLeds(false);

        log.info("[освещение][41_lighting_bedroom][спальня]; КОМАНДА=212 short; " +
            "гр.311=OFF; гр.311.1=OFF; локальная функция MR156/Input0 не изменялась");
    }
});


// --------------------------------------------------------------------------
// Кнопка 212, длинное нажатие.
//
// Счётчик long теперь опрашивается WB-MR6C156.
// Меняем только яркость гр.311 + 311.1:
// DAY 80% <-> NIGHT 10%.
// Состояние ON/OFF групп не меняем.
// --------------------------------------------------------------------------

defineRule("bedroom_212_long_day_night", {
    whenChanged: BUTTON_212_LONG,
    then: function () {
        if (isStartupWindow()) {
            return;
        }

        toggleDayNightMode("212 long");
    }
});


// ============================================================================
// 6. ПРИМЕЧАНИЕ ПО РЕЖИМАМ
//
// DAY/NIGHT в спальне не привязаны ко времени суток.
// Это ручной режим яркости:
// - DAY = 80%;
// - NIGHT = 10%.
//
// 209 long и 212 long переключают эти два режима.
// 210 short при включении основного света всегда задаёт DAY = 80%.
// ============================================================================
