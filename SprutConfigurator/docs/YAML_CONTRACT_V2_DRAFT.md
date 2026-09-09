# Sprut plan YAML contract — format_version 2 DRAFT

Status: Issue #22 working draft. `Service.visible` and `Characteristic.statusVisible` have field-confirmed write RPC. Alice remains fail-closed until current-state read and enable/create RPC are confirmed.

## 1. Purpose

Version 2 extends the proven v1 desired-state contract with Sprut presentation policy while preserving stable matching by SERIAL and runtime resolution of internal Sprut IDs.

The contract describes **desired state**. It never stores `aId`, `sId`, `cId`, `roomId`, token, cid or Sprut session serial.

## 2. Schema

```yaml
format_version: 2
object: optional human-readable context

accessories:
  - serial: "<stable serial>"
    name: "<Accessory display name>"
    room: "<existing Sprut room name>"

    services:
      - type: "<Sprut Service type>"
        name: "<Service display name>"
        visible: true | false

        status:
          <CharacteristicType>: true | false

        bridge:
          alice: true | false
```

## 3. Why `bridge` is inside Service

The real Sprut WebUI command captured on 2026-09-10 disables Alice/Yandex bridge membership using both `aId` and `sId`:

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

Therefore Alice membership is treated as **Service-scoped presentation state**, not a property of Accessory alone.

The earlier draft form:

```yaml
bridge:
  alice: true
```

at Accessory level is rejected as ambiguous.

## 4. Living-room example

```yaml
format_version: 2
object: "05 31 Иволга 13"

accessories:
  - serial: "NL_simple_thermostat_010"
    name: "Воздух"
    room: "Гостиная"
    services:
      - type: "Thermostat"
        name: "Воздух"
        visible: true
        status:
          CurrentHeatingCoolingState: true
          CurrentTemperature: true
        bridge:
          alice: true

  - serial: "NL_simple_thermostat_611"
    name: "Пол"
    room: "Гостиная"
    services:
      - type: "Thermostat"
        name: "Пол"
        visible: true
        status:
          CurrentHeatingCoolingState: false
          CurrentTemperature: false
        bridge:
          alice: false
```

## 5. Matching

Accessory:

```text
serial
```

Service:

```text
type inside the matched Accessory
```

Characteristic for status policy:

```text
Characteristic.type
or, when DISCOVER exposes type there,
Characteristic.control.type
```

If matching is missing or ambiguous, DRY RUN returns `ERROR`; runtime IDs are never guessed.

## 6. `services[].visible`

Desired runtime value of `Service.visible`.

Field-confirmed WebUI write shape:

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

Configurator resolves `aId` and `sId` from fresh DISCOVER.

The boolean value is part of desired state and participates in:

```text
DISCOVER → diff → DRY RUN → APPLY → fresh DISCOVER → VERIFY
```

## 7. `services[].status`

Map from stable Characteristic type to desired `Characteristic.statusVisible`.

Example:

```yaml
status:
  CurrentHeatingCoolingState: true
  CurrentTemperature: false
```

Field-confirmed WebUI write shape:

```json
{"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}}
```

Configurator resolves `aId`, `sId` and `cId` from fresh DISCOVER.

If DISCOVER does not contain `statusVisible` for the requested Characteristic, the state is treated as unknown and DRY RUN fails closed.

## 8. `services[].bridge.alice`

Desired membership of this Service in the Alice/Yandex bridge.

Captured disable command:

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

This confirms:

- operation family `bridgeService`;
- removal operation `delete`;
- bridge index `Yandex_1` on the current hub;
- membership address uses `aId + sId`.

It does **not** yet confirm:

- how current membership is read for DRY RUN / VERIFY;
- exact enable/create command.

Therefore any plan containing `bridge.alice` remains fail-closed until those two pieces are captured from real WebUI traffic.

## 9. Validation

Format v2 validates at least:

- `format_version == 2`;
- all proven v1 structural/name rules;
- `visible` must be boolean;
- every status value must be boolean;
- status key must be a non-empty Characteristic type string;
- `bridge` is allowed only inside Service;
- `bridge.alice` must be boolean;
- unknown bridge fields are rejected.

## 10. Safety

No presentation field may bypass the established sequence:

```text
DISCOVER
→ structural validation
→ diff
→ DRY RUN
→ user confirmation APPLY
→ write only CHANGE actions
→ fresh DISCOVER
→ VERIFY
```

If a write or read contract is not field-confirmed, Configurator must stop before any partial APPLY rather than mix confirmed and guessed operations.
