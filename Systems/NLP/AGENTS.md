# Постоянный контракт AI/Codex для NL Project 2.0

## Точка входа

Перед изменением NL Project:

1. прочитать `Systems/NLP/README.md`;
2. определить GitHub Issue и разрешённый scope;
3. прочитать относящиеся к задаче документы из `Systems/NLP/docs/product/`;
4. для AutoCAD/topology прочитать `Systems/NLP/docs/autocad/`;
5. проверить фактическую реализацию, migrations, resources и tests в текущей ветке;
6. учитывать `EIM/Standards/Development_lifecycle_standard.md` и `Software_naming_and_versioning_standard.md`.

## Постоянные запреты

- Не принимать самостоятельно новые предметные или архитектурные решения.
- Не считать Issue, PR, chat history, старые TASK/REPORT или `EIM/AutoCAD/Doc` заменой действующей документации `Systems/NLP/docs/`.
- Не изменять NL Project 1.0, её рабочие базы, DWG, настройки, ресурсы, backup или runtime-данные из задач NL Project 2.0.
- Не создавать production logic для конкретных test-object ID.
- Не подключаться к произвольному active AutoCAD document. Live-CAD работа допустима только для явно заданного target DWG после identity check.
- Не выполнять неявный Save и не закрывать AutoCAD автоматически.
- Не объявлять Release, пользовательский MVP или live-ready состояние только по результату unit/regression tests.
- Не переносить cache, `.venv`, `__pycache__`, `build`, `dist`, временные SQLite/DWG и generated artifacts в source of truth.

## Правила изменений

- Нетривиальное изменение: Issue → branch от актуального `main` → implementation/docs/tests → PR → review → merge.
- `main/Systems/NLP/` после merge является текущим принятым состоянием системы. Незамерженная ветка — только кандидат.
- Существенное принятое правило должно быть отражено в действующем документе в `docs/`, а не только в task text или коде.
- Machine resources должны сохранять parity с human-readable contract.
- Изменение schema head и/или catalog release считается завершённым только вместе с migrations, проверкой reopen/integrity и предусмотренными тестами.
- При конфликте нормативных источников, недостающем product decision или невозможности доказать безопасную миграцию остановиться и зафиксировать blocker в Issue/PR.

## Проверки

Для применимых изменений использовать штатные wrappers:

```powershell
& .\tools\format-check.ps1
& .\tools\check.ps1
& .\tools\test.ps1
```

AutoCAD contract и catalog дополнительно проверяются штатными tools/tests. Live AutoCAD smoke выполняется только при явном разрешении и только на определённом target DWG.
