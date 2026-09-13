# Sprut Templates — 05 31 Иволга 13

Объектовый архив кастомных MQTT-шаблонов Sprut.hub, необходимых для восстановления и анализа Иволги.

## Источник

13.09.2026 получены точные JSON-экспорты непосредственно со Sprut.hub **«Дом»**. Файлы ниже сохраняются без реконструкции matcher/mapping-логики по памяти или DISCOVER.

## Шаблоны, установленные/экспортированные с хаба «Дом»

```text
05_31_Ivolga_Relay_Lightbulb.json
NL_simple_thermostat.json
NL_combo_thermostat.json

WB-MSW4_M.json
WB-MSW4_TH.json
WB-MSW4_THM.json
WB-MSW4_CO.json
WB-MSW4_COM.json

WB-M1W2_W1_TEMP.json
WB-M1W2_W1_LEAK.json
WB-M1W2_W1_GERCON.json
WB-M1W2_W2_TEMP.json
WB-M1W2_W2_LEAK.json
WB-M1W2_W2_GERCON.json
```

`05_31_Ivolga_Relay_Lightbulb.json` и `NL_simple_thermostat.json` уже находились в репозитории; присланные экспорты подтверждают их рабочие варианты.

## Котельные узкие templates

Для хаба `Котельная` используются отдельные минимальные templates, чтобы общий MQTT-брокер не затягивал в этот хаб домашние сущности и чтобы инженерные исполнительные механизмы не получили write-path из Sprut.

```text
05_31_Ivolga_Kotel_Outdoor_Lightbulb.json
05_31_Ivolga_Kotel_Main_Water_Valve.json
05_31_Ivolga_Kotel_A07_Leaks.json
05_31_Ivolga_Kotel_House_Leaks.json
05_31_Ivolga_Kotel_Heating_501.json
05_31_Ivolga_Kotel_Heating_502.json
05_31_Ivolga_Kotel_Heating_503.json
05_31_Ivolga_Kotel_Heating_504.json
05_31_Ivolga_Kotel_Heating_505.json
05_31_Ivolga_Kotel_Boiler_ReadOnly.json
05_31_Ivolga_Kotel_Electricity_A01.json
```

- `05_31_Ivolga_Kotel_Outdoor_Lightbulb.json` — matcher только `A06/K1..K6`; наружное освещение для комнаты `Улица`.
- `05_31_Ivolga_Kotel_Main_Water_Valve.json` — matcher только `A07/Output K1`; создаёт только один `Valve` для ввода воды. Контракт `Valve + Active + InUseFromActive` и MQTT mapping взяты из штатного шаблона Sprut `WB-MWAC v.2`; `K2`, `Leakage Mode`, `Cleaning Mode`, `P1/P2 Volume` намеренно отсутствуют.
- `05_31_Ivolga_Kotel_A07_Leaks.json` — только `A07/Input F1` и `A07/Input F2`, каждый как отдельный `LeakSensor`.
- `05_31_Ivolga_Kotel_House_Leaks.json` — whitelist только пяти требуемых домовых датчиков протечки из актуальной физической карты.
- `05_31_Ivolga_Kotel_Heating_501/502/504.json` — read-only `FanBasic`: `On` читает насос `A03`, `RotationSpeed` читает фактическое положение подмеса `A05`; `topicSet` отсутствует.
- `05_31_Ivolga_Kotel_Heating_503/505.json` — read-only `FanBasic` насоса плюс read-only `TemperatureSensor` общей подачи 411; `topicSet` отсутствует.
- `05_31_Ivolga_Kotel_Boiler_ReadOnly.json` — отдельный read-only монитор котла, создаваемый от `905.3/input_1_value`: читает OpenTherm, уставку без возможности записи и физическое давление 421 с presentation step 0.1 бар.
- `05_31_Ivolga_Kotel_Electricity_A01.json` — минимальный read-only электромониторинг: `Total P` и напряжения L1/L2/L3.

## Текущий статус использования

- `NL_simple_thermostat.json` — актуальный шаблон зональных термостатов Дома.
- `NL_combo_thermostat.json` — сохранён как точный экспорт/исторический шаблон; текущая схема Дома на combo-термостатах не строится.
- `WB-MSW4_*` — профильные шаблоны климатических датчиков по MQTT-имени устройства.
- `WB-M1W2_W1_*` / `WB-M1W2_W2_*` — функциональные шаблоны двух каналов WB-M1W2.
- `05_31_Ivolga_Relay_Lightbulb.json` — объектовый шаблон релейных каналов освещения Дома/улицы; matcher содержит конкретные устройства Иволги (`A06`, `A11`, `A12`, `A16`).
- котельные `05_31_Ivolga_Kotel_*` — deploy set только для хаба `Котельная`; устанавливаются целевым набором, а не вместе со всеми объектными шаблонами.

## Важное правило для хаба «Котельная»

Этот каталог является **архивом шаблонов объекта**, а не списком, который нужно автоматически установить на каждый Sprut.hub.

У Иволги физически один Wiren Board обслуживает котельную и Дом, но используются два отдельных Sprut.hub: встроенный в контроллер хаб `Котельная` и отдельный Sprut.hub 2 `Дом`.

Для хаба `Котельная` шаблоны добавляются только после fresh DISCOVER и анализа необходимости. Цель — не затянуть в инженерный хаб лишние сущности Дома. Используются отдельные котельные templates с узкими matcher-условиями и read-only presentation.

Особенно нельзя автоматически устанавливать в котельную весь набор `WB-MSW4_*`, `WB-M1W2_*`, `NL_simple_thermostat` и широкий `05_31_Ivolga_Relay_Lightbulb.json`: они могут создать ненужные пользовательские сущности Дома на общем MQTT-брокере.

Для наружного света используется matcher только `A06`; для воды — отдельный template только для `A07/Output K1`; протечки имеют отдельный whitelist. Насосы и подмесы котельных контуров в Sprut представлены только read-only и не получают `topicSet`.

## Общая библиотека

`NL_simple_thermostat.json` также хранится как reusable-template в общей библиотеке репозитория:

```text
Templates/Sprut/Heating/NL_simple_thermostat.json
```

Профильные MSW/M1W2 exports пока сохраняются прежде всего как подтверждённый объектовый deploy/archive set. Решение о переносе их копий в общую reusable-библиотеку принимается отдельно, после проверки контрактов на других объектах.
