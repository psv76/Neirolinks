/* Иволга 504: комбо-логика и транспорт. ES5, без физических writes.
 * Уставки интерфейса не являются температурными пределами теплоносителя.
 */
exports.TOPIC = '/neiro/ivolga/504/v2/frame';
exports.VERSION = 2;
exports.SOURCE = 'ivolga-besedka-504';
exports.MIN_WB_RULES_VERSION = '2.42.0';
exports.RUNTIME_ERROR_RU = 'BLOCKED: нет доказуемого MQTT retain flag; штатный wb-rules 2.40.0 несовместим с текущим транспортом. Установка/обновление запрещены, см. ISSUE61.md';
exports.TTL_MS = 30000;
exports.SENSOR_TTL_MS = require('HHM3Config').config.sensorTtlMs;
exports.CLOCK_SKEW_MS = 2000;
exports.REVALIDATION_MS = 5000;
var Config504 = require('HHM3Config').config.circuits['504'];
function number(v) {
    if (typeof v !== 'number' && typeof v !== 'string') return null;
    if (typeof v === 'string' && !v.trim()) return null;
    v = Number(v);
    return isFinite(v) ? v : null;
}
function between(v, min, max) { return typeof v === 'number' && isFinite(v) && v >= min && v <= max; }
function settings(s) {
    return s && between(s.target, 15, 30) && between(s.hold, 18, Config504.floorTargetMaxC) &&
        between(s.heat, 20, Config504.floorTargetMaxC) && s.hold <= s.heat && s.enabled === true;
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

// Network/MSW/ack policy only. Local M1W2 uses localM1w2 below.
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
        error: function (v, retained) {
            // An error is conservative even if retained. Its clearance is not:
            // an old empty meta/error must never clear a newer live fault.
            var next = String(v || '');
            if (typeof retained !== 'boolean') { runtime = 'RUNTIME_UNSUPPORTED'; value = null; at = null; }
            if (next) { error = next; value = null; at = null; }
            else if (retained === false && runtime !== 'RUNTIME_UNSUPPORTED') {
                error = ''; value = null; at = null;
            }
        },
        runtimeStatus: function () { return runtime; },
        timestamp: function () { return at; },
        read: function (now, min, max) {
            clock(now);
            if (at !== null && now - at >= exports.SENSOR_TTL_MS) { value = null; at = null; }
            return runtime !== 'RUNTIME_UNSUPPORTED' && !error && at !== null && now >= at &&
                between(value, min, max) ? value : null;
        }
    };
};

