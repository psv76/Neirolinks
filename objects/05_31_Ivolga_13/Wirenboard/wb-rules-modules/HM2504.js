/* Иволга 504: комбо-логика и транспорт. ES5, без физических writes.
 * Уставки интерфейса не являются температурными пределами теплоносителя.
 */
exports.TOPIC = '/neiro/ivolga/504/v2/frame';
exports.VERSION = 2;
exports.SOURCE = 'ivolga-besedka-504';
exports.MIN_WB_RULES_VERSION = '2.42.0';
exports.RUNTIME_ERROR_RU = 'Нет булевого trackMqtt.retained; требуется wb-rules >= 2.42.0. Обновление только по согласованию';
exports.TTL_MS = 30000;
exports.SENSOR_TTL_MS = 120000;
exports.CLOCK_SKEW_MS = 2000;
exports.REVALIDATION_MS = 5000;
function number(v) {
    if (typeof v !== 'number' && typeof v !== 'string') return null;
    if (typeof v === 'string' && !v.trim()) return null;
    v = Number(v);
    return isFinite(v) ? v : null;
}
function between(v, min, max) { return typeof v === 'number' && isFinite(v) && v >= min && v <= max; }
function settings(s) {
    return s && between(s.target, 15, 30) && between(s.hold, 18, 30) &&
        between(s.heat, 20, 35) && s.hold <= s.heat && (s.enabled === true || s.enabled === false);
}
exports.number = number;
exports.settingsValid = settings;
function counter(v) { return between(v, 1, 9007199254740991) && Math.floor(v) === v; }
// Persistent session counter is independent of wall time, including an old v1 boot_ms.
exports.nextSession = function (storage) {
    var previous = storage.session_id;
    if (previous === undefined) previous = 0;
    if (previous !== 0 && !counter(previous)) throw new Error('Invalid 504 session counter');
    if (previous >= 9007199254740991) throw new Error('504 session counter exhausted');
    storage.session_id = previous + 1;
    return previous + 1;
};
exports.combo = function (memory, air, floor, s) {
    var result = { demand: false, valid: false, mode: 'BLOCKED', reason: 'SETTINGS_INVALID', floorTarget: null };
    if (!settings(s)) { memory.airHeat = false; memory.floorHeat = false; return result; }
    if (!s.enabled) {
        memory.airHeat = false; memory.floorHeat = false;
        result.valid = true; result.mode = 'OFF'; result.reason = 'OFF'; return result;
    }
    if (!between(floor, -20, 70)) {
        memory.floorHeat = false; memory.airHeat = false;
        result.reason = between(air, -20, 60) ? 'FLOOR_SENSOR_INVALID' : 'BOTH_SENSORS_INVALID';
        return result;
    }
    if (!between(air, -20, 60)) {
        memory.airHeat = false;
        result.mode = 'DEGRADED'; result.reason = 'AIR_SENSOR_INVALID_HOLD';
        result.floorTarget = s.hold;
    } else {
        if (air <= s.target - 0.3) memory.airHeat = true;
        if (air >= s.target + 0.3) memory.airHeat = false;
        result.mode = memory.airHeat ? 'HEAT' : 'HOLD';
        result.floorTarget = memory.airHeat ? s.heat : s.hold;
        result.reason = result.mode;
    }
    if (floor <= result.floorTarget - 1) memory.floorHeat = true;
    if (floor >= result.floorTarget) memory.floorHeat = false;
    result.valid = true; result.demand = memory.floorHeat === true;
    if (!result.demand && result.mode !== 'DEGRADED') result.reason = 'NO_DEMAND';
    return result;
};

// Only fresh non-retained sensor publications advance freshness. Errors invalidate
// immediately; clearing an error requires a subsequent fresh measurement.
exports.sensor = function () {
    var value = null, at = null, error = '', runtime = 'UNVERIFIED', lastNow = null;
    function clock(now) {
        if (lastNow !== null && now < lastNow) { value = null; at = null; }
        lastNow = now;
    }
    return {
        sample: function (v, retained, now) {
            clock(now);
            if (typeof retained !== 'boolean') { runtime = 'RUNTIME_UNSUPPORTED'; value = null; at = null; }
            if (runtime === 'RUNTIME_UNSUPPORTED') return;
            runtime = 'SUPPORTED';
            if (retained !== false) return;
            value = number(v); at = now;
        },
        error: function (v) {
            error = String(v || '');
            value = null; at = null;
        },
        runtimeStatus: function () { return runtime; },
        read: function (now, min, max) {
            clock(now);
            if (at !== null && now - at >= exports.SENSOR_TTL_MS) { value = null; at = null; }
            return runtime !== 'RUNTIME_UNSUPPORTED' && !error && at !== null && now >= at &&
                between(value, min, max) ? value : null;
        }
    };
};

var FIELDS = ['v', 'source', 'session_id', 'seq', 'sent_ms', 'ttl_ms', 'air', 'floor',
    'target', 'hold', 'heat', 'enabled', 'valid', 'demand', 'mode', 'reason'];
