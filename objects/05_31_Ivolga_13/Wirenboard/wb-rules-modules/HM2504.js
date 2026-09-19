/* Иволга 504: комбо-логика и транспорт. ES5, без физических writes.
 * Уставки интерфейса не являются температурными пределами теплоносителя.
 */
exports.TOPIC = '/neiro/ivolga/504/v1/frame';
exports.SOURCE = 'ivolga-besedka-504';
exports.TTL_MS = 30000;
exports.SENSOR_TTL_MS = 120000;
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
    var value = null, at = null, error = '';
    return {
        sample: function (v, retained, now) {
            if (retained !== false) return;
            value = number(v); at = now;
        },
        error: function (v) {
            error = String(v || '');
            value = null; at = null;
        },
        read: function (now, min, max) {
            return !error && at !== null && now >= at && now - at < exports.SENSOR_TTL_MS &&
                between(value, min, max) ? value : null;
        }
    };
};

var FIELDS = ['v', 'source', 'boot_ms', 'seq', 'sent_ms', 'ttl_ms', 'air', 'floor',
    'target', 'hold', 'heat', 'enabled', 'valid', 'demand', 'mode', 'reason'];
function frameValid(f) {
    if (!f || typeof f !== 'object' || Array.isArray(f)) return false;
    var keys = Object.keys(f);
    if (keys.length !== FIELDS.length || keys.some(function (k) { return FIELDS.indexOf(k) < 0; })) return false;
    if (f.v !== 1 || f.source !== exports.SOURCE || f.ttl_ms !== exports.TTL_MS ||
        !between(f.boot_ms, 1, 9007199254740991) || Math.floor(f.boot_ms) !== f.boot_ms ||
        !between(f.seq, 1, 9007199254740991) || Math.floor(f.seq) !== f.seq ||
        !between(f.sent_ms, f.boot_ms, 9007199254740991) || !settings(f) ||
        typeof f.valid !== 'boolean' || typeof f.demand !== 'boolean' ||
        (f.air !== null && !between(f.air, -20, 60)) ||
        (f.floor !== null && !between(f.floor, -20, 70))) return false;
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
    var boot = 0, seq = 0, sent = 0, received = null, first = null, ready = false, frame = null;
    var reason = 'STARTUP_VALIDATION';
    function fresh(now) {
        return received !== null && now >= received && now - received < exports.TTL_MS &&
            now >= sent && now - sent < exports.TTL_MS;
    }
    return {
        accept: function (payload, retained, now) {
            var f;
            if (retained !== false) return 'RETAINED_REJECTED';
            if (typeof payload !== 'string' || payload.length > 2048) return 'INVALID_FRAME';
            try { f = JSON.parse(payload); } catch (e) { return 'INVALID_JSON'; }
            if (!frameValid(f)) return 'INVALID_FRAME';
            if (f.sent_ms < started || f.sent_ms > now || now - f.sent_ms >= exports.TTL_MS) return 'STALE_OR_CLOCK';
            if (f.boot_ms < boot || (f.boot_ms === boot && (f.seq <= seq || f.sent_ms <= sent))) return 'DUPLICATE_OR_OLD';
            if (f.boot_ms !== boot || !fresh(now)) { ready = false; first = now; }
            boot = f.boot_ms; seq = f.seq; sent = f.sent_ms; received = now; frame = f;
            // Two distinct publications separated in receiver time: queued bursts cannot arm.
            if (now - first >= 5000) ready = true;
            reason = ready ? (f.valid ? 'NORMAL' : 'REMOTE_INVALID') : 'STARTUP_VALIDATION';
            return reason;
        },
        read: function (now) {
            var ok = fresh(now) && ready;
            return { fresh: ok, frame: ok ? frame : null,
                reason: fresh(now) ? reason : 'MQTT_STALE',
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
