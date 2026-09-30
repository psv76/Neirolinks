# HHM — Heating Manager

Общая разработка системы управления отоплением NEIROLINKS.

## Текущий статус

- последняя approved версия: **HHM 3.6**;
- GitHub Release: `nli-approved-hhm-3.6`;
- publication commit: `93f67430cc7c3528a5e7258bb43986afe775ba6c`;
- проверенный runtime commit HHM 3.6: `f4673abbe52f1a89db5c84dd4c8cd391bc9ee0ef`;
- проверенный manifest commit HHM 3.6: `12e5805d22e365bdbe049245fefccdc005e960fa`;
- manifest SHA256: boiler `9469bf5c...`, gazebo `df1efa30...`.

### Переходный выпуск HHM 3.6

HHM 3.6 был разработан и полностью проверен до миграции репозитория на `Systems/Objects`. Чтобы не менять уже проверенные runtime bytes и не получать новый непроверенный manifest, выпуск 3.6 сохраняет immutable provenance старой линии:

- runtime `R = f4673abbe52f1a89db5c84dd4c8cd391bc9ee0ef`;
- manifest `M = 12e5805d22e365bdbe049245fefccdc005e960fa`;
- source paths внутри manifest остаются историческими `objects/.../HHM3_FSE`.

При этом publication record 3.6 проходит уже по новому стандарту:

```text
release-prep PR → main
                ↓
конкретный commit main
                ↓
tag nli-approved-hhm-3.6
                ↓
GitHub Release + nli-catalog.json
```

Копии проверенных manifest 3.6 находятся в `Systems/NST/releases/` и должны совпадать по SHA256 с исходными immutable manifest.

Начиная со следующей разработки HHM новый release-ready код должен формироваться от актуального `main`, а не от старого stacked branch graph.

Releases 3.2–3.5 были опубликованы до принятия стандарта `EIM/Standards/Development_lifecycle_standard.md`. Их tags и Releases сохраняются как исторические неизменяемые точки и не переписываются задним числом. Для новых выпусков применяется правило: PR → main → конкретный commit main → tag → Release.

## Граница общей системы и объекта

Текущая реализация HHM 3.5 исторически разрабатывалась внутри:

`objects/05_31_Ivolga_13/HHM3_FSE/`

Этот каталог смешивает общий алгоритм и объектовую реализацию Иволги. При cleanup нельзя объявлять весь комплект общей системой.

Проверенная граница для HHM 3.5:

| Файл/слой | Статус |
|---|---|
| `core/HHM3Circuit.js` | общий алгоритм контура |
| `core/HHM3Mixing.js` | общий алгоритм смесительного регулирования |
| `HHM3Config.js` из выпуска 3.5 | объект Иволга: зоны, каналы, MQTT, уставки |
| `HHM3Wire.js` из выпуска 3.5 | пока объект Иволга: содержит Ivolga transport/topics |
| `HHM3Outputs.js` из выпуска 3.5 | пока объект Иволга: контракт конкретного A05/WB-MAO4 |
| `HHM3Runtime.js` из выпуска 3.5 | пока связан с объектовым `HHM3Config` |
| rules 500/620/624 | объектовая реализация Иволги |

В `Systems/HHM/` переносится только то, что подтверждено как общее. Объектные части должны находиться в `Objects/<object>/` после отдельной проверки актуального live-состояния.

## Core

`core/HHM3Circuit.js` и `core/HHM3Mixing.js` перенесены без изменения алгоритма из approved HHM 3.5 runtime commit `48408e6...`.

Оба модуля не содержат физических каналов, MQTT paths, помещений или уставок Иволги и не имеют внутренних `require()` на объектные модули.

## Разработка

Новая общая работа HHM по умолчанию:

```text
main/Systems/HHM/
        ↓
ветка system/hhm/<issue>-<topic>
        ↓
PR → main
        ↓
при необходимости approved Release
```

Объектная адаптация ведётся через `Objects/<object>/` и не должна переносить физические каналы одного объекта в другой.

## Источники актуальности

Для общей системы:
- `main/Systems/HHM/`;
- approved GitHub Releases.

Для конкретного объекта:
- `main/Objects/<object>/`;
- deployment/live evidence.

Рабочая ветка сама по себе не является источником текущей принятой версии.
