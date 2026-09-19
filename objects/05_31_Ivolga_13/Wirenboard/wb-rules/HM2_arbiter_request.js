// HM2_arbiter_request.js
// HM2 Ivolga / issue #29: calculation only; writes only its own virtual device.
var VD = 'hm2_request_arbiter';
// Static review gate, deliberately not writable/retained. Source manager does not
// yet accept 504; enabling this requires a separate source/tie-break decision.
var ENABLE_504_SELECTION = false;
var BES = { id: 'hm2_504_gp_besedka', number: '504', title: '504 ГП беседка' };
// Stable tie-break: 503 > 502 > 501. Never replace an equal-temperature winner.
var CONSUMERS = [
    { id: 'hm2_503_rad_dom', number: '503', title: '503 Радиаторы дом' },
    { id: 'hm2_502_gp_dom', number: '502', title: '502 ГП дом / плитка' },
    { id: 'hm2_501_tp_dom', number: '501', title: '501 ТП дом / паркет' }
];
var cells = {};
function cell(name, type, value) {
    cells[name] = { title: name, type: type, value: value, readonly: true };
}
cell('state', 'text', 'UNKNOWN');
cell('valid', 'switch', false);
cell('selected_consumer', 'text', '');
cell('selected_consumer_title', 'text', '');
cell('selected_requested_temperature', 'value', 0);
cell('selected_reason', 'text', 'STARTUP');
cell('no_demand_contract', 'switch', true);
cell('active_candidate_count', 'value', 0);
cell('rejected_candidate_count', 'value', 3);
cell('candidates_json', 'text', '[]');
cell('last_update_ts', 'text', '');
cell('grant_504_state', 'text', 'REJECTED');
cell('grant_504_reason', 'text', 'FEATURE_DISABLED');
cell('selection_504_enabled', 'switch', false);
CONSUMERS.forEach(function (consumer) {
    cell('grant_' + consumer.number + '_state', 'text', 'REJECTED');
    cell('grant_' + consumer.number + '_reason', 'text', 'STARTUP');
});
defineVirtualDevice(VD, { title: 'HM2 Иволга — Request Arbiter SHADOW', cells: cells });
function sc(name, value) { dev[VD + '/' + name] = value; }
function bool(value) {
    if (value === true || value === 1 || value === '1' || value === 'true') return true;
    if (value === false || value === 0 || value === '0' || value === 'false') return false;
    return null;
}
function positive(value) {
    if (typeof value !== 'number' && typeof value !== 'string') return null;
    var number = Number(value);
    return isFinite(number) && number > 0 ? number : null;
}
function candidate(consumer, now) {
    var result = { consumer: consumer.id, number: consumer.number, title: consumer.title,
        state: 'UNKNOWN', eligible: false, reason: 'READ_ERROR', temperature: 0,
        age_s: null, ttl_s: null };
    try {
        var prefix = consumer.id + '/';
        var state = dev[prefix + 'state'];
        var valid = bool(dev[prefix + 'valid']);
        var demand = bool(dev[prefix + 'heat_demand']);
        var ready = bool(dev[prefix + 'path_ready']);
        var fault = bool(dev[prefix + 'fault_latched']);
        var temperature = positive(dev[prefix + 'requested_source_temperature']);
        var timestamp = dev[prefix + 'request_timestamp'];
        var ttl = positive(dev[prefix + 'request_ttl_s']);
        var millis = typeof timestamp === 'string' ? Date.parse(timestamp) : NaN;
        var age = (now - millis) / 1000;
        result.state = typeof state === 'string' ? state : 'UNKNOWN';
        result.temperature = temperature === null ? 0 : temperature;
        result.age_s = isFinite(age) ? age : null;
        result.ttl_s = ttl;
        if (state !== 'ACTIVE') result.reason = 'NOT_ACTIVE';
        else if (valid !== true) result.reason = 'INVALID';
        else if (demand !== true) result.reason = 'NO_DEMAND';
        else if (ready !== true) result.reason = 'PATH_NOT_READY';
        else if (fault === true) result.reason = 'FAULT_LATCHED';
        else if (fault === null) result.reason = 'UNKNOWN_FAULT';
        else if (temperature === null) result.reason = 'INVALID_TEMPERATURE';
        else if (ttl === null || !isFinite(age) || age < 0) result.reason = 'INVALID_TIME';
        // The request expires at the TTL boundary, not one tick later.
        else if (age >= ttl) result.reason = 'STALE';
        else { result.eligible = true; result.reason = 'ELIGIBLE'; }
    } catch (error) {
        log('[HM2 Ivolga/HM2_arbiter_request] ' + consumer.id + ': ' + String(error));
    }
    return result;
}
function candidate504(now) {
    var result = { consumer: BES.id, number: BES.number, title: BES.title,
        state: 'UNKNOWN', eligible: false, reason: 'INVALID_ATOMIC_REQUEST',
        temperature: 0, age_s: null, ttl_s: null };
    try {
        var raw = dev[BES.id + '/request_json'];
        var r = typeof raw === 'string' && raw.length <= 2048 ? JSON.parse(raw) : null;
        if (!r || typeof r !== 'object' || Array.isArray(r)) return result;
        var age = (now - Date.parse(r.request_timestamp)) / 1000;
        result.state = typeof r.state === 'string' ? r.state : 'UNKNOWN';
        result.age_s = isFinite(age) ? age : null;
        result.ttl_s = r.request_ttl_s;
        result.temperature = typeof r.requested_source_temperature === 'number' ? r.requested_source_temperature : 0;
        if (r.fault_latched !== false) result.reason = 'FAULT_OR_UNKNOWN';
        else if (r.state !== 'ACTIVE') result.reason = 'NOT_ACTIVE';
        else if (r.valid !== true) result.reason = 'INVALID';
        else if (r.heat_demand !== true) result.reason = 'NO_DEMAND';
        else if (r.path_ready !== true) result.reason = 'PATH_NOT_READY';
        else if (typeof r.requested_source_temperature !== 'number' ||
            !isFinite(r.requested_source_temperature) || r.requested_source_temperature <= 0) result.reason = 'INVALID_TEMPERATURE';
        else if (typeof r.request_timestamp !== 'string' || !isFinite(age) || age < 0 ||
            typeof r.request_ttl_s !== 'number' || !isFinite(r.request_ttl_s) ||
            r.request_ttl_s <= 0 || r.request_ttl_s > 15) result.reason = 'INVALID_TIME';
        else if (age >= r.request_ttl_s) result.reason = 'STALE';
        else { result.eligible = true; result.reason = 'ELIGIBLE'; }
    } catch (e) { result.reason = 'INVALID_ATOMIC_REQUEST'; }
    return result;
}
function evaluate() {
    var now = Date.now();
    var selectionReason = ENABLE_504_SELECTION ? 'MAX_TEMPERATURE; TIE_503_502_501_504_PROPOSED' :
        'MAX_TEMPERATURE; TIE_503_502_501';
    var winner = null;
    var active = 0;
    var candidates = CONSUMERS.map(function (consumer) { return candidate(consumer, now); });
    var bes = candidate504(now);
    if (ENABLE_504_SELECTION) candidates.push(bes); // Append only: incumbents win equal-temperature ties.
    candidates.forEach(function (item) {
        if (!item.eligible) return;
        active += 1;
        if (winner === null || item.temperature > winner.temperature) winner = item;
    });
    // Invalidate during publication; last_update_ts is written last.
    sc('valid', false);
    sc('state', winner === null ? 'INACTIVE' : 'ACTIVE');
    sc('selected_consumer', winner === null ? '' : winner.consumer);
    sc('selected_consumer_title', winner === null ? '' : winner.title);
    sc('selected_requested_temperature', winner === null ? 0 : winner.temperature);
    sc('selected_reason', winner === null ? 'NO_ELIGIBLE_REQUEST' : selectionReason);
    sc('no_demand_contract', winner === null);
    sc('active_candidate_count', active);
    sc('rejected_candidate_count', candidates.length - active);
    if (!ENABLE_504_SELECTION) {
        bes.validation_reason = bes.reason;
        bes.eligible = false; bes.reason = 'FEATURE_DISABLED';
        sc('grant_504_state', 'REJECTED'); sc('grant_504_reason', 'FEATURE_DISABLED');
    }
    sc('selection_504_enabled', ENABLE_504_SELECTION);
    sc('candidates_json', JSON.stringify(ENABLE_504_SELECTION ? candidates : candidates.concat([bes])));
    candidates.forEach(function (item) {
        var selected = winner !== null && item.consumer === winner.consumer;
        sc('grant_' + item.number + '_state', !item.eligible ? 'REJECTED' :
            (selected ? 'SHADOW_SELECTED' : 'SHADOW_NOT_SELECTED'));
        sc('grant_' + item.number + '_reason', !item.eligible ? item.reason :
            (selected ? selectionReason : 'LOWER_TEMPERATURE_OR_TIE_PRIORITY'));
    });
    sc('valid', true);
    sc('last_update_ts', new Date(now).toISOString());
}
// Explicit reset also clears values restored by the virtual-device storage.
Object.keys(cells).forEach(function (name) { sc(name, cells[name].value); });
setTimeout(function () {
    evaluate();
    setInterval(evaluate, 5000);
    log('[HM2 Ivolga/HM2_arbiter_request] SHADOW started; diagnostic grants only');
}, 3000);
