# Контур разработки NL Project 3.0

Runtime зафиксирован в `runtime.lock.json`, зависимости — в `requirements.lock`.

```powershell
& .\tools\bootstrap.ps1
& .\tools\check.ps1
& .\tools\format-check.ps1
& .\tools\test.ps1
& .\tools\run.ps1
& .\tools\build.ps1
```

Все wrappers используют `.venv\Scripts\python.exe`, созданный из CPython 3.13.14 x64 внутри текущего source tree.

Source launcher: `START_NL_PROJECT_3.vbs`.

Frozen build: `dist\NLProject3\NLProject3.exe`.

Внешняя/runtime identity — NL Project 3.0. Внутренний Python package `nl_project_2` временно сохраняется для compatibility и не является пользовательским именем версии.
