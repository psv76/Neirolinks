/*
 * Heating Manager 2.0 — reusable mixing-circuit controller.
 *
 * Algorithm: step-hold with FAST / TRIM phases, trend-aware step sizing,
 * deadband, post-move settling, reversal lock, source-temperature guard,
 * startup opening cap and hard supply-temperature limit.
 *
 * This module contains no object-specific MQTT paths, room names or setpoints.
 * The caller owns demand logic, pump ownership, HM2 contracts and logging.
 *
 * ES5 / wb-rules module. Intended location on controller:
 * /etc/wb-rules-modules/MixingController.js
 */

exports.VERSION = "1.0.0";

function clamp(x, a, b) {
    x = Number(x);
    if (isNaN(x)) x = a;
    if (x < a) return a;
    if (x > b) return b;
    return x;
}

function numberOrNull(v) {
    if (v === null || v === undefined || v === "") return null;
    v = Number(v);
    return isNaN(v) ? null : v;
}

function finiteNumber(v, name) {
    v = Number(v);
    if (isNaN(v) || !isFinite(v)) {
        throw new Error("MixingController: invalid numeric config " + name);
    }
    return v;
}

function boolValue(v, name) {
    if (v === true || v === false) return v;
    throw new Error("MixingController: invalid boolean config " + name);
}

function requireFunction(obj, name) {
    if (!obj || typeof obj[name] !== "function") {
        throw new Error("MixingController: io." + name + " function is required");
    }
}

function validateTuning(t) {
    var numeric = [
        "bandC",
        "biasC",
        "farErrorC",
        "fastHoldColdS",
        "fastHoldHotS",
        "fastMinStepPct",
        "fastMaxStepPct",
        "trimHoldColdS",
        "trimHoldHotS",
        "trimMinStepPct",
        "trimMaxStepPct",
        "pctPerCCold",
        "pctPerCHot",
        "reverseLockS",
        "trendOkCPerMin",
        "trendSlowCPerMin",
        "stagnationS",
        "postMoveSettleS",
        "minPosPct",
        "maxPosPct",
        "hardMaxC",
        "supplyValidMinC",
        "supplyValidMaxC",
        "sensorBadLimit",
        "sourceMarginC",
        "sourceValidMinC",
        "sourceValidMaxC",
        "startupDurationS",
        "startupMaxPosPct",
        "enableRetryS"
    ];
    var i;

    if (!t) throw new Error("MixingController: tuning is required");

    for (i = 0; i < numeric.length; i++) {
        finiteNumber(t[numeric[i]], "tuning." + numeric[i]);
    }

    boolValue(t.sourceGuardEnabled, "tuning.sourceGuardEnabled");
    boolValue(t.startupCapEnabled, "tuning.startupCapEnabled");
    boolValue(t.safeCloseOnDisable, "tuning.safeCloseOnDisable");

    if (t.bandC < 0) throw new Error("MixingController: bandC must be >= 0");
    if (t.farErrorC < 0) throw new Error("MixingController: farErrorC must be >= 0");
    if (t.fastMinStepPct < 0 || t.fastMaxStepPct < t.fastMinStepPct) {
        throw new Error("MixingController: invalid FAST step limits");
    }
    if (t.trimMinStepPct < 0 || t.trimMaxStepPct < t.trimMinStepPct) {
        throw new Error("MixingController: invalid TRIM step limits");
    }
    if (t.minPosPct < 0 || t.maxPosPct > 100 || t.maxPosPct < t.minPosPct) {
        throw new Error("MixingController: invalid valve position limits");
    }
    if (t.supplyValidMaxC < t.supplyValidMinC) {
        throw new Error("MixingController: invalid supply validity range");
    }
    if (t.sourceValidMaxC < t.sourceValidMinC) {
        throw new Error("MixingController: invalid source validity range");
    }
    if (t.sensorBadLimit < 1) {
        throw new Error("MixingController: sensorBadLimit must be >= 1");
    }
}

