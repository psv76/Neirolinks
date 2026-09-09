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

User decision in Issue #22:

```text
NL_simple_thermostat_010 = Воздух
sensor                  = 902.01_MSW_TH/Temperature
outputs                 = A09/K4 + A09/K5

NL_simple_thermostat_611 = Пол
sensor                  = 902.02_M1W2_TEMP_NONE/External Sensor 1
output                  = A13/K6
```

`NL_simple_thermostat_011` is no longer a separate zone. It must not become a third thermostat tile in Sprut.

Target:

```text
Гостиная
├─ Воздух   → NL_simple_thermostat_010
├─ Пол      → NL_simple_thermostat_611
└─ Влажность → 902.01_MSW_TH/Humidity (tile hidden, status only)
```

The humidity control follows from the confirmed `902.01_MSW_TH` profile. Final inclusion in generated YAML must still be checked against the actual Sprut template/accessory identity produced for this MSW profile.

## 3. Heating-system rooms

### ТП дом

Confirmed physical sources:

```text
pump            A03/K1
valve position  A05/Channel 1 Dimming Level
supply          wb-m1w2_141/External Sensor 1
return          wb-m1w2_141/External Sensor 2
```

Target presentation:

- read-only Heating Circuit Monitor for pump + valve position;
- supply temperature;
- return temperature;
- no physical write path from Sprut to pump/valve.

### ГП дом

```text
pump            A03/K2
valve position  A05/Channel 2 Dimming Level
supply          wb-m1w2_167/External Sensor 1
return          wb-m1w2_167/External Sensor 2
```

Same presentation policy as ТП дом.

### Радиаторы дом

```text
pump            A03/K3
supply          wb-m1w2_170/External Sensor 1
return          wb-m1w2_121/External Sensor 1
```

Target presentation:

- read-only pump state;
- supply temperature;
- return temperature.

No valve-position control exists for this circuit in the current physical map.

### ГП беседка

```text
pump            A03/K4
valve position  A05/Channel 3 Dimming Level
supply          wb-m1w2_173/External Sensor 1
return          wb-m1w2_173/External Sensor 2
```

Same presentation policy as ТП дом.

### Радиаторы хозблок

```text
pump            A03/K5
supply          wb-m1w2_170/External Sensor 1
return          wb-m1w2_166/External Sensor 1
```

Target presentation:

- read-only pump state;
- supply temperature;
- return temperature.

### Котёл

Confirmed physical sources:

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

### Common water valve

```text
A07/Output K1
```

Target:

- Valve;
- visible;
- user-controllable;
- no K2;
- no Leakage Mode tile;
- no Cleaning Mode tile;
- no P1/P2 counter Services.

### Leak sensors currently recorded in object map

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

The only currently explicit motion control in the physical map is:

```text
902.05_MSW_THM/Current Motion → прихожая
```

Its final Sprut/Alice presentation remains an object policy decision and is not inferred in this draft.

## 6. Outside / Улица

Current known user lighting functions are sourced from object channels such as `A06/K1…K6`, but final Sprut target must be generated from current Project presentation data, not by automatically exposing every available relay.

## 7. Non-target entities

Do not produce as final customer entities merely because the MQTT control exists:

- physical heating servo outputs;
- physical pump outputs as writable Switch/Lightbulb;
- physical valve-position outputs as writable controls;
- duplicate physical TemperatureSensor values already represented by thermostats;
- unused WB-MWAC services;
- technical counters/modes with no user purpose.

## 8. Remaining blockers before final YAML/APPLY

1. Exact WebUI write RPC for:
   - Service.visible;
   - Characteristic.statusVisible;
   - Alice bridge policy.
2. Actual Sprut Catalog sample for `Sprut.device + Параметр`.
3. Field-test of read-only Fan/mirror presentation for Heating Circuit Monitor.
4. Current NL Project source/model needed to implement Project → `sprut_plan.yaml` generation.
5. Confirm final identity/SERIAL produced by any new templates before writing them into object YAML.

Until these are resolved, this document is desired presentation state, not an APPLY-ready plan.