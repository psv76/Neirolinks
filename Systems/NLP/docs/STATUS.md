# NL Project 2.0 — текущее состояние

## Current development state

`Systems/NLP/` в `main` является каноническим текущим состоянием NL Project 2.0. Миграция из локальных `D:\NLP_2` / `D:\NLP_2_DOCS` завершена через Issue #118 и PR #119; локальные исторические комплекты больше не являются параллельным source of truth.

Текущие подтверждённые факты:

- NL Project: `2.0` development state;
- schema head: `000000000012_timber_mount_way`;
- AutoCAD machine contract: `3.1.0`, 71 canonical block definitions / 10 groups;
- equipment catalog release: `nlp2.mvp.equipment.2026-08-24.repair-05`;
- equipment catalog: 18 passports / 31 products;
- conduit contract поддерживает `ППЛ20 -> PP20`, `ППЛ25 -> PP25`, `МПТ16 -> MPT16` для ordinary и bus route fields; для `В брусе` обязательны `ППЛ20/ППЛ25`, кабельный запас составляет `0,5 м` на segment и не входит в длину трубы; material code полипропилена остаётся `PP`;
- полный non-live/non-manual regression на состоянии PR #121: **631 passed, 0 failed, 0 skipped**; один существующий SQLite datetime adapter warning;
- AutoCAD contract, human ↔ machine parity, catalog checker и static checks на PR #121: `PASS`;
- PR #123 добавил корневой `.gitattributes` с `text eol=lf` для `Systems/NLP/resources/catalogs/*.json`, чтобы Windows checkout не менял байты catalog payload и не ломал manifest hashes;
- после PR #123 локально подтверждены clean clone на Windows, bootstrap CPython 3.13.14 x64 и source launch NL Project из `Systems/NLP`.

## Что не является текущим source of truth

Временные build/recovery TASK/REPORT, `90_ARCHIVE`, caches, `.venv`, `build`, `dist`, пользовательские SQLite/DWG и иные generated/runtime данные не являются действующими требованиями системы.

Три ранних документа `EIM/AutoCAD/Doc/Blocks.md`, `Parsing.md` и `NL_Cloud_Desktop_v1.0.md` удалены после появления канонических successors. Карта замены и исторические проверки переноса находятся в [MIGRATION.md](MIGRATION.md).

## Открытый technical debt

Format check по-прежнему выявляет 52 Python-файла, требующих `ruff format`. Этот долг существовал до миграции и пока не исправлен массовым форматированием.

## User acceptance и Release

Общая пользовательская приёмка NL Project 2.0 не завершена. Merge технических PR и успешные автоматические проверки сами по себе не создают Release.

Текущий `main` остаётся development state; отдельный Release не создан.
