// 414_Pressure_makeup.js — 04 42 Ласточка, датчик 414
// Импульсная автоматическая подпитка системы отопления.
// Датчик: wb-mai2-mini_46, вход 1, 4–20 мА, шкала 0–6000 = 0–6 бар.
// Выход подтверждён; ввод в эксплуатацию и все команды ON отключены до ПНР.
// Один физический выход = один управляющий скрипт. ES5, Wiren Board wb-rules.

var CH = {
    pressureValue: "wb-mai2-mini_46/input_1_value",
    pressureCurrent: "wb-mai2-mini_46/input_1_current",
    valve: "wb-mr6cu_196/K5" // Клапан подпитки
};

var CFG = {
    commissioned: false,       // true — ТОЛЬКО после проверки подключения и ПНР.
    pressureStartBar: 1.0,    // Начать подпитку при давлении котла <= 1,0 бар.
    pressureTargetBar: 1.2,   // Остановить при давлении котла >= 1,2 бар.
    pressureAlarmBar: 0.8,    // Предварительная аварийная граница, согласовать.
    offsetDefaultBar: -0.2,   // Котёл = датчик 414 + поправка.
    offsetMinBar: -1.0,
    offsetMaxBar: 1.0,
    pressureHighBar: 2.5,      // ПРЕДВАРИТЕЛЬНО; аварийная блокировка.
    currentLowMa: 3.6,        // Ниже — обрыв/ошибка.
    currentHighMa: 20.5,      // Выше — выход за нормальный диапазон.
    // MAI2 публикует current и value раздельно, не синхронной парой.
    // Сравнение в момент каждого MQTT-события давало ложную аварию.
    sensorFreshMs: 120000,    // При отсутствии НОВЫХ публикаций блокировать.
    startupBlockMs: 60000,    // После перезапуска wb-rules.
    pulseOpenMs: 3000,
    pulsePauseMs: 20000,
    watchdogMs: 5000,         // Предельная длительность команды ВКЛ.
    offReadbackTimeoutMs: 5000, // Ожидание обновления канала K5 после OFF.
    offRetryMs: 1000,          // Повтор OFF при ещё видимом ON.
    maxPulses: 5,             // На один цикл.
    maxCycles1h: 3,           // Счётчики сбрасываются при restart wb-rules.
    maxCycles24h: 6
};

var STATE = {
    pressureSeenAt: 0,
    currentSeenAt: 0,
    blockUntil: Date.now() + CFG.startupBlockMs,
    cycle: false,
    pulse: false,
    pulseStartedAt: 0,
    pauseUntil: 0,
    pulseCount: 0,
    pulseTimer: null,
    offRequestedAt: 0,
    lastOffRetryAt: 0,
    relayOffTimeoutReported: false,
    history: [],
    latchedFault: "",
    lastEvent: "Ожидание проверки конфигурации",
    offsetBar: CFG.offsetDefaultBar,
    lowAlarm: false,
    sensorAlarmReported: false
};

function boolOn(v)
{
    return v === true || v === 1 || v === "1" || v === "true" || v === "ON";
}

function boolOff(v)
{
    return v === false || v === 0 || v === "0" || v === "false" || v === "OFF";
}

function numberOrNull(v)
{
    if (v === null || v === undefined || v === "")
        return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
}

// Поправка сохраняется через PersistentStorage при перезапуске wb-rules.
var OFFSET_STORAGE = new PersistentStorage("lastochka_pressure_makeup_414", {global: true});
var storedOffset = numberOrNull(OFFSET_STORAGE["offset_bar"]);
if (storedOffset !== null &&
    storedOffset >= CFG.offsetMinBar &&
    storedOffset <= CFG.offsetMaxBar)
    STATE.offsetBar = storedOffset;
else
    OFFSET_STORAGE["offset_bar"] = STATE.offsetBar;

function rounded(v)
{
    return v === null ? null : Math.round(v * 1000) / 1000;
}

function writeCell(name, value)
{
    var path = "lastochka_pressure_makeup/" + name;
    if (dev[path] !== value)
        dev[path] = value;
}

