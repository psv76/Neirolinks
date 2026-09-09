# Карта переработки исходного архива

Исходный documentation package от 2026-09-08 был не перенесён в GitHub как набор неизменённых файлов. Его содержание переработано и разнесено по общей разработке и объектовой зоне фактов.

## Общая разработка

| Исходный документ | Куда перенесён смысл |
|---|---|
| `00_README.md` | `SprutConfigurator/README.md`, object/reference separation |
| `01_PROGRESS_2026-09-06_08.md` | baseline status, `CONFIGURATOR_V0_2_2.md`, `KNOWN_LIMITATIONS.md`, object acceptance snapshot |
| `02_SPRUT_CONFIGURATOR_MQTT_TEMPLATES_ARCHITECTURE.md` | `MQTT_AND_IDENTITY_CONTRACTS.md`, `ARCHITECTURE.md` |
| `03_THERMOSTATS_WB_AND_SPRUT.md` | `THERMOSTATS_AND_TEMPLATES.md`; конкретные объектовые зоны не перенесены в общую документацию |
| `04_SPRUT_TEMPLATES_CATALOG.md` | `THERMOSTATS_AND_TEMPLATES.md`, `KNOWN_LIMITATIONS.md` |
| `05_SPRUT_CONFIGURATOR.md` | `CONFIGURATOR_V0_2_2.md`, `YAML_CONTRACT_V1.md` |
| `06_NL_PROJECT_INTEGRATION.md` | `NL_PROJECT_BOUNDARY.md`; будущая интеграция оставлена архитектурным направлением, а не условием закрытия текущей разработки |
| `07_IVOLGA_REFERENCE_IMPLEMENTATION.md` | объектовый acceptance snapshot в `objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/` |
| `08_TYPICAL_DEPLOYMENT_CHECKLIST.md` | `DEPLOYMENT_CHECKLIST.md` |
| `09_OPEN_ISSUES_AND_ROADMAP.md` | только актуальные общие ограничения в `KNOWN_LIMITATIONS.md`; объектовый и бесконечный roadmap не перенесён в общую Issue |
| `10_OWNERSHIP_AND_CONTRACTS.md` | `ARCHITECTURE.md` |

## Объектовая часть

В общую папку `SprutConfigurator/` не переносились:

- физические каналы Иволги;
- объектовые relay aliases;
- помещения Иволги;
- конкретные heating zones;
- object-specific whitelist;
- полный список target Accessory.

Frozen acceptance plan сохранён отдельно:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/05_31_Ivolga_sprut_plan_v3.yaml
```

Он помечен как исторический regression fixture и не является текущим источником физических данных объекта.

## Что намеренно не импортировано

Большой DISCOVER JSON конкретного объекта не добавлялся в общую папку.

Исходный documentation archive не содержал source standalone-приложения, поэтому code package не восстанавливался по описанию и не объявлялся reference source.

## Результат

После переработки общая разработка может читаться без истории чатов и без знания Иволги, а объектовая информация остаётся внутри `objects/05_31_Ivolga_13/`.
