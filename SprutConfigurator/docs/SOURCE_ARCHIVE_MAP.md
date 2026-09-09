# Карта переработки исходного архива

Исходный documentation package от 2026-09-08 был не перенесён в GitHub как набор неизменённых файлов. Его содержание переработано и разнесено по общей разработке и объектовой зоне фактов.

Отдельно от documentation package был использован реальный рабочий пакет `Sprut_Configurator_v0.2.2`, из которого в generic reference tree перенесены оригинальные source/runtime-файлы standalone Configurator.

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

## Реальный рабочий пакет v0.2.2

Из рабочего ZIP в:

```text
SprutConfigurator/reference/v0.2.2/
```

перенесены оригинальные:

```text
sprut_configurator.py
selftest.py
requirements.txt
setup.bat
run.bat
```

Они не восстановлены по описанию. Для `sprut_configurator.py` подтверждено точное совпадение с исходным рабочим ZIP:

```text
Git blob SHA-1: 8cacfb101f979ed51bb94a5eb86dba634e670e03
SHA-256:        2cf996de6df1d6c3a1353faef4a2de66713d658155ec2f2ae45988dcc6e85781
size:           51433 bytes
```

Оригинальный `selftest.py` также проверен на исходном комплекте fixtures и дал:

```text
targets: 51
changes: 167
errors: 0
PASS
```

## Объектовая часть

В общую папку `SprutConfigurator/` не переносились как общие факты:

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

Большой `Ivolga_home_sprut_2.json` из рабочего пакета не добавлялся в общую папку Configurator. Это runtime DISCOVER snapshot конкретного объекта, а не generic source/contract.

Объектовый YAML также не дублируется рядом с generic source: он хранится в объектовой зоне фактов.

## Результат

После переработки общая разработка может читаться без истории чатов и без знания Иволги, а объектовая информация остаётся внутри `objects/05_31_Ivolga_13/`.

При этом standalone v0.2.2 теперь зафиксирован не только документально, но и исходным рабочим кодом.
