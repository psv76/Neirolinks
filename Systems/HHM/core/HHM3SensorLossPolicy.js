/* HHM3 sensor loss policy: local decision helper, no physical IO.
 * Keep regulation progress during transient sensor loss, then require
 * a physically approved nonzero limited-heating fallback.
 * The caller still owns sensor health, hydraulic permits and thermal safety.
 */
function finite(v) { return typeof v === 'number' && isFinite(v); }
function pct(v) { return finite(v) && v >= 0 && v <= 100; }

exports.create = function (cfg) {
    if (!cfg || !finite(cfg.holdMs) || cfg.holdMs <= 0 ||
        !finite(cfg.recoveryStableMs) || cfg.recoveryStableMs <= 0 ||
        !finite(cfg.recoverySamples) || cfg.recoverySamples < 2 ||
        Math.floor(cfg.recoverySamples) !== cfg.recoverySamples ||
        !finite(cfg.limitedValvePct) || cfg.limitedValvePct <= 0 ||
        cfg.limitedValvePct > 100) {
        throw new Error('Sensor loss policy requires reviewed hold/recovery and nonzero fallback');
    }

    var lastNow = null;
    var lastAcceptedPct = null;
    var lostAt = null;
    var recoveryAt = null;
    var recoveryCount = 0;
    var state = 'UNQUALIFIED';

    function reset() {
        lastAcceptedPct = null;
        lostAt = null;
        recoveryAt = null;
        recoveryCount = 0;
        state = 'UNQUALIFIED';
    }

    function output(code, valve, command, heat, detail) {
        state = code;
        return {
            state: code,
            valvePct: valve,
            commandValve: command,
            heatDemand: heat,
            sensorLostSinceMs: lostAt,
            lastAcceptedValvePct: lastAcceptedPct,
            reason: detail || ''
        };
    }

    return {
        reset: function () { reset(); lastNow = null; },
        step: function (i) {
            if (!i || !finite(i.nowMs) || typeof i.sensorValid !== 'boolean' ||
                typeof i.heatRequested !== 'boolean' ||
                typeof i.hydraulicPathReady !== 'boolean' ||
                typeof i.protectionActive !== 'boolean') {
                throw new Error('Sensor loss policy requires explicit current inputs');
            }

            if (lastNow !== null && i.nowMs < lastNow) reset();
            lastNow = i.nowMs;

            // These inputs are evaluated upstream by independently tested guards.
            // Never make a physical ON/OFF decision in this helper.
            if (i.protectionActive) {
                reset();
                return output('PROTECTION_ACTIVE', null, false, null,
                    'Independent physical protection owns this transition');
            }
            if (!i.heatRequested) {
                reset();
                return output('NO_DEMAND', null, false, false, 'Explicit absence of heat demand');
            }
            if (!i.hydraulicPathReady) {
                reset();
                return output('PATH_UNAVAILABLE', null, false, null,
                    'No qualified hydraulic path; upstream policy required');
            }

            // A requested valve level is not an accepted command. Only an
            // explicit upstream acknowledgement may update held progress.
            if (i.acceptedValveConfirmed === true) {
                if (!pct(i.acceptedValvePct))
                    throw new Error('Confirmed valve level is invalid');
                lastAcceptedPct = i.acceptedValvePct;
            }

            if (i.sensorValid) {
                if (lostAt !== null) {
                    if (recoveryAt === null) {
                        recoveryAt = i.nowMs;
                        recoveryCount = 0;
                    }
                    recoveryCount += 1;
                    if (i.nowMs - recoveryAt < cfg.recoveryStableMs ||
                        recoveryCount < cfg.recoverySamples ||
                        i.acceptedValveConfirmed !== true) {
                        return output('RECOVERY_HOLD', lastAcceptedPct, false, true,
                            'Require stable sensor and confirmed valve command before resuming');
                    }
                    lostAt = null;
                    recoveryAt = null;
                    recoveryCount = 0;
                }
                return output('NORMAL', lastAcceptedPct, false, true,
                    'Normal mixer controller owns valve commands');
            }

            // A single healthy read does not restart the loss grace window.
            recoveryAt = null;
            recoveryCount = 0;
            if (lostAt === null) lostAt = i.nowMs;

            if (lastAcceptedPct !== null && i.nowMs - lostAt < cfg.holdMs) {
                return output('HOLD_LAST_ACCEPTED', lastAcceptedPct, false, true,
                    'No new valve command; preserve accepted mixer position');
            }

            // Only the object adapter can authorize limited heating on other
            // physical evidence. Unknown evidence never means "close to zero".
            if (i.fallbackAuthorized === true && i.independentLimitOk === true) {
                // Do not call a calculated fallback level "accepted" until
                // its writer explicitly acknowledges it on a later cycle.
                return output('LIMITED_HEAT', cfg.limitedValvePct, true, true,
                    'Approved nonzero local fallback; supply temperature unknown');
            }

            return output('FALLBACK_NOT_VERIFIED', null, false, null,
                'Object safety contract needed; do not implicitly issue OFF');
        },
        snapshot: function () {
            return { state: state, lastAcceptedValvePct: lastAcceptedPct,
                sensorLostSinceMs: lostAt, recoverySinceMs: recoveryAt };
        }
    };
};
