/* Иволга 504: локальная политика, общая механика MixingController, без MQTT IO.
 * Хранилище содержит только ввод в эксплуатацию и текущую термозащиту.
 * Отсутствие отклика/OT/411/419 не является разрешением остановить отопление.
 */
function finite(v) { return typeof v === 'number' && isFinite(v); }
function valveConfig(c) {
    return finite(c.valveClosedLevel) && finite(c.valveOpenLevel) &&
        c.valveClosedLevel >= 0 && c.valveClosedLevel <= 100 &&
        c.valveOpenLevel >= 0 && c.valveOpenLevel <= 100 &&
        c.valveClosedLevel !== c.valveOpenLevel && typeof c.valveClosedEnable === 'boolean';
}
exports.create = function (c, storage, Mixing) {
    ['normalSupplyC', 'maxSupplyC', 'autonomousSupplyC', 'supplyCloseC', 'supplyStopC',
        'supplyImmediateStopC', 'floorCloseC', 'floorStopC', 'floorTargetMaxC',
        'supplyHysteresisC', 'floorHysteresisC', 'periodMs', 'closeObserveMs', 'coolStableMs',
        'circulationCheckMs', 'postrunMs', 'responseMs', 'responseRiseC', 'sourceMarginC',
        'floorStepPct', 'floorStepMs', 'requestTtlS'].forEach(function (k) {
        if (!finite(c[k]) || c[k] < 0) throw new Error('504 invalid config: ' + k);
    });
    if (!(c.normalSupplyC <= c.maxSupplyC && c.autonomousSupplyC <= c.maxSupplyC &&
        c.maxSupplyC < c.supplyCloseC && c.supplyCloseC < c.supplyStopC &&
        c.supplyStopC < c.supplyImmediateStopC && c.floorTargetMaxC < c.floorCloseC &&
        c.floorCloseC < c.floorStopC && c.periodMs > 0 && c.requestTtlS > c.periodMs / 1000 &&
        c.requestTtlS <= 15 && c.coolStableMs >= c.periodMs && c.circulationCheckMs >= c.periodMs &&
        c.supplyHysteresisC > 0 && c.floorHysteresisC > 0 && c.floorStepMs >= c.periodMs &&
        c.floorStepPct > 0 && c.floorStepPct <= 100)) throw new Error('504 inconsistent temperature/timing config');
    var mix, mode = '', position = 0, lastNow = null, circulationAt = null;
    var closeAt = null, coolAt = null, coolSupplyAt = null, coolFloorAt = null;
    var closeFloorSession = 0, closeFloorSeq = 0;
    var idleAt = null, floorStepAt = null, responseAt = null, baseline = null;
    function newMixer() {
        var t = {}, k;
        for (k in c.tuning) if (Object.prototype.hasOwnProperty.call(c.tuning, k)) t[k] = c.tuning[k];
        t.hardMaxC = c.supplyCloseC;
        mix = Mixing.create({ initialValvePositionPct: 0, tuning: t }, {
            writeValvePosition: function (pct) { position = pct; return true; },
            writeValveEnable: function () { return true; }
        });
        position = 0;
    }
    newMixer();
    function resetTiming() {
        circulationAt = null; closeAt = null; coolAt = null;
        idleAt = null; floorStepAt = null; responseAt = null; baseline = null;
        newMixer();
    }
    function result(reason, pump, demand, target, valve, warning) {
        return { reason: reason, pump: pump, demand: demand, target: target,
            valve: valve, warning: warning || '', write: storage.inService === true && valveConfig(c),
            valid: demand || reason === 'NO_DEMAND' };
    }
    return {
        commission: function () {
            if (!valveConfig(c)) return false;
            storage.inService = true; return true;
        },
        step: function (i) {
            var now = i.now, f = i.frame, supply = i.supply, floor = f ? f.floor : null;
            if (lastNow !== null && (now < lastNow || now - lastNow > c.periodMs * 3)) resetTiming();
            lastNow = now;
            if (storage.inService !== true) return result('FIRST_COMMISSIONING', false, false, 0, 0);
            if (!valveConfig(c)) return result('VALVE_CONFIG_MISSING', false, false, 0, 0);
            var hotSupply = supply !== null && supply >= c.supplyCloseC;
            var hotFloor = floor !== null && floor >= c.floorCloseC;
            if (hotSupply) storage.supplyProtection = true;
            if (hotFloor) storage.floorProtection = true;
            // First close, then observe continued overheating. 50 C never waits.
            var observed = closeAt !== null && now - closeAt >= c.closeObserveMs;
            if ((supply !== null && supply >= c.supplyImmediateStopC) ||
                (observed && ((supply !== null && supply >= c.supplyStopC && i.supplyAt > closeAt) ||
                (floor !== null && floor >= c.floorStopC && (f.session_id > closeFloorSession ||
                (f.session_id === closeFloorSession && f.seq > closeFloorSeq)))))) storage.thermalStop = true;
            if (storage.supplyProtection || storage.floorProtection || storage.thermalStop) {
                if (closeAt === null) {
                    closeAt = now; closeFloorSession = f ? f.session_id : 0; closeFloorSeq = f ? f.seq : 0;
                }
                var cooled = (!storage.supplyProtection || (supply !== null && supply <= c.supplyCloseC - c.supplyHysteresisC)) &&
                    (!storage.floorProtection || (floor !== null && floor <= c.floorCloseC - c.floorHysteresisC));
                // The triggering sensor must return; unknown is never evidence of cooling.
                if (!cooled) coolAt = null;
                else if (coolAt === null) { coolAt = now; coolSupplyAt = i.supplyAt; coolFloorAt = f ? f.sent_ms : null; }
                var newSamples = (!storage.supplyProtection || i.supplyAt > coolSupplyAt) &&
                    (!storage.floorProtection || (f && f.sent_ms > coolFloorAt));
                if (cooled && newSamples && now - coolAt >= c.coolStableMs) {
                    storage.supplyProtection = false; storage.floorProtection = false; storage.thermalStop = false;
                    resetTiming();
                } else {
                    circulationAt = null; newMixer();
                    return result(storage.thermalStop ? 'OVERHEAT_STOP' : 'OVERHEAT_CLOSE',
                        !storage.thermalStop, false, 0, 0, 'Перегрев: горячий подмес закрыт' +
                        (storage.thermalStop ? ', насос остановлен' : ', насос циркулирует'));
                }
            }
            closeAt = null;
            // No feedback: close hot port, retain recirculation; freeze protection is NOT proven.
            if (supply === null && floor === null) {
                circulationAt = null; newMixer();
                return result('NO_FEEDBACK_UNCOVERED', true, false, 0, 0,
                    'Нет 418 и пола: подмес закрыт, рециркуляция; защита трассы от замерзания не обеспечена');
            }
            var remoteValid = !!(f && f.valid && f.enabled === true);
            var demand = remoteValid ? f.demand : true;
            var target = Math.min(c.maxSupplyC, remoteValid ? c.normalSupplyC : c.autonomousSupplyC);
            var nextMode = supply === null ? 'FLOOR_ONLY' : (remoteValid ? 'NORMAL' : 'AUTONOMOUS');
            var warning = remoteValid ? '' : ('Автономия: ' + (f ? f.reason : i.linkReason));
            if (nextMode !== mode) { newMixer(); floorStepAt = null; mode = nextMode; }
            if (!demand) {
                if (idleAt === null) idleAt = now;
                circulationAt = null; responseAt = null; newMixer();
                return result('NO_DEMAND', now - idleAt < c.postrunMs, false, 0, 0);
            }
            idleAt = null;
            if (circulationAt === null) circulationAt = now;
            if (now - circulationAt < c.circulationCheckMs) {
                newMixer(); return result('CIRCULATION_CHECK', true, true, target, 0, warning);
            }
            if (nextMode === 'FLOOR_ONLY') {
                if (!finite(c.floorOnlyMaxPct) || c.floorOnlyMaxPct <= 0 || c.floorOnlyMaxPct > 100) {
                    return result('FLOOR_CAP_UNMEASURED', true, false, 0, 0,
                        'Нет проверенного предела открытия 562 для режима по полу; требуется ПНР на горячем источнике');
                }
                // Fresh floor is the feedback, never pretend it measures mixed water.
                var floorTarget = remoteValid ? (f.mode === 'HEAT' ? f.heat : f.hold) : c.floorTargetMaxC - 1;
                if (floor >= floorTarget) position = 0;
                else if (floorStepAt === null || now - floorStepAt >= c.floorStepMs) {
                    position = Math.min(c.floorOnlyMaxPct, position + c.floorStepPct); floorStepAt = now;
                }
                warning = 'Отказ 418: ограниченное управление по полу; температура подачи не измеряется';
            } else {
                position = mix.step({ now: now / 1000, enabled: true, pumpOn: true,
                    supplyTempC: supply, sourceTempC: i.source, targetC: target, sensorOffsetC: 0,
                    valveEnableOn: true, phaseMode: 'auto', freeze: false, manualValvePct: 0 }).valvePositionPct;
            }
            if (i.source === null || i.ret === null) warning += '; нет свежего 411/419';
            if (i.source !== null && i.source < target) warning += '; источник ещё холодный';
            var responseTemp = supply !== null ? supply : floor;
            if (responseAt === null) { responseAt = now; baseline = responseTemp; }
            if (responseTemp >= target - 1 || responseTemp >= baseline + c.responseRiseC) {
                responseAt = now; baseline = responseTemp;
            } else if (now - responseAt >= c.responseMs) warning += '; NO_RESPONSE: нет роста температуры, расход не измерен';
            return result(nextMode, true, true, target, position, warning);
        }
    };
};
