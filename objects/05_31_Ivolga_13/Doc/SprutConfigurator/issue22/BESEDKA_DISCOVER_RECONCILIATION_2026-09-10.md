# 05 31 Иволга — Беседка: reconciliation Project ↔ Sprut DISCOVER

Дата DISCOVER: 2026-09-10 03:39:33 local

Источник Project: read-only extract из NL Project 1.0 (`NLP56.zip`).
Источник actual: `Ivolga_besedka_sprut_1.json`, снятый Sprut Configurator v0.2.2 с хаба «Беседка».

## 1. Сводка actual Sprut

```text
rooms        6
accessories  53
services     139
serial-less  0
duplicate serials  0
```

Комнаты actual:

```text
Новая комната
Прихожая
Гостиная
Кухня
Санузел
Улица
```

Важно: в Project используется комната `Фасад`, а в текущем Sprut.hub такой комнаты нет. Для пользовательского представления наружные устройства должны экспортироваться в существующую комнату `Улица`. Это presentation mapping, а не изменение физической комнаты в Project.

## 2. Свет / управляемые нагрузки — точное совпадение SERIAL

Из 18 Project-линий света/диммирования 12 уже имеют точный Accessory SERIAL в Sprut:

| Line | Project purpose | Project point | Actual Sprut | Вывод |
|---|---|---|---|---|
| 301 | Свет фасад беседки | `A41/K1` | `A41/K1`, Lightbulb | resolved |
| 302 | Свет прихожая | `A41/K2` | `A41/K2`, Lightbulb | resolved |
| 303 | Свет санузел | `A41/K3` | `A41/K3`, Lightbulb | resolved |
| 304 | Свет кухня | `A42/K1` | `A42/K1`, Lightbulb | resolved |
| 305 | Люстра кухня | `A42/K2` | `A42/K2`, Lightbulb | resolved; actual room/name are stale |
| 306 | Люстра гостиная | `A42/K3` | `A42/K3`, Lightbulb | resolved |
| 307 | Бра мангала слева | `A43/K1` | `A43/K1`, Lightbulb | resolved |
| 308 | Бра мангала в центре | `A43/K2` | `A43/K2`, Lightbulb | resolved |
| 309 | Бра мангала справа | `A43/K3` | `A43/K3`, Lightbulb | resolved |
| 310 | Бра гостиная | `A43/K4` | `A43/K4`, Lightbulb | resolved |
| 311 | Подсветка зеркала | `A43/K5` | `A43/K5`, Lightbulb | resolved; actual is generic `Лампочка` in `Новая комната` |
| 320 | Гирлянда | `A45/K1` | `A45/K1`, Lightbulb | resolved; actual is generic `Лампочка` in `Новая комната` |

Несколько current-state расхождений являются именно тем, что Configurator должен исправить desired-state plan:

```text
A42/K2  current: Люстра ТВ / Гостиная
         target: 305 Люстра кухня / Кухня

A43/K5  current: Лампочка / Новая комната
         target: 311 Подсветка зеркала / Санузел

A45/K1  current: Лампочка / Новая комната
         target: 320 Гирлянда / Улица
```

Префикс Line ID остаётся частью пользовательского имени Sprut для проектных управляемых нагрузок.

## 3. WB-LED — шесть Project-линий отсутствуют в Sprut DISCOVER

В Project есть:

```text
351 → A47/Channel 1
352 → A47/Channel 2
353 → A47/Channel 3
354 → A48/Channel 1
355 → A48/Channel 2
356 → A48/Channel 3
```

В текущем DISCOVER нет ни одного Accessory с SERIAL `A47/...` или `A48/...` и вообще нет Accessory модели WB-LED.

Следствие: текущий полный generated plan должен закономерно дать ERROR на этих шести target, пока WB-LED не появится в Sprut под подтверждённой стабильной identity. Нельзя заменять эти SERIAL угадыванием.

## 4. Вытяжка 501

Project:

```text
501  Санузел  Вентилятор вытяжной  A43/K6
```

Actual содержит сразу два связанных по смыслу, но не доказанных как связка объекта:

```text
A43/K6  модель WB-MRx_Lightbulb
        Service Lightbulb
        name `Вытяжка`
        room `Санузел`
        Service.visible = false

serial `133`
        модель Virtual
        Service FanBasic
        name `Вентилятор`
        room `Санузел`
        visible = true
```

DISCOVER не содержит связи, доказывающей, что Virtual `133` управляет именно `A43/K6`. Поэтому generator не должен автоматически использовать runtime-like serial `133` как persistent identity.

