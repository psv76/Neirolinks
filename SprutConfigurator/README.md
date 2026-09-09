# Sprut Configurator

Sprut Configurator — общая разработка NEIROLINKS для воспроизводимой массовой настройки Sprut.hub по декларативному плану.

Текущий зафиксированный baseline: **standalone v0.2.2**.

Рабочий цикл:

```text
DISCOVER
→ YAML
→ DRY RUN
→ APPLY
→ VERIFY
```

## Назначение

Configurator не создаёт инженерную автоматику и не заменяет Wiren Board. Его задача — сравнить фактическое состояние Sprut.hub с desired state и безопасно применить только разрешённые изменения.

Базовое разделение:

```text
Project / проектные данные
    ↓ desired state
YAML plan
    ↓
Sprut Configurator
    ↓ reconcile
Sprut.hub
```

Wiren Board остаётся владельцем инженерной логики, защит и физических исполнительных команд.

## Что входит в этот раздел

```text
SprutConfigurator/
├─ README.md
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ MQTT_AND_IDENTITY_CONTRACTS.md
│  ├─ YAML_CONTRACT_V1.md
│  ├─ CONFIGURATOR_V0_2_2.md
│  ├─ THERMOSTATS_AND_TEMPLATES.md
│  ├─ NL_PROJECT_BOUNDARY.md
│  ├─ DEPLOYMENT_CHECKLIST.md
│  ├─ KNOWN_LIMITATIONS.md
│  └─ SOURCE_ARCHIVE_MAP.md
└─ reference/
   └─ v0.2.2/
      └─ README.md
```

Общие Sprut template JSON остаются в `Templates/Sprut/`. Этот раздел описывает их контракты и связь с Configurator, но не дублирует сами template-файлы.

Исходный пакет документации, из которого создан этот раздел, не содержал исходник standalone-приложения. Поэтому Issue #21 фиксирует механизм, контракт и field-proven поведение v0.2.2; сам source/executable не объявляется частью импортированного documentation baseline.

Карта переработки исходных документов:

```text
SprutConfigurator/docs/SOURCE_ARCHIVE_MAP.md
```

## Что сюда не входит

Физические каналы, помещения, объектовые MQTT-алиасы, whitelist конкретных реле и объектовые YAML-планы не являются общей разработкой.

Они хранятся внутри соответствующего объекта:

```text
objects/<object>/
```

Для первого полевого reference объекта acceptance snapshot вынесен в:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/
```

Этот snapshot не является источником текущей физической карты объекта. Актуальные объектовые факты должны браться из текущих карт и конфигов самого объекта.

## Подтверждённое ядро v0.2.2

Полевым применением подтверждены:

- DISCOVER rooms/accessories/services/characteristics;
- стабильный matching Accessory по `serial`;
- разрешение room по имени;
- разрешение Service по `type` с ошибкой при неоднозначности;
- YAML validation;
- read-only DRY RUN;
- fresh preflight перед APPLY;
- явное локальное подтверждение `APPLY`;
- запись только `CHANGE`-операций;
- fresh DISCOVER + VERIFY после записи;
- хранение Sprut session credentials только в RAM;
- защита от известных round-trip ограничений имён Sprut.

## Принцип развития

Общая база Configurator живёт постоянно, но GitHub Issues под разработку должны быть конечными.

Новая объектная или функциональная задача:

1. дорабатывает standalone Configurator настолько, насколько нужно для конкретной цели;
2. проходит реальную проверку;
3. переносимые решения возвращаются в эту общую документацию;
4. задача закрывается.

Standalone Configurator можно развивать до момента фактического переноса его функций внутрь NL Project. Сам будущий перенос не является условием существования или закрытия текущих задач Configurator.

Следующая объектная работа: GitHub Issue **#22**.
