# Постоянный контракт AI/Codex для NL Project 3.x

## Точка входа

Перед изменением NL Project:

1. прочитать GitHub Issue `#145` как глобальный development/recovery router;
2. прочитать `Systems/NLP/README.md`;
3. **полностью проверить открытые NLP Issues, PR и все GitHub remote branches, включая docs-only, spikes, аудиты, ветки без PR и приватный NEIROLINKS-TechDocs; не ограничиваться текущим sub-issue**; сверить [реестр работ](docs/engineering/NLP_WORK_REGISTER.md) и актуализировать незакрытые пункты;
4. определить текущий sub-issue и связанный PR/branch;
5. прочитать относящиеся документы `Systems/NLP/docs/product/`;
6. для AutoCAD/topology прочитать `Systems/NLP/docs/autocad/`;
7. проверить implementation, migrations, resources и tests в текущей ветке;
8. учитывать standards в `EIM/Standards/`.


## Обязательный gate полноты задач и релизов

При любом новом релизе, интеграции, переносе scope и создании нового чата:

1. Запрашивать живой список **всех** открытых NLP PR и Issue, **полный список remote branches** с пагинацией/без обрезания, а также документы и PR из TechDocs. Особенно `docs/*`, `spike/*`, `fix/*`, `system/nlp/*`, `feat/*`, `feature/*`, `audit/*`, `release/*`; orphan branch — отдельный кандидат для разбора.
2. Сопоставлять с **NLP_WORK_REGISTER.md**, привязать Issue/PR/head branch, подтверждённые решения пользователя (в том числе выбранный UI в doc-only PR), реальные файлы/тесты/экраны в `main`, состояние интеграции и target release.
3. До релиза сформировать документальную матрицу **`ВКЛЮЧЕНО` / `НЕ ВКЛЮЧЕНО — согласован перенос` / `ЗАБЛОКИРОВАНО`** для **всех принятых требований**. Если функциональность согласована, но не присутствует в реальном candidate UI/runtime, нельзя молча исключить её; сообщить пользователю до release и запросить решение. Не считать CI PASS или merge ancestor доказательством наличия функции.
4. Не разрешать выпуск со статусом `полная согласованная версия`, пока есть неразобранные `UNKNOWN_UNTRIAGED` или отсутствует согласование явного исключения. Запись в реестре — навигация, не изменение норматива.
5. При новом решении пользователя обновить **#145 + реестр + конкретную Issue/PR**, чтобы следующий чат не нуждался в прежней памяти. Следить и за согласованными **docs-only** ветками, которые могут не содержать production code.

**Зафиксированный пропуск NL Project 3.1:** [#217 Q07 дерево «Линий»](https://github.com/psv76/Neirolinks/pull/217) и [#220 норматив интерфейса B «Трасс»](https://github.com/psv76/Neirolinks/pull/220) / [#221 production вкладка «Трассы»](https://github.com/psv76/Neirolinks/pull/221) не вошли в выпуск, несмотря на утверждённый UX. Восстановить как патч 3.1, не считать автоматически отложенным на 3.2.

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
