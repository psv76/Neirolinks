# NL Project 2.0

NL Project 2.0 — Windows desktop-система NEIROLINKS для ведения связанной цифровой модели проекта электрики и проводного умного дома. AutoCAD остаётся рабочим чертежом; NL Project связывает планировочные данные, кабельные линии, полевое оборудование, щиты, аппараты, ресурсы каналов и выходную документацию в одной модели.

`Systems/NLP/` — каноническое место текущего принятого состояния NL Project в репозитории NEIROLINKS. Исторические локальные комплекты `D:\NLP_2`, `D:\NLP_2_DOCS` и старые документы `EIM/AutoCAD/Doc` не являются параллельными источниками истины после завершения миграции.

## Текущий статус

Текущий `main` содержит завершённую миграцию Repair 08 и последующие принятые repair:

- NL Project: `2.0` development state;
- schema head: `000000000011_topology_autocad_contract`;
- AutoCAD machine contract: `3.0.0`, 71 canonical block definitions / 10 groups;
- equipment catalog release: `nlp2.mvp.equipment.2026-08-24.repair-05`;
- catalog: 18 passports / 31 products;
- conduit contract: `ППЛ20 -> PP20`, `ППЛ25 -> PP25`, `МПТ16 -> MPT16` для ordinary и bus route fields;
- последний полный non-live/non-manual regression после PR #121: **631 passed, 0 failed, 0 skipped**;
- Windows clean checkout catalog JSON защищён `.gitattributes` с LF после PR #123;
- clean clone, bootstrap CPython 3.13.14 x64 и source launch на Windows подтверждены локально.

Известный format debt по 52 Python-файлам остаётся отдельной задачей. Общая пользовательская приёмка не завершена; отдельный Release не создан.

## Источники истины

При работе с NL Project используется следующий порядок:

1. `EIM/Standards/Development_lifecycle_standard.md` — жизненный цикл разработки, PR, main и Releases.
2. `EIM/Standards/Software_naming_and_versioning_standard.md` — имя и формат версии ПО.
3. `docs/product/` — действующие предметные и продуктовые правила NL Project 2.0.
4. `docs/autocad/` — действующая физическая topology AutoCAD ↔ Project и точный справочник canonical block/ATTDEF.
5. `resources/autocad/block_contract.json` — machine projection AutoCAD-контракта.
6. `resources/catalogs/` — machine catalogs и schemas.
7. `src/`, migrations и `tests/` — фактическая реализация и её проверки.

Если эти источники противоречат друг другу и противоречие нельзя разрешить без нового предметного решения, работа должна остановиться и перейти в GitHub Issue.

## Основные каталоги

```text
Systems/NLP/
├─ docs/
│  ├─ product/          действующие продуктовые правила
│  └─ autocad/          topology и canonical block reference
├─ src/                 исходный код
├─ tests/               автоматические тесты
├─ resources/           machine contracts, catalogs, schemas
├─ tools/               проверки, bootstrap, build и service tools
├─ packaging/           packaging/compliance metadata
└─ data/README.md       правила локальных пользовательских данных
```

## Разработка и запуск

Текущий runtime зафиксирован в `runtime.lock.json`; зависимости — в `requirements.lock`. Рабочий контур рассчитан на Windows x64 и PowerShell 7.

После clean clone:

```powershell
& .\tools\bootstrap.ps1
& .\tools\run.ps1

& .\tools\format-check.ps1
& .\tools\check.ps1
& .\tools\test.ps1
```

После bootstrap source-запуск также доступен через `START_NL_PROJECT_2.vbs`.

Runtime catalog JSON в `resources/catalogs/` должны checkout-иться с LF; это закреплено корневым `.gitattributes`, потому что manifest проверяет SHA-256 сырых байтов payload.

Clean build:

```powershell
& .\tools\build.ps1
& .\dist\NLProject2\NLProject2.exe
```

Generated `build/`, `dist/`, `.venv/`, caches, пользовательские SQLite/DWG и временные runtime-данные не хранятся как каноническое состояние системы.

## NL Project 1.0

NL Project 1.0 и NL Project 2.0 — независимые системы. Существующие объекты 1.0 не мигрируют автоматически в 2.0. Работы в `Systems/NLP/` не должны изменять локальную NL Project 1.0, её базы, DWG или runtime-данные. Подробные правила находятся в `docs/product/01_VERSION_SEPARATION.md`.
