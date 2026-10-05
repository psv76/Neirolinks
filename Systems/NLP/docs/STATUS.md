# NL Project 3.0 — текущее состояние

## Current development state

`Systems/NLP/` в `main` — канонический source tree текущей линии NL Project 3.x. Глобальный development/recovery router: GitHub Issue `#145`.

Подтверждённая база перехода:

- Stage 0 / Issue #142 / PR #144 merged to `main`;
- accepted Lines UI and one-click DWG workflow are canonical;
- PR #144 Windows non-live/non-manual regression: **715 passed, 0 failed, 1 existing SQLite datetime adapter warning**;
- schema head: `000000000013_screed_mount_way`;
- AutoCAD machine contract: `3.0.0`, 71 canonical block definitions / 10 groups;
- equipment catalog release `nlp2.mvp.equipment.2026-08-24.repair-05` сохраняет исходную immutable identity;
- current product line: `3.0` development state.

## Runtime separation 3.0

- launcher: `START_NL_PROJECT_3.vbs`;
- build: `NLProject3\NLProject3.exe`;
- environment namespace: `NLP3_*`;
- default database: `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite`;
- local state: `%LOCALAPPDATA%\NL Project 3.0`;
- backups: `D:\NLP_3_BACKUPS`;
- releases: `D:\NLP_3_RELEASES`;
- optional cloud backup root: `NLP3_CLOUD_BACKUP_ROOT`; production workstation target is `D:\YandexDisk\05 NeiroLinks\NL Project 3.0\Backups`.

Внутренний Python package `nl_project_2` временно сохраняется для compatibility и не является user-facing identity.

## User acceptance и Release

Product line 3.0 остаётся development state. Runtime rename не создаёт Release и не подтверждает live readiness.

Оставшиеся launch stages по #145:

- #147 — clean DB + backup/cloud contour;
- #148 — DWG refresh performance gate;
- #149 — real Bogdanovich acceptance and final cutover.
