/* WB беседки: один комбо-термостат 504, воздух выбирает цель пола.
 * Пишет только собственное virtual device и non-retained логический frame.
 * Физических выходов и удалённых /on здесь нет.
 */
var H = require('HM2504');
var VD = 'NL_combo_thermostat_504';
var memory = { airHeat: false, floorHeat: false };
var air = H.sensor(), floor = H.sensor();
var store504 = new PersistentStorage('ivolga_504_sender', { global: true });
var boot = Math.max(Date.now(), (H.number(store504.boot_ms) || 0) + 1);
store504.boot_ms = boot;
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
cell('floor_min_temperature', 'Пол при поддержании, °C', 'range', 25, false, 18, 30);
cell('floor_max_temperature', 'Пол при нагреве, °C', 'range', 29, false, 20, 35);
cell('target_state', 'Режим: 0 выключен, 1 нагрев', 'value', 0, false, 0, 1);
cell('current_state', 'Расчётный запрос нагрева', 'value', 0, true);
cell('air_valid', 'Воздух достоверен', 'switch', false, true);
cell('floor_valid', 'Пол достоверен', 'switch', false, true);
cell('demand_valid', 'Запрос достоверен', 'switch', false, true);
cell('state', 'Состояние', 'text', 'Самопроверка датчиков', true);
cell('reason', 'Причина', 'text', 'STARTUP', true);
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
    var targetState = H.number(dev[VD + '/target_state']);
    var s = { target: H.number(dev[VD + '/target_temperature']),
        hold: H.number(dev[VD + '/floor_min_temperature']),
        heat: H.number(dev[VD + '/floor_max_temperature']),
        enabled: targetState === 1 };
    if (targetState !== 0 && targetState !== 1) s.enabled = null;
    var r = H.combo(memory, a, f, s);
    if (a !== null) sc('air_temperature', a);
    if (f !== null) sc('floor_temperature', f);
    sc('air_valid', a !== null); sc('floor_valid', f !== null);
    sc('current_state', r.demand ? 1 : 0); sc('demand_valid', r.valid); sc('reason', r.reason);
    sc('state', r.mode === 'OFF' ? 'Выключен' : (!r.valid ? 'Блокировка: проверьте датчики и уставки' :
        (r.mode === 'DEGRADED' ? 'Нет воздуха: поддержание пола' :
        (r.demand ? (r.mode === 'HEAT' ? 'Нагрев пола по запросу воздуха' : 'Поддержание пола') : 'Ожидание'))));
    if (r.reason !== lastReason) {
        log.info('[отопление][624_combo_besedka][504 беседка]; STATE=' + r.reason);
        lastReason = r.reason;
    }
    // Invalid settings are not normalized into a plausible remote request.
    if (!H.settingsValid(s)) return;
    seq += 1;
    publish(H.TOPIC, JSON.stringify({ v: 1, source: H.SOURCE, boot_ms: boot, seq: seq,
        sent_ms: now, ttl_ms: H.TTL_MS, air: a, floor: f, target: s.target,
        hold: s.hold, heat: s.heat, enabled: s.enabled, valid: r.valid,
        demand: r.demand, mode: r.mode, reason: r.reason }), 0, false);
}
setTimeout(function () { evaluate(); setInterval(evaluate, 5000); }, 3000);
log.info('[отопление][624_combo_besedka][504 беседка]; SCRIPT=Самопроверка; физических writes нет');
