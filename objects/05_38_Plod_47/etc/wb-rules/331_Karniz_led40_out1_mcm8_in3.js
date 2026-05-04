// Управление светом карниза от правой клавиши выключателя у дивана.
//
// Короткое нажатие:
// wb-mcm8_103/Input 3 Single Press Counter -> вкл/выкл wb-led_40/CCT1
//
// Длительное нажатие:
// wb-mcm8_103/Input 3 Long Press Counter -> диммирование wb-led_40/CCT1 Brightness
//
// Направление диммирования меняется после каждого длинного нажатия.
// При достижении 0% или 100% направление также меняется.

var wbLed40Cct1Button = "wb-mcm8_103/Input 3";
var wbLed40Cct1SinglePress = "wb-mcm8_103/Input 3 Single Press Counter";
var wbLed40Cct1LongPress = "wb-mcm8_103/Input 3 Long Press Counter";

var wbLed40Cct1Switch = "wb-led_40/CCT1";
var wbLed40Cct1Brightness = "wb-led_40/CCT1 Brightness";

var wbLed40Cct1TimerName = "wb_led_40_cct1_brightness_from_input_3";

var wbLed40Cct1DimDirection = 1; // 1 = увеличить, -1 = уменьшить
var wbLed40Cct1DimActive = false;
var wbLed40Cct1DirectionChangedByLimit = false;

var wbLed40Cct1Step = 1;
var wbLed40Cct1IntervalMs = 75;

function wbLed40Cct1Clamp(value, min, max) {
    if (value < min) {
        return min;
    }

    if (value > max) {
        return max;
    }

    return value;
}

function wbLed40Cct1GetBrightness() {
    var value = Number(dev[wbLed40Cct1Brightness]);

    if (isNaN(value)) {
        value = 50;
    }

    return wbLed40Cct1Clamp(value, 0, 100);
}

function wbLed40Cct1SetBrightness(value) {
    dev[wbLed40Cct1Brightness] = wbLed40Cct1Clamp(value, 0, 100);
}

function wbLed40Cct1StopDimming(changeDirection) {
    if (timers[wbLed40Cct1TimerName]) {
        timers[wbLed40Cct1TimerName].stop();
    }

    if (wbLed40Cct1DimActive && changeDirection && !wbLed40Cct1DirectionChangedByLimit) {
        wbLed40Cct1DimDirection = wbLed40Cct1DimDirection * -1;
    }

    wbLed40Cct1DimActive = false;
    wbLed40Cct1DirectionChangedByLimit = false;
}

function wbLed40Cct1StartDimming() {
    dev[wbLed40Cct1Switch] = true; // Свет карнизы

    wbLed40Cct1DimActive = true;
    wbLed40Cct1DirectionChangedByLimit = false;

    startTicker(wbLed40Cct1TimerName, wbLed40Cct1IntervalMs);
}

// Правая клавиша, одинарное нажатие
defineRule({
    whenChanged: wbLed40Cct1SinglePress,
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev[wbLed40Cct1Switch] = !dev[wbLed40Cct1Switch]; // Свет карнизы
        }
    }
});

// Правая клавиша, длительное нажатие
defineRule({
    whenChanged: wbLed40Cct1LongPress,
    then: function (newValue, devName, cellName) {
        if (newValue) {
            wbLed40Cct1StopDimming(false);
            wbLed40Cct1StartDimming();
        }
    }
});

// Правая клавиша, отпускание после длительного нажатия
defineRule({
    whenChanged: wbLed40Cct1Button,
    then: function (newValue, devName, cellName) {
        if (!newValue) {
            wbLed40Cct1StopDimming(true);
        }
    }
});

// Изменение яркости пока клавиша удерживается
defineRule({
    when: function () {
        return timers[wbLed40Cct1TimerName] && timers[wbLed40Cct1TimerName].firing;
    },
    then: function () {
        var currentBrightness;
        var nextBrightness;

        if (!dev[wbLed40Cct1Button]) {
            wbLed40Cct1StopDimming(true);
            return;
        }

        currentBrightness = wbLed40Cct1GetBrightness();
        nextBrightness = currentBrightness + wbLed40Cct1DimDirection * wbLed40Cct1Step;

        if (nextBrightness >= 100) {
            nextBrightness = 100;
            wbLed40Cct1DimDirection = -1;
            wbLed40Cct1DirectionChangedByLimit = true;
        }

        if (nextBrightness <= 0) {
            nextBrightness = 0;
            wbLed40Cct1DimDirection = 1;
            wbLed40Cct1DirectionChangedByLimit = true;
        }

        wbLed40Cct1SetBrightness(nextBrightness);
    }
});