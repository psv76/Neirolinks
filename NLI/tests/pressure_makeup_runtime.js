'use strict';
// Exact baseline executed only in Node VM with fake dev/timers; no hardware API.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(path.join(__dirname, '../releases/pressure_makeup/1.0/507_Pressure_makeup.js'), 'utf8');

function boot(values) {
  const timers = new Map(), writes = [], logs = [];
  let now = 0, id = 0;
  const context = vm.createContext({
    dev: new Proxy(values, {
      set(obj, key, value) { writes.push({key, value}); obj[key] = value; return true; }
    }),
    require(name) {
      assert.strictEqual(name, 'system');
      return {safeLog: s => logs.push(s), sendAlert: () => {}};
    },
    defineVirtualDevice(name, spec) {
      for (const [cell, meta] of Object.entries(spec.cells)) {
        const key = name + '/' + cell;
        if (!(key in values)) values[key] = meta.value;
      }
    },
    defineRule() {},
    setTimeout(fn, delay) { timers.set(++id, {fn, at: now + delay}); return id; },
    clearTimeout(timer) { timers.delete(timer); },
    PersistentStorage() { throw new Error('507 runtime must not be persisted'); }
  });
  vm.runInContext(source, context, {filename: '507_Pressure_makeup.js', timeout: 1000});
  function tick(ms) {
    const end = now + ms;
    while (true) {
      const next = [...timers].filter(([,t]) => t.at <= end).sort((a,b) => a[1].at-b[1].at)[0];
      if (!next) break;
      now = next[1].at;
      timers.delete(next[0]);
      next[1].fn();
    }
    now = end;
  }
  return {context, writes, logs, tick};
}

const values = {'905.3/input_1_value': 1.6, '905.3/input_1_current': 8, 'A04/K1': false};
let runtime = boot(values);
runtime.tick(3000);
runtime.context.STATE.pulseCount = 5;
for (const name of ['sensorAlarm', 'lowPressureAlarm', 'makeupFailedAlarm', 'watchdogAlarm']) {
  runtime.context.STATE[name] = true;
}
runtime.context.updateVirtualState(1.6, 8);
assert.strictEqual(values['pressure_makeup/pulse_count'], 5);
assert.strictEqual(values['pressure_makeup/watchdog_alarm'], true);
values['A04/K1'] = true;
runtime = boot(values); // new wb-rules VM, retained virtual cells still present
assert.strictEqual(runtime.context.STATE.pulseCount, 0);
runtime.tick(3000);
assert.strictEqual(values['pressure_makeup/pulse_count'], 0);
for (const name of ['sensor_alarm','low_pressure_alarm','makeup_failed_alarm','watchdog_alarm']) {
  assert.strictEqual(values['pressure_makeup/' + name], false);
}
assert.strictEqual(values['A04/K1'], false);
assert(runtime.logs.some(s => s.includes('[507_Pressure_makeup] Запуск скрипта')));
console.log('PASS exact 507: restart resets pulseCount/alarms, startup closes valve, no PersistentStorage');

values['905.3/input_1_value'] = 1.1;
runtime = boot(values);
runtime.tick(3000);
const physical = runtime.writes.filter(w => !w.key.startsWith('pressure_makeup/'));
assert.deepStrictEqual(physical, [{key:'A04/K1',value:false},{key:'A04/K1',value:true}]);
assert.strictEqual(values['pressure_makeup/active'], true);
assert.strictEqual(values['pressure_makeup/pulse_count'], 1);
runtime.tick(3000);
assert.strictEqual(values['A04/K1'], false);
assert.strictEqual(runtime.context.STATE.waitingPause, true);
console.log('PASS exact 507: ordinary init/evaluate may reopen A04/K1 and pulse timer closes it');

values['905.3/input_1_current'] = 0;
runtime = boot(values);
runtime.tick(3000);
assert.strictEqual(values['A04/K1'], false);
assert.strictEqual(values['pressure_makeup/sensor_alarm'], true);
console.log('PASS exact 507: reset does not suppress alarms re-evaluated from inputs; Node model only');
