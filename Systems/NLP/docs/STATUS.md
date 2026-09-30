# NL Project 2.0 — состояние переносимого baseline

## Baseline

Состояние восстанавливается из локальных снимков документации и программы, использовавшихся до переноса в `Systems/NLP/`.

Подтверждённые артефактами baseline-факты:

- schema head: `000000000011_topology_autocad_contract`;
- AutoCAD machine contract: `3.0.0`;
- canonical AutoCAD block definitions: 71;
- equipment catalog release: `nlp2.mvp.equipment.2026-08-24.repair-05`;
- equipment catalog: 18 passports / 31 products;
- Repair 08 implementation report исходного build-комплекта: `PASSED`;
- общий пользовательский acceptance исходного build-комплекта: не завершён.

## Что не переносится как source of truth

Не переносятся временные build/recovery TASK/REPORT, `90_ARCHIVE`, caches, `.venv`, `build`, `dist`, пользовательские SQLite/DWG и иные generated/runtime данные. Их историческая ценность не превращает их в действующие требования.

Три ранних документа `EIM/AutoCAD/Doc/Blocks.md`, `Parsing.md` и `NL_Cloud_Desktop_v1.0.md` удалены в migration branch после появления канонических successors. Карта замены и фактические проверки переноса находятся в [MIGRATION.md](MIGRATION.md).

Повторный non-live/non-manual regression перенесённой копии: **586 passed, 0 failed, 0 skipped**. Contract/catalog parity и static check пройдены. Format check сохраняет исходное замечание по 52 файлам; оно не исправлялось массовым форматированием в migration scope. PR остаётся Draft, merge требует отдельного подтверждения пользователя.

## Release

Этот baseline является текущим development state NL Project 2.0. Перенос в GitHub не создаёт Release и не подтверждает пользовательскую приёмку.
