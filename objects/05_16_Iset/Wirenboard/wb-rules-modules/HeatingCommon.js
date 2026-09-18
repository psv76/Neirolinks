/* ES5 / wb-rules 2.40: local dev inputs, HA heartbeat, HM2 packet TTL, журнал. */
function number(v) {
    if (typeof v !== "number" && typeof v !== "string") return null;
    if (typeof v === "string" && !/^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?\s*$/i.test(v)) return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
}
function boolean(v) {
    if (v === true || v === 1 || v === "1" || v === "true") return true;
    if (v === false || v === 0 || v === "0" || v === "false") return false;
    return null;
}
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function uiPad2(v) { return v < 10 ? "0" + v : String(v); }
function uiTime(ts) {
    var n = number(ts), d;
    if (n === null || n <= 0) return "—";
    d = new Date(n * 1000);
    return uiPad2(d.getDate()) + "." + uiPad2(d.getMonth() + 1) + " " +
        uiPad2(d.getHours()) + ":" + uiPad2(d.getMinutes()) + ":" + uiPad2(d.getSeconds());
}
function uiState(v) {
    var m = {
        STARTUP_VALIDATION: "Запуск / проверка входов",
        READY: "Норма",
        DEGRADED: "Ограниченный режим",
        WATCHDOG_INTERLOCK: "Блокировка защитой",
        BOILER_FAULT: "Авария котла / OpenTherm",
        ACTIVE: "Активен / есть запрос",
        INACTIVE: "Запроса нет",
        UNKNOWN: "Нет достоверных данных / блокировка",
        ACTIVE_PARALLEL: "Параллельная работа",
        NO_DEMAND: "Запросов тепла нет",
        DHW_CONDITIONAL_PRIORITY: "Приоритет ГВС",
        FROST_OVERRIDE: "Защита от замерзания",
        OUTPUTS_DISABLED: "Физические выходы отключены",
        OFF_METHOD_NOT_COMMISSIONED: "Способ выключения котла не введён",
        SAFETY_INTERLOCK: "Блокировка Safety",
        DHW: "ГВС"
    };
    return m[v] || String(v || "—");
}
function uiPriority(v) {
    var m = {
        COMFORT: "Комфортное отопление",
        DHW: "ГВС",
        PROCESS: "Технологический потребитель",
        FROST_SAFETY: "Защита от замерзания"
    };
    return m[v] || String(v || "—");
}
function uiReason(v) {
    var m = {
        STARTUP_VALIDATION: "Запуск / проверка входов",
        STARTUP_OR_RECOVERY: "Ожидание после запуска / восстановления",
        ZONE_REQUEST: "Есть запрос комнатных термостатов",
        NO_DEMAND: "Нет запроса тепла",
        LOCAL_THERMOSTAT: "Запрос по температуре помещений",
        TANK_THERMOSTAT: "По температуре бойлера ГВС",
        SENSOR_FAILSAFE_OR_STARTUP: "Датчик не готов / запуск",
        CIRCULATION_FAULT_LATCHED: "Авария циркуляции — требуется подтверждение",
        DHW_TOTAL_TIMEOUT_LATCHED: "ГВС: превышено время нагрева — требуется подтверждение",
        HA_HEARTBEAT_LOST: "Нет свежей связи с Home Assistant",
        HA_DEMAND_UNKNOWN: "Неизвестен запрос Home Assistant",
        ACTUATOR_COMMAND_OR_READBACK_FAILED: "Ошибка команды или подтверждения сервопривода",
        LIVING_MAP_NOT_COMMISSIONED: "Карта жилых зон не введена",
        AHU_FROST_CONTRACT_NOT_COMMISSIONED: "ПВУ не введена в HM2",
        COMMISSIONED_AHU_REQUEST: "Запрос ПВУ",
        OUTPUT_WRITE_FAILED: "Ошибка записи физического выхода",
        ACTIVE: "Активный запрос",
        DHW: "ГВС",
        FROST_OVERRIDE: "Защита от замерзания",
        BOILER_FAULT: "Авария котла / OpenTherm",
        SAFETY_INTERLOCK: "Блокировка Safety"
    };
    var names = {floor: "Тёплый пол", basement: "Цоколь", living: "Жилая зона", dhw: "ГВС", ahu: "ПВУ", NONE: "Никто"};
    var text = String(v || "—"), winner, invalid, w;
    if (m[text]) return m[text];
    if (text.indexOf("ACTIVE:LIMIT_RAMP") === 0)
        return "Нагрев; уставка меняется с ограничением скорости";
    if (text.indexOf("DHW:LIMIT_RAMP") === 0)
        return "ГВС; уставка меняется с ограничением скорости";
    if (text.indexOf("REQUIRED_TEMPERATURE_NOT_READY:") === 0)
        return "Не готовы обязательные температурные датчики";
    if (text.indexOf("winner=") === 0) {
        winner = /winner=([^;]+)/.exec(text);
        invalid = /invalid=([0-9]+)/.exec(text);
        w = winner ? winner[1] : "NONE";
        return "Победитель: " + (names[w] || w) +
            (invalid ? "; недостоверных потребителей: " + invalid[1] : "");
    }
    if (text.indexOf("missing=") === 0)
        return "Проверка достоверности менеджеров и датчиков";
    return text;
}
function fresh(ts, now, ttl, boot) {
    return number(ts) !== null && ts > boot && ts <= now && now - ts <= ttl;
}
function request(state, supply, priority, reason, now) {
    return { state: state, valid: state === "UNKNOWN" ? 0 : 1,
        requested_supply: state === "ACTIVE" ? supply : "NOT_READY",
        priority_class: priority, grant_required: 1, reason: reason, updated_at: now };
}
function validRequest(r, now, ttl, boot, lo, hi) {
    if (!r || !fresh(r.updated_at, now, ttl, boot) || r.valid !== 1) return false;
    if (r.state !== "ACTIVE" && r.state !== "INACTIVE") return false;
    if (r.grant_required !== 1) return false;
    if (["COMFORT", "DHW", "PROCESS", "FROST_SAFETY"].indexOf(r.priority_class) < 0) return false;
    if (r.state === "INACTIVE") return r.requested_supply === "NOT_READY";
    var t = number(r.requested_supply);
    return t !== null && t >= lo && t <= hi;
}
function create(api, name, ttl, options) {
    options = options || {};
    var boot = Date.now() / 1000, watched = {}, signatures = {}, deviceCells = {}, errors = {};
    function now() { return Date.now() / 1000; }
    function read(path) { try { return path ? api.dev[path] : undefined; } catch (e) { return undefined; } }
    function writeLog(type, event, params) {
        var text = "[отопление][" + name.toLowerCase() + "][контур]; " + type + "=" + event;
        var k;
        for (k in params) if (Object.prototype.hasOwnProperty.call(params, k)) text += "; " + k + "=" + params[k];
        if (type === "АВАРИЯ" || type === "WATCHDOG") api.log.error(text);
        else if (type === "ОШИБКА") api.log.warning(text);
        else api.log.info(text);
    }
    function changed(key, type, event, params) {
        var signature = event + JSON.stringify(params || {});
        if (signatures[key] !== signature) { signatures[key] = signature; writeLog(type, event, params || {}); }
    }
    function watch(path, callback) {
        if (!path || watched[path]) return;
        watched[path] = true;
        var slash = path.indexOf("/"), topic = "/devices/" + path.slice(0, slash) + "/controls/" + path.slice(slash + 1);
        /* wb-rules 2.40 does not expose retained here. Data events only run
         * guards promptly; local validity always comes from current dev[]. */
        api.trackMqtt(topic, function () { if (callback) callback(); });
        api.trackMqtt(topic + "/meta/error", function (m) {
            errors[path] = m.value !== "" && m.value !== null && m.value !== undefined;
            if (callback) callback();
        });
    }
    function inputStatus(path) {
        if (!path) return "NOT_COMMISSIONED";
        if (errors[path]) return "INPUT_ERROR";
        var value = read(path);
        return value === undefined || value === null || value === "" ? "INPUT_UNKNOWN" : "VALID";
    }
    function commissioned(paths) {
        if (!paths || !paths.length) return false;
        for (var i = 0; i < paths.length; i++) if (!paths[i]) return false;
        return true;
    }
    function input(path) {
        return inputStatus(path) === "VALID" ? read(path) : undefined;
    }
    function num(path, lo, hi) {
        var n = number(input(path));
        return n !== null && n >= lo && n <= hi ? n : null;
    }
    function heartbeatFresh(path, age) {
        return !!path && fresh(number(read(path)), now(), age || ttl.haHeartbeat, boot);
    }
    function haInput(path, heartbeatPath) {
        return heartbeatFresh(heartbeatPath, ttl.haHeartbeat) ? input(path) : undefined;
    }
    function haNum(path, heartbeatPath, lo, hi) {
        var n = number(haInput(path, heartbeatPath));
        return n !== null && n >= lo && n <= hi ? n : null;
    }
    function json(path) { try { return JSON.parse(read(path)); } catch (e) { return null; } }
    function packet(path) {
        var p = json(path);
        return p && fresh(p.updated_at, now(), ttl.request, boot) ? p : null;
    }
    function cell(value, title) { return { type: typeof value === "boolean" ? "switch" : typeof value === "number" ? "value" : "text", value: value, title: title, readonly: true, forceDefault: true }; }
    function device(id, title, extra, consumer) {
        var cells = {
            state_ui: cell("Запуск / проверка входов", "Состояние"),
            reason_ui: cell("Запуск / проверка входов", "Почему")
        }, k;
        if (consumer) {
            cells.valid = cell(false, "Данные достоверны");
            cells.requested_supply = cell("NOT_READY", "Требуемая температура источника, °C");
            cells.priority_ui = cell("Комфортное отопление", "Назначение запроса");
            cells.grant_required = cell(true, "Требуется разрешение арбитра");
        }
        for (k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) cells[k] = extra[k];
        cells.updated_ui = cell("—", "Последний расчёт");

        cells.state = cell("STARTUP_VALIDATION", "Код состояния");
        cells.state.hidden = true;

        cells.reason = cell("STARTUP_VALIDATION", "Код причины");
        cells.reason.hidden = true;

        cells.updated_at = cell(0, "Последний расчёт, unix");
        cells.updated_at.hidden = true;

        if (consumer) {
            cells.priority_class = cell("COMFORT", "Класс запроса (код)");
            cells.priority_class.hidden = true;
        }

        cells.packet = cell("{}", "Атомарный контракт JSON");
        cells.packet.hidden = true;

        var order = 1;
        for (k in cells) if (Object.prototype.hasOwnProperty.call(cells, k)) cells[k].order = order++;
        deviceCells[id] = cells;
        api.defineVirtualDevice(id, { title: title, cells: cells });
        writeLog("СКРИПТ", "STARTUP_VALIDATION", {});
    }
    function publish(id, p) {
        var k, fields = ["state", "reason", "updated_at", "valid", "requested_supply", "priority_class", "grant_required"];
        var stateUi = uiState(p.state);
        var reasonUi = uiReason(p.reason);

        if (id === "heating_ahu" && p.commissioned === false) {
            stateUi = "Автономно / вне HM2";
            reasonUi = "ПВУ управляется отдельной логикой";
        }

        if (deviceCells[id].state_ui) api.dev[id + "/state_ui"] = stateUi;
        if (deviceCells[id].reason_ui) api.dev[id + "/reason_ui"] = reasonUi;
        if (deviceCells[id].updated_ui) api.dev[id + "/updated_ui"] = uiTime(p.updated_at);
        if (deviceCells[id].priority_ui && p.priority_class !== undefined)
            api.dev[id + "/priority_ui"] = uiPriority(p.priority_class);
        for (k = 0; k < fields.length; k++) if (p[fields[k]] !== undefined && deviceCells[id][fields[k]]) {
            var value = p[fields[k]];
            if (fields[k] === "valid" || fields[k] === "grant_required") value = value === 1;
            if (fields[k] === "requested_supply") value = String(value);
            api.dev[id + "/" + fields[k]] = value;
        }
        /* Читатели используют только packet, никогда смесь нескольких MQTT controls. */
        api.dev[id + "/packet"] = JSON.stringify(p);
        changed(id, p.state === "UNKNOWN" ? "ОШИБКА" : "СОСТОЯНИЕ", p.state, { причина: p.reason });
    }
    function output(path, value, enabled) {
        if (!options.allowedOutputs || options.allowedOutputs.indexOf(path) < 0) {
            changed("ownership", "ОШИБКА", "OUTPUT_OWNER_DENIED", {канал: path}); return false;
        }
        if (!enabled) return false;
        var old = typeof value === "boolean" ? boolean(read(path)) : number(read(path));
        if (old === value) return true;
        try {
            api.dev[path] = value;
            writeLog("КОМАНДА", "Запись", { канал: path, значение: value });
            return true;
        } catch (e) { changed(path, "ОШИБКА", "OUTPUT_WRITE_FAILED", { канал: path }); return false; }
    }
    function permit(id) {
        var s = packet("heating_safety/packet"), a = packet("heating_state/packet");
        return !!(s && s.allow_normal === true && a && a.grants && a.grants[id] === "GRANTED");
    }
    return { boot: boot, now: now, read: read, watch: watch, input: input, inputStatus: inputStatus, num: num,
        commissioned: commissioned, heartbeatFresh: heartbeatFresh, haInput: haInput, haNum: haNum,
        haBool: function (p, h) { return boolean(haInput(p, h)); },
        bool: function (p) { return boolean(input(p)); }, packet: packet, json: json,
        cell: cell, device: device, publish: publish, output: output, permit: permit,
        log: writeLog, changed: changed };
}
function readbackMatch(actual, command, policy) {
    if (!policy || policy.commissioned !== true || number(actual) === null || number(command) === null ||
        number(policy.tolerance) === null || policy.tolerance < 0 ||
        number(policy.settleSeconds) === null || policy.settleSeconds < 0) return null;
    var expected = command;
    if (policy.normalization === "CLAMP") {
        if (number(policy.minimum) === null || number(policy.maximum) === null || policy.minimum > policy.maximum) return null;
        expected = clamp(command, policy.minimum, policy.maximum);
    } else if (policy.normalization !== "EXACT") return null;
    return Math.abs(actual - expected) <= policy.tolerance;
}
function pathTimers() {
    var gates = {};
    return function (key, open, now, delay) {
        if (!gates[key]) gates[key] = stableGate();
        return gates[key](open === true, now, delay);
    };
}
function stableGate() {
    var since = null;
    return function (ok, now, delay) {
        if (!ok) { since = null; return false; }
        if (since === null || now < since) since = now;
        return now - since >= delay;
    };
}
function responseWatch() {
    var since = null, start = null;
    return function (active, temperature, now, window, rise) {
        if (!active || temperature === null) { since = null; start = null; return "NOT_MONITORED"; }
        if (since === null || now < since) { since = now; start = temperature; }
        if (temperature - start >= rise) { since = now; start = temperature; return "RESPONSE_CONFIRMED"; }
        return now - since >= window ? "NO_RESPONSE" : "OBSERVING";
    };
}
exports.number = number; exports.boolean = boolean; exports.clamp = clamp;
exports.uiState = uiState; exports.uiReason = uiReason; exports.uiPriority = uiPriority; exports.uiTime = uiTime;
exports.fresh = fresh; exports.request = request; exports.validRequest = validRequest;
exports.create = create; exports.stableGate = stableGate; exports.responseWatch = responseWatch;
exports.readbackMatch = readbackMatch; exports.pathTimers = pathTimers;
