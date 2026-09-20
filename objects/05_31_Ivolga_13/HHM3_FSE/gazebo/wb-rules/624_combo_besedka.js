/* WB беседки: один комбо-термостат 504, воздух выбирает цель пола.
 * Пишет только собственное virtual device и non-retained логический frame.
 * Физических выходов и удалённых /on здесь нет.
 */
var H = require('HHM3Wire');
var C = require('HHM3Config').config.circuits['504'];
var events = require('HHM3Runtime').io({dev:dev,now:Date.now,trackMqtt:trackMqtt,publish:publish,log:log},'624_combo_besedka',[]);
var VD = 'NL_combo_thermostat_504';
var memory = { airHeat: false, floorHeat: false };
var air = H.sensor(), floor = H.sensor();
var store504 = new PersistentStorage('hhm3_504_sender', { global: true });
var session = H.nextSession(store504);
var seq = 0, lastReason = '';
var cells = {}, order = 0;
function cell(name, title, type, value, readonly, min, max) {
    order += 10;
    cells[name] = { title: title, type: type, value: value, readonly: readonly,
        forceDefault: readonly, order: order };
    if (min !== undefined) { cells[name].min = min; cells[name].max = max; }
}
cell('air_temperature', 'Воздух, °C (см. достоверность)', 'temperature', 0, true);
cell('floor_temperature', 'Пол, °C (см. достоверность)', 'temperature', 0, true);
cell('target_temperature', 'Цель воздуха, °C', 'range', 22, false, 15, 30);
cell('floor_min_temperature', 'Пол при поддержании, °C', 'range', 25, false, 18, C.floorTargetMaxC);
cell('floor_max_temperature', 'Пол при нагреве, °C', 'range', 29, false, 20, C.floorTargetMaxC);
cell('target_state', 'Круглогодичное отопление', 'value', 1, true, 1, 1);
cell('current_state', 'Расчётный запрос нагрева', 'value', 0, true);
cell('air_valid', 'Воздух достоверен', 'switch', false, true);
cell('floor_valid', 'Пол достоверен', 'switch', false, true);
cell('demand_valid', 'Запрос достоверен', 'switch', false, true);
cell('state', 'Состояние', 'text', 'Самопроверка датчиков', true);
cell('reason', 'Причина', 'text', 'STARTUP', true);
cell('runtime_status', 'Совместимость wb-rules', 'text', 'Ожидание MQTT: требуется wb-rules >= 2.42.0', true);
defineVirtualDevice(VD, { title: '504 Беседка — воздух и пол', cells: cells });
function sc(k, v) { dev[VD + '/' + k] = v; }
function watch(path, sensor) {
    var p = path.indexOf('/');
    var topic = '/devices/' + path.slice(0, p) + '/controls/' + path.slice(p + 1);
    trackMqtt(topic, function (m) { sensor.sample(m.value, m.retained, Date.now()); });
    trackMqtt(topic + '/meta/error', function (m) { sensor.error(m.value); });
}
watch('921.09_MSW_TH/Temperature', air);
watch('921.10_TEMP_NONE/External Sensor 1', floor);
function evaluate() {
    var now = Date.now(), a = air.read(now, -20, 60), f = floor.read(now, -20, 70);
    sc('target_state', 1); // Compatibility display only; never a user OFF command.
    var s = { target: H.number(dev[VD + '/target_temperature']),
        hold: H.number(dev[VD + '/floor_min_temperature']),
        heat: H.number(dev[VD + '/floor_max_temperature']),
        enabled: true };
    var r = H.combo(memory, a, f, s);
    var unsupported = air.runtimeStatus() === 'RUNTIME_UNSUPPORTED' || floor.runtimeStatus() === 'RUNTIME_UNSUPPORTED';
    sc('runtime_status', unsupported ? H.RUNTIME_ERROR_RU :
        (air.runtimeStatus() === 'SUPPORTED' && floor.runtimeStatus() === 'SUPPORTED' ?
        'trackMqtt.retained поддерживается; версию проверить до установки' : 'Ожидание MQTT: требуется wb-rules >= 2.42.0'));
    if (unsupported) {
        memory.airHeat = false; memory.floorHeat = false;
        r = { valid: false, demand: false, mode: 'BLOCKED', reason: 'RUNTIME_UNSUPPORTED' };
    }
    // Canonical diagnostic frame: no substitute defaults and no silent heartbeat loss.
    if (!H.settingsValid(s)) {
        s = { target: null, hold: null, heat: null, enabled: null };
        r = { valid: false, demand: false, mode: 'BLOCKED', reason: 'SETTINGS_INVALID' };
    }
    if (a !== null) sc('air_temperature', a);
    if (f !== null) sc('floor_temperature', f);
    sc('air_valid', a !== null); sc('floor_valid', f !== null);
    sc('current_state', r.demand ? 1 : 0); sc('demand_valid', r.valid); sc('reason', r.reason);
    sc('state', unsupported ? H.RUNTIME_ERROR_RU : (!r.valid ? 'Проверьте датчики и уставки' :
        (r.mode === 'DEGRADED' ? 'Нет воздуха: поддержание пола' :
        (r.demand ? (r.mode === 'HEAT' ? 'Нагрев пола по запросу воздуха' : 'Поддержание пола') : 'Ожидание'))));
    if (r.reason !== lastReason) {
        events.event('504',r.reason,!r.valid||r.mode==='DEGRADED'?'Недостоверность датчиков или настроек':'');
        lastReason = r.reason;
    }
    seq += 1;
    publish(H.TOPIC, JSON.stringify({ v: H.VERSION, source: H.SOURCE, session_id: session, seq: seq,
        sent_ms: now, ttl_ms: H.TTL_MS, air: a, floor: f, target: s.target,
        hold: s.hold, heat: s.heat, enabled: s.enabled, valid: r.valid,
        demand: r.demand, mode: r.mode, reason: r.reason }), 0, false);
}
setTimeout(function () { evaluate(); setInterval(evaluate, 5000); }, 3000);
log.info('[отопление][624_combo_besedka][504 беседка]; SCRIPT=Самопроверка; физических writes нет');
