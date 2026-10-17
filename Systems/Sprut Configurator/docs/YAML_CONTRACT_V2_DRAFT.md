# Sprut plan YAML contract — format_version 2 DRAFT

Status: Issue #22 working draft. `Service.visible`, `Characteristic.statusVisible` and Alice/Yandex bridge read/create/delete have been field-confirmed on the real Sprut WebUI.

## 1. Purpose

Version 2 extends the proven v1 desired-state contract with Sprut presentation policy while preserving stable matching by SERIAL and runtime resolution of internal Sprut IDs.

The contract describes **desired state for one currently opened Sprut.hub**. It never stores `aId`, `sId`, `cId`, `roomId`, token, cid or Sprut session serial.

## 2. Deployment boundary: one YAML → one active hub

A YAML file does **not** contain `target_hub`, hub serial or another persistent hub-routing field.

Operator workflow is intentionally explicit:

```text
open required Sprut.hub in WebUI
→ capture/use that hub session
→ select the YAML prepared for this hub
→ DISCOVER
→ DRY RUN
→ APPLY
→ VERIFY

then repeat for the next hub
```

For an object with several independent hubs it is normal to have several plan files, for example:

```text
sprut_plan_dom.yaml
sprut_plan_besedka.yaml
sprut_plan_kotelnaya.yaml
```

The filename is an operator/deployment aid, not a runtime identity contract.

This boundary is deliberate: physical building membership and Sprut.hub deployment are not necessarily the same thing. On Ivolga, for example, the separate `Котельная` hub contains heating-circuit presentation for the house, gazebo and utility block. Therefore automatic `building → hub` routing would encode a false domain assumption.

If Project exports several plans, selection/routing belongs to the export operation or an external export profile, not to every normalized device entity.

## 3. Schema

```yaml
format_version: 2
object: optional human-readable context

accessories:
  - serial: "<stable serial>"
    name: "<Accessory display name>"
    room: "<existing Sprut room name>"

    services:
      - type: "<Sprut Service type>"
        match_name: "<optional exact current Service name selector>"
        name: "<Service display name>"
        visible: true | false

        status:
          <CharacteristicType>: true | false

        bridge:
          alice: true | false
```

`match_name` is optional. It is needed only when one Accessory contains several non-system Services with the same `type`.

## 4. Why `bridge` is inside Service

Real Sprut WebUI operations address bridge membership by both `aId` and `sId`, therefore Alice membership is **Service-scoped presentation state**, not an Accessory-wide property.

Accessory-level form is rejected as ambiguous.

## 5. Living-room example

```yaml
format_version: 2
object: "05 31 Иволга 13 — Дом"

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

## 6. Matching

Accessory:

```text
serial
```

Service by default:

```text
type inside the matched Accessory
```

If that gives exactly one non-system Service, matching is complete.

When several Services inside one Accessory have the same type, format v2 may use the optional exact selector:

```yaml
- type: C_VoltMeter
  match_name: Напряжение L2
  name: Напряжение L2
```

Then matching is:

```text
type + exact current Service.name
```

The selector exists specifically to avoid persisting runtime `sId` in YAML. If `type + match_name` finds zero or more than one Service, DRY RUN returns `ERROR`; no fallback to an arbitrary Service is allowed.

Initial v0.3.1 implementation deliberately requires:

```text
match_name == name
```

Thus a duplicate-type Service can be selected safely, but it cannot simultaneously be renamed in the same pass. This keeps fresh DISCOVER → VERIFY stable after APPLY. A future contract may introduce a separate immutable Service identity if Sprut exposes one.

Characteristic for status policy:

```text
Characteristic.type
or, when DISCOVER exposes type there,
Characteristic.control.type
```

If matching is missing or ambiguous, DRY RUN returns `ERROR`; runtime IDs are never guessed.

## 7. `services[].visible`

Desired runtime value of `Service.visible`.

Field-confirmed WebUI write shape:

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

## 8. `services[].status`

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

If DISCOVER does not contain `statusVisible` for the requested Characteristic, DRY RUN fails closed.

## 9. `services[].bridge.alice`

Desired membership of this Service in `Yandex_1`.

Read:

```json
{"params":{"bridgeService":{"list":{"bridgeIndex":"Yandex_1"}}}}
```

Membership is determined by exact `(aId, sId)` presence in `result.bridgeService.list.services`.

Enable:

```json
{"params":{"bridgeService":{"create":{"bridgeIndex":"Yandex_1","aId":118,"sId":13,"write":true}}}}
```

Disable:

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

Thus `bridge.alice` participates in the same full desired-state cycle as other presentation properties.

## 10. Validation

Format v2 validates at least:

- `format_version == 2`;
- all proven v1 structural/name rules;
- optional `match_name` is a non-empty string;
- in v0.3.1 `match_name == name`;
- duplicate Service types are accepted only when the selector makes each requested Service unambiguous;
- `visible` is boolean;
- every status value is boolean;
- status key is a non-empty Characteristic type string;
- `bridge` is allowed only inside Service;
- `bridge.alice` is boolean;
- unknown bridge fields are rejected.

## 11. Safety

Every plan is applied only to the currently active Sprut.hub session:

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

Configurator does not silently switch hubs and does not infer a target hub from the YAML.

A wrong YAML should fail at DRY RUN when stable identities/services do not resolve; APPLY is never allowed on a DRY RUN with errors.
