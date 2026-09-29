# Neirolinks

Репозиторий NEIROLINKS для инженерной интеграции систем автоматизации, разработки скриптов Wiren Board и хранения документации по объектам.

## Структура репозитория

### `EIM/`

Метод инженерной интеграции: описание подхода, pipeline разработки, инструкции для ИИ-ассистентов и общие стандарты проекта.

Основные документы:

- [Pipeline разработки системы автоматизации](EIM/Pipeline.md)
- [Принципы работы с ChatGPT](EIM/AI/AI_workflow.md)
- [Инструкция для ИИ-ассистента](EIM/AI/AI_instruction.md)
- [Wiren Board coding standard](EIM/Standards/WB_coding_standard.md)
- [WB-rules logging standard](EIM/Standards/WB_logging_standard.md)
- [Стандарт развития, версионирования и накопления инженерного опыта](EIM/Standards/Development_lifecycle_standard.md)

### `Systems/`

Общие разрабатываемые системы NEIROLINKS.

Текущие разделы:

- [HHM — Heating Manager](Systems/HHM/README.md) — общая система управления отоплением; в main находится подтверждённый общий core, объектовые адаптации хранятся отдельно.
- [NST — NEIROLINKS Service Tool](Systems/NST/README.md) — сервисная система для identity, desired state, deployment, diagnostics, rollback, firmware и обслуживания контроллеров.
- [Sprut Configurator](Systems/Sprut%20Configurator/README.md) — архитектура, MQTT/identity contracts, YAML contract, baseline standalone v0.2.2 и reference implementation.

### `Templates/`

Шаблоны для повторного использования между объектами.

Текущие направления:

- `Templates/Sprut/` — шаблоны Sprut.hub MQTT.
- `Templates/WB-rules/` — планируемое место для шаблонов правил Wiren Board.

### `Objects/`

Каноническое место реальных объектов. Каждый объект является отдельной зоной фактов: описание, конфиги, бэкапы, скрипты, документация и подтверждённое актуальное состояние.

Текущий этап миграции:

- `Objects/05_31_Ivolga_13/` — Иволга уже переведена на каноническую структуру;
- `objects/` — временный legacy-раздел для остальных объектов, которые ещё не проходили отдельный cleanup.

Остальные объекты не переносить автоматически вместе с Иволгой: каждый объект должен проходить отдельную проверку актуальности.

Объектовые Sprut plan, whitelist и acceptance fixtures должны храниться внутри соответствующего `Objects/<object>/`, а не в общей папке Configurator.
