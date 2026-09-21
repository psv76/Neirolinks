/* HHM3 / Ivolga A05 WB-MAO4: ordinary Dimming Level only sets voltage.
 * Opening: Level, explicit Switch ON, then pump ON. Closing: pump OFF,
 * explicit Switch OFF (saved Level stays unchanged). Only HHM3 owns A05.
 * MQTT readback is a reported value, never proof of physical valve travel.
 * On synchronous write error attempt pump OFF / Switch OFF and withhold heat.
 */
exports.create = function (c, io) {
    if (!(c.periodMs > 0 && c.valveActiveMinLevel > 0 &&
          c.valveActiveMinLevel < c.valveActiveMaxLevel &&
          c.valveActiveMaxLevel <= 100 && c.valveOffCommand === false)) {
        throw new Error('Invalid A05 output contract');
    }
    var state = 'INITIAL', level = null, lastEnableAt = null, lastNow = null;
    var fault = '', pumpCommand = false;
    function report(ready) {
        return {state:state, ready:ready, pump:pumpCommand, fault:fault,
            saved_level:io.read(c.level), requested_level:level,
            requested_enable:level !== null, closed_command:level === null,
            closed_readback_match:io.matches(c.enable,false),
            readback:{level:io.readback(c.level), enable:io.readback(c.enable),
                pump:io.readback(c.pump)}};
    }
    function pump(on) {
        var w = io.write(c.pump,on);
        if (!w.ok) {pumpCommand=null;return false;}
        pumpCommand=on;
        return true;
    }
    function close(keepPump,reason) {
        var stopped=pump(false);
        var off=io.write(c.enable,false,true);
        level=null;lastEnableAt=null;
        if (!off.ok) {
            state='OFF_WRITE_ERROR';fault='OFF_WRITE_ERROR';return report(false);
        }
        if (!stopped) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
        }
        state='OFF_COMMANDED';fault=reason||'';
        if (keepPump && !pump(true)) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
        }
        return report(keepPump);
    }
    function abort(reason) {
        var stopped=pump(false);
        var off=io.write(c.enable,false,true);
        level=null;lastEnableAt=null;
        if (!off.ok) {
            state='OFF_WRITE_ERROR';fault=reason+'; OFF_WRITE_ERROR';
        } else {
            state=stopped?reason:'PUMP_WRITE_ERROR';
            fault=stopped?reason:reason+'; PUMP_WRITE_ERROR';
        }
        return report(false);
    }
    return function (r,now) {
        var want=r.pump===true && typeof r.valve==='number' && isFinite(r.valve) &&
            r.valve>0 && r.valve<=100;
        var target=want?Math.max(c.valveActiveMinLevel,
            Math.min(c.valveActiveMaxLevel,Math.round(c.valveActiveMinLevel+
                (c.valveActiveMaxLevel-c.valveActiveMinLevel)*r.valve/100))):null;
        if (state==='INITIAL'||(lastNow!==null&&
            (now<lastNow||now-lastNow>c.periodMs*3))) {
            lastNow=now;
            return close(false,'');
        }
        lastNow=now;
        if (!want) {
            if (state!=='OFF_COMMANDED'||level!==null)return close(r.pump===true,'');
            if (!pump(r.pump===true))return abort('PUMP_WRITE_ERROR');
            fault='';return report(r.pump===true);
        }
        if (state==='OFF_WRITE_ERROR'||state==='PUMP_WRITE_ERROR'||
            state==='ENABLE_WRITE_ERROR')return close(false,'');
        var needLevel=level!==target||state==='LEVEL_WRITE_ERROR';
        if (needLevel) {
            if (level===null&&!pump(false))return abort('PUMP_WRITE_ERROR');
            if (!io.write(c.level,target,true).ok)return abort('LEVEL_WRITE_ERROR');
            level=target;
        }
        // Ordinary Level never guarantees Switch ON. Reassert explicit ON
        // after a new Level or a reported OFF, throttled against stale echo.
        var needEnable=needLevel||(io.matches(c.enable,false)&&
            (lastEnableAt===null||now-lastEnableAt>=30000));
        if (needEnable) {
            if (!io.write(c.enable,true,true).ok)return abort('ENABLE_WRITE_ERROR');
            lastEnableAt=now;
        }
        if (!pump(true))return abort('PUMP_WRITE_ERROR');
        state='HEAT_COMMANDED';fault='';
        return report(true);
    };
};