function journal(kind, message)
{
    var line = "[отопление][414_Pressure_makeup][ласточка]; " +
        kind + "=" + message;
    if (typeof log !== "undefined" && log)
    {
        if ((kind === "АВАРИЯ" || kind === "WATCHDOG") &&
            typeof log.error === "function")
            log.error(line);
        else if (kind === "ОШИБКА" && typeof log.warning === "function")
            log.warning(line);
        else if (typeof log.info === "function")
            log.info(line);
        else if (typeof log === "function")
            log(line);
    }
}

function event(kind, message)
{
    if (STATE.lastEvent === message)
        return;
    STATE.lastEvent = message;
    journal(kind, message);
}

function sensor()
{
    var raw = numberOrNull(dev[CH.pressureValue]);
    var ma = numberOrNull(dev[CH.pressureCurrent]);
    var now = Date.now();
    var pRaw = raw === null ? null : raw / 1000;
    var p = pRaw === null ? null : pRaw + STATE.offsetBar;
    var error = "";

    if (raw === null || ma === null)
        error = "Нет числового значения давления или тока";
    else if (STATE.pressureSeenAt === 0 || STATE.currentSeenAt === 0)
        error = "Нет новых публикаций обоих каналов после запуска";
    else if ((now - STATE.pressureSeenAt > CFG.sensorFreshMs) ||
             (now - STATE.currentSeenAt > CFG.sensorFreshMs))
        error = "Устаревшие данные датчика давления";
    else if (ma < CFG.currentLowMa || ma > CFG.currentHighMa)
        error = "Ток датчика вне диапазона: " + ma + " мА";
    else if (raw < 0 || raw > 6000)
        error = "Пересчитанное значение вне диапазона 0–6000";
    else if (p < 0 || p > 6)
        error = "Скорректированное давление вне диапазона 0–6 бар";

    return { pressure: p, rawPressure: pRaw, current: ma, error: error };
}

function settingsOk()
{
    return CH.valve !== null &&
        typeof CH.valve === "string" &&
        CH.valve.length > 0 &&
        CFG.commissioned === true &&
        CFG.pressureStartBar > 0 &&
        CFG.pressureTargetBar > CFG.pressureStartBar &&
        CFG.pressureHighBar > CFG.pressureTargetBar &&
        CFG.pressureHighBar <= 6 &&
        CFG.pulseOpenMs > 0 &&
        CFG.watchdogMs > CFG.pulseOpenMs &&
        CFG.maxPulses >= 1;
}

function commandOff(why)
{
    if (!CH.valve || !CFG.commissioned)
        return;
    try
    {
        // Команда OFF — НЕ подтверждение физического закрытия клапана.
        if (STATE.offRequestedAt === 0)
            STATE.offRequestedAt = Date.now();
        STATE.lastOffRetryAt = Date.now();
        // OFF — команда в MQTT, НЕ аппаратное подтверждение закрытия.
        dev[CH.valve] = false;
        journal("КОМАНДА", "Выключить реле подпитки; канал=" +
            CH.valve + "; причина=" + why);
    }
    catch (e)
    {
        journal("ОШИБКА", "Не удалось записать OFF в " + CH.valve);
    }
}

function commandOn()
{
    if (!settingsOk() || !boolOff(dev[CH.valve]))
        return false;
    try
    {
        dev[CH.valve] = true;
        STATE.offRequestedAt = 0;
        STATE.lastOffRetryAt = 0;
        STATE.relayOffTimeoutReported = false;
        journal("КОМАНДА", "Включить реле подпитки; канал=" +
            CH.valve + "; на=" + CFG.pulseOpenMs + " мс");
        return true;
    }
    catch (e)
    {
        journal("ОШИБКА", "Не удалось записать ON в " + CH.valve);
        return false;
    }
}

function cancelPulseTimer()
{
    if (STATE.pulseTimer !== null)
    {
        clearTimeout(STATE.pulseTimer);
        STATE.pulseTimer = null;
    }
}

function stopCycle(why)
{
    cancelPulseTimer();
    if (STATE.pulse || (CFG.commissioned && CH.valve && boolOn(dev[CH.valve])))
        commandOff(why);
    STATE.pulse = false;
    STATE.cycle = false;
    STATE.pauseUntil = 0;
    event("СОСТОЯНИЕ", why);
}

function trip(why)
{
    stopCycle(why);
    if (!STATE.latchedFault)
    {
        STATE.latchedFault = why;
        journal("АВАРИЯ", why + "; автоподпитка заблокирована до сброса");
    }
}

