# Граница Sprut Configurator ↔ NL Project

## 1. Архитектурное направление

Целевой смысл интеграции:

```text
NL Project / normalized project model
→ Sprut plan
→ Configurator reconciliation engine
→ Sprut.hub
```

Это направление, а не условие завершения baseline Sprut Configurator.

Standalone Configurator может и должен дорабатываться конечными задачами до момента, когда реально будет принято решение встроить его функции в NL Project.

## 2. YAML остаётся полезным boundary artifact

Даже при будущей генерации из Project YAML полезен как:

- review artifact;
- Git diff;
- audit;
- handoff;
- regression fixture;
- диагностика desired state;
- воспроизводимый промежуточный контракт.

Базовое разделение:

```text
Project отвечает: каким Sprut должен быть.
Configurator отвечает: чем actual отличается и как безопасно выполнить reconciliation.
```

## 3. Источник будущего plan

Plan не должен строиться напрямую из DWG.

Логический источник — нормализованная модель NL Project после успешной синхронизации и разрешения проектных конфликтов.

## 4. Что Project должен уметь предоставить

Минимум baseline:

```text
stable serial
user display name
room
Service types
Service display names
```

В дальнейшем Project-owned presentation model может расширяться, но конкретные поля должны вводиться только по мере реализованного Configurator contract.

## 5. Sprut exposure

Не каждый физический channel обязан становиться пользовательской сущностью Sprut.

Project model должна уметь различать как минимум:

```text
физическая capability
функциональное назначение
нужна ли пользовательская сущность Sprut
какой entity/service contract ей соответствует
```

Точные имена таблиц и migrations не фиксируются этим документом.

## 6. Thermostat / heating zone model

Для будущей генерации виртуальных thermostat entities Project нужен нормализованный логический объект зоны, способный описать:

```text
zone_id
type
room
title
sensor references
heating outputs
optional cooling device
default setpoints / policy
```

Конкретная schema определяется отдельной задачей NL Project, а не baseline Configurator.

## 7. Не привязываться к standalone UI

Reference v0.2.2 использует Tkinter.

При будущем переносе следует переиспользовать поведение engine:

```text
session parsing
RPC
DISCOVER
validation
diff
APPLY
VERIFY
```

а UI реализовать нативно для NL Project.

## 8. Что не является текущей обязанностью Configurator project

Общая документация не обещает срок или готовность:

- полного встраивания в NL Project;
- PySide6 UI;
- окончательной SQLite schema;
- полного автоматического генератора всех Sprut entities.

Эти вещи должны оформляться отдельными конечными Issue в момент фактической реализации.
