# HHM sensor loss: draft core integration (#204 / PR #205)

Status: **offline code only**. Nothing here is installed on a Wiren Board.
No object is opted into this feature. Numerical values in tests are
**synthetic fixtures** (15 s HOLD, 18% limit, 10 s recovery), not field
setpoints or a physical-safe value for Iset/Ivolga.

## What is implemented

- `HHM3SensorLossPolicy.js`: pure ES5 state machine.
- `HHM3Circuit.js`: optional `c.sensorLossPolicy` activates the state
  machine; absent config preserves the previously approved execution path.
  Common `pumpPostrunMs` is now required and checked at creation.
- `HHM3Mixing.js`: `resumeAfterSensorGap(confirmedPct)` keeps valve
  position and move/hold memory while invalidating derivative/filter data.
- `adapters/HHM3Mao4Output.js`: candidate reusable WB-MAO4 single-writer
  adapter based on the approved Ivolga A05 output contract. Under `HOLD`
  it **never writes valve Level/Switch**, while maintaining the previously
  authorized pump command only with a qualified path and matching output
  readback. `NO_COMMAND` writes nothing at all and does not discard the
  accepted valve position. Legacy `APPLY` open/close semantics are preserved.
  This module is NOT connected to a deployed object or `rule 500`.
- `Circuit.result.mixing`: exposes `status`, `sensorFault`,
  `alarmActive`, `sourceGuardActive` etc. This is a **calculated mixer
  snapshot, not proof of physical delivery** (#191).
- `Circuit.result.sensorLossState` and `valveAction`: independent
  diagnostics for the downstream output adapter.

State sequence:
`NORMAL → HOLD_LAST_ACCEPTED → LIMITED_HEAT → RECOVERY_HOLD → NORMAL`.
A recovered sample alone does not reset the grace period. With confirmed
accepted output evidence, stable recovery resumes from that position. If
no previously accepted output position can be established (e.g. a cold
boot), stable sensor recovery takes the normal **bounded cold-start**
path instead of waiting forever for impossible output proof.

## Mandatory object-side contract (NOT IMPLEMENTED YET)

An enabled `Circuit` must receive these values each evaluation:

| Input | Meaning |
|---|---|
| `sensorValid` | health-qualified, fresh local sensor, e.g. M1W2 Sensor OK + error policy |
| `hydraulicPathReady` | independently confirmed hydraulic permission; not a guessed flow |
| `protectionActive` | explicit boolean from independent real protection checks; unknown is not false |
| `fallbackAuthorized` | approved autonomous heating arrangement, including startup-cap check |
| `independentLimitOk` | independent thermal evidence allows that specific valve limit |
| `valveActionSupported=true` | output adapter really honors all three `valveAction` codes |
| `acceptedValveConfirmed` + `acceptedValvePct` | last accepted output command from the **actual owner**, not the virtual mixer calculation |

`valveAction` is `APPLY`, `HOLD`, or `NO_COMMAND`. The historical
**Ivolga `outputSteps` still does not consume this field**. The new common
MAO4 adapter provides an implementation candidate but is **not wired to the
Ivolga or Iset object rule**. Do not deploy with the existing output adapter.
`HOLD` means do not send a valve command;
`NO_COMMAND` returns no output write while retaining previously accepted
output/readback evidence if still consistent. It does **not** assert a fresh
pump permission or an automatic source grant. The source requests need a separately
documented handling policy; retain independent pump control according
to a qualified open path. `APPLY` is a calculated request and does not
prove valve stroke, water flow or confirmed readback.

Do not accept a passed `valveActionSupported` flag without auditing
the physical writer. A valve level readback is not proof of actual
mixing movement. When a real thermal protection is active, that
protection overrides the HOLD/limited request. The source-independent
protection path is not implemented by this decision module.

## Open blockers before integration/commissioning

1. Object mapping and sensor health provenance for Iset and Ivolga.
2. Validated hot-port direction, independent max temperature, NO
   actuator paths/bypass, K2/K4 pump ownership and source continuity.
3. Integrate and review the common MAO4 output adapter with real object
   `outputSteps` and the single writer. Verify initialization, output
   handshake, readback faults, authority transfer, and no false pump OFF.
4. Full output acceptance/readback and operator journal transitions.
5. Explicitly approved HOLD and fallback values with startup cap and
   worst-case sensor outage consideration; model cold-start, network
   recovery and unexpected stopped circulation.
6. Hardware-independent replay plus physical PNR and rollback.

Do not infer object-safe 18% from test settings. In particular, when
the pump is still in the normal startup opening cap, a larger fallback
position must not be enabled without a verified commissioning contract.

## Offline tests

```sh
node Systems/HHM/tests/sensor-loss-policy.js
node Systems/HHM/tests/circuit-sensor-loss-integration.js
node Systems/HHM/tests/mao4-output-actions.js
# Or the aggregate test runner:
node Systems/HHM/tests/run.js
```

The tests have no MQTT, no wb-rules runtime, no real actuator and no
hardware feedback. A PASS is not an approved HHM release, a physical
acceptance, or permission to change an active controller.