function finishPulse()
{
    if (!STATE.pulse)
        return;
    cancelPulseTimer();
    commandOff("Окончание импульса");
    STATE.pulse = false;
    STATE.pauseUntil = Date.now() + CFG.pulsePauseMs;
    event("СОСТОЯНИЕ", "Импульс завершён, пауза " +
        CFG.pulsePauseMs / 1000 + " с");
}

function openPulse()
{
    if (STATE.pulse || STATE.latchedFault || !settingsOk())
        return;
    if (!commandOn())
    {
        trip("Не удалось включить реле или нет подтверждённого состояния OFF");
        return;
    }
    STATE.pulse = true;
    STATE.pulseStartedAt = Date.now();
    STATE.pulseCount++;
    event("СОСТОЯНИЕ", "Импульс " + STATE.pulseCount + "/" + CFG.maxPulses);
    STATE.pulseTimer = setTimeout(function () {
        finishPulse();
    }, CFG.pulseOpenMs);
}

function recentCycles(now)
{
    var i;
    var keep = [];
    var n1 = 0;
    for (i = 0; i < STATE.history.length; i++)
    {
        if (now - STATE.history[i] < 24 * 60 * 60 * 1000)
        {
            keep.push(STATE.history[i]);
            if (now - STATE.history[i] < 60 * 60 * 1000)
                n1++;
        }
    }
    STATE.history = keep;
    return { n1: n1, n24: keep.length };
}

function startCycle(now)
{
    var counts = recentCycles(now);
    if (counts.n1 >= CFG.maxCycles1h ||
        counts.n24 >= CFG.maxCycles24h)
    {
        trip("Превышен лимит частоты автоподпитки");
        return;
    }
    STATE.history.push(now);
    STATE.cycle = true;
    STATE.pulseCount = 0;
    event("СОСТОЯНИЕ", "Старт цикла подпитки");
    openPulse();
}

function status(s, why)
{
    var counts = recentCycles(Date.now());
    writeCell("pressure_bar", rounded(s.pressure));
    writeCell("raw_pressure_bar", rounded(s.rawPressure));
    writeCell("current_ma", rounded(s.current));
    writeCell("cycle_active", STATE.cycle);
    writeCell("relay_command_on", STATE.pulse);
    writeCell("pulses", STATE.pulseCount);
    writeCell("cycles_1h", counts.n1);
    writeCell("cycles_24h", counts.n24);
    writeCell("sensor_alarm", !!s.error);
    writeCell("low_pressure_alarm", STATE.lowAlarm);
    writeCell("alarm", !!STATE.latchedFault);
    writeCell("fault", STATE.latchedFault);
    writeCell("block_reason", why);
    writeCell("last_event", STATE.lastEvent);
}

