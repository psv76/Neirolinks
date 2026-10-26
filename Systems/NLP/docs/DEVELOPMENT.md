# Контур разработки NL Project 3.x

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


## Доказательство полноты workstream перед релизом

**ChatGPT-координатор, а не Codex:** при начале новой ветки чата, постановке задачи, подготовке интеграции или выпуска сверяет [Issue #145](https://github.com/psv76/Neirolinks/issues/145) и [реестр открытых работ](engineering/NLP_WORK_REGISTER.md). **Codex получает подготовленный task brief и занимается только реализацией в заданном scope, кодом, тестами и отчётом по результату.**

Координатору обязательны полный GitHub inventory `Issues + open PR + все remote branches` (включая `docs/*`, `spike/*` и ветки без PR), чтение принятых UX решений и docs-only PR, проверка зависимого `psv76/NEIROLINKS-TechDocs`, затем **release coverage matrix** на фактическом HEAD и UI: `SHIPPED_VERIFIED / NOT_INCLUDED_APPROVED / BLOCKED` для каждого принятого требования.

**Не выпускать молча неполную реализацию:** зелёный CI/PR merge не доказывает наличие рабочего экрана. При исключении согласованного UX или функции требуется предварительное решение владельца, записанное в #145 + issue + docs register; не заменять это предположением, что работа «перенесена на следующую версию».
