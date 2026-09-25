# Neirolinks

Репозиторий NEIROLINKS для инженерной интеграции систем автоматизации, разработки скриптов Wiren Board и хранения документации по объектам.

[NLI 0.1 — Installer/Updater для Wiren Board](NLI/README.md): Python core, HHM manifests, managed backup/rollback, штатный firmware wrapper и Debian packaging. Статус: sandbox/review, без live deployment.

Комплект отопления Иволги по #59: [HHM 3.0 FSE — код двух WB, тесты, манифест и ПНР](objects/05_31_Ivolga_13/HHM3_FSE/README.md). Для установки используется только его INSTALL, а не прежние снимки контроллеров в репозитории.

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