function tick()
{
    var now = Date.now();
    var s = sensor();
    var enabled = boolOn(dev["lastochka_pressure_makeup/enabled"]);
    var autoMode = boolOn(dev["lastochka_pressure_makeup/auto_mode"]);
    var reason = "";

    if (s.pressure !== null && !s.error)
    {
        var low = s.pressure < CFG.pressureAlarmBar;
        if (low !== STATE.lowAlarm && !s.error)
        {
            STATE.lowAlarm = low;
            journal(low ? "АВАРИЯ" : "СОСТОЯНИЕ",
                low ? "Давление отопления ниже аварийного порога" :
                      "Аварийно низкое давление устранено");
        }
    }

    // После команды OFF readback K5 может некоторое время показывать старое ON.
    // Не считаем это чужой командой в течение ограниченного окна ожидания.
    if (CFG.commissioned && CH.valve && !STATE.pulse)
    {
        if (boolOff(dev[CH.valve]))
        {
            STATE.offRequestedAt = 0;
            STATE.lastOffRetryAt = 0;
            STATE.relayOffTimeoutReported = false;
        }
        else if (boolOn(dev[CH.valve]))
        {
            if (STATE.offRequestedAt === 0)
                trip("Выход подпитки включён вне разрешённого импульса");
            else
            {
                if (now - STATE.lastOffRetryAt >= CFG.offRetryMs)
                    commandOff("Повтор OFF: MQTT K5 ещё показывает ON");

                if (now - STATE.offRequestedAt >= CFG.offReadbackTimeoutMs &&
                    !STATE.relayOffTimeoutReported)
                {
                    STATE.relayOffTimeoutReported = true;
                    trip("После команды OFF состояние K5 остаётся ON");
                    journal("WATCHDOG", "OFF не подтверждён за " +
                        CFG.offReadbackTimeoutMs + " мс; нужна проверка реле");
                }
            }
        }
    }

    if (STATE.pulse)
    {
        if (now - STATE.pulseStartedAt >= CFG.watchdogMs)
        {
            trip("WATCHDOG: превышена длительность команды клапану");
            journal("WATCHDOG", "Аварийная попытка отключения реле");
        }
        else if (now - STATE.pulseStartedAt >= CFG.pulseOpenMs)
            finishPulse();
    }

    if (s.error)
    {
        if (STATE.pulse || STATE.cycle)
            trip("Ошибка датчика во время подпитки: " + s.error);
        if (!STATE.sensorAlarmReported)
        {
            journal("ОШИБКА", s.error);
            STATE.sensorAlarmReported = true;
        }
        reason = s.error;
    }
    else if (STATE.sensorAlarmReported)
    {
        journal("СОСТОЯНИЕ", "Показания датчика восстановились");
        STATE.sensorAlarmReported = false;
    }

    if (!settingsOk())
        reason = "Не подтверждён клапан / конфигурация не введена в эксплуатацию";
    else if (!enabled || !autoMode)
        reason = "Отключено в интерфейсе";
    else if (STATE.latchedFault)
        reason = STATE.latchedFault;
    else if (now < STATE.blockUntil)
        reason = "Блокировка после запуска или сброса";
    else if (s.error)
        reason = s.error;
    else if (!boolOff(dev[CH.valve]) && !STATE.pulse)
    {
        if (STATE.offRequestedAt !== 0 &&
            now - STATE.offRequestedAt < CFG.offReadbackTimeoutMs)
        {
            // Цикл сохраняется, следующий импульс запрещён до видимого OFF.
            status(s, "Ожидание обновления MQTT K5 после команды OFF");
            return;
        }
        reason = "Нет достоверного OFF релейного выхода";
    }
    else if (s.pressure >= CFG.pressureHighBar)
    {
        trip("Давление выше аварийного верхнего порога");
        reason = STATE.latchedFault;
    }

    if (reason)
    {
        if (STATE.pulse || STATE.cycle)
            stopCycle("Остановка подпитки: " + reason);
        status(s, reason);
        return;
    }

    if (STATE.pulse)
    {
        if (s.pressure >= CFG.pressureTargetBar)
            stopCycle("Достигнута цель, подпитка прекращена");
        status(s, "");
        return;
    }

    if (STATE.cycle && s.pressure >= CFG.pressureTargetBar)
    {
        stopCycle("Достигнуто целевое давление");
        STATE.pulseCount = 0;
    }
    else if (STATE.cycle)
    {
        if (now >= STATE.pauseUntil)
        {
            if (STATE.pulseCount >= CFG.maxPulses)
                trip("Цель не достигнута за " + CFG.maxPulses + " импульсов");
            else
                openPulse();
        }
    }
    else if (s.pressure <= CFG.pressureStartBar)
        startCycle(now);

    status(s, "");
}

