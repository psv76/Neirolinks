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

### `SprutConfigurator/`

Общая разработка Sprut Configurator: архитектура, MQTT/identity contracts, YAML contract, baseline standalone v0.2.2, правила templates и граница будущей интеграции с NL Project.

Главный документ:

- [Sprut Configurator](SprutConfigurator/README.md)

### `Templates/`

Шаблоны для повторного использования между объектами.

Текущие направления:

- `Templates/Sprut/` — шаблоны Sprut.hub MQTT.
- `Templates/WB-rules/` — планируемое место для шаблонов правил Wiren Board.

### `objects/`

Реальные объекты. Каждый объект хранится в отдельной папке и является отдельной зоной фактов: описание объекта, конфиги, бэкапы, скрипты, документация и рабочие материалы.

Объектовые Sprut plan, whitelist и acceptance fixtures должны храниться внутри соответствующего `objects/<object>/`, а не в общей папке Configurator.
