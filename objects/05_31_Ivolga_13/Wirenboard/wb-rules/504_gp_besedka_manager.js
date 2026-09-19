/* WB котельной / Иволга 504: non-writing blocked manager.
 * Принимает комбо-запрос, проверяет freshness и местные датчики.
 * Нет writer физических каналов, включая OFF. Допуск требует отдельной реализации
 * после утверждения 562, температур, автономной политики и COLD_SLAB параметров.
 */
var H = require('HM2504');
var MixingController = require('MixingController');
var VD = 'hm2_504_gp_besedka';
var CH = { supply: 'wb-m1w2_173/External Sensor 1', ret: 'wb-m1w2_173/External Sensor 2',
    source: 'wb-m1w2_170/External Sensor 1' };
// Deliberately absent engineering facts. No MQTT control can fill/enable these.
var PROFILE = null;
var mix = H.shadowMixer(MixingController, PROFILE);
var receiver = H.receiver(Date.now());
var sensors = { supply: H.sensor(), ret: H.sensor(), source: H.sensor() };
var persistent = new PersistentStorage('ivolga_504_safety', { global: true });
var cells = {}, order = 0, lastStatus = '';
function cell(name, title, type, value, readonly) {
    order += 10;
    cells[name] = { title: title, type: type, value: value, readonly: readonly,
        forceDefault: true, order: order };
}
cell('status', 'Состояние', 'text', 'DECISION_REQUIRED', true);
cell('state', 'HM2 state', 'text', 'UNKNOWN', true);
cell('valid', 'HM2 valid', 'switch', false, true);
cell('heat_demand', 'Допущенный запрос', 'switch', false, true);
cell('request_reason', 'Причина блокировки', 'text', 'DECISION_REQUIRED', true);
cell('request_timestamp', 'Время атомарного запроса', 'text', '', true);
cell('request_json', 'Атомарный снимок запроса 504', 'text', '{}', true);
cell('request_ttl_s', 'TTL запроса, с', 'value', 15, true);
cell('requested_supply_c', 'Запрос подачи (не определён)', 'value', 0, true);
cell('requested_source_temperature', 'Запрос источника (не определён)', 'value', 0, true);
cell('path_ready', 'Гидравлический путь подтверждён', 'switch', false, true);
cell('fault_latched', 'Сохранённая защёлка аварии', 'switch', false, true);
cell('fault_text', 'Причина сохранённой аварии', 'text', '', true);
cell('reset_fault', 'Проверить возможность сброса аварии', 'pushbutton', false, false);
cell('reset_reason', 'Результат запроса сброса', 'text', '', true);
cell('enabled', 'Логика допуска (не реализована)', 'switch', false, true);
cell('commissioned', 'ПНР завершён', 'switch', false, true);
cell('outputs_enabled', 'Физические writes', 'switch', false, true);
cell('physical_write_grant', 'Владение выходами', 'switch', false, true);
cell('remote_demand', 'Полученный расчётный demand', 'switch', false, true);
cell('remote_valid', 'Достоверный удалённый запрос', 'switch', false, true);
cell('remote_reason', 'Причина термостата', 'text', '', true);
cell('link_state', 'Связь и самопроверка', 'text', 'STARTUP_VALIDATION', true);
cell('link_age_s', 'Возраст последнего сообщения, с', 'value', -1, true);
cell('last_receive_result', 'Последний результат приёма', 'text', '', true);
cell('runtime_status', 'Совместимость wb-rules', 'text', 'Ожидание MQTT: требуется wb-rules >= 2.42.0', true);
cell('local_sensors_valid', 'Свежие 411/418/419', 'switch', false, true);
cell('supply_temp_c', 'Подача 418, °C (см. достоверность)', 'temperature', 0, true);
cell('return_temp_c', 'Обратка 419, °C (см. достоверность)', 'temperature', 0, true);
cell('source_temp_c', 'Источник 411, °C (см. достоверность)', 'temperature', 0, true);
cell('supply_trend_c_per_min', 'Тренд 418, °C/мин (диагностика)', 'value', 0, true);
cell('safety_state', 'Защиты', 'text', 'LIMITS_NOT_CONFIRMED', true);
cell('response_status', 'Контроль прогрева', 'text', 'NOT_COMMISSIONED', true);
cell('availability_state', 'Доступность источника / протока', 'text', 'NOT_CONFIRMED', true);
cell('autonomous_state', 'Автономный режим', 'text', 'POLICY_NOT_CONFIRMED', true);
cell('mixing_status', 'Регулятор', 'text', mix ? 'SHADOW' : 'TUNING_NOT_CONFIRMED', true);
defineVirtualDevice(VD, { title: 'HM2 504 Беседка — НЕПИШУЩИЙ SHADOW', cells: cells });
function sc(k, v) { dev[VD + '/' + k] = v; }
Object.keys(cells).forEach(function (k) { sc(k, cells[k].value); });
Object.keys(CH).forEach(function (key) {
    var path = CH[key], p = path.indexOf('/');
    var topic = '/devices/' + path.slice(0, p) + '/controls/' + path.slice(p + 1);
    trackMqtt(topic, function (m) { sensors[key].sample(m.value, m.retained, Date.now()); });
    trackMqtt(topic + '/meta/error', function (m) { sensors[key].error(m.value); });
});
trackMqtt(H.TOPIC, function (m) {
    sc('last_receive_result', receiver.accept(m.value, m.retained, Date.now()));
});
var previousSupply = null, previousTime = null;
function evaluate() {
    var now = Date.now(), link = receiver.read(now), f = link.frame;
    var supply = sensors.supply.read(now, -20, 95), ret = sensors.ret.read(now, -20, 95);
    var source = sensors.source.read(now, -20, 95);
    var localOk = supply !== null && ret !== null && source !== null;
    var unsupported = link.runtime === 'RUNTIME_UNSUPPORTED' || Object.keys(sensors).some(function (k) {
        return sensors[k].runtimeStatus() === 'RUNTIME_UNSUPPORTED';
    });
    var runtimeVerified = link.runtime === 'SUPPORTED' && Object.keys(sensors).every(function (k) {
        return sensors[k].runtimeStatus() === 'SUPPORTED';
    });
    sc('runtime_status', unsupported ? H.RUNTIME_ERROR_RU : (runtimeVerified ?
        'trackMqtt.retained поддерживается; версию проверить до установки' : 'Ожидание MQTT: требуется wb-rules >= 2.42.0'));
    var fault = typeof persistent.fault === 'string' ? persistent.fault : '';
    var reason = fault ? 'FAULT_LATCHED' : (unsupported ? 'RUNTIME_UNSUPPORTED' : (!localOk ? 'LOCAL_SENSOR_INTERLOCK' :
        (!link.fresh ? 'DEGRADED_POLICY_NOT_CONFIRMED' :
        (!f.valid ? (f.reason === 'SETTINGS_INVALID' ? 'SETTINGS_INVALID' :
        (f.reason === 'RUNTIME_UNSUPPORTED' ? 'REMOTE_RUNTIME_UNSUPPORTED' : 'REMOTE_SENSOR_INTERLOCK')) : 'DECISION_REQUIRED'))));
    sc('valid', false); // Begin publication; never committed valid in this blocked build.
    sc('state', 'UNKNOWN'); sc('heat_demand', false); sc('path_ready', false);
    sc('requested_supply_c', 0); sc('requested_source_temperature', 0);
    sc('request_reason', reason); sc('request_ttl_s', 15);
    sc('fault_latched', !!fault); sc('fault_text', fault);
    ['enabled', 'commissioned', 'outputs_enabled', 'physical_write_grant'].forEach(function (k) { sc(k, false); });
    sc('remote_demand', !!(!unsupported && f && f.demand)); sc('remote_valid', !!(!unsupported && f && f.valid));
    sc('remote_reason', f ? f.reason : ''); sc('link_state', link.reason); sc('link_age_s', link.age_s);
    sc('local_sensors_valid', localOk);
    if (supply !== null) sc('supply_temp_c', supply);
    if (ret !== null) sc('return_temp_c', ret);
    if (source !== null) sc('source_temp_c', source);
    sc('supply_trend_c_per_min', supply !== null && previousSupply !== null && now > previousTime ?
        (supply - previousSupply) * 60000 / (now - previousTime) : 0);
    previousSupply = supply; previousTime = now;
    sc('safety_state', !localOk ? 'SENSOR_INTERLOCK' : 'LIMITS_NOT_CONFIRMED');
    sc('status', reason + '; ' + (unsupported ? H.RUNTIME_ERROR_RU :
        (f && f.reason === 'SETTINGS_INVALID' ? 'Некорректные уставки термостата беседки' :
        (f && f.reason === 'RUNTIME_UNSUPPORTED' ? 'WB беседки: ' + H.RUNTIME_ERROR_RU : 'пределы 504 и резерв не утверждены'))) +
        '; физических writes нет');
    var timestamp = new Date(now).toISOString();
    sc('request_json', JSON.stringify({ state: 'UNKNOWN', valid: false, heat_demand: false,
        path_ready: false, fault_latched: !!fault, requested_supply_c: 0,
        requested_source_temperature: 0, request_reason: reason,
        request_timestamp: timestamp, request_ttl_s: 15 }));
    sc('request_timestamp', timestamp); // Commit marker last.
    if (reason !== lastStatus) {
        log.warning('[отопление][504_gp_besedka_manager][504 беседка]; STATE=' + reason);
        lastStatus = reason;
    }
}
defineRule('hm2_504_reset', { whenChanged: VD + '/reset_fault', then: function () {
    // Unknown safety limits cannot justify clearing a pre-existing dangerous latch.
    sc('reset_reason', 'DECISION_REQUIRED: пределы и безопасный сброс ещё не подтверждены');
    log.warning('[отопление][504_gp_besedka_manager][504 беседка]; RESET=Отказ: пределы не подтверждены');
} });
evaluate();
setInterval(evaluate, 5000);
log.info('[отопление][504_gp_besedka_manager][504 беседка]; SCRIPT=BLOCKED; физических writes нет');
