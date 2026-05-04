// Сценарий управления вытяжкой кухни.
// Логика:
// - 4 дискретных входа выбирают режим
// - если все входы выключены, включается общеобменный режим 16%
// - если активны несколько входов одновременно, приоритет у максимальной скорости


var KITCHEN_HOOD_CFG = {
    enabled: true,                  // главный флаг логики
    applyOnStart: true,             // применять состояние после загрузки правил
    startDelayMs: 1000,             // задержка после старта wb-rules
    forceSwitchOn: true,            // всегда держать канал включённым
    enableLog: true,                // логировать действия в журнал

    inputs: {
        speed1: "wb-mcm8_50/Input 1",   // Скорость 1
        speed2: "wb-mcm8_50/Input 2",   // Скорость 2
        speed3: "wb-mcm8_50/Input 3",   // Скорость 3
        speed4: "wb-mcm8_50/Input 4"    // Скорость 4
    },

    output: {
        switchControl: "A16/Channel 1 Switch",
        levelControl: "A16/Channel 1 Dimming Level"
    },

    levels: {
        background: 16, // общеобменная вентиляция
        speed1: 25,
        speed2: 50,
        speed3: 75,
        speed4: 100
    }
};

function kitchenHoodLog(message) {
    if (KITCHEN_HOOD_CFG.enableLog) {
        log("[Kitchen_Hood] " + message);
    }
}

function getBool(cell) {
    return !!dev[cell];
}

function getTargetLevel() {
    var in1 = getBool(KITCHEN_HOOD_CFG.inputs.speed1);
    var in2 = getBool(KITCHEN_HOOD_CFG.inputs.speed2);
    var in3 = getBool(KITCHEN_HOOD_CFG.inputs.speed3);
    var in4 = getBool(KITCHEN_HOOD_CFG.inputs.speed4);

    // Приоритет максимальной скорости
    if (in4) {
        return KITCHEN_HOOD_CFG.levels.speed4;
    }

    if (in3) {
        return KITCHEN_HOOD_CFG.levels.speed3;
    }

    if (in2) {
        return KITCHEN_HOOD_CFG.levels.speed2;
    }

    if (in1) {
        return KITCHEN_HOOD_CFG.levels.speed1;
    }

    return KITCHEN_HOOD_CFG.levels.background;
}

function getActiveInputsText() {
    var active = [];

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed1)) {
        active.push("S1");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed2)) {
        active.push("S2");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed3)) {
        active.push("S3");
    }

    if (getBool(KITCHEN_HOOD_CFG.inputs.speed4)) {
        active.push("S4");
    }

    if (active.length === 0) {
        return "none";
    }

    return active.join(",");
}

function applyKitchenHoodState(reason) {
    var targetLevel;
    var currentSwitch;
    var currentLevel;
    var activeInputsText;

    if (!KITCHEN_HOOD_CFG.enabled) {
        kitchenHoodLog("Сценарий отключён флагом enabled");
        return;
    }

    targetLevel = getTargetLevel();
    currentSwitch = !!dev[KITCHEN_HOOD_CFG.output.switchControl];
    currentLevel = Number(dev[KITCHEN_HOOD_CFG.output.levelControl]);
    activeInputsText = getActiveInputsText();

    if (KITCHEN_HOOD_CFG.forceSwitchOn) {
        if (!currentSwitch) {
            dev[KITCHEN_HOOD_CFG.output.switchControl] = true;
            kitchenHoodLog("Включен канал управления");
        }
    }

    if (currentLevel !== targetLevel) {
        dev[KITCHEN_HOOD_CFG.output.levelControl] = targetLevel;
        kitchenHoodLog(
            "Причина=" + reason +
            "; входы=" + activeInputsText +
            "; установлен уровень=" + targetLevel + "%"
        );
    } else {
        kitchenHoodLog(
            "Причина=" + reason +
            "; входы=" + activeInputsText +
            "; уровень без изменений=" + targetLevel + "%"
        );
    }
}

defineRule("kitchen_hood_apply_on_inputs_change", {
    whenChanged: [
        KITCHEN_HOOD_CFG.inputs.speed1,
        KITCHEN_HOOD_CFG.inputs.speed2,
        KITCHEN_HOOD_CFG.inputs.speed3,
        KITCHEN_HOOD_CFG.inputs.speed4
    ],
    then: function () {
        applyKitchenHoodState("inputs_changed");
    }
});

if (KITCHEN_HOOD_CFG.applyOnStart) {
    setTimeout(function () {
        applyKitchenHoodState("startup");
    }, KITCHEN_HOOD_CFG.startDelayMs);
}