Безопасный факт: физический relay identity `A43/K6` подтверждён. Его можно переименовать и оставить скрытым, но финальный пользовательский Fan contract требует отдельного подтверждения/пересборки стабильной virtual identity.

## 5. WB-MWAC / протечки

Project:

```text
441 → A44/F1  Санузел
442 → A44/F2  Кухня
```

Actual Sprut содержит WB-MWAC как:

```text
main serial: wb-mwac-v2_66
F1: wb-mwac-v2_66/Input F1
F2: wb-mwac-v2_66/Input F2
F3: wb-mwac-v2_66/Input F3
F4: wb-mwac-v2_66/Input F4
F5: wb-mwac-v2_66/Input F5
S6: wb-mwac-v2_66/Input S6
```

F1/F2 имеют LeakSensor Service и являются сильными live-кандидатами на Project 441/442, но Project хранит module identity `A44`, а actual MQTT/Sprut serial всё ещё raw-address based (`wb-mwac-v2_66`). В Project у A44 указан legacy Modbus address 44, поэтому автоматически объявлять `wb-mwac-v2_66/Input F1` равным `A44/F1` без проверки WB-конфигурации нельзя.

Также main WB-MWAC сейчас создаёт лишние customer-visible Services:

```text
Valve Кран 1       visible true
Valve Кран 2       visible true
Switch Режим протечка          visible true
Switch Режим влажная уборка    visible true
Water meter 1/2                visible false
```

Это подтверждает необходимость минимального WB-MWAC presentation/template contract из Issue #22. Отдельно важно: два Service типа `Valve` внутри одного Accessory делают type-only service matching неоднозначным; правильное решение — минимальный template, где ненужный K2 Service не создаётся, а не persistence runtime `sId` в YAML.

## 6. M1W2 / герконы

Project:

```text
470 → 921.06/W1  Геркон слева
471 → 921.06/W2  Геркон справа
921.06 = WB-M1W2 v3, legacy Modbus address 100
```

Actual Sprut не содержит serial `921.06`.

В DISCOVER видны raw families:

```text
wb-m1w2_142/1
wb-m1w2_142/2
wb-m1w2_142/1/1
wb-m1w2_142/2/1
wb-m1w2_151/1
wb-m1w2_151/1/1
```

Часть записей дублирует один физический control через разные stock template variants. Нельзя определить по DISCOVER, какой raw family является Project `921.06`, а какой — `921.10`. Нужна текущая WB configuration/MQTT device identity.

## 7. WB-MSW 921.09

Project подтверждает функциональность:

```text
Temperature + Humidity + Motion
```

То есть profile по текущему контракту соответствует `MSW_THM`.

Но в actual DISCOVER отсутствует любой Accessory модели/serial WB-MSW. Поэтому `921.09_MSW_THM` пока нельзя включать как существующую target identity только по Project.

## 8. Остальные Project field devices

Не найдены в current Sprut DISCOVER под стабильными Project identities:

```text
921.10  WB-M1W2
922.01  отдельный датчик движения
923.01  карниз справа
923.02  карниз слева
924.01  кондиционер
```

Это не означает, что физического оборудования нет. Это означает только, что текущий Sprut DISCOVER не даёт безопасного stable identity mapping к этим Project строкам.

## 9. Relay garbage, подтверждённый DISCOVER

Custom relay template уже используется: 18 Accessory модели `NEIROLINKS / WB-MRx_Lightbulb`.

Они точно соответствуют:

```text
12 Project light outputs
1 physical exhaust relay A43/K6
5 unused outputs A45/K2 ... A45/K6
```

Следовательно, Configurator/presentation policy может безопасно работать с существующими Project-used relay SERIAL. Отдельное правило suppression unused outputs нужно проектировать явно; нельзя скрывать все unlisted accessories глобально.

## 10. Что подтверждено для следующего шага

Можно продолжать без дополнительных предположений:

1. добавить presentation room mapping `Фасад → Улица` в reusable Project→YAML generator;
2. генерировать полный desired plan по Project, оставляя отсутствующие `A47/A48` как DRY RUN errors до исправления источника;
3. использовать 12 exact relay SERIAL как live-confirmed targets;
4. считать `A43/K6` подтверждённой physical identity, но не считать Virtual `133` стабильной identity;
5. не маппить M1W2/MSW/MWAC raw serial к Project identity до чтения текущей WB конфигурации.

## 11. Следующий внешний evidence

Для снятия remaining identity blockers нужен current Wiren Board configuration беседки, прежде всего MQTT/device aliases и serial-device configuration для:

```text
WB-MWAC
WB-M1W2
WB-MSW
WB-LED
```

Рабочую configuration менять на этапе evidence collection не требуется.