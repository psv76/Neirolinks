# Перенос текущего состояния NL Project 2.0

Миграция NL Project 2.0 в канонический `Systems/NLP/` выполнена по Issue #118 и завершена merge PR #119. Исходники были взяты из актуального на момент переноса `D:\NLP_2`; документация сверена с `D:\NLP_2_DOCS_19.zip` и принятым Repair 08. После merge `Systems/NLP/` в `main` стал единственным каноническим источником текущего состояния NL Project 2.0.

Все 20 product Markdown-файлов, два normative catalog JSON, два approved topology/ATTDEF source и Repair 08 report в архиве побайтно совпадали с локальным комплектом документации. При переносе были заменены локальные ссылки; из [20_AUTOCAD_BLOCK_CONTRACT.md](product/20_AUTOCAD_BLOCK_CONTRACT.md) и [25_DWG_SYNCHRONIZATION.md](product/25_DWG_SYNCHRONIZATION.md) удалены явно non-normative legacy appendices. Устаревшие build plans/recovery history не переносились как действующие требования.

273 программных/ресурсных/каталожных файла были перенесены побайтно. В [tools/catalog_check.py](../tools/catalog_check.py) и одном recovery test был изменён только путь к нормативному каталогу: теперь используется [docs/product/catalogs](product/catalogs), без зависимости от соседнего `NLP_2_DOCS`. Рабочие SQLite, DWG, cache, venv, build, dist и runtime artifacts в канонический репозиторий не включались.

## Канонические successors

| Старый материал | Действующий источник |
|---|---|
| `EIM/AutoCAD/Doc/Blocks.md` | [20_AUTOCAD_BLOCK_CONTRACT.md](product/20_AUTOCAD_BLOCK_CONTRACT.md), [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md) |
| `EIM/AutoCAD/Doc/Parsing.md` | [25_DWG_SYNCHRONIZATION.md](product/25_DWG_SYNCHRONIZATION.md), [CURRENT_TOPOLOGY_ARCHITECTURE.md](autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md), [src/nl_project_2/cad_contract/](../src/nl_project_2/cad_contract), [src/nl_project_2/cad_sync/](../src/nl_project_2/cad_sync) |
| `EIM/AutoCAD/Doc/NL_Cloud_Desktop_v1.0.md` | [README.md](../README.md), [00_ARCHITECTURE_COMPASS.md](product/00_ARCHITECTURE_COMPASS.md), [TECHNICAL_ARCHITECTURE.md](engineering/TECHNICAL_ARCHITECTURE.md), [01_VERSION_SEPARATION.md](product/01_VERSION_SEPARATION.md) |

Machine `source_documents` сохраняет исходные provenance-имена: `01_CURRENT_TOPOLOGY_ARCHITECTURE_2026-08-30.md` соответствует [CURRENT_TOPOLOGY_ARCHITECTURE.md](autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md); `02_AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE_2026-08-30.md` — [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md).

## Проверки миграции

На состоянии migration PR #119 независимая сверка human-readable ATTDEF с machine contract подтвердила все 71 canonical name и exact ATTDEF sets. AutoCAD checker: `3.0.0`, 71 names, 10 groups. Catalog checker: Repair 05 SHA256 `f8d27710485e1d1f8b23070e6ffa693ddd304c05150996a3c7eeae455c4af4c5`, 18 passports / 31 products; normative identity/facts совпали. Compile/static Ruff checks прошли.

Полный default non-live/non-manual regression миграционной копии: **586 passed, 0 failed, 0 skipped**, один существующий SQLite datetime adapter deprecation warning.

Format check выявил 52 файла, требующих форматирования. Тот же набор воспроизводился на исходном `D:\NLP_2`; массовое форматирование сознательно не входило в migration scope и остаётся отдельным technical debt.

Live AutoCAD, DWG writeback, рабочая БД, NL Project 1.0 и общая пользовательская приёмка не являлись критериями завершения самой миграции. Merge PR #119 не создавал Release.

## Documentation review repair

В рамках Issue #118 / PR #119 были устранены устаревшие BOX/port identifiers, конкурирующая модель шин, ограничения состава каталога и обязательные execution/recovery зависимости. Все 39 принятых UI acceptance criteria восстановлены в [ACCEPTANCE_CRITERIA.md](engineering/ACCEPTANCE_CRITERIA.md) без истории выполнения. Код, migrations, machine contract и catalog payload этим documentation repair не изменялись.

## Follow-up после миграции

После merge PR #119 канонический `main` получил отдельные проверенные изменения:

- PR #121: `ППЛ20/25 -> PP20/25`, `МПТ16 -> MPT16` для ordinary/bus conduit fields; полный regression **631 passed, 0 failed, 0 skipped**; catalog остался 18 passports / 31 products.
- PR #123: добавлен корневой `.gitattributes` с `Systems/NLP/resources/catalogs/*.json text eol=lf`, исправляющий clean checkout catalog JSON на Windows без изменения catalog payload или manifest hashes.
- после PR #123 локально подтверждены clean clone, bootstrap CPython 3.13.14 x64 и source launch NL Project из `Systems/NLP`.

Эти follow-up PR изменяют текущее состояние `main`, но не переписывают исторические результаты migration PR #119. Общая user acceptance и Release по-прежнему отдельные этапы.
