# WB-local room thermostat — offline stage (#204, decisions 4–7)

Implementation: `core/HHMRoomThermostat.js`,
`core/HHMRoomSensorEvidence.js`, `core/HHMRoomPathGate.js`, and
`core/HHMRoomMqttReadEvidence.js`, ECMAScript 5. The passive read-bound
MQTT evaluator requires a separately qualified running-driver policy; the
current Iset `max_unchanged_interval` is absent (= -1) and therefore does
not qualify this candidate. See `tests/ROOM_MQTT_READ_EVIDENCE.md`.

The Wiren Board must own accepted setpoints/modes and calculate room demand
locally. Home Assistant, Sprut, Apple HomeKit, Yandex Alice and WB WebUI
are **untrusted user-facing transports**, not sources of final heat demand.
This module does **not** depend on any of those services, MQTT, Node timers,
a physical relay or a cloud connection.

## Contract

`create(config, durableStore)` requires `durableStore.read()` to return
previously approved local `{mode, setpointC, revision, lastIntentId}`.
It **refuses to commission** without valid locally persisted settings.
`durableStore.commit(next)` must synchronously and durably return `true`
before memory state or revision changes. An actual Wiren Board storage
adapter with verified persistence and restart behavior is **not yet built**.

`step(frame)` uses primary/backup local measurements, each with
`{id, temperatureC, ok, observedAtMs}`. The object adapter must construct
`observedAtMs` from an **actual fresh local health-qualified observation**.
A constant temperature may remain valid if the WB sensor continues to
report healthy; retained or old values may not be re-stamped artificially.

`HHMRoomSensorEvidence` is a **pure contract evaluator**, not an installed
WB-MQTT/Modbus driver. It only accepts explicitly attested successful
local poll evidence with an exact WB-MSW Temperature topic, matching
bootEpoch and increasing pollSequence, plus a non-retained flag. Retained
MQTT readings, an unchanged cached value, a duplicate poll, a stale poll,
a poll failure and an old boot epoch cannot silently become a new healthy
measurement. A genuinely new successful poll may confirm **the same
numerical temperature**.

**Driver verification note:** official `wb-mqtt-serial` documentation
states `max_unchanged_interval=-1` by default: identical values are
published only when they change. Consequently lack of a fresh MQTT
Temperature message is NOT equivalent to lack of a successful Modbus
poll. The driver reports errors through `/meta/error`; the real object
adapter must read the active driver configuration and interpret the
actual error/clear events without inventing a positive health signal.
Changing publication periods or adding direct poll requests on a live
WB is outside this PR. Documentation:
https://github.com/wirenboard/wb-mqtt-serial (driver description).
 The real object-level adapter that obtains
trustworthy per-device poll success/sequence from wb-mqtt-serial remains
to be implemented and tested; setting `source='WB_LOCAL_MODBUS_POLL'` in
arbitrary MQTT rules is **not independent proof** of polling. Live MQTT
Temperature/meta alone contains insufficient health evidence.

The primary sensor must be object-mapped. Backup sensor is optional,
and may be used only when its placement and physical suitability for
the same room have been explicitly validated. Primary re-qualification
requires distinct healthy observations, time and sample count.

If neither sensor is valid, the module does **not** use the last sample
forever and does not translate `UNKNOWN` to `OFF`. Optional
`sensorLossHoldMs` temporarily preserves the **last computed demand**
(`SENSOR_HOLD`) for a short outage; it does not re-evaluate stale
measurements. A momentary good sample cannot infinitely renew HOLD:
primary requalification still requires distinct observations and a
time threshold. Physical safety overrides HOLD. **The 15 s in tests is
synthetic only**, not an approved Iset hold time. The object-specific
controller must supply `fallbackAuthorized`, `fallbackHeatDemand`,
`independentSafetyOk` and `hydraulicPathReady`. These are explicit
local facts, not defaults. `FALLBACK_HEAT` / `FALLBACK_LIMITED_OFF`
are only computed from a separate **approved bounded heating policy**.
If unavailable: `UNVERIFIED_FALLBACK` with `heatDemand=null`.
A true physical protection can also produce
`INDEPENDENT_PROTECTION` and must be handled by the downstream safety
owner. An individual unknown room does not veto unrelated healthy rooms.

