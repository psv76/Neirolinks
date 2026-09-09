# 05 31 Иволга 13 — Sprut presentation plan DRAFT

Status: working document for Issue #22. Physical channels are based only on current object repository sources.

## 1. Sprut.hub deployment on Ivolga

На объекте используются три независимых Sprut.hub:

```text
Дом
Беседка
Котельная
```

Configurator не должен хранить `target_hub` внутри сущностей или автоматически выбирать хаб.

Рабочий процесс:

```text
открыть нужный hub в WebUI
→ получить его текущую сессию
→ выбрать YAML именно для этого hub
→ DISCOVER / DRY RUN / APPLY / VERIFY
→ перейти к следующему hub
```

Поэтому текущий объект может иметь три отдельных deployment plan:

```text
sprut_plan_dom.yaml
sprut_plan_besedka.yaml
sprut_plan_kotelnaya.yaml
```

Важно: физическое здание и Sprut.hub не эквивалентны. Отдельный hub `Котельная` содержит инженерное представление контуров разных зданий, в том числе дома, беседки и хозблока. Значит автоматическое правило `здание → hub` применять нельзя.

## 2. Hub `Дом` — living-room presentation

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

### Confirmed decision: Гостиная

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

## 3. Hub `Котельная`

Current UI confirms engineering rooms such as:

```text
Котёл
Контур Дом паркет
Контур Дом плитка
Контур Дом радиаторы
Контур Беседка тёплый пол
Контур Хоз блок радиаторы
Электричество
```

This is the key reason not to use `target_hub` as a physical-building property.

### ТП дом / `Контур Дом плитка`

```text
pump            A03/K1
valve position  A05/Channel 1 Dimming Level
supply          wb-m1w2_141/External Sensor 1
return          wb-m1w2_141/External Sensor 2
```

Target: read-only Heating Circuit Monitor for pump + valve position, supply and return temperatures, with no physical write path from Sprut.

### ГП дом / `Контур Дом паркет`

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

### ГП беседка / `Контур Беседка тёплый пол`

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

Final hub placement of `Вода` is an explicit deployment-plan fact; it is not inferred from physical building ownership.

## 5. Hub `Беседка`

Object data for the gazebo currently exists only in NL Project 1.0.

Issue #22 will use a limited legacy adapter/extractor for NL Project 1.0 to obtain the required gazebo facts and pass them into the same normalized Sprut Plan/YAML generator contract intended for future NL Project 2.0.

The legacy adapter is not a long-term integration layer and is not developed beyond what is needed to extract current Ivolga data.

## 6. Motion

Motion is not automatically exposed because an MSW profile has motion capability.

The currently explicit motion control in the physical map is:

```text
902.05_MSW_THM/Current Motion → прихожая
```

Its final Sprut/Alice presentation remains an object policy decision and is not inferred.

## 7. Confirmed presentation RPC 2026-09-10

### Hide/show Service tile

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

### Status line

```json
{"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}}
```

### Alice/Yandex read

```json
{"params":{"bridgeService":{"list":{"bridgeIndex":"Yandex_1"}}}}
```

Membership is determined by exact `(aId, sId)` presence in returned `services[]`.

### Alice/Yandex enable

```json
{"params":{"bridgeService":{"create":{"bridgeIndex":"Yandex_1","aId":118,"sId":13,"write":true}}}}
```

### Alice/Yandex disable

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

The Alice policy is now field-confirmed for read/create/delete and can participate in full DRY RUN/APPLY/VERIFY.

## 8. Non-target entities

Do not produce as final customer entities merely because the MQTT control exists:

- physical heating servo outputs;
- physical pump outputs as writable Switch/Lightbulb;
- physical valve-position outputs as writable controls;
- duplicate physical TemperatureSensor values already represented by thermostats;
- unused WB-MWAC services;
- technical counters/modes with no user purpose.

## 9. Remaining blockers before final YAML/APPLY

1. Actual Sprut Catalog sample for `Sprut.device + Параметр`.
2. Field-test of read-only Fan/mirror presentation for Heating Circuit Monitor.
3. NL Project 1.0 source/database for the limited legacy extractor, especially gazebo data.
4. Confirm final identity/SERIAL produced by new templates before writing them into final plans.

Until these are resolved, this document is desired presentation state, not an APPLY-ready final plan.