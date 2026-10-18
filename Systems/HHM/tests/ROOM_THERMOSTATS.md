# WB-local room thermostat — offline stage (#204, decisions 4–7)

Implementation: `core/HHMRoomThermostat.js` and
`core/HHMRoomPathGate.js`, ECMAScript 5.

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

The primary sensor must be object-mapped. Backup sensor is optional,
and may be used only when its placement and physical suitability for
the same room have been explicitly validated. Primary re-qualification
requires distinct healthy observations, time and sample count.

If neither sensor is valid, the module does **not** use the last sample
forever and does not translate `UNKNOWN` to `OFF`. The object-specific
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
- No verified `PersistentStorage` adapter or UI bridge/authorization.
- No full HHM/NST release or physical commissioning. Separate gates.

## Tests

Run on a developer computer (not on WB):

```sh
node Systems/HHM/tests/room-thermostats.js
node Systems/HHM/tests/iset-room-map.js
node Systems/HHM/tests/room-path-gate.js
```

Object mapping evidence and current room-sensor audit:
`Objects/05_16_Iset/Doc/HHM_ROOM_THERMOSTATS_BASELINE_20261018.md`.
WebUI SHA256 `8c08f64fd2e8186948fada6b3388bb1fc6ae832835e61187b1db9bbe06a8666a`.
HA historical handoff: `C:\\Users\\psv76\\Downloads\\05_16_Исеть_Home_Assistant_передача_изменений_термостаты_воздух.docx` (2026-09-07).
That document reports HA sensor entity registry unique IDs were checked
against the WB-MSW numbers; it is historical, not current HA API access.
Both tests operate only in memory; no MQTT messages or physical writes.
