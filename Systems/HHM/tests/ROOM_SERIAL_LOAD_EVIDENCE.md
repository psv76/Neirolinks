# WB-MSW: local serial RPC read evidence candidate (#204 / PR #206)

**Status: offline only; no Wiren Board rule, MQTT transport, deployment,
source setpoint or relay writer is provided.** The eight Iset room sensors
are identified in `Objects/05_16_Iset/HHM/room_zones.js`; no room is commissioned.

## Why regular MQTT Temperature cannot prove a fresh poll

`wb-mqtt-serial` documents `max_unchanged_interval=-1` as the default:
unchanged register values may have no new MQTT publish, even though
Modbus polling continues. `max_publish_interval` can resend the last cached
value independently of a fresh register read. Retained `/devices/.../controls/
Temperature` is therefore neither a poll timestamp nor positive health proof.
Device `/meta/error` can supply negative/clear diagnostics but no guaranteed
per-channel consecutive successful polls. Do NOT synthesize
`WB_LOCAL_MODBUS_POLL` from a cached reading, a clear-error event or a clock tick.

Official driver documentation:
https://github.com/wirenboard/wb-mqtt-serial (README: publication intervals,
"Чтение каналов и параметров устройств" and device/Load RPC).
Schema: https://github.com/wirenboard/wb-mqtt-serial/blob/master/wb-mqtt-serial-rpc-device-load-request.schema.json

## Candidate: direct read-only device/Load

The documented driver RPC request is published to
`wb-mqtt-serial/device/Load/<unique_client_id>` with JSON:

```json
{"device_id":"wb-msw-v4_22","channels":["Temperature"]}
```

The matching reply topic is the request topic plus `/reply`.
Expected JSON envelope is `{ "id": <number>, "error": null,
"result": { "channels": { "Temperature": <number> } } }`.
Unlike `device/LoadConfig`, the documented `device/Load` is an actual
read of device channels through the driver. It adds RS-485 traffic; there is
**no** default poll interval or permission to publish real requests in this PR.

`core/HHMRoomSerialLoadEvidence.js` accepts the `HHMRoomSensorEvidence`
module through dependency injection (as in the existing HHM core), without a
Node-specific relative `require` in production code. It only PLANS a request and EVALUATES a
received reply. `request(now, bootEpoch)` returns `send`, `topic`, `payload`,
`retained:false` and the exact `replyTopic`. It does not publish anything.
The later `reply({nowMs, bootEpoch, topic, retained:false, payload})` requires:

- Same process/boot epoch; one current pending request, a **unique reply
  topic per request** and expiration before `replyTimeoutMs`.
- Exact non-retained reply topic, `error:null`, numeric `id` and
  `result.channels.Temperature` carrying a finite/in-range number.
- Successful result produces a newly numbered, local
  `HHMRoomSensorEvidence.observePoll` event; even an unchanged temperature
  then counts as a new reading. Failed/timeout RPC invalidates old health.
- A stale, unsolicited, duplicate, different-sensor, old-boot or malformed
  reply cannot qualify a room. Response readback is not proof of physical
  installation location or overall heating safety.

The WB-local transport (NOT included here) must keep `clientPrefix` unique
per process lifetime and sensor, authenticate its own MQTT subscription,
subscribe to the intended RPC reply namespace before requesting, use a
monotonic local clock and actual WB boot identity, pass the MQTT retain flag,
and ensure only `device/Load` replies (never `device/Set`, `device/SetPoll`
or `device/LoadConfig`) are routed here. No retained publish or write to
physical outputs is permitted. A retained spoof or third-party MQTT publisher
cannot be considered trustworthy merely from its topic name.

This is a **candidate poll provenance** strategy, not yet a field-verified
`wb-mqtt-serial` adapter. We have not inspected a genuine live `device/Load`
reply for `wb-msw-v4_22` or verified the installed driver's exact response
shape. Any mismatch must fail closed instead of introducing a permissive
parser. On the active WB, diagnostics and `meta/error` handling will need
separate observational qualification; an optional direct RPC probe is NOT a
replacement for independent hardware protections.

## Gates before any WB integration / install

1. Read only: inspect installed `wb-mqtt-serial` version, current
   `/etc/wb-mqtt-serial.conf` / device template and `meta/error` behavior.
2. Establish a bus traffic budget: poll intervals per sensor, replies and
   timeouts, RS-485 queue utilization and service load. Running eight extra
   high-priority RPC reads is NOT pre-approved.
3. In a separately authorized non-actuating test, observe genuine replies,
   confirm `id`, channel names, numeric format, error/timeout semantics,
   broker lifecycle, behavior at driver reboot, and uniqueness of reply topics.
4. Implement a WB-local authenticated transport that never uses its own
   retained values as positive evidence. Verify startup, clock changes,
   missing replies, wrong sensor, errors, driver crash, boot/restart and
   recovery. Only then choose object `freshMs`, request scheduling, hold
   duration and fallback policy; current test numbers are synthetic.
5. Preserve `commissioned=false`, the existing physical HM2 writer and
   Gate A/B/E/F restrictions of Issue #204 until full cutover review.

Offline tests (no MQTT or physical commands):

```sh
node Systems/HHM/tests/room-serial-load-evidence.js
```
