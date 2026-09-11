// Расшифровка статуса котла через OpenTherm (WBE2-I-OPENTHERM)
// Создаёт виртуальное устройство "Состояние котла" с читаемыми статусами.
// Не дублирует то, что уже отображается в панели "Котельная".

var OT = "wbe2-i-opentherm_11";

var SRC = {
    boilerStatus:  OT + "/Boiler Status",
    flame:         OT + "/Boiler Flame Status",
    chEnable:      OT + "/Master CH enable",
    chMode:        OT + "/Boiler CH mode",
    dhwEnable:     OT + "/Master DHW enable",
    dhwMode:       OT + "/Boiler DHW mode",
    fault:         OT + "/Boiler fault indication",
    errorCode:     OT + "/Error Code",
    lowWaterPress: OT + "/Low water press",
    gasFlame:      OT + "/GAS Flame fault",
    airPress:      OT + "/Air press fault",
    overtemp:      OT + "/Water overtemp",
    noConn:        OT + "/Invalid Connection",
    modulation:    OT + "/Burner Modulation Level"
};

// ── Вспомогательные функции ──────────────────────────────────────────────────

function rb(path)
{
    var v = dev[path];
    return v === true || v === 1 || v === "1" || v === "true";
}

function rn(path)
{
    var v = Number(dev[path]);
    return isNaN(v) ? null : v;
}

function sc(name, value)
{
    if (dev["boiler_state/" + name] !== value)
        dev["boiler_state/" + name] = value;
}

// ── Логика расшифровки ───────────────────────────────────────────────────────

// Собирает список активных неисправностей.
// Приоритет — конкретные флаги, потом общий индикатор аварии.
function collectFaults()
{
    var faults = [];

    if (rb(SRC.lowWaterPress))  faults.push("низкое давление воды");
    if (rb(SRC.gasFlame))       faults.push("ошибка газ/розжиг");
    if (rb(SRC.airPress))       faults.push("ошибка прессостата воздуха");
    if (rb(SRC.overtemp))       faults.push("перегрев теплоносителя");

    var code = rn(SRC.errorCode);
    if (code !== null && code !== 0)
        faults.push("код OEM: " + code);

    // Общий флаг аварии без конкретики
    if (rb(SRC.fault) && !faults.length)
        faults.push("общая авария (нет уточнения)");

    return faults;
}

// Главный текст: одна фраза о том, что котёл делает прямо сейчас.
function buildSummary(faults)
{
    if (rb(SRC.noConn))
        return "⚠ Нет связи с котлом";

    if (faults.length)
        return "⚠ АВАРИЯ: " + faults.join(", ");

    var mod    = rn(SRC.modulation);
    var modStr = (mod !== null && mod > 0) ? " (горелка " + mod + "%)" : "";

    if (rb(SRC.dhwMode) && rb(SRC.flame))
        return "Нагрев ГВС" + modStr;

    if (rb(SRC.chMode) && rb(SRC.flame))
        return "Нагрев ЦО" + modStr;

    // Горелка горит, но режим ещё не установлен (переходное состояние)
    if (rb(SRC.flame))
        return "Горелка работает" + modStr;

    if (rb(SRC.dhwEnable) && !rb(SRC.dhwMode))
        return "Запрос ГВС — ожидание розжига";

    if (rb(SRC.chEnable) && !rb(SRC.chMode))
        return "Запрос ЦО — ожидание розжига";

    return "Ожидание запроса";
}

// Расшифровка битового поля Boiler Status (OpenTherm Message ID 0, low byte).
// Даёт понять, что именно зашифровано в числе «12» и подобных.
function buildStatusBits()
{
    var raw = rn(SRC.boilerStatus);
    if (raw === null) return "нет данных";

    var flags = [];
    if (raw & 0x01) flags.push("авария");
    if (raw & 0x02) flags.push("ЦО активен");
    if (raw & 0x04) flags.push("ГВС активен");
    if (raw & 0x08) flags.push("горелка");
    if (raw & 0x10) flags.push("охлаждение");
    if (raw & 0x20) flags.push("ЦО-2 активен");
    if (raw & 0x40) flags.push("диагностика");

    var decoded = flags.length ? flags.join(", ") : "нет активных флагов";
    return "0x" + raw.toString(16).toUpperCase() + " → " + decoded;
}

// ── Основная функция обновления ──────────────────────────────────────────────

function evaluate()
{
    var faults = collectFaults();

    sc("summary",     buildSummary(faults));
    sc("faults_text", faults.length ? faults.join(", ") : "нет");
    sc("connection",  rb(SRC.noConn) ? "⚠ Ошибка связи" : "OK");
    sc("status_bits", buildStatusBits());
}

// ── Виртуальное устройство ───────────────────────────────────────────────────

defineVirtualDevice("boiler_state", {
    title: "Состояние котла",
    cells: {
        // Одна фраза о текущем режиме — главный индикатор
        summary: {
            type: "text", title: "Что происходит",
            value: "", readonly: true
        },
        // Активные неисправности с расшифровкой по типам
        // (панель показывает только 0/1, без деталей)
        faults_text: {
            type: "text", title: "Активные неисправности",
            value: "", readonly: true
        },
        // Связь с котлом — отдельного виджета на панели нет
        connection: {
            type: "text", title: "Связь с котлом",
            value: "", readonly: true
        },
        // Расшифровка числа из «Статус котла» в читаемые флаги
        // (панель показывает просто число, например «12»)
        status_bits: {
            type: "text", title: "Флаги статуса OpenTherm",
            value: "", readonly: true
        }
    }
});

// ── Правило и инициализация ──────────────────────────────────────────────────

defineRule("boiler_state_evaluate", {
    whenChanged: [
        SRC.boilerStatus, SRC.flame,
        SRC.chEnable,     SRC.chMode,
        SRC.dhwEnable,    SRC.dhwMode,
        SRC.fault,        SRC.errorCode,
        SRC.lowWaterPress, SRC.gasFlame,
        SRC.airPress,     SRC.overtemp,
        SRC.noConn,       SRC.modulation
    ],
    then: function () { evaluate(); }
});

// Первый прогон через 3 с после загрузки правил
setTimeout(function () { evaluate(); }, 3000);