function frameValid(f) {
    if (!f || typeof f !== 'object' || Array.isArray(f)) return false;
    var keys = Object.keys(f);
    if (keys.length !== FIELDS.length || keys.some(function (k) { return FIELDS.indexOf(k) < 0; })) return false;
    if (f.v !== exports.VERSION || f.source !== exports.SOURCE || f.ttl_ms !== exports.TTL_MS ||
        !counter(f.session_id) || !counter(f.seq) || !counter(f.sent_ms) ||
        typeof f.valid !== 'boolean' || typeof f.demand !== 'boolean' ||
        (f.air !== null && !between(f.air, -20, 60)) ||
        (f.floor !== null && !between(f.floor, -20, 70))) return false;
    // Invalid settings have exactly one canonical representation: no plausible defaults.
    if (f.reason === 'SETTINGS_INVALID') return f.valid === false && f.demand === false &&
        f.mode === 'BLOCKED' && f.target === null && f.hold === null && f.heat === null && f.enabled === null;
    if (!settings(f)) return false;
    if (f.reason === 'RUNTIME_UNSUPPORTED') return f.valid === false && f.demand === false && f.mode === 'BLOCKED';
    if (['BLOCKED', 'OFF', 'DEGRADED', 'HEAT', 'HOLD'].indexOf(f.mode) < 0 ||
        ['SETTINGS_INVALID', 'OFF', 'FLOOR_SENSOR_INVALID', 'BOTH_SENSORS_INVALID',
            'AIR_SENSOR_INVALID_HOLD', 'HEAT', 'HOLD', 'NO_DEMAND'].indexOf(f.reason) < 0) return false;
    if (f.demand && (!f.valid || !f.enabled || f.floor === null)) return false;
    if (f.valid && f.enabled && f.floor === null) return false;
    if (!f.enabled && (f.demand || f.mode !== 'OFF')) return false;
    if (f.enabled && f.valid && f.air === null && f.mode !== 'DEGRADED') return false;
    if (f.mode === 'BLOCKED' && f.valid) return false;
    if (f.mode === 'OFF' && f.enabled) return false;
    return true;
}
exports.frameValid = frameValid;
exports.receiver = function (started) {
    var session = 0, seq = 0, sent = 0, received = null, first = null, firstSent = null;
    var ready = false, frame = null, reason = 'STARTUP_VALIDATION';
    var lastNow = started, barrier = started, runtime = 'UNVERIFIED';
    function invalidate(why) {
        received = null; first = null; firstSent = null; ready = false; frame = null; reason = why;
    }
    function clock(now) {
        if (now < lastNow) {
            invalidate('CLOCK_REVALIDATION'); barrier = now;
        }
        lastNow = now;
    }
    function fresh(now) {
        return received !== null && now >= received && now - received < exports.TTL_MS &&
            sent - now <= exports.CLOCK_SKEW_MS && now - sent < exports.TTL_MS;
    }
    return {
        accept: function (payload, retained, now) {
            var f;
            clock(now);
            if (typeof retained !== 'boolean') { runtime = 'RUNTIME_UNSUPPORTED'; invalidate('RUNTIME_UNSUPPORTED'); }
            if (runtime === 'RUNTIME_UNSUPPORTED') return 'RUNTIME_UNSUPPORTED';
            runtime = 'SUPPORTED';
            if (retained !== false) return 'RETAINED_REJECTED';
            if (typeof payload !== 'string' || payload.length > 2048) return 'INVALID_FRAME';
            try { f = JSON.parse(payload); } catch (e) { return 'INVALID_JSON'; }
            if (!frameValid(f)) return 'INVALID_FRAME';
            // Check sequence before clocks so a replay cannot trigger recovery or renew TTL.
            if (f.session_id < session || (f.session_id === session && f.seq <= seq)) return 'DUPLICATE_OR_OLD';
            if (f.sent_ms < barrier - exports.CLOCK_SKEW_MS || f.sent_ms - now > exports.CLOCK_SKEW_MS ||
                now - f.sent_ms >= exports.TTL_MS) return 'STALE_OR_CLOCK';
            if (f.session_id !== session || !fresh(now) || f.sent_ms <= sent) {
                ready = false; first = now; firstSent = f.sent_ms;
            }
            session = f.session_id; seq = f.seq; sent = f.sent_ms; received = now; frame = f;
            // Two distinct publications separated in receiver time: queued bursts cannot arm.
            // Also require sender progress: replayed near-start frames cannot arm after reboot.
            if (now - first >= exports.REVALIDATION_MS &&
                sent - firstSent >= exports.REVALIDATION_MS - 2 * exports.CLOCK_SKEW_MS &&
                sent >= first + exports.REVALIDATION_MS - exports.CLOCK_SKEW_MS) ready = true;
            reason = ready ? (f.valid ? 'NORMAL' : f.reason) : 'STARTUP_VALIDATION';
            return reason;
        },
        read: function (now) {
            clock(now);
            if (received !== null && !fresh(now)) invalidate('MQTT_STALE');
            var ok = fresh(now) && ready;
            return { fresh: ok, frame: ok ? frame : null,
                reason: runtime === 'RUNTIME_UNSUPPORTED' ? runtime : reason,
                runtime: runtime,
                age_s: received === null ? -1 : (now - received) / 1000 };
        }
    };
};

// Adapter reserved for explicitly reviewed 504 tuning. No default copied from 501/502.
// Callbacks accept calculated commands in memory only, including safe-close commands.
exports.shadowMixer = function (MixingController, tuning) {
    if (!tuning) return null;
    Object.keys(tuning).forEach(function (key) {
        if (tuning[key] === null || tuning[key] === undefined) throw new Error('Unconfirmed tuning: ' + key);
    });
    return MixingController.create({ initialValvePositionPct: 0, tuning: tuning }, {
        writeValvePosition: function () { return true; },
        writeValveEnable: function () { return true; }
    });
};
