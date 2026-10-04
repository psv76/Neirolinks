# NL Project 3.0

NL Project 3.0 — Windows desktop-система NEIROLINKS для проектирования электрики и проводного умного дома рядом с AutoCAD. AutoCAD остаётся основным местом работы с планом; NL Project является вторым рабочим представлением проекта.

`Systems/NLP/` — канонический source tree текущей линии NL Project 3.x. Отдельная папка `Systems/NLP3` не создаётся. История 1.0/2.0 сохраняется Git history и legacy artifacts, но не является runtime source 3.0.

## Текущий статус

- product line: `3.0` development state;
- global development/recovery router: GitHub Issue `#145`;
- Stage 0: Issue `#142` / PR `#144` merged — accepted Lines UI, one-click DWG workflow and local cell-specific remediation;
- current stage: Issue `#146` — external/runtime identity 3.0;
- schema head: `000000000012_timber_mount_way`;
- AutoCAD machine contract: `3.0.0`, 71 canonical block definitions / 10 groups;
- equipment catalog release remains `nlp2.mvp.equipment.2026-08-24.repair-05` as an immutable catalog identity;
- PR #144 Windows non-live/non-manual regression: **715 passed, 0 failed, 1 existing warning**.

3.0 is not Release/live-ready until #147, #148 and #149 are complete.

## Runtime identity 3.0

```text
NLP3_PROJECTS_ROOT
NLP3_LOCAL_STATE_ROOT
NLP3_BACKUP_ROOT
NLP3_RELEASE_ROOT
```

Defaults:

```text
Projects:     D:\NL_Project_3_Data\Projects
Database:     nl_project_3.sqlite
Local state:  %LOCALAPPDATA%\NL Project 3.0
Backups:      D:\NLP_3_BACKUPS
Releases:     D:\NLP_3_RELEASES
```

`NLP2_*` variables do not redirect the 3.0 runtime. Python package `nl_project_2` is retained temporarily only as an internal compatibility name.

## Разработка и запуск

```powershell
& .\tools\bootstrap.ps1
& .\tools\run.ps1
& .\tools\format-check.ps1
& .\tools\check.ps1
& .\tools\test.ps1
```

Source launcher: `START_NL_PROJECT_3.vbs`.

Clean build:

```powershell
& .\tools\build.ps1
& .\dist\NLProject3\NLProject3.exe
```

Generated `build/`, `dist/`, `.venv/`, caches, user SQLite/DWG and temporary runtime data are not source of truth.
