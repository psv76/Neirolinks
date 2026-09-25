/* 05 31 Иволга 13: две операторские панели — запросы/дельты и котловой контур.
 * Один файл вместо прежних 600_Heat_diagnostics.js и 610_Boiler_state.js.
 * Пишет только виртуальные heat_diagnostics/* и boiler_state/*.
 * Физические выходы, котёл, уставки и защиту не изменяет.
 */

var HD_OT = 'wbe2-i-opentherm_11';
var HD_DEV = 'heat_diagnostics';
var HD_BOILER = 'boiler_state';

var HD_SENSORS = {
    boilerS: 'wb-m1w2_170/External Sensor 1', // 411
    boilerR: 'wb-m1w2_170/External Sensor 2', // 412
    tpS: 'wb-m1w2_141/External Sensor 1',     // 413
    tpR: 'wb-m1w2_141/External Sensor 2',     // 414
    gpS: 'wb-m1w2_167/External Sensor 1',     // 415
    gpR: 'wb-m1w2_167/External Sensor 2',     // 416
    radR: 'wb-m1w2_121/External Sensor 1',    // 417
    besS: 'wb-m1w2_173/External Sensor 1',    // 418
    besR: 'wb-m1w2_173/External Sensor 2',    // 419
    hozR: 'wb-m1w2_166/External Sensor 1'     // 420
};

var HD_PAIRS = [
    {id:'delta_boiler', title:'ΔT котлового контура', s:HD_SENSORS.boilerS, r:HD_SENSORS.boilerR},
    {id:'delta_501', title:'501 ΔT ТП дом', s:HD_SENSORS.tpS, r:HD_SENSORS.tpR},
    {id:'delta_502', title:'502 ΔT ГП дом', s:HD_SENSORS.gpS, r:HD_SENSORS.gpR},
    {id:'delta_503', title:'503 ΔT Радиаторы дом', s:HD_SENSORS.boilerS, r:HD_SENSORS.radR},
    {id:'delta_504', title:'504 ΔT ГП беседка', s:HD_SENSORS.besS, r:HD_SENSORS.besR},
    {id:'delta_505', title:'505 ΔT Радиаторы хоз. блок', s:HD_SENSORS.boilerS, r:HD_SENSORS.hozR}
];

var HD_OT_SRC = {
    boilerStatus: HD_OT + '/Boiler Status',
    flame: HD_OT + '/Boiler Flame Status',
    chEnable: HD_OT + '/Master CH enable',
    chMode: HD_OT + '/Boiler CH mode',
    dhwEnable: HD_OT + '/Master DHW enable',
    dhwMode: HD_OT + '/Boiler DHW mode',
    fault: HD_OT + '/Boiler fault indication',
    errorCode: HD_OT + '/Error Code',
    lowWaterPress: HD_OT + '/Low water press',
    gasFlame: HD_OT + '/GAS Flame fault',
    airPress: HD_OT + '/Air press fault',
    overtemp: HD_OT + '/Water overtemp',
    noConn: HD_OT + '/Invalid Connection'
};

function hdNumber(path) {
    var v = dev[path], n;
    if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
    if (typeof v === 'string' && !v.replace(/\s/g, '')) return null;
    n = Number(v);
    return isFinite(n) ? n : null;
}
function hdTemperature(path) {
    var t = hdNumber(path);
    return t !== null && t >= -40 && t <= 120 ? t : null;
}
function hdBool(path) {
    var v = dev[path];
    return v === true || v === 1 || v === '1' || v === 'true';
}
function hdSet(device, key, value) {
    var p = device + '/' + key;
    if (dev[p] !== value) dev[p] = value;
}
function hdDegrees(n) {
    return String(Math.round(n * 10) / 10) + ' °C';
}
function hdDelta(pair) {
    var s = hdTemperature(pair.s), r = hdTemperature(pair.r);
    if (s === null || r === null) return 'нет данных';
    return hdDegrees(s - r);
}
function hdRequest(path) {
    var n = hdNumber(path);
    if (n === null || n < 0 || n > 100) return 'нет данных';
    return n === 0 ? 'нет' : hdDegrees(n);
}
function hdDemand(id) {
    return hdRequest('HHM3_FSE/diag_request_' + id);
}
function hdBoilerRequest() {
    // Compact HHM3 diagnostic feed: -1 unknown, 0 no demand, >0 requested °C.
    return hdRequest('HHM3_FSE/diag_request_boiler');
}
function hdFaults() {
    var f = [], code;
    if (hdBool(HD_OT_SRC.lowWaterPress)) f.push('низкое давление воды');
    if (hdBool(HD_OT_SRC.gasFlame)) f.push('ошибка газ/розжиг');
    if (hdBool(HD_OT_SRC.airPress)) f.push('ошибка прессостата воздуха');
    if (hdBool(HD_OT_SRC.overtemp)) f.push('перегрев теплоносителя');
    code = hdNumber(HD_OT_SRC.errorCode);
    if (code !== null && code !== 0) f.push('код OEM: ' + code);
    if (hdBool(HD_OT_SRC.fault) && !f.length) f.push('общая авария (нет уточнения)');
    return f;
}
function hdSummary(faults) {
    if (hdBool(HD_OT_SRC.noConn)) return 'Нет связи с котлом';
    if (faults.length) return 'АВАРИЯ: ' + faults.join(', ');
    if (hdBool(HD_OT_SRC.dhwMode) && hdBool(HD_OT_SRC.flame)) return 'Нагрев ГВС';
    if (hdBool(HD_OT_SRC.chMode) && hdBool(HD_OT_SRC.flame)) return 'Нагрев ЦО';
    if (hdBool(HD_OT_SRC.flame)) return 'Горелка работает';
    if (hdBool(HD_OT_SRC.dhwEnable) && !hdBool(HD_OT_SRC.dhwMode)) return 'Запрос ГВС — ожидание розжига';
    if (hdBool(HD_OT_SRC.chEnable) && !hdBool(HD_OT_SRC.chMode)) return 'Запрос ЦО — ожидание розжига';
    return 'Ожидание запроса';
}
function hdStatusBits() {
    var raw = hdNumber(HD_OT_SRC.boilerStatus), flags = [];
    if (raw === null || raw < 0 || raw > 255 || Math.floor(raw) !== raw) return 'нет данных';
    if (raw & 0x01) flags.push('авария');
    if (raw & 0x02) flags.push('ЦО активен');
    if (raw & 0x04) flags.push('ГВС активен');
    if (raw & 0x08) flags.push('горелка');
    if (raw & 0x10) flags.push('охлаждение');
    if (raw & 0x20) flags.push('ЦО-2 активен');
    if (raw & 0x40) flags.push('диагностика');
    return '0x' + raw.toString(16).toUpperCase() + ' → ' + (flags.length ? flags.join(', ') : 'нет активных флагов');
}

