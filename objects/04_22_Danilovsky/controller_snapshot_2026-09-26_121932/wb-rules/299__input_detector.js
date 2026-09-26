// 299__input_detector.js
// Универсальный определитель входов для ПНР Wiren Board.
//
// Что делает:
// - ловит физические входы и счётчики нажатий;
// - после первого события в течение заданного времени собирает ВСЕ входы,
//   относящиеся к одному нажатию;
// - объединяет raw-вход и его Single/Long/Double Press Counter
//   в один физический вход;
// - показывает отдельно:
//      1. физические входы;
//      2. сырые MQTT-события.
//
// Пример:
// одна клавиша физически подключена одновременно к:
//   wb-led_58/Input 1
//   wb-led_13/Input 1
//
// В поле "Входы за нажатие" будут показаны ОБА входа.

var SYSTEM_NAME = "диагностика";
var SCRIPT_NAME = "299__input_detector";
var CONTEXT_NAME = "поиск входа";

var DEVICE_ID = "input_detector";

// Первые сообщения после подписки могут быть retained MQTT.
// После запуска некоторое время ничего не анализируем.
var IGNORE_STARTUP_MS = 3000;

// Сколько времени после первого события собирать входы одного нажатия.
// Для ПНР специально сделано с запасом, чтобы успели ответить разные
// устройства на разных RS-485.
var CAPTURE_WINDOW_MS = 1200;

// Сырые изменения пишем в системный журнал.
var LOG_INPUT_CHANGES = true;

// Результат одного законченного захвата тоже пишем в журнал.
var LOG_CAPTURE_RESULT = true;

// Свои и служебные устройства исключаем.
var EXCLUDED_DEVICES = [
    DEVICE_ID,
    "wbrules"
];

// Контролы, похожие на физические входы и счётчики нажатий.
var INCLUDE_CONTROL_PATTERNS = [
    "^Input [0-9]+$",
    "^Input [0-9]+ counter$",
    "^Input [0-9]+ .+Counter$",
    "^IN[0-9]+$",
    "^.*_IN[0-9]+$",
    "^.*\\.in[0-9]+$",
    "^in[0-9]+$",
    "^S[0-9]+$",
    "^F[0-9]+$"
];

// Исключаем типовые выходы и датчики.
var EXCLUDE_CONTROL_PATTERNS = [
    "^K[0-9]+$",
    "^Relay [0-9]+$",
    "^Channel [0-9]+ Switch$",
    "^Channel [0-9]+ Dimming Level$",
    "^Voltage$",
    "^Current$",
    "^Temperature$",
    "^Humidity$",
    "^Motion$",
    "^Illuminance$",
    "^Sound Level$",
    "^CO2$",
    "^VOC$",
    "^PM[0-9.]+$"
];

// ============================================================================
// ВИРТУАЛЬНОЕ УСТРОЙСТВО
// ============================================================================

defineVirtualDevice(DEVICE_ID, {
    title: "Определитель входов",
    cells: {
        enabled: {
            title: "Определитель включен",
            type: "switch",
            value: true,
            readonly: false,
            order: 10
        },

        capture_inputs: {
            title: "Входы за нажатие",
            type: "text",
            value: "нет данных",
            readonly: true,
            order: 20
        },

        capture_count: {
            title: "Количество физических входов",
            type: "value",
            value: 0,
            readonly: true,
            order: 30
        },

        raw_events: {
            title: "Сырые события",
            type: "text",
            value: "",
            readonly: true,
            order: 40
        },

        last_input: {
            title: "Последний физический вход",
            type: "text",
            value: "нет данных",
            readonly: true,
            order: 50
        },

        last_device: {
            title: "Последнее устройство",
            type: "text",
            value: "",
            readonly: true,
            order: 60
        },

        last_control: {
            title: "Последний контрол",
            type: "text",
            value: "",
            readonly: true,
            order: 70
        },

        last_value: {
            title: "Последнее значение",
            type: "text",
            value: "",
            readonly: true,
            order: 80
        },

        last_time: {
            title: "Время результата",
            type: "text",
            value: "",
            readonly: true,
            order: 90
        },

        capture_counter: {
            title: "Счётчик нажатий",
            type: "value",
            value: 0,
            readonly: true,
            order: 100
        },

        event_counter: {
            title: "Счётчик сырых событий",
            type: "value",
            value: 0,
            readonly: true,
            order: 110
        },

        status: {
            title: "Статус",
            type: "text",
            value: "Ожидание",
            readonly: true,
            order: 120
        }
    }
});

// ============================================================================
// СОСТОЯНИЕ
// ============================================================================