defineVirtualDevice("lastochka_pressure_makeup", {
    title: "414 Подпитка отопления — Ласточка (проект)",
    cells: {
        pressure_bar: { title: "Давление котла (с поправкой), бар", type: "value",
            value: 0, readonly: true, order: 1 },
        raw_pressure_bar: { title: "Давление датчика 414, бар", type: "value",
            value: 0, readonly: true, order: 2 },
        offset_bar: { title: "Поправка датчика 414, бар", type: "value",
            value: STATE.offsetBar, order: 3 },
        current_ma: { title: "Ток датчика 414, мА", type: "value",
            value: 0, readonly: true, order: 2 },
        cycle_active: { title: "Цикл подпитки", type: "switch",
            value: false, readonly: true, order: 3 },
        relay_command_on: { title: "Команда клапану ON", type: "switch",
            value: false, readonly: true, order: 4 },
        pulses: { title: "Импульсов в цикле", type: "value",
            value: 0, readonly: true, order: 5 },
        cycles_1h: { title: "Циклов за 1 час", type: "value",
            value: 0, readonly: true, order: 6 },
        cycles_24h: { title: "Циклов за 24 часа", type: "value",
            value: 0, readonly: true, order: 7 },
        sensor_alarm: { title: "Ошибка датчика", type: "switch",
            value: false, readonly: true, order: 10 },
        low_pressure_alarm: { title: "Низкое давление", type: "switch",
            value: false, readonly: true, order: 11 },
        alarm: { title: "Аварийная блокировка", type: "switch",
            value: false, readonly: true, order: 12 },
        fault: { title: "Причина аварии", type: "text",
            value: "", readonly: true, order: 13 },
        block_reason: { title: "Причина запрета подпитки", type: "text",
            value: "", readonly: true, order: 14 },
        last_event: { title: "Последнее событие", type: "text",
            value: "", readonly: true, order: 15 },
        enabled: { title: "Разрешить подпитку", type: "switch",
            value: false, order: 20 },
        auto_mode: { title: "Авторежим", type: "switch",
            value: false, order: 21 },
        manual_close: { title: "Остановить и заблокировать", type: "pushbutton",
            order: 22 },
        reset_alarm: { title: "Сброс аварий и блокировки", type: "pushbutton",
            order: 23 }
    }
});

// trackMqtt получает каждую публикацию, включая неизменившееся значение.
// Это важно для достоверного контроля устаревания показаний.
if (typeof trackMqtt === "function")
{
    trackMqtt("/devices/wb-mai2-mini_46/controls/input_1_value", function () {
        STATE.pressureSeenAt = Date.now();
        tick();
    });
    trackMqtt("/devices/wb-mai2-mini_46/controls/input_1_current", function () {
        STATE.currentSeenAt = Date.now();
        tick();
    });
}
else
    journal("ОШИБКА", "trackMqtt недоступен: подпитка запрещена");

// Изменение поправки прекращает текущий цикл; после изменения ожидание 60 с.
defineRule("lastochka_makeup_offset_414", {
    whenChanged: "lastochka_pressure_makeup/offset_bar",
    then: function (v) {
        var correction = numberOrNull(v);
        if (correction === null ||
            correction < CFG.offsetMinBar || correction > CFG.offsetMaxBar)
        {
            journal("ОШИБКА", "Недопустимая поправка датчика, разрешено от " +
                CFG.offsetMinBar + " до " + CFG.offsetMaxBar + " бар");
            writeCell("offset_bar", STATE.offsetBar);
            return;
        }
        correction = Math.round(correction * 1000) / 1000;
        if (correction === STATE.offsetBar)
            return;
        var before = STATE.offsetBar;
        stopCycle("Изменена поправка датчика");
        STATE.offsetBar = correction;
        OFFSET_STORAGE["offset_bar"] = correction;
        STATE.blockUntil = Date.now() + CFG.startupBlockMs;
        writeCell("offset_bar", correction);
        journal("НАСТРОЙКА", "Поправка датчика 414; было=" + before +
            " бар; стало=" + correction + " бар");
        tick();
    }
});

defineRule("lastochka_makeup_enable", {
    whenChanged: ["lastochka_pressure_makeup/enabled",
                  "lastochka_pressure_makeup/auto_mode"],
    then: function () {
        tick();
    }
});

defineRule("lastochka_makeup_manual_stop", {
    whenChanged: "lastochka_pressure_makeup/manual_close",
    then: function (v) {
        if (!boolOn(v))
            return;
        trip("Остановлено вручную");
        tick();
    }
});

defineRule("lastochka_makeup_reset", {
    whenChanged: "lastochka_pressure_makeup/reset_alarm",
    then: function (v) {
        if (!boolOn(v))
            return;
        stopCycle("Сброс оператором");
        STATE.latchedFault = "";
        STATE.pulseCount = 0;
        STATE.blockUntil = Date.now() + CFG.startupBlockMs;
        journal("СОСТОЯНИЕ", "Аварии сброшены; задержка автозапуска");
        tick();
    }
});

journal("СКРИПТ", "Загружен проект 414 Ласточка; поправка=" + STATE.offsetBar +
    " бар; ввод в эксплуатацию=" +
    CFG.commissioned + "; клапан=" + (CH.valve || "НЕ НАЗНАЧЕН"));

if (CFG.commissioned && CH.valve)
    commandOff("Старт скрипта");

setInterval(tick, 1000);
