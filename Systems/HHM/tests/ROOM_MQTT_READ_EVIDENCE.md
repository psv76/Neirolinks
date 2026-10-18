> **ЭКСПЕРИМЕНТ, НЕ ПРИМЕНЯТЬ НА ИСЕТИ (решение 18.10.2026).**
> Разработка пассивной проверки достоверности прекращена для объекта
> 05 16 Исеть. Оставлена лишь исследовательская реализация/тесты.
> НЕ изменять `wb-mqtt-serial.conf` ради этой функции.
> Актуальная простая политика: `Objects/05_16_Iset/Doc/HHM_ROOM_SIMPLE_POLICY.md`.

# HHM #204 / Iset: passive read-bound WB-MSW MQTT health (PR #206)

**Status: OFFLINE/DRAFT. Does not modify live Wiren Board, driver configuration,
MQTT broker, room settings, actuators, pumps, HA, or NST.**

## Actual driver and evidence (2026-10-18, SSH read-only)

- Controller `AFMEUYOT`, Debian 13.7; `wb-mqtt-serial 2.268.0-wb102`
  running and active.
- Config: `/etc/wb-mqtt-serial.conf` ->
  `/mnt/data/etc/wb-mqtt-serial.conf`;
  SHA256 `6f05f8fcf239595c0854c5fbe6de9769468d22a3ba629a2c237adf0f1ee7b9e7`.
- Top-level `max_unchanged_interval` **ABSENT**. In version 2.268,
  this means the documented default **-1**: an unchanged
  `Temperature` sample need not produce any new MQTT message.
- Eight WB-MSW v4 sensors 22, 47, 53, 52, 54, 116, 43, 106 are
  all on `/dev/ttyRS485-2`, 9600 baud, 8N2, 24 devices on this bus.
- Passive broker **metadata** snapshot (not live message rate):
  1323 matching `/devices/+/controls/+/meta/type` messages in
  a 4-second subscription, 164 with WB-MSW v4 identifiers.
  These are metadata retained/initial-delivery counts and are NOT
  measurements of the normal polling rate or of future MQTT traffic.
- No driver restart, config edit, Modbus RPC or physical command
  was executed. The single `device/Load` attempt in the earlier
  session was blocked before execution and is not being retried.

## Manufacturer evidence pinned to deployed version

Read the **tagged upstream base-version** documentation, not only `master`.
The installed package suffix `-wb102` is a packaging revision; the exact
compiled binary was **not** matched to a checked-out source tree, so tagged
upstream semantics still require operational validation:
https://github.com/wirenboard/wb-mqtt-serial/blob/v2.268.0/README.md

It explicitly defines `max_unchanged_interval` in **seconds**:
- `-1` default: publish changed values only;
- `0`: publish every read value;
- positive interval: after the interval, publish unchanged
  **obtained** values, no more frequently than channel reads;
- positive values 1–4 are clamped to 5 seconds.

The schema on the same release places `max_unchanged_interval` at
the **global/root** level:
https://github.com/wirenboard/wb-mqtt-serial/blob/v2.268.0/wb-mqtt-serial-ports.schema.json

An unrelated `max_publish_interval` cached republisher was introduced
in 2.270.0 and is not available in the currently installed 2.268.0:
https://github.com/wirenboard/wb-mqtt-serial/blob/master/debian/changelog

**Engineering inference requiring commissioning:** once a positive
read-bound interval has been configured and the driver version is pinned,
a newly published non-retained `Temperature` is a *candidate*
for proof of a completed normal channel read without an added
RS-485 `device/Load`. It does NOT by itself prove sensor placement,
temperature correctness, a healthy network of other controllers,
active boiler heating, relay position, water flow, or authenticated
MQTT publisher identity.

## Pure ES5 implementation

`core/HHMRoomMqttReadEvidence.js` is a **passive evaluator** with:
- `qualifyPolicy(frame)`: requires explicit local service+config
  audit, exact approved SHA, exact driver version, positive read-bound
  interval, verified absence of cache republish, boot and process epochs.
  No policy, mismatched file, absent interval, or changed version =>
  NOT QUALIFIED, never infer it from MQTT temperature alone.
- `observeTemperature(frame)`: only a new **non-retained** publication
  on the exact room Temperature topic, from a trusted local transport,
  in the same WB/driver process session, with finite temperature in
  configured range, can enter thermostat sampling.
  `observedAtMs` is the trusted monotonic local *receive* time, not
  an invented Modbus timestamp. Unchanged numeric temperature may be a
  legitimate new publish under the qualified read-bound policy.
- `observeError(frame)`: normalised device-level `meta/error`
  fault immediately revokes the reading. Recovery after a real fault
  requires a **non-retained** clear indication and a later newly
  received Temperature. A retained clear is never sufficient.
  Exact payload/error normalization belongs to the missing WB adapter.
- `sample(now,bootEpoch,driverEpoch)`: returns thermostat contract
  `{id,temperatureC,ok,observedAtMs,reason}`. Staleness, reboot,
  driver restart or local monotonic clock rewind => `ok=false`.
  No channel or MQTT output is written. Unknown is not OFF.

**Security/operations boundary:** this core code cannot authenticate
the publisher, read a real `systemd` process epoch, hash the active
file, verify the driver running build, subscribe with retain flags, or
detect broker/service reconnection itself. All that MUST be provided
by a separately reviewed, local WB adapter. Synthetic flags such as
`qualifiedLocalTransport=true` do not constitute independent proof
without that adapter. The 30s unchanged interval, 90s fresh TTL,
temperature limits and example SHA in offline tests are **fixtures**,
not operational settings or an approved Iset configuration.

## Tests and the physical implications

```sh
node Systems/HHM/tests/room-mqtt-read-evidence.js
```

22 offline tests verify positive/negative policy qualification, MQTT
retain, wrong sensor, errors, retained clear, old service epoch,
clock rollback, freshness, repeat same numeric value and the
`sensor -> SENSOR_HOLD -> NO gate` integration, including no
command to close a running zone on temporary sensor absence.
Run alongside existing 108 tests in PR #206. Offline replay is
NOT field commissioning.

## Preferred design / gates before changing the live driver

1. Prefer **normal polling + read-bound MQTT publications** instead
   of adding high-priority `device/Load` requests on the 24-device
   9600-baud bus, provided exact driver 2.268 semantics are verified
   against real on-device observation.
2. Draft a controlled, backup-backed change to the **global**
   `max_unchanged_interval`. Determine interval only after measuring
   effective polling turnaround and resulting MQTT message rate,
   accounting for all devices and channels, not only eight WB-MSW.
3. A driver restart may interrupt every Modbus service on that
   process, including existing HM2 monitoring/control. **Separate
   approved service window, cutover/rollback and functional safety
   review are required**. No change or restart has been executed.
4. Implement trusted local event transport/provenance and verify
   `meta/error` payloads and recovery order, retain semantics,
   service reboot, OTA upgrades and outage injection before enabling.
5. Do not commission unapproved room setpoints, fallback duty cycle,
   `freshMs`, `sensorLossHoldMs`, or physical single writer
   K1–K11/K4. `room_zones.commissioned=false` and HM2 remains live.
