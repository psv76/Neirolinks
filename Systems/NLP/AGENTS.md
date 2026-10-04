# Постоянный контракт AI/Codex для NL Project 3.0

## Точка входа

Перед изменением NL Project:

1. прочитать GitHub Issue `#145` как глобальный development/recovery router;
2. прочитать `Systems/NLP/README.md`;
3. определить текущий sub-issue и связанный PR/branch;
4. прочитать относящиеся документы `Systems/NLP/docs/product/`;
5. для AutoCAD/topology прочитать `Systems/NLP/docs/autocad/`;
6. проверить implementation, migrations, resources и tests в текущей ветке;
7. учитывать standards в `EIM/Standards/`.

## Постоянные запреты

- Не принимать самостоятельно новые предметные или архитектурные решения.
- Не считать Issue, PR или chat history заменой действующей документации.
- Не изменять рабочие данные NL Project 1.0/2.0 из задач 3.0.
- Не подключаться к произвольному active DWG; live CAD — только по явно заданному target после identity check.
- Не выполнять неявный Save и не закрывать AutoCAD автоматически.
- Не объявлять Release/live-ready только по automated tests.
- Не переносить cache, `.venv`, `build`, `dist`, временные SQLite/DWG в source of truth.
- Внутреннее Python-имя `nl_project_2` считать compatibility detail, а не пользовательской версией.

## Правила изменений

Issue → branch от актуального `main` → implementation/docs/tests → PR → review → merge.

Существенное принятое правило отражается в `docs/`; machine resources сохраняют parity с human contract.

## Проверки

```powershell
& .\tools\format-check.ps1
& .\tools\check.ps1
& .\tools\test.ps1
```
