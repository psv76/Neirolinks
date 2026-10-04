# Разделение NL Project 1.0, 2.0 и NL Project 3.0

## Назначение

Документ определяет runtime/data boundary текущей NL Project 3.0 относительно legacy NL Project 1.0 и 2.0.

## Канонический source tree

Текущая разработка 3.x продолжается в `Systems/NLP/`. Отдельная копия `Systems/NLP3/` не создаётся. История 2.0 сохраняется Git history/tags/PR и legacy artifacts, но не является параллельным source of truth.

Внутренний Python package `nl_project_2` может временно сохраняться как compatibility implementation detail. Он не означает, что runtime или данные принадлежат версии 2.0.

## Независимость runtime-данных

NL Project 3.0 использует:

```text
NLP3_PROJECTS_ROOT
NLP3_LOCAL_STATE_ROOT
NLP3_BACKUP_ROOT
NLP3_RELEASE_ROOT
```

Defaults:

```text
D:\NL_Project_3_Data\Projects\nl_project_3.sqlite
%LOCALAPPDATA%\NL Project 3.0
D:\NLP_3_BACKUPS
D:\NLP_3_RELEASES
```

`NLP2_*`, рабочая SQLite 2.0, её local state и backups не являются fallback для 3.0. Legacy database может читаться только в явно разрешённой migration/seed operation отдельной задачи.

## Legacy 1.0/2.0

Задачи 3.0 не изменяют рабочие базы, DWG, настройки, resources, backups или runtime state версий 1.0/2.0.

Исторические пути `D:\NLP`, `D:\NLP_2`, `D:\NLP_2_DOCS` не являются source of truth 3.0.

## Граница cutover

Переименование продукта само по себе не означает пользовательский cutover. Последовательность запуска ведётся Issue #145:

1. accepted UI/DWG flow;
2. runtime identity 3.0;
3. clean DB + backup;
4. performance;
5. real Bogdanovich acceptance.

Только после финальной acceptance 2.0 перестаёт быть штатной рабочей программой.
