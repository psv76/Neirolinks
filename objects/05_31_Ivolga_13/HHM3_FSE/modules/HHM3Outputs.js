/* HHM3 / Иволга A05 WB-MAO4. Новый Level может включить Switch сам.
 * Открытие: новый Level, при необходимости Switch ON, свежее подтверждение.
 * Закрытие: только Switch OFF, сохранённый Level не меняется.
 * Readback не доказывает ход штока или расход. Выбег ограничивает контур.
 */
exports.create = function (c, io) {
    if (!(c.periodMs > 0 && c.valveActiveMinLevel > 0 &&
          c.valveActiveMinLevel < c.valveActiveMaxLevel &&
          c.valveActiveMaxLevel <= 100 && c.valveOffCommand === false)) {
        throw new Error('Invalid A05 output contract');
    }
    var state = 'INITIAL', level = null, lastEnableAt = null, lastNow = null;
    var fault = '', pumpCommand = false;
    var offBase=0,offAt=null,offTryAt=null,offTries=0,offConfirmed=false;
    var levelBase=0,enableBase=0,openingAt=null;
    var timeout=c.commandTimeoutMs||10000,retry=c.commandRetryMs||5000;
    function sequence(path){return io.readback(path).seq;}
    function fresh(path,value,base){
        var b=io.readback(path);
        return b.value===value&&typeof b.seq==='number'&&b.seq>base;
    }
    function closed(){return fresh(c.enable,0,offBase);}
    function report(ready) {
        return {state:state, ready:ready, pump:pumpCommand, fault:fault,
            saved_level:io.read(c.level), requested_level:level,
            requested_enable:level !== null, closed_command:level === null,
            closed_readback_match:closed(),
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
        var stopped=keepPump?true:pump(false);
        offBase=sequence(c.enable);offAt=lastNow;offTryAt=lastNow;offTries=1;offConfirmed=false;
        var off=io.write(c.enable,false,true);
        level=null;lastEnableAt=null;openingAt=null;
        if (!off.ok) {
            pump(false);
            state='OFF_WRITE_ERROR';fault='OFF_WRITE_ERROR';return report(false);
        }
        if (!stopped) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
        }
        state='OFF_COMMANDED';fault=reason||'';
        if (keepPump && !pump(true)) {
            state='PUMP_WRITE_ERROR';fault='PUMP_WRITE_ERROR';return report(false);
        }
        offConfirmed=closed();
        return report(keepPump&&offConfirmed);
    }
    function abort(reason) {
        var stopped=pump(false);
        offBase=sequence(c.enable);offAt=lastNow;offTryAt=lastNow;offTries=1;offConfirmed=false;
        var off=io.write(c.enable,false,true);
        level=null;lastEnableAt=null;openingAt=null;
        if (!off.ok) {
            state='OFF_WRITE_ERROR';fault=reason+'; OFF_WRITE_ERROR';
        } else {
            state=stopped?reason:'PUMP_WRITE_ERROR';
            fault=stopped?reason:reason+'; PUMP_WRITE_ERROR';
        }
        return report(false);
    }
    function holdClosed(keepPump,now){
        if(closed()){
            offConfirmed=true;fault='';state='OFF_COMMANDED';
            if(!pump(keepPump))return abort('PUMP_WRITE_ERROR');
            return report(keepPump);
        }
        if(offConfirmed){
            // Свежий ON или потеря достоверного OFF начинает один конечный повтор.
            offConfirmed=false;offAt=now;offTries=0;offTryAt=null;
        }
        if(offAt===null)offAt=now;
        if(now-offAt>=timeout){
            pump(false);state='CLOSURE_UNCERTAIN';fault='CLOSURE_UNCERTAIN';return report(false);
        }
        if(offTries<2&&(offTryAt===null||now-offTryAt>=retry)){
            offBase=sequence(c.enable);offTryAt=now;offTries++;
            if(!io.write(c.enable,false,true).ok){pump(false);state='OFF_WRITE_ERROR';fault='OFF_WRITE_ERROR';return report(false);}
        }
        if(!pump(keepPump&&fault===''))return abort('PUMP_WRITE_ERROR');
        return report(keepPump&&closed()&&fault==='');
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
        // До подтверждения предыдущего OFF положительный Level запрещён.
        if(level===null&&offAt!==null&&!closed())return holdClosed(r.pump===true&&!want,now);
        if (!want) {
            if (state!=='OFF_COMMANDED'||level!==null)return close(r.pump===true,'');
            return holdClosed(r.pump===true,now);
        }
        if (state==='OFF_WRITE_ERROR'||state==='PUMP_WRITE_ERROR'||
            state==='ENABLE_WRITE_ERROR'||state==='CLOSURE_UNCERTAIN')return close(false,'');
        var openingReady=level!==null&&fresh(c.level,level,levelBase)&&fresh(c.enable,1,enableBase);
        if(openingAt!==null&&!openingReady&&now-openingAt>=timeout)return abort('ENABLE_UNCERTAIN');
        // Во время ожидания не сдвигаем срок новым расчётом цели каждый цикл.
        if(openingAt!==null&&!openingReady)target=level;
        var needLevel=level!==target||state==='LEVEL_WRITE_ERROR';
        if (needLevel) {
            if (level===null&&pumpCommand!==true&&!pump(false))return abort('PUMP_WRITE_ERROR');
            levelBase=sequence(c.level);enableBase=sequence(c.enable);openingAt=now;
            if (!io.write(c.level,target,true).ok)return abort('LEVEL_WRITE_ERROR');
            level=target;
        }
        // Если Level уже дал свежий AUTO-ON, лишняя команда Switch не нужна.
        var needEnable=(needLevel&&!fresh(c.enable,1,enableBase))||(io.matches(c.enable,false)&&
            (lastEnableAt===null||now-lastEnableAt>=30000));
        if (needEnable) {
            if (!io.write(c.enable,true,true).ok)return abort('ENABLE_WRITE_ERROR');
            lastEnableAt=now;
        }
        if(!fresh(c.level,level,levelBase)||!fresh(c.enable,1,enableBase)){
            if(openingAt===null)openingAt=now;
            state='WAIT_OUTPUT_READBACK';fault='';return report(false);
        }
        openingAt=null;
        if (!pump(true))return abort('PUMP_WRITE_ERROR');
        state='HEAT_COMMANDED';fault='';
        return report(true);
    };
};