// m1w2-health-v1. readControl returns the actual local value and #error.
// Neither retained values, empty error metadata nor repeated reads qualify startup.
// Both channels need a live value, synchronized with the local model, for admission.
// Admission belongs to this rules instance; current health is checked on EVERY read.
// An ordinary local fault must not erase admission and require numeric republish.
// After qualification validity is state based, not numeric-publication age based.
exports.localM1w2 = function (readControl) {
    var proof = [false, false], seen = [false, false], faults = ['', ''], runtime = 'UNVERIFIED';
    var reported = [null, null], admitted = false, measuredAt = null, lastNow = null, reason = 'STARTUP_VALIDATION';
    var revalidate = [false, false], pendingSample = [false, false], errorObserved = [false, false];
    var retainedClear = [false, false];
    var cause = 'NEW_INSTANCE';
    function clock(now) {
        if (lastNow !== null && now < lastNow) {
            proof = [false, false]; seen = [false, false]; admitted = false; measuredAt = null;
            pendingSample = [false, false]; cause = 'CLOCK_ROLLBACK';
        }
        lastNow = now;
    }
    function metadata(retained) {
        if (typeof retained !== 'boolean') { runtime = 'RUNTIME_UNSUPPORTED'; proof = [false, false]; admitted = false; cause = 'MQTT_METADATA_UNSUPPORTED'; }
        else if (runtime !== 'RUNTIME_UNSUPPORTED') runtime = 'SUPPORTED';
        return runtime !== 'RUNTIME_UNSUPPORTED' && retained === false;
    }
    function ok(v) { return v === true || v === 1 || v === '1'; }
    return {
        sample: function (channel, value, retained, now) {
            clock(now);
            // A late retained delivery must not replace a qualified live reading.
            if (retained === true) {
                proof[channel] = false; seen[channel] = false; revalidate[channel] = true;
                cause = channel === 0 ? 'RETAINED_TEMPERATURE' : 'RETAINED_HEALTH';
            }
            if (!metadata(retained)) return;
            reported[channel] = channel === 0 ? number(value) : ok(value);
            proof[channel] = channel === 0 ? number(value) !== null : ok(value);
            seen[channel] = proof[channel];
            pendingSample[channel] = true;
            // A retained/reconnect barrier is released by read only after a live
            // sample matches the local model, even for an already admitted sensor.
            if (channel === 0) measuredAt = now;
        },
        error: function (channel, value, retained, now) {
            clock(now);
            var live = metadata(retained), error = value === undefined || value === null ? '' : String(value);
            if (error) {
                faults[channel] = error; errorObserved[channel] = false; retainedClear[channel] = false;
                if (!admitted) proof[channel] = false;
                cause = channel === 0 ? 'MQTT_TEMPERATURE_ERROR' : 'MQTT_HEALTH_ERROR';
            } else if (live) { faults[channel] = ''; errorObserved[channel] = false; retainedClear[channel] = false; proof[channel] = seen[channel]; }
            // A retained empty error must not masquerade as local recovery.
            else if (retained === true && faults[channel]) retainedClear[channel] = true;
        },
        runtimeStatus: function () { return runtime; },
        timestamp: function () { return measuredAt; },
        status: function () { return reason; },
        diagnostics: function () {
            return { phase: admitted ? 'RUNTIME' : 'STARTUP', reason: reason, cause: cause,
                proof: proof.slice(), revalidate: revalidate.slice() };
        },
        read: function (now, min, max) {
            clock(now);
            if (runtime === 'RUNTIME_UNSUPPORTED') { reason = runtime; return null; }
            var t, h, value;
            try { t = readControl(0); h = readControl(1); }
            catch (e) { t = null; h = null; }
            if (!t || !h) {
                if (!admitted) {
                    if (!t) { proof[0] = false; seen[0] = false; }
                    if (!h) { proof[1] = false; seen[1] = false; }
                }
                cause = !t ? 'LOCAL_TEMPERATURE_MISSING' : 'LOCAL_HEALTH_MISSING';
                reason = 'CONTROL_MISSING'; return null;
            }
            // A callback may precede the device-model update. Do not clear its
            // fault using the old healthy cache. Once observed locally, current
            // local error clearance is sufficient for an admitted sensor.
            [t, h].forEach(function (control, channel) {
                if (control.error && faults[channel]) errorObserved[channel] = true;
                else if (admitted && !control.error && errorObserved[channel] && !retainedClear[channel]) {
                    faults[channel] = ''; errorObserved[channel] = false;
                }
            });
            value = number(t.value);
            // Observe all simultaneous faults, even if an error takes precedence
            // in the returned reason. Otherwise a bad sample hidden by an error
            // would remain pending after both local conditions recover.
            if (!between(value, min, max)) pendingSample[0] = false;
            if (!ok(h.value)) pendingSample[1] = false;
            if (t.error || h.error || faults[0] || faults[1]) {
                if (!admitted) {
                    if (t.error || faults[0]) proof[0] = false;
                    if (h.error || faults[1]) proof[1] = false;
                }
                cause = t.error || faults[0] ? 'TEMPERATURE_ERROR' : 'HEALTH_ERROR';
                reason = 'CONTROL_ERROR'; return null;
            }
            if (!between(value, min, max)) {
                if (!admitted) proof[0] = false;
                pendingSample[0] = false; cause = 'LOCAL_TEMPERATURE_INVALID'; reason = 'VALUE_INVALID'; return null;
            }
            if (!ok(h.value)) {
                if (!admitted) proof[1] = false;
                pendingSample[1] = false; cause = 'LOCAL_HEALTH_NOT_OK'; reason = 'SENSOR_NOT_OK'; return null;
            }
            if (proof[0] && value === reported[0]) revalidate[0] = false;
            if (proof[1] && ok(h.value) === reported[1]) revalidate[1] = false;
            if (revalidate[0] || revalidate[1]) { reason = 'RETAINED_REVALIDATION'; return null; }
            if (!admitted && (!proof[0] || !proof[1])) { reason = 'STARTUP_VALIDATION'; return null; }
            // Bad live samples block immediately, even before the model catches up.
            // After the bad state was observed locally, normal current-state recovery
            // applies. A good sample also removes the pending bad-sample barrier.
            if ((pendingSample[0] && !between(reported[0], min, max)) ||
                (pendingSample[1] && reported[1] !== true)) {
                cause = 'LIVE_INVALID_SAMPLE'; reason = 'CONTROL_SYNC_WAIT'; return null;
            }
            pendingSample = [false, false];
            // trackMqtt and the device-model subscriber may run in either order.
            // Startup must synchronize before using a cached value.
            // Once admitted, the current local control remains authoritative:
            // a harmless callback/cache skew must not create a false sensor fault.
            if (!admitted && (value !== reported[0] || ok(h.value) !== reported[1])) { reason = 'CONTROL_SYNC_WAIT'; return null; }
            admitted = true; reason = 'VALID'; return value;
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
    if (['BLOCKED', 'DEGRADED', 'HEAT', 'HOLD'].indexOf(f.mode) < 0 ||
        ['FLOOR_SENSOR_INVALID', 'BOTH_SENSORS_INVALID',
            'AIR_SENSOR_INVALID_HOLD', 'HEAT', 'HOLD', 'NO_DEMAND'].indexOf(f.reason) < 0) return false;
    if (f.demand && (!f.valid || !f.enabled || f.floor === null)) return false;
    if (f.valid && f.enabled && f.floor === null) return false;
    if (f.enabled && f.valid && f.air === null && f.mode !== 'DEGRADED') return false;
    if (f.mode === 'BLOCKED' && f.valid) return false;
    return true;
}
exports.frameValid = frameValid;
exports.receiver = function (started, validate) {
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
            if (typeof payload !== 'string' || payload.length > 16384) return 'INVALID_FRAME';
            try { f = JSON.parse(payload); } catch (e) { return 'INVALID_JSON'; }
            if (!(validate || frameValid)(f)) return 'INVALID_FRAME';
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
