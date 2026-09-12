# HM2 — source writer and thermal response watchdog contract

Status: draft for review.  
Scope: common Heating Manager 2.0 rules. No object MQTT addresses, relay numbers, sensors or setpoints are defined here.

Related issues:

- #18 — Heating Manager 2.0 common development;
- #19 — 05 16 Iset production review evidence;
- #20 — 05 31 Ivolga object adaptation;
- #39 — this common source/response contract task.

## 1. Purpose

This document defines the transferable HM2 contract for:

- the single source writer;
- source response watchdog;
- consumer thermal response watchdog;
- latched-fault interaction with arbiter;
- runtime status separation.

The contract is based on field evidence from Iset, but it intentionally does not copy Iset physical bindings. Each object must provide its own source endpoint, sensors, pumps, valves, limits, timing and commissioning decisions.

## 2. Proven failure mode from Iset

The reusable lesson is not an object address. The reusable lesson is the failure mode:

```text
logical demand exists
source can be hot
hydraulic path may be commanded
but the measured circuit temperature does not react
```

HM2 must not treat this as a valid active heating request indefinitely.

A second proven failure mode is contract leakage after a latched circulation fault:

```text
consumer has fault_latched=true
but still publishes state=ACTIVE / valid=1 / requested temperature
arbiter accepts it
source keeps serving a physically dead request
```

HM2 therefore requires two independent protections:

1. the consumer manager must make its own request invalid when fault-latched;
2. the arbiter must independently reject any request with `fault_latched=true`.

## 3. Terms

| Term | Meaning |
|---|---|
| source | Boiler, heat pump, buffer, hydraulic source or another heat generator controlled by HM2. |
| source writer | The only HM2 component allowed to write the source setpoint / source enable command. |
| consumer | A circuit or subsystem requesting heat from the source. |
| request | Fresh bounded consumer contract passed to the arbiter. |
| path_ready | Physical circulation path is allowed to be considered ready after actuator/pump delays and readbacks. |
| thermal response | Measured temperature movement proving that heat is actually transferred. |
| latched fault | Persistent fault state that requires explicit reset/commissioning action. |
| commissioning debt | Planned not-ready state because a subsystem has not been commissioned. |
| runtime fault | A fault of a commissioned subsystem while it was expected to work. |

## 4. Base architecture

```text
consumer manager
  -> bounded heat request
  -> demand arbiter
  -> source manager / source writer
  -> physical source endpoint
```

Required rule:

```text
one physical source endpoint -> one writer
```

No watchdog, diagnostic script, thermostat, scene, user-interface helper or object-specific commissioning tool may write the source endpoint directly.

## 5. Consumer request contract

Each consumer manager must publish one atomic request contract.

Minimum fields:

| Field | Required behavior |
|---|---|
| `state` | `ACTIVE`, `INACTIVE`, `UNKNOWN` or `FAULT`. |
| `valid` | True only when required inputs are fresh and the consumer may participate in arbitration. |
| `heat_demand` | True only when the consumer currently needs heat. |
| `requested_source_temperature` | Numeric requested source temperature after object limits, or 0/empty when no valid demand exists. |
| `request_timestamp` | Time of calculation. |
| `request_ttl_s` | Explicit validity window. |
| `path_ready` | True only after the actuator/pump circulation path is expected to be physically available. |
| `fault_latched` | True when the consumer is locked out by a persistent fault. |
| `status` / `reason` | Human-readable current reason. |

A boolean demand without timestamp and TTL is not a valid HM2 request.

## 6. Arbiter rejection rules

The arbiter must reject a consumer if any of the following is true:

- `valid !== true`;
- `state !== ACTIVE`;
- `heat_demand !== true`;
- `path_ready !== true`;
- `fault_latched === true`;
- requested temperature is absent, non-numeric or <= 0;
- request timestamp is missing, stale or from the future beyond allowed clock tolerance;
- TTL is missing, invalid or expired.

A failed consumer must not block other valid consumers. It is rejected locally and the arbiter continues evaluating the remaining candidates.

## 7. Source writer contract

The source writer is the only component allowed to write the physical source endpoint.

It must:

- read only the arbiter output, not individual consumers directly for control decisions;
- validate the arbiter output freshness;
- apply object-specific minimum/maximum limits;
- apply rate limiting and/or ramp rules where needed;
- apply hysteresis/debounce to avoid setpoint chatter;
- publish intended, limited and actually written setpoint;
- publish state and reason;
- have a commissioned safe-OFF/no-demand behavior;
- reset all live-write gates on startup/reload;
- fail safe when the source endpoint or safe-OFF behavior is not commissioned.

It must not:

- infer physical object addresses from another object;
- allow retained MQTT gates to re-enable source writes after restart;
- let response watchdogs write the source setpoint directly;
- silently choose a safe-OFF method when the source behavior is unknown.

## 8. Source writer gates

The generic live-write path must require all gates:

```text
source_commissioned == true
source_write_enabled == true
manual_source_grant == true or equivalent explicit live grant
arbiter_request_valid == true
safe_limits_valid == true
source_endpoint_confirmed == true
safe_off_commissioned == true
```

On startup/reload:

```text
source_write_enabled = false
manual_source_grant = false
physical_write_grant = false
```

A shadow source manager may calculate intended setpoint, but must keep `physical_write_grant=false` and must not write the source endpoint.

## 9. Source states

Common source states:

| State | Meaning |
|---|---|
| `NOT_COMMISSIONED` | Source writer or safe-OFF contract is not commissioned. |
| `SHADOW_NO_DEMAND` | Shadow calculation, no valid demand. |
| `SHADOW_DEMAND` | Shadow calculation, valid demand exists, no physical write. |
| `NO_DEMAND` | Live source writer is commissioned and no valid demand exists. |
| `STARTING` | Demand exists, source command has been issued, waiting for source response. |
| `WAIT_HOT_SOURCE` | Source setpoint/request exists, but measured source temperature is not yet sufficient. |
| `ACTIVE` | Source is producing/available within expected limits. |
| `SAFE_OFF` | Source is in commissioned no-demand/off state. |
| `INTERLOCK` | Source command is blocked by external/system interlock. |
| `SOURCE_FAULT` | Source failed to respond or reported a source fault. |
| `UNKNOWN` | Required source data is missing/stale. |

## 10. Source response watchdog

The source response watchdog verifies that the configured source reacts to source requests.

It must use object-specific source sensors and source status channels supplied by the object manager/config.

It should check:

- source setpoint/request was actually written or intentionally withheld;
- source temperature becomes valid and moves toward the request;
- source reaches minimum useful temperature within a configured window;
- source fault / invalid connection / interlock channels remain clear;
- safe-OFF/no-demand behavior is consistent with the commissioned policy.

Failure handling:

- source failure must not be represented as a normal no-demand state;
- source fault should block new positive source writes until explicit recovery policy is met;
- consumers should see that heat is unavailable rather than continuing to receive fake successful grants.

## 11. Consumer thermal response watchdog

The consumer thermal watchdog verifies heat transfer to the requested circuit.

For mixed circuits it must distinguish at least:

```text
source temperature valid and hot enough
pump command / pump readback
valve enable / valve position command / valve readback where available
actuator delay / path_ready
supply temperature after mixer
return temperature where available
thermal trend over time
```

For direct circuits it must distinguish at least:

```text
source temperature valid and hot enough
pump command / pump readback
actuator delay / path_ready if zone valves exist
return or circuit temperature
thermal trend over time
```

A positive logical demand does not prove heat transfer. A running pump does not prove heat transfer. An open valve does not prove heat transfer. A hot source does not prove heat transfer to a specific circuit.

## 12. Thermal response policy

The watchdog must not permanent-latch on one borderline sample.

Each object manager must configure:

| Parameter | Purpose |
|---|---|
| `response_window_s` | Main observation window. |
| `response_grace_s` | Extra time near the boundary. |
| `min_rise_c` | Required temperature rise. |
| `min_samples` | Minimum confirming samples. |
| `sample_interval_s` | Measurement cadence. |
| `sensor_valid_ttl_s` | Sensor freshness limit. |
| `source_hot_threshold_c` | Minimum useful source temperature. |
| `max_supply_c` | Hard over-temperature limit for the circuit. |
| `fault_latch_enabled` | Whether this object stage may latch or only report shadow fault. |

Recommended generic decision logic:

```text
if no valid demand:
    response monitor = IDLE
else if source is not confirmed hot:
    response monitor = WAIT_HOT_SOURCE
else if path is not ready:
    response monitor = WAIT_PATH_READY
else if temperature rise >= min_rise_c on enough samples:
    response monitor = RESPONSE_OK
else if main window expired but grace remains:
    response monitor = RESPONSE_GRACE
else if main + grace expired and confirming failed samples exist:
    response monitor = RESPONSE_TIMEOUT
```

Only `RESPONSE_TIMEOUT` after the full configured window may latch a runtime fault.

## 13. Consumer failure behavior

When a commissioned consumer latches a thermal response fault, it must publish:

```text
state = FAULT or UNKNOWN
valid = false
heat_demand = false or request not eligible
requested_source_temperature = 0 / NOT_READY
path_ready = false
fault_latched = true
status/reason = clear fault reason
```

The arbiter must reject it even if any other field accidentally remains active.

The consumer must safe-stop its own owned outputs according to object policy.

Other consumers must remain eligible if their own requests are valid.

## 14. System status separation

HM2 must not overload one `DEGRADED` status for both planned commissioning debt and runtime faults.

Minimum common status model:

| Status | Use |
|---|---|
| `READY` | Commissioned required subsystems are valid and no runtime fault exists. |
| `NOT_COMMISSIONED` | Required subsystem is intentionally not commissioned. |
| `DEGRADED_PLANNED` | System is partially usable with known commissioning debt. |
| `DEGRADED_RUNTIME` | Runtime issue exists, but the system can still serve other valid consumers. |
| `INTERLOCK` | Operation intentionally blocked by safety/interlock. |
| `FAULT` | A fault requires action/reset before normal operation continues. |

Operator views should show runtime fault severity separately from not-commissioned items.

## 15. Commissioning runner constraints

An object-specific commissioning runner may interact with HM2 only through approved controls and scenarios.

It must:

- reject arbitrary command execution;
- whitelist scenarios;
- run one physical scenario at a time;
- require explicit physical/live confirmation for any positive source or pump command;
- install a stop-all trap on error, timeout and interruption;
- log source, consumer, arbiter and physical readbacks;
- treat PASS as scenario-local, not as full production commissioning.

It must not bypass source writer gates or write the source endpoint directly.

## 16. Minimal acceptance checklist for object implementations

Before a source writer or physical runner is accepted on an object:

- source endpoint is confirmed;
- source safe-OFF behavior is confirmed;
- exactly one source writer exists;
- startup/reload resets gates;
- arbiter rejects stale/fault-latched/path-not-ready consumers;
- consumer managers publish request timestamp and TTL;
- consumer thermal response watchdog has grace and confirming samples;
- over-temperature limits are object-specific and explicit;
- failed consumer does not block healthy consumers;
- documentation states whether live tests were actually performed.

## 17. Non-goals

This document does not define:

- object physical channels;
- object setpoints;
- object sensor names;
- object valve direction;
- boiler-specific safe-OFF value;
- production enable procedure for any particular object.

Those belong to the object issue and object documentation.