// Text controls show "нет данных" rather than retaining a stale numeric ΔT.
var HD_CELLS = {}, HD_ORDER = 0;
function hdCell(id, title, initial) {
    HD_ORDER += 10;
    HD_CELLS[id] = {type:'text', title:title, value:initial,
        readonly:true, forceDefault:true, order:HD_ORDER};
}
hdCell('section_requests', '── Запрос тепла ──', ' ');
hdCell('request_501', '501 ТП дом', 'нет данных');
hdCell('request_502', '502 ГП дом', 'нет данных');
hdCell('request_503', '503 Радиаторы дом', 'нет данных');
hdCell('request_504', '504 ГП беседка', 'нет данных');
hdCell('request_505', '505 Радиаторы хоз. блок', 'нет данных');
hdCell('request_boiler', 'Запрос в котёл', 'нет данных');
hdCell('section_delta', '── Разбор тепла ──', ' ');
for (var hdI = 0; hdI < HD_PAIRS.length; hdI++) {
    hdCell(HD_PAIRS[hdI].id, HD_PAIRS[hdI].title, 'нет данных');
}
hdCell('section_sensors', '── Показания датчиков ──', ' ');
hdCell('section_ot', '── OpenTherm ──', ' ');

defineVirtualDevice(HD_DEV, {title:'Диагностика отопления', cells:HD_CELLS});

// The original boiler_state IDs are kept for compatibility with other widgets.
defineVirtualDevice(HD_BOILER, {title:'Состояние котла', cells:{
    summary:{type:'text', title:'Что происходит', value:'Ожидание данных', readonly:true, forceDefault:true, order:10},
    faults_text:{type:'text', title:'Активные неисправности', value:'нет данных', readonly:true, forceDefault:true, order:20},
    connection:{type:'text', title:'Связь с котлом', value:'нет данных', readonly:true, forceDefault:true, order:30},
    status_bits:{type:'text', title:'Флаги статуса OpenTherm', value:'нет данных', readonly:true, forceDefault:true, order:40}
}});

function hdEvaluate() {
    var ids = ['501','502','503','504','505'], i, faults;
    for (i = 0; i < ids.length; i++) hdSet(HD_DEV, 'request_' + ids[i], hdDemand(ids[i]));
    hdSet(HD_DEV, 'request_boiler', hdBoilerRequest());
    for (i = 0; i < HD_PAIRS.length; i++) {
        hdSet(HD_DEV, HD_PAIRS[i].id, hdDelta(HD_PAIRS[i]));
    }
    faults = hdFaults();
    hdSet(HD_BOILER, 'summary', hdSummary(faults));
    hdSet(HD_BOILER, 'faults_text', faults.length ? faults.join(', ') : 'нет');
    hdSet(HD_BOILER, 'connection', hdBool(HD_OT_SRC.noConn) ? 'Ошибка связи' : 'OK');
    hdSet(HD_BOILER, 'status_bits', hdStatusBits());
}

var HD_WATCH = [
    'HHM3_FSE/diag_request_501',
    'HHM3_FSE/diag_request_502',
    'HHM3_FSE/diag_request_503',
    'HHM3_FSE/diag_request_504',
    'HHM3_FSE/diag_request_505',
    'HHM3_FSE/diag_request_boiler'
];
for (var hdJ = 0; hdJ < HD_PAIRS.length; hdJ++) {
    HD_WATCH.push(HD_PAIRS[hdJ].s, HD_PAIRS[hdJ].r);
}
for (var hdKey in HD_OT_SRC) {
    if (Object.prototype.hasOwnProperty.call(HD_OT_SRC, hdKey)) HD_WATCH.push(HD_OT_SRC[hdKey]);
}
var HD_UNIQUE_WATCH = [], hdSeen = {};
for (var hdW = 0; hdW < HD_WATCH.length; hdW++) {
    if (!hdSeen[HD_WATCH[hdW]]) {
        hdSeen[HD_WATCH[hdW]] = true;
        HD_UNIQUE_WATCH.push(HD_WATCH[hdW]);
    }
}
defineRule('heat_diagnostics_evaluate', {whenChanged:HD_UNIQUE_WATCH, then:hdEvaluate});
setTimeout(hdEvaluate, 3000);
setInterval(hdEvaluate, 30000);