function create(config, io) {
    var tuning;
    var state;

    config = config || {};
    tuning = config.tuning;

    validateTuning(tuning);
    requireFunction(io, "writeValvePosition");
    requireFunction(io, "writeValveEnable");

    state = {
        posCmd: clamp(config.initialValvePositionPct || 0, 0, 100),
        lastAcceptedPos: clamp(config.initialValvePositionPct || 0, 0, 100),
        lastMoveTs: 0,
        lastDir: "",
        lastT: null,
        lastTs: 0,
        lastNonBandTs: 0,
        lastTWhenNonBand: null,
        pumpWasOn: false,
        pumpOnTs: 0,
        filterBuf: [],
        badSupplyCount: 0,
        lastGoodSupply: null,
        lastValveEnableWriteTs: 0,
        alarmActive: false,
        alarmText: "",
        sourceGuardActive: false,
        startupRemainingS: 0,
        phase: "STOPPED",
        trendCPerMin: 0,
        effectiveTargetC: null,
        status: "init"
    };

    function resetMotionMemory() {
        state.lastMoveTs = 0;
        state.lastDir = "";
        state.lastNonBandTs = 0;
        state.lastTWhenNonBand = null;
    }

    function setAlarm(active, text) {
        state.alarmActive = !!active;
        state.alarmText = active ? String(text || "mixing controller alarm") : "";
    }

    function writeRawPosition(pct) {
        var p = clamp(pct, 0, 100);
        var accepted = io.writeValvePosition(p) === true;

        if (accepted) {
            state.lastAcceptedPos = p;
            state.posCmd = p;
        } else {
            state.posCmd = state.lastAcceptedPos;
        }

        return accepted;
    }

    function writePosition(pct, maxPos) {
        var p = clamp(pct, tuning.minPosPct, maxPos);
        return writeRawPosition(p);
    }

    function closeSafe(reason) {
        writeRawPosition(0);
        resetMotionMemory();
        state.phase = "STOPPED";
        if (reason) state.status = reason;
    }

    function filterSupply(v) {
        var i;
        var sum = 0;

        state.filterBuf.push(v);
        if (state.filterBuf.length > 3) state.filterBuf.shift();

        for (i = 0; i < state.filterBuf.length; i++) sum += state.filterBuf[i];
        return sum / state.filterBuf.length;
    }

    function correctedSupply(raw, offset) {
        var reason = "";
        var corr;
        var filtered;
        var badLimit = Math.round(tuning.sensorBadLimit);

        raw = numberOrNull(raw);
        offset = numberOrNull(offset);
        if (offset === null) offset = 0;

        if (raw === null) {
            reason = "NO_SUPPLY_SENSOR_DATA";
        } else if (raw < tuning.supplyValidMinC || raw > tuning.supplyValidMaxC) {
            reason = "SUPPLY_SENSOR_OUT_OF_RANGE";
        }

        if (!reason) {
            corr = raw + offset;
            if (corr < tuning.supplyValidMinC || corr > tuning.supplyValidMaxC) {
                reason = "CORRECTED_SUPPLY_OUT_OF_RANGE";
            }
        }

        if (reason) {
            state.badSupplyCount += 1;
            if (state.badSupplyCount >= badLimit) {
                setAlarm(true, reason);
                return null;
            }
            return state.lastGoodSupply;
        }

        filtered = filterSupply(corr);
        state.badSupplyCount = 0;
        state.lastGoodSupply = filtered;
        return filtered;
    }

    function effectiveMaxPosition(now) {
        var maxPos = tuning.maxPosPct;
        var elapsed;

        state.startupRemainingS = 0;

        if (tuning.startupCapEnabled && state.pumpOnTs > 0 && tuning.startupDurationS > 0) {
            elapsed = now - state.pumpOnTs;
            if (elapsed < tuning.startupDurationS) {
                state.startupRemainingS = Math.max(0, Math.round(tuning.startupDurationS - elapsed));
                if (tuning.startupMaxPosPct < maxPos) maxPos = tuning.startupMaxPosPct;
            }
        }

        if (maxPos < tuning.minPosPct) maxPos = tuning.minPosPct;
        return maxPos;
    }

    function sourceBlocksOpening(sourceTemp, target) {
        var source = numberOrNull(sourceTemp);
        var required;

        state.sourceGuardActive = false;

        if (!tuning.sourceGuardEnabled) return false;

        if (source === null || source < tuning.sourceValidMinC || source > tuning.sourceValidMaxC) {
            state.sourceGuardActive = true;
            return true;
        }

        required = target + tuning.sourceMarginC;
        if (source < required) {
            state.sourceGuardActive = true;
            return true;
        }

        return false;
    }

    function choosePhase(absErr, phaseMode) {
        if (phaseMode === "fast") return "FAST";
        if (phaseMode === "trim") return "TRIM";
        return absErr >= tuning.farErrorC ? "FAST" : "TRIM";
    }

    function holdSeconds(phase, lastDir) {
        if (phase === "FAST") {
            if (lastDir === "hotter") return tuning.fastHoldHotS;
            if (lastDir === "colder") return tuning.fastHoldColdS;
            return Math.max(tuning.fastHoldColdS, tuning.fastHoldHotS);
        }

        if (lastDir === "hotter") return tuning.trimHoldHotS;
        if (lastDir === "colder") return tuning.trimHoldColdS;
        return Math.max(tuning.trimHoldColdS, tuning.trimHoldHotS);
    }

    function stepLimits(phase) {
        if (phase === "FAST") {
            return {minStep: tuning.fastMinStepPct, maxStep: tuning.fastMaxStepPct};
        }
        return {minStep: tuning.trimMinStepPct, maxStep: tuning.trimMaxStepPct};
    }

    function ensureValveEnabled(input, now) {
        if (input.valveEnableOn === true) return true;

        if (state.lastValveEnableWriteTs === 0 || now - state.lastValveEnableWriteTs >= tuning.enableRetryS) {
            state.lastValveEnableWriteTs = now;
            return io.writeValveEnable(true) === true;
        }

        return false;
    }

    function snapshot() {
        return {
            valvePositionPct: state.posCmd,
            lastAcceptedValvePositionPct: state.lastAcceptedPos,
            phase: state.phase,
            trendCPerMin: state.trendCPerMin,
            effectiveTargetC: state.effectiveTargetC,
            sourceGuardActive: state.sourceGuardActive,
            startupRemainingS: state.startupRemainingS,
            sensorFault: state.badSupplyCount > 0,
            badSensorCount: state.badSupplyCount,
            alarmActive: state.alarmActive,
            alarmText: state.alarmText,
            status: state.status
        };
    }

    function step(input) {
        var now;
        var supply;
        var target;
        var maxPos;
        var err;
        var absErr;
        var trend = 0;
        var dt;
        var phase;
        var sinceMove;
        var holdS;
        var dir;
        var movingRight;
        var movingWrong;
        var absTrend;
        var k;
        var limits;
        var baseStep;
        var stepPct;
        var newCmd;

        input = input || {};
        now = finiteNumber(input.now, "input.now");

        if (input.pumpOn === true && !state.pumpWasOn) {
            state.pumpOnTs = now;
            state.filterBuf = [];
            state.lastT = null;
            state.lastTs = 0;
        } else if (input.pumpOn !== true && state.pumpWasOn) {
            state.pumpOnTs = 0;
            state.filterBuf = [];
            state.lastT = null;
            state.lastTs = 0;
            closeSafe("PUMP_OFF_SAFE_CLOSE");
        }
        state.pumpWasOn = input.pumpOn === true;

        if (input.enabled !== true) {
            state.sourceGuardActive = false;
            state.startupRemainingS = 0;
            if (tuning.safeCloseOnDisable) closeSafe("DISABLED_SAFE_CLOSE");
            else state.status = "DISABLED_HOLD";
            return snapshot();
        }

        if (input.pumpOn !== true) {
            state.sourceGuardActive = false;
            state.startupRemainingS = 0;
            closeSafe("PUMP_OFF_SAFE_CLOSE");
            return snapshot();
        }

        supply = correctedSupply(input.supplyTempC, input.sensorOffsetC);
        if (supply === null) {
            state.sourceGuardActive = false;
            if (state.alarmActive) closeSafe("SUPPLY_SENSOR_FAILSAFE_CLOSE");
            else state.status = "SUPPLY_SENSOR_TRANSIENT_HOLD";
            return snapshot();
        }

        if (state.badSupplyCount > 0) {
            state.status = "SUPPLY_SENSOR_TRANSIENT_HOLD";
            return snapshot();
        }

        if (input.freeze === true) {
            state.posCmd = clamp(input.manualValvePct, 0, 100);
            writeRawPosition(state.posCmd);
            state.phase = "MANUAL";
            state.status = "MANUAL_HOLD";
            return snapshot();
        }

        ensureValveEnabled(input, now);

        if (supply >= tuning.hardMaxC) {
            setAlarm(true, "SUPPLY_HARD_MAX");
            closeSafe("SUPPLY_HARD_MAX_SAFE_CLOSE");
            return snapshot();
        }

        setAlarm(false, "");

        target = numberOrNull(input.targetC);
        if (target === null) {
            closeSafe("TARGET_NOT_READY_SAFE_CLOSE");
            return snapshot();
        }
        state.effectiveTargetC = supply < target ? target + tuning.biasC : target;
        state.sourceGuardActive = false;

        if (state.lastT !== null && state.lastTs !== 0) {
            dt = now - state.lastTs;
            if (dt > 0) trend = (supply - state.lastT) * 60.0 / dt;
        }
        state.trendCPerMin = Math.round(trend * 100) / 100;
        state.lastT = supply;
        state.lastTs = now;

        maxPos = effectiveMaxPosition(now);
        if (state.posCmd > maxPos) {
            writePosition(maxPos, maxPos);
            state.status = "STARTUP_OR_MAX_POSITION_CAP";
            return snapshot();
        }

        target = state.effectiveTargetC;
        err = target - supply;
        absErr = Math.abs(err);

        if (absErr <= tuning.bandC) {
            state.phase = "TRIM";
            state.lastNonBandTs = 0;
            state.lastTWhenNonBand = null;
            state.status = "DEADBAND_HOLD";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        if (!state.lastNonBandTs) {
            state.lastNonBandTs = now;
            state.lastTWhenNonBand = supply;
        }

        phase = choosePhase(absErr, input.phaseMode || "auto");
        if (phase === "FAST" && absErr < 1.8) phase = "TRIM";
        state.phase = phase;

        sinceMove = state.lastMoveTs ? now - state.lastMoveTs : 999999;
        if (sinceMove < tuning.postMoveSettleS) {
            state.status = "POST_MOVE_SETTLE";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        holdS = holdSeconds(phase, state.lastDir);
        if (state.lastMoveTs && now - state.lastMoveTs < holdS) {
            state.status = "STEP_HOLD_WAIT";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        dir = err > 0 ? "hotter" : "colder";

        if (dir === "hotter" && sourceBlocksOpening(input.sourceTempC, target)) {
            state.status = "SOURCE_GUARD_HOLD";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        if (state.lastDir && dir !== state.lastDir && now - state.lastMoveTs < tuning.reverseLockS) {
            state.status = "REVERSE_LOCK_HOLD";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        movingRight = (err > 0 && trend > 0) || (err < 0 && trend < 0);
        movingWrong = (err > 0 && trend < 0) || (err < 0 && trend > 0);
        absTrend = Math.abs(trend);

        if (movingRight && absTrend >= tuning.trendOkCPerMin) {
            state.status = "TREND_OK_HOLD";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        k = dir === "hotter" ? tuning.pctPerCCold : tuning.pctPerCHot;
        limits = stepLimits(phase);
        baseStep = absErr * k;

        if (movingRight && absTrend > tuning.trendSlowCPerMin && absTrend < tuning.trendOkCPerMin) {
            baseStep *= 0.45;
        }
        if (movingWrong && absTrend > tuning.trendSlowCPerMin) {
            baseStep *= 1.15;
        }
        if (absErr < 1.5) baseStep *= 0.7;

        if (tuning.stagnationS > 0 && state.lastNonBandTs && now - state.lastNonBandTs >= tuning.stagnationS && state.lastTWhenNonBand !== null) {
            if (Math.abs(supply - state.lastTWhenNonBand) < 0.1) {
                baseStep = Math.max(baseStep, limits.minStep);
            }
            state.lastNonBandTs = now;
            state.lastTWhenNonBand = supply;
        }

        stepPct = clamp(baseStep, limits.minStep, limits.maxStep);
        newCmd = state.posCmd + (dir === "hotter" ? stepPct : -stepPct);
        newCmd = clamp(newCmd, tuning.minPosPct, maxPos);

        if (Math.abs(newCmd - state.posCmd) < 0.001) {
            state.status = "POSITION_LIMIT_HOLD";
            writePosition(state.posCmd, maxPos);
            return snapshot();
        }

        if (writePosition(newCmd, maxPos)) {
            state.lastDir = dir;
            state.lastMoveTs = now;
            state.status = dir === "hotter" ? "STEP_OPEN" : "STEP_CLOSE";
        } else {
            state.status = "OUTPUT_WRITE_REJECTED";
        }

        return snapshot();
    }

    function reset(options) {
        options = options || {};
        resetMotionMemory();
        state.lastT = null;
        state.lastTs = 0;
        state.lastNonBandTs = 0;
        state.lastTWhenNonBand = null;
        state.filterBuf = [];
        state.badSupplyCount = 0;
        state.lastGoodSupply = null;
        state.sourceGuardActive = false;
        state.startupRemainingS = 0;
        state.alarmActive = false;
        state.alarmText = "";
        state.phase = "STOPPED";
        state.status = "RESET";

        if (options.valvePositionPct !== undefined) {
            state.posCmd = clamp(options.valvePositionPct, 0, 100);
            state.lastAcceptedPos = state.posCmd;
        }

        if (options.pumpOn === true) {
            state.pumpWasOn = true;
            state.pumpOnTs = options.now ? Number(options.now) : 0;
        } else {
            state.pumpWasOn = false;
            state.pumpOnTs = 0;
        }

        return snapshot();
    }

    return {
        step: step,
        reset: reset,
        snapshot: snapshot
    };
}

exports.create = create;