A user command uses `applyIntent({clientId, intentId, issuedAtMs,
expectedRevision, retained:false, mode?, setpointC?}, nowMs)`.
`expectedRevision` is checked against the *WB*-accepted revision.
Retained commands, expired commands, future timestamps and old revisions
are rejected. The actual upper-level transport must provide authenticated
client identity, command IDs, time synchronization and access control.
The `clientId` string alone is **not authentication**. The module's
revision/TTL contract is a design candidate, not a claim that HA,
HomeKit or Alice currently provide this envelope.

## What is explicitly NOT done

- No modification to `23_heating_living_manager.js` or physical K1–K11/K4.
- No installation on WB, and no deletion of existing HA rules.
- All eight WB-local temperature channel IDs are verified against active
  WebUI `Климат` and WB MQTT on controller `AFMEUYOT`. The original
  HA thermostat sensor and climate entity IDs are recovered from the
  contemporaneous HA handoff document dated 2026-09-07, which says
  `master_bedroom` **intentionally** uses sensor 47 in its wardrobe.
  ONOKOM 9 read 0°C when the AC was off, so it is not the heating input.
  Current HA runtime configuration (after the handoff) is not checked.
  Do not mark this object commissioned: local setpoints, health adapter,
  fallback, storage, and writer cutover are still unapproved.
- No thermostat setpoints, fallback duty-cycle or heating limits chosen
  for Iset. Test fixtures (22 °C etc.) are not approved settings.
- `HHMRoomPathGate.js` now **calculates a START permission only** after
  an accepted NO=0 command/readback on every actuator of a requested
  zone, a 180s fixture delay, and a matching `bootEpoch`. A missing
  demand means HOLD the actuator proposal, **not** CLOSE. Independent
  protection blocks proposals to open; no physical outputs are written.
  Output readback + time does not prove stem position or actual flow.
- No physical NO-actuator writer, complete pump deadhead protection,
  pump OFF/postrun policy, PWM of reserve heating or output ownership
  transfer is implemented here. The real K4 owner must enforce these.
- A working `PersistentStorage` usage example exists at
  `objects/04_22_Danilovsky/Wirenboard/wb-rules/44_master_scenes.js`.
  Nevertheless, the Iset HHM persistent storage adapter, power-loss
  durability/restore checks and UI bridge/authorization are **not yet
  implemented or validated**. Readback of an in-memory JS property does
  not prove physical disk persistence.
- No full HHM/NST release or physical commissioning. Separate gates.

## Tests

Run on a developer computer (not on WB):

```sh
node Systems/HHM/tests/room-thermostats.js
node Systems/HHM/tests/iset-room-map.js
node Systems/HHM/tests/room-path-gate.js
node Systems/HHM/tests/room-sensor-evidence.js
node Systems/HHM/tests/room-mqtt-read-evidence.js
node Systems/HHM/tests/room-serial-load-evidence.js
```

Object mapping evidence and current room-sensor audit:
`Objects/05_16_Iset/Doc/HHM_ROOM_THERMOSTATS_BASELINE_20261018.md`.
WebUI SHA256 `8c08f64fd2e8186948fada6b3388bb1fc6ae832835e61187b1db9bbe06a8666a`.
HA historical handoff: `C:\\Users\\psv76\\Downloads\\05_16_Исеть_Home_Assistant_передача_изменений_термостаты_воздух.docx` (2026-09-07).
That document reports HA sensor entity registry unique IDs were checked
against the WB-MSW numbers; it is historical, not current HA API access.
All test scripts operate only in memory; no MQTT messages or physical writes.
