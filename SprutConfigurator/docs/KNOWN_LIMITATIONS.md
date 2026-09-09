# Known limitations и состояние на момент baseline

Дата baseline: **2026-09-08 / v0.2.2**.

Этот файл не является бесконечным backlog Issue. Он фиксирует ограничения текущего состояния, чтобы следующие конечные задачи могли осознанно менять contract.

## 1. Configurator presentation contract ограничен

v0.2.2 умеет reconcile только:

```text
Accessory name
room
Service name
```

Не реализованы в baseline:

```text
Service.visible
Characteristic.statusVisible
Alice / bridge policy
Service order
другие UI properties
```

Следующая объектная задача #22 должна расширить механизм только в реально требуемом объёме и затем вернуть подтверждённые общие изменения в этот проект.

## 2. YAML format_version 1 ограничен тем же contract

Presentation properties из пункта выше не входят в format v1 baseline.

Любое расширение должно сопровождаться:

```text
schema/validation
DISCOVER mapping
diff
DRY RUN
APPLY
VERIFY
```

## 3. Генерация YAML из NL Project не является частью baseline

Сейчас YAML может быть авторским/внешним артефактом.

Генерация из NL Project — следующая отдельная реализация, а не основание держать текущую общую Issue открытой.

## 4. CLIMATE template не field-verified в текущем repository snapshot

`Templates/Sprut/Heating/NL_climate_thermostat.json` содержит `init: false` в options.

До отдельной проверки нельзя считать его равным по статусу SIMPLE/COMBO.

## 5. Полнота sensor template library в GitHub не доказана

Полевой baseline подтвердил часть MSW/M1W2 scenarios, но archive/repository inventory не доказывает наличие в GitHub полного набора generic sensor JSON.

Не нужно подменять этот пробел предположением. При следующей работе следует либо сохранить фактически используемые templates, либо создать их из подтверждённого contract.

## 6. Relay Lightbulb generic contract ещё не завершён

Object-specific whitelist допустим и field-proven, но общий механизм должен получать функциональный тип канала из Project model/явного контракта.

## 7. Standalone prototype пока не импортирован как source package

Документационный архив Issue #21 не содержал исходник приложения, поэтому в `SprutConfigurator/` не добавлялся восстановленный или неполный код.

Поведение v0.2.2 зафиксировано как field-proven contract. Если source потребуется хранить в GitHub, его нужно добавить из фактического рабочего пакета в рамках отдельной доработки, а не восстанавливать по документации.

## 8. Template drift

Установленный в Sprut template и файл GitHub могут разойтись.

Baseline Configurator не выполняет inventory/version reconciliation templates.

## 9. Alias drift

Project-owned alias может быть вручную изменён в WB.

Configurator обнаружит отсутствие expected SERIAL, но не исправляет WB alias автоматически.

## 10. Object-specific facts не должны мигрировать в общие docs

Любые физические channels, rooms, object YAML и field mappings должны оставаться в `objects/<object>/`.

Если объектная задача даёт переносимый вывод, в общую документацию переносится только механизм/contract, а не физические данные объекта.
