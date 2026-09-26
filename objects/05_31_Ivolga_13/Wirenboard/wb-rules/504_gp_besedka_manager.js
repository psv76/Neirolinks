/* Иволга 504, контракт v1.0. Единственный writer после однократной ПНР. */
var H = require('HM2504');
var C = require('HM2504Config').config;
var Control = require('HM2504Control');
var VD = 'hm2_504_gp_besedka';
var CH = { pump: 'A03/K4', level: 'A05/Channel 3 Dimming Level', enable: 'A05/Channel 3 Switch',
    supply: 'wb-m1w2_173/External Sensor 1', ret: 'wb-m1w2_173/External Sensor 2',
    source: 'wb-m1w2_170/External Sensor 1' };
var persistent = new PersistentStorage('ivolga_504_operation', { global: true });
var control = Control.create(C, persistent, require('MixingController'));
var receiver = H.receiver(Date.now());
var sensors = { supply: H.sensor(), ret: H.sensor(), source: H.sensor() };
var cells = {}, lastEvent = '';
function cell(k, title, type, value, readonly) {
    cells[k] = { title: title, type: type, value: value, readonly: readonly !== false, forceDefault: true };
}
cell('start_heating', 'Включить отопление (однократно при ПНР)', 'pushbutton', false, false);
cell('in_service', 'Введён в эксплуатацию', 'switch', false);
cell('status', 'Состояние', 'text', 'Первичная ПНР');
cell('warning', 'Предупреждение', 'text', '');
cell('notification_json', 'Последнее событие для доставки', 'text', '{}');
cell('state', 'HM2 state', 'text', 'UNKNOWN');
cell('valid', 'Достоверность запроса', 'switch', false);
cell('heat_demand', 'Запрос тепла', 'switch', false);
cell('path_ready', 'Команда циркуляции принята (не расход)', 'switch', false);
cell('requested_supply_c', 'Цель подачи 418, °C', 'value', 0);
cell('requested_source_temperature', 'Запрос источнику, °C', 'value', 0);
cell('request_reason', 'Режим', 'text', 'FIRST_COMMISSIONING');
cell('request_json', 'Атомарный запрос', 'text', '{}');
cell('request_timestamp', 'Время запроса', 'text', '');
cell('request_ttl_s', 'TTL запроса, с', 'value', C.requestTtlS);
cell('remote_valid', 'Достоверный запрос термостата', 'switch', false);
cell('remote_reason', 'Причина термостата', 'text', '');
cell('link_state', 'Связь', 'text', 'STARTUP_VALIDATION');
cell('runtime_status', 'Совместимость runtime', 'text', 'Ожидание MQTT; wb-rules >= 2.42.0');
cell('pump_command', 'Команда насоса', 'switch', false);
cell('valve_command_pct', 'Открытие горячего входа, %', 'value', 0);
cell('output_status', 'Выдача команд (не расход)', 'text', 'NO_WRITE');
defineVirtualDevice(VD, { title: 'HM2 504 — отопление беседки', cells: cells });
function sc(k, v) { dev[VD + '/' + k] = v; }
Object.keys(cells).forEach(function (k) { sc(k, cells[k].value); });
Object.keys(sensors).forEach(function (key) {
    var path = CH[key], p = path.indexOf('/');
    var topic = '/devices/' + path.slice(0, p) + '/controls/' + path.slice(p + 1);
    trackMqtt(topic, function (m) { sensors[key].sample(m.value, m.retained, Date.now()); evaluate(); });
    trackMqtt(topic + '/meta/error', function (m) { sensors[key].error(m.value); evaluate(); });
});
trackMqtt(H.TOPIC, function (m) { receiver.accept(m.value, m.retained, Date.now()); evaluate(); });
function write(path, value) {
    try { dev[path] = value; return true; }
    catch (e) { log.error('[отопление][504] Не выдана команда ' + path + ': ' + String(e)); return false; }
}
function outputs(r) {
    if (!r.write) return 'NO_WRITE';
    var level = C.valveClosedLevel + (C.valveOpenLevel - C.valveClosedLevel) * r.valve / 100;
    var ok = true;
    // Do not suppress closure if another write fails. Level precedes Switch ON.
    if (!r.pump) ok = write(CH.pump, false) && ok;
    ok = write(CH.level, level) && ok;
    ok = write(CH.enable, r.valve > 0 ? true : C.valveClosedEnable) && ok;
    if (r.pump) ok = write(CH.pump, true) && ok;
    return ok ? 'COMMANDS_SENT_NOT_FLOW_PROOF' : 'OUTPUT_WRITE_ERROR';
}
function evaluate() {
    var now = Date.now(), link = receiver.read(now), f = link.frame;
    var supply = sensors.supply.read(now, -20, 110), ret = sensors.ret.read(now, -20, 110);
    var source = sensors.source.read(now, -20, 110);
    var unsupported = link.runtime === 'RUNTIME_UNSUPPORTED' || Object.keys(sensors).some(function (k) {
        return sensors[k].runtimeStatus() === 'RUNTIME_UNSUPPORTED';
    });
    sc('runtime_status', unsupported ? H.RUNTIME_ERROR_RU : 'MQTT freshness проверяется; wb-rules >= 2.42.0');
    var r = control.step({ now: now, supply: supply, supplyAt: sensors.supply.timestamp(),
        ret: ret, source: source, frame: f, linkReason: link.reason });
    var outputStatus = outputs(r), valid = r.valid && r.write && outputStatus !== 'OUTPUT_WRITE_ERROR';
    var demand = valid && r.demand, ready = r.write && r.pump && outputStatus !== 'OUTPUT_WRITE_ERROR';
    var requestedSource = demand ? r.target + C.sourceMarginC : 0, timestamp = new Date(now).toISOString();
    var warning = r.warning + (unsupported ? '; ' + H.RUNTIME_ERROR_RU : '') +
        (outputStatus === 'OUTPUT_WRITE_ERROR' ? '; ошибка записи выходов, повтор автоматически' : '');
    var state = demand ? 'ACTIVE' : (valid ? 'INACTIVE' : 'UNKNOWN');
    sc('in_service', persistent.inService === true); sc('state', state);
    sc('valid', valid); sc('heat_demand', demand); sc('path_ready', ready);
    sc('requested_supply_c', demand ? r.target : 0); sc('requested_source_temperature', requestedSource);
    sc('request_reason', r.reason); sc('remote_valid', !!(f && f.valid));
    sc('remote_reason', f ? f.reason : link.reason); sc('link_state', link.reason);
    sc('pump_command', r.write && r.pump); sc('valve_command_pct', r.write ? r.valve : 0);
    sc('output_status', outputStatus); sc('warning', warning); sc('status', r.reason + (warning ? '; ' + warning : ''));
    sc('request_json', JSON.stringify({ state: state, valid: valid, heat_demand: demand,
        path_ready: ready, fault_latched: false, requested_supply_c: demand ? r.target : 0,
        requested_source_temperature: requestedSource, request_reason: r.reason,
        request_timestamp: timestamp, request_ttl_s: C.requestTtlS }));
    sc('request_timestamp', timestamp);
    var key = r.reason + ';' + warning;
    if (key !== lastEvent) {
        var text = 'Иволга 13, беседка 504: ' + r.reason + (warning ? '; ' + warning : '; штатный переход');
        sc('notification_json', JSON.stringify({ timestamp: timestamp, reason: r.reason, text: text }));
        // Existing site adapter subscribes here. No invented credentials or delivery queue.
        // Receipt/delivery must be verified at PNR; local journal is always available.
        if (warning) log.warning('[отопление][504] ' + text); else log.info('[отопление][504] ' + text);
        lastEvent = key;
    }
}
defineRule('hm2_504_first_start', { whenChanged: VD + '/start_heating', then: function (value) {
    if (value !== true && value !== 1 && value !== '1') return;
    if (persistent.inService === true) return;
    if (!control.commission()) {
        sc('status', 'ПНР: измерить closed/open Level и Switch закрытого 562 в HM2504Config'); return;
    }
    evaluate();
} });
evaluate();
setInterval(evaluate, C.periodMs);
