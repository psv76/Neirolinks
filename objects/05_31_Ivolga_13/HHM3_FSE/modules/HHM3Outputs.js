/* A05: Switch OFF closes the hot port and preserves Level. A positive Level
 * requests opening (AUTO-ON). No Switch ON and no Level write on closing.
 * MQTT state is diagnostic, not proof of valve travel or a precondition for heat.
 * The temperature policy owns overheat and loss-of-sensor protection.
 */
exports.create = function (c, io) {
    if (!(c.valveActiveMinLevel > 0 && c.valveActiveMinLevel < c.valveActiveMaxLevel &&
          c.valveActiveMaxLevel <= 100 && c.valveOffCommand === false)) {
        throw new Error('Invalid A05 output contract');
    }
    var state = 'INITIAL', level = null, lastLevelAt = null, lastNow = null;
    var fault = '', pumpCommand = false;
    function report(ready) {
        return {state:state, ready:ready, pump:pumpCommand, fault:fault,
            saved_level:io.read(c.level), requested_level:level,
            requested_enable:level !== null, closed_command:level === null,
            // This is only a reported switch state, never hydraulic proof.
            closed_readback_match:io.matches(c.enable,false),
            readback:{level:io.readback(c.level), enable:io.readback(c.enable),
                pump:io.readback(c.pump)}};
    }
    function pump(on) {
        var w = io.write(c.pump,on);
        pumpCommand = on;
        return w.ok;
    }
    function close(keepPump, reason) {
        // No reliance on a fresh MQTT echo for sending OFF.
        pump(false);
        var w = io.write(c.enable,false,true);
        if (!w.ok) {
            state='OFF_WRITE_ERROR';fault='OFF_WRITE_ERROR';
            level=null;return report(false);
        }
        level=null;lastLevelAt=null;
        fault=reason||'';
        state='OFF_COMMANDED';
        if (keepPump && !pump(true)) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
        }
        return report(keepPump);
    }
    return function (r,now) {
        var want = r.pump === true && typeof r.valve === 'number' &&
            isFinite(r.valve) && r.valve > 0 && r.valve <= 100;
        var target = want ? Math.max(c.valveActiveMinLevel,
            Math.min(c.valveActiveMaxLevel,Math.round(c.valveActiveMinLevel +
                (c.valveActiveMaxLevel-c.valveActiveMinLevel)*r.valve/100))) : null;
        // On restart qualify the safe OFF command before any Level command.
        if (state === 'INITIAL' || (lastNow !== null &&
            (now < lastNow || now-lastNow > c.periodMs*3))) {
            lastNow=now;
            return close(false,'');
        }
        lastNow=now;
        if (!want) {
            if (state !== 'OFF_COMMANDED' || level !== null) return close(r.pump === true,'');
            if (!pump(r.pump === true)) {
                fault='PUMP_WRITE_ERROR';state='PUMP_WRITE_ERROR';return report(false);
            }
            fault='';return report(r.pump === true);
        }
        // A failed OFF on startup must never be bypassed by an opening command.
        if (state === 'OFF_WRITE_ERROR') return close(false,'');
        // Reissue a positive Level when the target changes; also recover from a
        // reported OFF without hammering the bus every 5 seconds. A readback
        // echo is not required for the pump or the heat request to proceed.
        var needLevel = level !== target || state === 'LEVEL_WRITE_ERROR' ||
            (io.matches(c.enable,false) &&
                (lastLevelAt === null || now-lastLevelAt >= 30000));
        if (needLevel) {
            if (!pump(false)) {
                state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
            }
            var w = io.write(c.level,target,true);
            if (!w.ok) {
                state='LEVEL_WRITE_ERROR';fault='LEVEL_WRITE_ERROR';
                pump(false);io.write(c.enable,false,true);return report(false);
            }
            level=target;lastLevelAt=now;
        }
        if (!pump(true)) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';
            pump(false);io.write(c.enable,false,true);level=null;return report(false);
        }
        state='HEAT_COMMANDED';fault='';
        return report(true);
    };
};
