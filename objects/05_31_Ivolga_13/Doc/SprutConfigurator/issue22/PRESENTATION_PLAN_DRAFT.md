# 05 31 Иволга 13 — Sprut presentation plan DRAFT

Status: working document for Issue #22. Physical channels are based only on current object repository sources.

## 1. Living-room target

For rooms that have both a user air thermostat and a floor thermostat, target Sprut UI:

```text
[ Воздух ] [ Пол ]
```

### `Воздух`

```text
tile visible                         yes
status CurrentHeatingCoolingState    yes
status CurrentTemperature            yes
Alice                                yes
```

### `Пол`

```text
tile visible                         yes
status CurrentHeatingCoolingState    no
status CurrentTemperature            no
Alice                                no
```

Standalone physical TemperatureSensor entities for the same air/floor values are not part of the target presentation.

Humidity remains a separate Service/Accessory only where required by the object model:

```text
tile visible                         no
status CurrentRelativeHumidity       yes
Alice                                no
```

## 2. Confirmed living-room decision: Гостиная

```text
NL_simple_thermostat_010 = Воздух
sensor                  = 902.01_MSW_TH/Temperature
outputs                 = A09/K4 + A09/K5

NL_simple_thermostat_611 = Пол
sensor                  = 902.02_M1W2_TEMP_NONE/External Sensor 1
output                  = A13/K6
```

`NL_simple_thermostat_011` is no longer a separate zone.

Target:

```text
Гостиная
├─ Воздух    → NL_simple_thermostat_010
├─ Пол       → NL_simple_thermostat_611
└─ Влажность → 902.01_MSW_TH/Humidity (tile hidden, status only)
```

For YAML v2, Alice policy belongs to the specific Service because the real Sprut command uses `aId + sId`.

## 3. Heating-system rooms

### ТП дом

```text
pump            A03/K1
valve position  A05/Channel 1 Dimming Level
supply          wb-m1w2_141/External Sensor 1
return          wb-m1w2_141/External Sensor 2
```

Target: read-only Heating Circuit Monitor for pump + valve position, supply and return temperatures, with no physical write path from Sprut.

### ГП дом

```text
pump            A03/K2
valve position  A05/Channel 2 Dimming Level
supply          wb-m1w2_167/External Sensor 1
return          wb-m1w2_167/External Sensor 2
```

### Радиаторы дом

```text
pump            A03/K3
supply          wb-m1w2_170/External Sensor 1
return          wb-m1w2_121/External Sensor 1
```

### ГП беседка

```text
pump            A03/K4
valve position  A05/Channel 3 Dimming Level
supply          wb-m1w2_173/External Sensor 1
return          wb-m1w2_173/External Sensor 2
```

### Радиаторы хозблок

```text
pump            A03/K5
supply          wb-m1w2_170/External Sensor 1
return          wb-m1w2_166/External Sensor 1
```

### Котёл

```text
system supply   wb-m1w2_170/External Sensor 1
boiler return   wb-m1w2_170/External Sensor 2
pressure        905.3/input_1_value
OpenTherm       wbe2-i-opentherm_11/*
```

Target pressure presentation: Sprut `Параметр`, display precision 0.1 bar, without changing source precision in WB.

The exact `Sprut.device + Параметр` template schema is still pending inspection of the actual Sprut Catalog example.

## 4. Water room

Target room: `Вода`.

Common water valve:

```text
A07/Output K1
```

Target: visible and controllable Valve. Do not expose K2, Leakage Mode, Cleaning Mode or P1/P2 counter services.

Leak sensors currently recorded in the object map:

```text
A07/Input F1                         котельная
A07/Input F2                         санузел хозблока
wb-m1w2_165/Input 1                  кухня
wb-m1w2_138/Input 1                  санузел мастер-спальни
902.15_M1W2_LEAK_NONE/Input 1        постирочная
902.13_M1W2_LEAK_TEMP/Input 1        ванная
902.04_M1W2_LEAK_TEMP/Input 1        санузел прихожей
```

All target LeakSensor entities belong to room `Вода` unless a fresher object source changes this set.

## 5. Motion

Motion is not automatically exposed because an MSW profile has motion capability.

The currently explicit motion control in the physical map is:

```text
902.05_MSW_THM/Current Motion → прихожая
```

Its final Sprut/Alice presentation remains an object policy decision and is not inferred.

## 6. Confirmed presentation RPC 2026-09-10

### Hide/show Service tile

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

`Service.visible` is now implemented in v0.3.0-dev APPLY/VERIFY.

### Status line

```json
{"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}}
```

`Characteristic.statusVisible` is now implemented in v0.3.0-dev APPLY/VERIFY.

### Disable Alice bridge membership

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

This confirms that Alice membership is Service-scoped. Generic `bridge.alice` APPLY remains blocked until current membership read-path and enable/create RPC are captured.

## 7. Non-target entities

Do not produce as final customer entities merely because the MQTT control exists:

- physical heating servo outputs;
- physical pump outputs as writable Switch/Lightbulb;
- physical valve-position outputs as writable controls;
- duplicate physical TemperatureSensor values already represented by thermostats;
- unused WB-MWAC services;
- technical counters/modes with no user purpose.

## 8. Remaining blockers before final YAML/APPLY

1. Alice:
   - exact enable/create outgoing frame;
   - read-path current membership of `Yandex_1` for DRY RUN/VERIFY.
2. Actual Sprut Catalog sample for `Sprut.device + Параметр`.
3. Field-test of read-only Fan/mirror presentation for Heating Circuit Monitor.
4. Current NL Project source/model needed to implement Project → `sprut_plan.yaml` generation.
5. Confirm final identity/SERIAL produced by new templates before writing them into the final object plan.

Until these are resolved, this document is desired presentation state, not an APPLY-ready final plan.
