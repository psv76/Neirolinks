# Перенос текущего состояния NL Project 2.0

Перенос выполняется по Issue #118 в Draft PR #119. Исходники взяты из текущего `D:\NLP_2`; документация сверена с `D:\NLP_2_DOCS_19.zip` и принятым Repair 08. Продуктовые правила не изменены. До merge ветка остаётся кандидатом на принятие.

Все 20 product Markdown-файлов, два normative catalog JSON, два approved topology/ATTDEF source и Repair 08 report в архиве побайтно совпадают с локальным комплектом документации. При переносе заменены локальные ссылки; из [20_AUTOCAD_BLOCK_CONTRACT.md](product/20_AUTOCAD_BLOCK_CONTRACT.md) и [25_DWG_SYNCHRONIZATION.md](product/25_DWG_SYNCHRONIZATION.md) удалены явно non-normative legacy appendices. Устаревшие build plans/recovery history не перенесены как действующие требования.

273 программных/ресурсных/каталожных файлов перенесены побайтно. В [tools/catalog_check.py](../tools/catalog_check.py) и одном recovery test изменён только путь к нормативному каталогу: теперь [docs/product/catalogs](product/catalogs), без зависимости от соседнего `NLP_2_DOCS`. Дополнен `.gitignore`. Рабочие SQLite, DWG, cache, venv, build, dist и runtime artifacts не включены.

## Канонические successors

| Старый материал | Действующий источник |
|---|---|
| `EIM/AutoCAD/Doc/Blocks.md` | [20_AUTOCAD_BLOCK_CONTRACT.md](product/20_AUTOCAD_BLOCK_CONTRACT.md), [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md) |
| `EIM/AutoCAD/Doc/Parsing.md` | [25_DWG_SYNCHRONIZATION.md](product/25_DWG_SYNCHRONIZATION.md), [CURRENT_TOPOLOGY_ARCHITECTURE.md](autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md), [src/nl_project_2/cad_contract/](../src/nl_project_2/cad_contract), [src/nl_project_2/cad_sync/](../src/nl_project_2/cad_sync) |
| `EIM/AutoCAD/Doc/NL_Cloud_Desktop_v1.0.md` | [README.md](../README.md), [00_ARCHITECTURE_COMPASS.md](product/00_ARCHITECTURE_COMPASS.md), [TECHNICAL_ARCHITECTURE.md](engineering/TECHNICAL_ARCHITECTURE.md), [01_VERSION_SEPARATION.md](product/01_VERSION_SEPARATION.md) |

Machine `source_documents` сохраняет исходные provenance-имена: `01_CURRENT_TOPOLOGY_ARCHITECTURE_2026-08-30.md` соответствует [CURRENT_TOPOLOGY_ARCHITECTURE.md](autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md); `02_AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE_2026-08-30.md` — [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md).

## Проверки и ограничения

Независимая сверка human-readable ATTDEF с machine contract подтвердила все 71 canonical name и все exact ATTDEF sets. AutoCAD checker: `3.0.0`, 71 names, 10 groups. Catalog checker: Repair 05 SHA256 `f8d27710485e1d1f8b23070e6ffa693ddd304c05150996a3c7eeae455c4af4c5`, 18 passports / 31 products, нормативные identity/facts совпадают. Compile/static Ruff checks пройдены.

Проверки выполняются в отдельной копии, CPython 3.13.14 x64; локальное тестовое окружение использует уже установленный набор зависимостей исходного snapshot. Чистый bootstrap и packaged build этим переносом не проверяются.

Полный default non-live/non-manual regression в перенесённой копии: **586 passed, 0 failed, 0 skipped**, 169.75 s. Один warning — существующее SQLite datetime adapter deprecation. Проверка включает upgrade/reopen/integrity и Repair 08 exact ATTDEF fixtures. Первичный запуск без локальной `.venv` дал 585 passed / 1 environment failure; после подготовки локального окружения полный повторный прогон прошёл.

Format check обнаружил 52 файла, требующих форматирования. Тот же результат воспроизведён на исходном `D:\NLP_2`; массовое переформатирование не включено в перенос. Замечание остаётся для отдельной правки.

Live AutoCAD, DWG writeback, рабочая БД, NL Project 1.0 и пользовательская приёмка не выполнялись. Перенос не создаёт Release и не закрывает `USER_ACCEPTANCE_PENDING`.

## Documentation review repair

В рамках того же Issue #118 / Draft PR #119 устранены устаревшие BOX/port identifiers, конкурирующая модель шин, ограничения состава каталога и обязательные execution/recovery зависимости. Все 39 принятых UI acceptance criteria восстановлены в [ACCEPTANCE_CRITERIA.md](engineering/ACCEPTANCE_CRITERIA.md) без истории выполнения. Ссылки ведут на канонические successors. Код, migrations, machine contract и catalog payload не изменены. Technical PASS не означает user acceptance или Release.