var STATE = {
    startedAtMs: nowMs(),

    eventCounter: 0,
    captureCounter: 0,

    captureActive: false,
    captureTimer: null,

    // Физические входы за текущее нажатие.
    // Ключ: wb-mr6c_138/Input 1
    physicalInputs: {},

    // Полный список сырых событий.
    rawEvents: []
};

// ============================================================================
// ОБЩИЕ ФУНКЦИИ
// ============================================================================

function nowMs() {
    return new Date().getTime();
}

function pad2(value) {
    value = Number(value);
    return value < 10 ? "0" + value : "" + value;
}

function formatDateTime(date) {
    return pad2(date.getDate()) + "." +
        pad2(date.getMonth() + 1) + "." +
        date.getFullYear() + " " +
        pad2(date.getHours()) + ":" +
        pad2(date.getMinutes()) + ":" +
        pad2(date.getSeconds());
}

function setControl(controlName, value) {
    var topic = DEVICE_ID + "/" + controlName;

    if (dev[topic] !== value) {
        dev[topic] = value;
    }
}

function formatParams(params) {
    var list = [];
    var k;

    if (!params) {
        return "";
    }

    for (k in params) {
        if (params.hasOwnProperty(k)) {
            if (
                params[k] !== undefined &&
                params[k] !== null &&
                params[k] !== ""
            ) {
                list.push(k + "=" + params[k]);
            }
        }
    }

    if (list.length === 0) {
        return "";
    }

    return "; " + list.join("; ");
}

function writeLog(eventName, eventText, params) {
    var message =
        "[" + SYSTEM_NAME + "]" +
        "[" + SCRIPT_NAME + "]" +
        "[" + CONTEXT_NAME + "]; " +
        eventName + "=" + eventText +
        formatParams(params);

    if (eventName === "АВАРИЯ" || eventName === "WATCHDOG") {
        log.error(message);
        return;
    }

    if (eventName === "ОШИБКА") {
        log.warning(message);
        return;
    }

    log.info(message);
}

function matchesAny(text, patterns) {
    var i;
    var re;

    for (i = 0; i < patterns.length; i++) {
        re = new RegExp(patterns[i]);

        if (re.test(text)) {
            return true;
        }
    }

    return false;
}

function isExcludedDevice(deviceName) {
    var i;

    for (i = 0; i < EXCLUDED_DEVICES.length; i++) {
        if (deviceName === EXCLUDED_DEVICES[i]) {
            return true;
        }
    }

    return false;
}

function parseDeviceControlTopic(topic) {
    var prefix = "/devices/";
    var middle = "/controls/";
    var middleIndex;
    var deviceName;
    var controlName;

    if (topic.indexOf(prefix) !== 0) {
        return null;
    }

    middleIndex = topic.indexOf(middle);

    if (middleIndex < 0) {
        return null;
    }

    deviceName = topic.substring(prefix.length, middleIndex);
    controlName = topic.substring(middleIndex + middle.length);

    if (controlName.indexOf("/") >= 0) {
        return null;
    }

    if (!deviceName || !controlName) {
        return null;
    }

    return {
        device: deviceName,
        control: controlName
    };
}

function isInputControl(deviceName, controlName) {
    if (isExcludedDevice(deviceName)) {
        return false;
    }

    if (matchesAny(controlName, EXCLUDE_CONTROL_PATTERNS)) {
        return false;
    }

    return matchesAny(controlName, INCLUDE_CONTROL_PATTERNS);
}

function normalizeValue(value) {
    if (
        value === true ||
        value === "true" ||
        value === "1" ||
        value === 1 ||
        value === "ON" ||
        value === "on"
    ) {
        return "ON";
    }

    if (
        value === false ||
        value === "false" ||
        value === "0" ||
        value === 0 ||
        value === "OFF" ||
        value === "off"
    ) {
        return "OFF";
    }

    return String(value);
}

// ============================================================================
// ПРЕОБРАЗОВАНИЕ СОБЫТИЯ В ФИЗИЧЕСКИЙ ВХОД
// ============================================================================

// Нам важно отличить:
//
// wb-mr6c_138/Input 1
// wb-mr6c_138/Input 1 Single Press Counter
// wb-mr6c_138/Input 1 Long Press Counter
//
// Это всё ОДИН физический Input 1.
//
// Поэтому для итогового списка убираем название счётчика.

function getPhysicalControlName(controlName) {
    var match;

    match = controlName.match(/^Input ([0-9]+)/);

    if (match) {
        return "Input " + match[1];
    }

    // Остальные типы входов пока оставляем как есть.
    return controlName;
}

function getPhysicalInputName(deviceName, controlName) {
    return deviceName + "/" + getPhysicalControlName(controlName);
}

