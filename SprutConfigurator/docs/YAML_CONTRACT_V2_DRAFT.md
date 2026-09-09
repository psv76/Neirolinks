# Sprut plan YAML contract — format_version 2 DRAFT

Status: Issue #22 working draft. Not production-ready until write RPC are field-confirmed.

## 1. Purpose

Version 2 extends the v1 desired-state contract with user presentation policy while preserving stable matching by SERIAL and runtime resolution of Sprut internal IDs.

The contract describes **what Sprut must look like**, not how the WebSocket write is encoded.

## 2. Proposed schema

```yaml
format_version: 2
object: optional human-readable context

accessories:
  - serial: "<stable serial>"
    name: "<Accessory display name>"
    room: "<existing Sprut room name>"

    bridge:
      alice: true | false

    services:
      - type: "<Sprut Service type>"
        name: "<Service display name>"
        visible: true | false

        status:
          <CharacteristicType>: true | false
```

Example for a living room:

```yaml
format_version: 2
object: "05 31 Иволга 13"

accessories:
  - serial: "NL_simple_thermostat_010"
    name: "Воздух"
    room: "Гостиная"
    bridge:
      alice: true
    services:
      - type: "Thermostat"
        name: "Воздух"
        visible: true
        status:
          CurrentHeatingCoolingState: true
          CurrentTemperature: true

  - serial: "NL_simple_thermostat_611"
    name: "Пол"
    room: "Гостиная"
    bridge:
      alice: false
    services:
      - type: "Thermostat"
        name: "Пол"
        visible: true
        status:
          CurrentHeatingCoolingState: false
          CurrentTemperature: false
```

## 3. Semantics

### `services[].visible`

Desired value of runtime `Service.visible`.

- `true` — Service tile is visible on Sprut desktop/room UI;
- `false` — Service remains present but its tile is hidden.

This is presentation state only. It does not create or delete a Service.

### `services[].status`

Map keyed by Sprut Characteristic `type`.

Each boolean is the desired runtime `Characteristic.statusVisible` value.

Example:

```yaml
status:
  CurrentTemperature: true
  CurrentHeatingCoolingState: false
```

Configurator must resolve the Characteristic inside the uniquely matched Service by `type` and compare the current `statusVisible` value.

If the requested Characteristic type is absent or ambiguous inside the Service, DRY RUN must fail with `ERROR`.

### `bridge.alice`

Desired Alice bridge exposure policy for the Accessory/Service according to the actual granularity exposed by Sprut WebUI.

The final RPC shape and exact matching level are intentionally **not fixed in this draft**. They must be captured from a real outgoing WebUI message before APPLY support is enabled.

If field testing shows Alice bridge membership is Service-granular rather than Accessory-granular, the schema will be adjusted before production use. The semantic requirement remains explicit per-user presentation entity.

## 4. Matching rules retained from v1

Accessory:

```text
serial
```

Room:

```text
exact room name
```

Service:

```text
type inside matched Accessory
```

Characteristic status target:

```text
Characteristic.type inside matched Service
```

No Sprut internal IDs are stored in YAML.

## 5. Required validation

In addition to v1 validation:

- `visible` must be boolean when present;
- `status` must be a mapping when present;
- every status value must be boolean;
- Characteristic type keys must be non-empty strings;
- `bridge` must be a mapping when present;
- `bridge.alice` must be boolean when present;
- a requested status Characteristic must exist exactly once in the matched Service;
- unsupported write properties must block APPLY rather than silently falling back to manual changes.

## 6. Required diff/action kinds

Configurator v2 must be able to produce at least:

```text
accessory_name
room
service_name
service_visible
characteristic_status_visible
alice_bridge
```

Each action must participate in:

```text
DISCOVER
→ DRY RUN
→ APPLY
→ fresh DISCOVER
→ VERIFY
```

## 7. DISCOVER source fields already observed

Current `accessory.list expand=services,characteristics` responses expose:

Service:

```text
visible
order
grid
```

Characteristic:

```text
statusVisible
control.read
control.write
control.visible
```

Therefore `visible` and `statusVisible` are readable desired-state properties and can already be included in diff/VERIFY logic.

## 8. Write safety gate

At the draft stage:

- read/diff/VERIFY semantics may be implemented;
- APPLY support for a new property is enabled only after its exact WebUI write RPC is captured and reproduced;
- no RPC is inferred by analogy from `service.update`, `accessory.update` or `characteristic.update` value writes.

Required captures:

1. toggle one Service tile visibility;
2. toggle one Characteristic in room status line;
3. toggle Alice exposure.

Only the sanitized `params` structure is needed. Session token/cid/serial must not be stored in the repository.

## 9. Presentation vs capability

The v2 contract enforces the architectural rule:

```text
physical device capability != mandatory Sprut presentation
```

If a physical temperature is already represented by a thermostat and is not needed as a separate user entity, the correct solution is normally not to create that standalone TemperatureSensor in the Sprut template/plan.

`visible: false` is intended for Services that must remain present but should not have a tile, such as Humidity used in room status.

## 10. Compatibility

`format_version: 1` remains the frozen v0.2.2 baseline.

A v2-capable Configurator may support both versions, but must never reinterpret a v1 plan as if missing presentation fields meant `false`. Missing v2 presentation fields mean **not managed by this plan** unless the final contract explicitly states otherwise.