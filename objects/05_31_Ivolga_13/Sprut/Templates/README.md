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

Для хаба `Котельная` используются отдельные минимальные templates, чтобы общий MQTT-брокер не затягивал в этот хаб домашние сущности.

```text
05_31_Ivolga_Kotel_Outdoor_Lightbulb.json
05_31_Ivolga_Kotel_Main_Water_Valve.json
```

- `05_31_Ivolga_Kotel_Outdoor_Lightbulb.json` — matcher только `A06/K1..K6`; наружное освещение для комнаты `Улица`.
- `05_31_Ivolga_Kotel_Main_Water_Valve.json` — matcher только `A07/Output K1`; создаёт только один `Valve` для главного крана воды. Контракт `Valve + Active + InUseFromActive` и MQTT mapping взяты из штатного шаблона Sprut `WB-MWAC v.2`; `K2`, `Leakage Mode`, `Cleaning Mode`, `P1/P2 Volume` намеренно отсутствуют.

## Текущий статус использования

- `NL_simple_thermostat.json` — актуальный шаблон зональных термостатов Дома.
- `NL_combo_thermostat.json` — сохранён как точный экспорт/исторический шаблон; текущая схема Дома на combo-термостатах не строится.
- `WB-MSW4_*` — профильные шаблоны климатических датчиков по MQTT-имени устройства.
- `WB-M1W2_W1_*` / `WB-M1W2_W2_*` — функциональные шаблоны двух каналов WB-M1W2.
- `05_31_Ivolga_Relay_Lightbulb.json` — объектовый шаблон релейных каналов освещения Дома/улицы; matcher содержит конкретные устройства Иволги (`A06`, `A11`, `A12`, `A16`).
- `05_31_Ivolga_Kotel_Outdoor_Lightbulb.json` — узкий котельный replacement для наружного `A06`.
- `05_31_Ivolga_Kotel_Main_Water_Valve.json` — узкий котельный template для `A07/Output K1`.

## Важное правило для хаба «Котельная»

Этот каталог является **архивом шаблонов объекта**, а не списком, который нужно автоматически установить на каждый Sprut.hub.

У Иволги физически один Wiren Board обслуживает котельную и Дом, но используются два отдельных Sprut.hub: встроенный в контроллер хаб `Котельная` и отдельный Sprut.hub 2 `Дом`.

Для хаба `Котельная` шаблоны добавляются только после fresh DISCOVER и анализа необходимости. Цель — не затянуть в инженерный хаб лишние сущности Дома. При необходимости используются отдельные котельные templates с более узкими matcher-условиями и read-only presentation.

Особенно нельзя автоматически устанавливать в котельную весь набор `WB-MSW4_*`, `WB-M1W2_*`, `NL_simple_thermostat` и широкий `05_31_Ivolga_Relay_Lightbulb.json`: они могут создать ненужные пользовательские сущности Дома на общем MQTT-брокере.

Для наружного света это уже решено отдельным matcher только `A06`. Для воды применяется тот же принцип: отдельный template только для `A07/Output K1` вместо полного штатного представления WB-MWAC.

## Общая библиотека

`NL_simple_thermostat.json` также хранится как reusable-template в общей библиотеке:

```text
Templates/Sprut/Heating/NL_simple_thermostat.json
```

Профильные MSW/M1W2 exports пока сохраняются прежде всего как подтверждённый объектовый deploy/archive set. Решение о переносе их копий в общую reusable-библиотеку принимается отдельно, после проверки контрактов на других объектах.