// ============================================================================
// ЗАХВАТ ОДНОГО НАЖАТИЯ
// ============================================================================

function clearCurrentCapture() {
    STATE.physicalInputs = {};
    STATE.rawEvents = [];
}

function startCapture() {
    clearCurrentCapture();

    STATE.captureActive = true;

    setControl("status", "Собираю входы...");

    STATE.captureTimer = setTimeout(function () {
        finishCapture();
    }, CAPTURE_WINDOW_MS);
}

function addPhysicalInput(deviceName, controlName) {
    var physicalName =
        getPhysicalInputName(deviceName, controlName);

    STATE.physicalInputs[physicalName] = true;

    return physicalName;
}

function addRawEvent(deviceName, controlName, value) {
    var text =
        deviceName + "/" +
        controlName + " = " +
        normalizeValue(value);

    STATE.rawEvents.push(text);
}

function objectKeys(object) {
    var result = [];
    var key;

    for (key in object) {
        if (object.hasOwnProperty(key)) {
            result.push(key);
        }
    }

    return result;
}

function finishCapture() {
    var physicalList;
    var physicalText;
    var rawText;
    var now;

    STATE.captureActive = false;
    STATE.captureTimer = null;

    physicalList = objectKeys(STATE.physicalInputs);

    physicalList.sort();

    if (physicalList.length === 0) {
        setControl("status", "Ничего не найдено");
        return;
    }

    physicalText = physicalList.join("\n");
    rawText = STATE.rawEvents.join("\n");

    now = new Date();

    STATE.captureCounter += 1;

    setControl("capture_inputs", physicalText);
    setControl("capture_count", physicalList.length);
    setControl("raw_events", rawText);
    setControl("last_time", formatDateTime(now));
    setControl("capture_counter", STATE.captureCounter);

    setControl(
        "status",
        "Найдено физических входов: " + physicalList.length
    );

    if (LOG_CAPTURE_RESULT) {
        writeLog(
            "РЕЗУЛЬТАТ",
            "Захват нажатия завершён",
            {
                "количество": physicalList.length,
                "входы": physicalList.join(" | ")
            }
        );
    }
}

// ============================================================================
// ОБРАБОТКА MQTT
// ============================================================================

function handleMqttMessage(message) {
    var parsed;
    var topic;
    var value;
    var physicalInput;
    var normalizedValue;

    if (!dev[DEVICE_ID + "/enabled"]) {
        return;
    }

    if (nowMs() - STATE.startedAtMs < IGNORE_STARTUP_MS) {
        return;
    }

    if (!message || !message.topic) {
        return;
    }

    topic = String(message.topic);
    value = message.value;

    parsed = parseDeviceControlTopic(topic);

    if (!parsed) {
        return;
    }

    if (!isInputControl(parsed.device, parsed.control)) {
        return;
    }

    // Для обычного raw-входа учитываем только нажатие ON.
    // Отпускание OFF нам для определения физической клавиши не нужно.
    //
    // Для счётчиков нажатий учитываем любое изменение значения,
    // потому что счётчик обычно приходит числом 12 -> 13 и т.п.

    if (
        /^Input [0-9]+$/.test(parsed.control) &&
        normalizeValue(value) !== "ON"
    ) {
        return;
    }

    if (!STATE.captureActive) {
        startCapture();
    }

    physicalInput =
        addPhysicalInput(parsed.device, parsed.control);

    addRawEvent(
        parsed.device,
        parsed.control,
        value
    );

    STATE.eventCounter += 1;

    normalizedValue = normalizeValue(value);

    setControl("last_input", physicalInput);
    setControl("last_device", parsed.device);
    setControl("last_control", parsed.control);
    setControl("last_value", normalizedValue);
    setControl("event_counter", STATE.eventCounter);

    if (LOG_INPUT_CHANGES) {
        writeLog(
            "СОБЫТИЕ",
            "Обнаружен вход",
            {
                "физический_вход": physicalInput,
                "устройство": parsed.device,
                "контрол": parsed.control,
                "значение": normalizedValue
            }
        );
    }
}

// ============================================================================
// ЗАПУСК
// ============================================================================

writeLog(
    "СКРИПТ",
    "Скрипт загружен",
    {
        "устройство": DEVICE_ID,
        "задержка_старта_мс": IGNORE_STARTUP_MS,
        "окно_захвата_мс": CAPTURE_WINDOW_MS
    }
);

trackMqtt(
    "/devices/+/controls/+",
    function (message) {
        handleMqttMessage(message);
    }
);

writeLog(
    "СКРИПТ",
    "Стартовая инициализация завершена",
    {
        "устройство": DEVICE_ID
    }
);