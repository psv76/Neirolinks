// HM2_source_manager.js
// HM2 Ivolga / issue #29: intended setpoint only, no hardware writer exists here.
var VD = 'hm2_source_manager';
var ARBITER = 'hm2_request_arbiter';
var cells = {};
function cell(name, type, value, readonly) {
    cells[name] = { title: name, type: type, value: value, readonly: readonly };
}
cell('state', 'text', 'UNKNOWN', true);
cell('source_state', 'text', 'SHADOW_NO_DEMAND', true);
cell('selected_consumer', 'text', '', true);
cell('intended_heating_setpoint', 'value', 0, true);
cell('no_demand_contract', 'switch', true, true);
cell('write_enabled', 'switch', false, false);
cell('physical_write_grant', 'switch', false, true);
cell('last_update_ts', 'text', '', true);
cell('status', 'text', 'STARTUP; SHADOW ONLY', true);
defineVirtualDevice(VD, { title: 'HM2 Иволга — Source Manager SHADOW', cells: cells });
function sc(name, value) { dev[VD + '/' + name] = value; }
function bool(value) {
    if (value === true || value === 1 || value === '1' || value === 'true') return true;
    if (value === false || value === 0 || value === '0' || value === 'false') return false;
    return null;
}
function evaluate() {
    var selected = '';
    var temperature = 0;
    var status = 'SHADOW ONLY; NO_DEMAND';
    try {
        var valid = bool(dev[ARBITER + '/valid']);
        var noDemand = bool(dev[ARBITER + '/no_demand_contract']);
        var consumer = dev[ARBITER + '/selected_consumer'];
        var raw = dev[ARBITER + '/selected_requested_temperature'];
        var requested = typeof raw === 'number' || typeof raw === 'string' ? Number(raw) : NaN;
        var known = consumer === 'hm2_501_tp_dom' || consumer === 'hm2_502_gp_dom' ||
            consumer === 'hm2_503_rad_dom';
        if (valid === true && noDemand === false && known && isFinite(requested) && requested > 0) {
            selected = consumer;
            temperature = requested;
            status = 'SHADOW ONLY; CALCULATED_SETPOINT';
        } else if (valid !== true || noDemand !== true) {
            status = 'SHADOW ONLY; INVALID_ARBITER_OR_NO_SELECTION';
        }
    } catch (error) {
        status = 'SHADOW ONLY; ARBITER_READ_ERROR';
        log('[HM2 Ivolga/HM2_source_manager] ' + String(error));
    }
    // write_enabled is an inert future interface, never a writer switch in this version.
    if (bool(dev[VD + '/write_enabled']) === true) status += '; WRITE_ENABLED_IGNORED';
    sc('physical_write_grant', false);
    sc('state', selected === '' ? 'INACTIVE' : 'ACTIVE');
    sc('source_state', selected === '' ? 'SHADOW_NO_DEMAND' : 'SHADOW_DEMAND');
    sc('selected_consumer', selected);
    sc('intended_heating_setpoint', temperature);
    sc('no_demand_contract', selected === '');
    sc('status', status);
    sc('last_update_ts', new Date().toISOString());
}
// Never trust persisted gates or calculated setpoints across reload/startup.
Object.keys(cells).forEach(function (name) { sc(name, cells[name].value); });
setTimeout(function () {
    evaluate();
    setInterval(evaluate, 5000);
    log('[HM2 Ivolga/HM2_source_manager] SHADOW started; write gates reset');
}, 3000);
