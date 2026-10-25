# NLP 3.1 / Issue #255 — план ограниченных задач Codex

Источник требований: [Issue #255](https://github.com/psv76/Neirolinks/issues/255). Норматив процесса: [CODEX_SESSION_STANDARD.md](CODEX_SESSION_STANDARD.md).

**База реализации:** отдельная task-ветка от **актуального проверенного D23-кандидата**, а не от устаревшей версии контракта в `main`. Перед первым запуском координатор пинует точный SHA и проверяет нет ли движений ветки/нового merge. Реализацию #255 не коммитить в D23 и не смешивать с #262/#263 до отдельной интеграционной приёмки.

## Вехи

| ID | Исполнимый срез | Приёмка | Зависит от |
| --- | --- | --- | --- |
| C0 | Зафиксировать base SHA, API/тестовые ссылки, точные allow/deny правила | Размеченное ТЗ C1 и отдельная ветка | #255, D23 |
| **C1** | Чистый парсер формата рабочего слоя `GGG_<name>` без подключения к runtime | Параметризованные positive/negative unit tests, никакой смены текущего scan | C0 |
| C2 | Сопоставление префикса → group и разрешённые типы, `HVAC=600` из HEATING+VENTILATION | Проверки существующих специальных типов, non-AV Cable ID, не скрывать неверные группы | C1 |
| C3 | `AV=700`, свободный `CABLE_ID`, BOARD_AV и identity | AV free-text и negative тесты без навязанного `7YY` | C2 |
| C4 | Логический `DALI_GROUP` на `300_*`/`400_*` без обязательного DALI_GROUPS | Инварианты DALI ID/dynamics, смешанный слой и отсутствие физической линии | C2 |
| C5 | Селектор слоёв перед дорогими COM-чтениями, incremental #148 | Spy/mock удостоверяет отсутствие дорогостоящих COM вызовов вне рабочих слоёв | C1–C4 |
| C6 | Переход старых DWG: fail-closed защита missing/reconciliation | Изменение слоя не превращает неувиденные старые вставки в подтверждённое удаление; повторный scan no-op | C5 |
| C7 | Совместная проверка #255 + D23, канонический норматив и docs, подготовка live gate | Все выбранные Linux CI + locked-suite план, отдельный Windows/AutoCAD acceptance; никакой production activation | C2–C6 |

Никакой из срезов C1–C6 не означает завершения #255 целиком. Схема/catalog и рабочая база — отдельный release gate, если их изменения потребуются.

## Первый запуск — C1

**TASK_ID:** NLP-255-C1-LAYER-PARSER

**ISSUE:** #255 (действующие требования); новые Issues не создавать.

**REPO:** `psv76/Neirolinks`; `Systems/NLP`.

**BASE_REF:** `integration/nlp-237-d23-stagec-d22-candidate` как актуальная подтверждённая D23-база. **BASE_SHA (подготовлен и проверен):** `9366629eb8710de8985149e8bbc3a3e85a1823ea`. Перед запуском ещё раз сверить `BASE_REF` с этим SHA. При расхождении остановиться, пересогласовать базу и обновить brief; не угадывать SHA.

**WORK_BRANCH:** `feature/nlp-255-c1-layer-parser` (создать только перед работой после проверки BASE_SHA; не менять source branches).

**CURRENT CONTRACT:** функция `BlockContractCatalog.groups_for_layer` сейчас использует точный `layer in rule.layers`; рабочие группы `HEATING`/`VENTILATION` ещё не объединены. Это не поведение для исправления в C1.

**RESULT:** новая чистая, детерминированная функция разбора **имени рабочего слоя** в отдельном небольшом модуле `Systems/NLP/src/nl_project_2/cad_contract/layer_names.py`. Она возвращает номер группы (или `None` для нерабочего/некорректного слоя) без обращений к COM, SQLite, contract JSON и без изменения существующих runtime вызовов. Строго девять префиксов `100,200,...,900`, затем `_` и непустой суффикс, без начального/конечного пробела; суффикс в остальном не интерпретировать и не ограничивать искусственным словарём. Не делать скрытого `strip()` с исправлением невалидного ввода.

**ALLOWED FILES:** `cad_contract/layer_names.py` и новый `tests/cad_contract/test_layer_names.py` (путь под `Systems/NLP/`). При необходимости минимальные package exports только с объяснением.

**OUT OF SCOPE:** `catalog.py`, `validator.py`, COM bridge, scan/filter, reconciliation, `block_contract.json`, migration, HVAC/AV/DALI mapping, runtime wiring, docs/TechDocs, установленные файлы.

**POSITIVE TESTS:** `100_Socket`, `100_Line`, `200_сценарники`, `300_Light 230V floor`, `400_LED карнизы`, `600_Отопление`, `600_Вентиляция`, `700_HDMI`, `700_Акустика`, `800_NETWORK`, `900_RS-485 карнизы`; несколько имён с одним префиксом, дополнительные `_`, регистр и кириллица.

**NEGATIVE TESTS:** `300`, `300_`, `300_  `, `300_ Свет`, `300_Свет `, `350_Свет`, `000_Свет`, `1000_Свет`, `DALI_GROUPS`, `ARCH_WALLS`, пустая строка; non-string input должен не падать с неожиданным исключением (зафиксировать контракт).

**TESTS:** `PYTHONPATH=src python -m pytest -q tests/cad_contract/test_layer_names.py`, `python -m compileall -q src/nl_project_2/cad_contract`, `python -m ruff check src/nl_project_2/cad_contract/layer_names.py tests/cad_contract/test_layer_names.py` (в рабочем каталоге `Systems/NLP`).

**ACCEPTANCE:** минимальный код + тесты PASS; никакого runtime подключения нового парсера; отсутствие изменений вне scope; коммит в рабочую ветку и отчёт с SHA. Если не хватает времени — безопасный partial commit + checkpoint.

**CHECKPOINT:** комментарий в #255 и отдельный короткий файл `Systems/NLP/docs/engineering/checkpoints/NLP_255_C1.md` в рабочей ветке с `base_sha/head_sha/status/tests/next_action` (создавать checkpoint после изменения исходников).

**STOP CONDITIONS:** изменился base SHA, требования противоречат принятому #255, тесты требуют COM/live DWG, выбранный scope недостаточен, лимит подходит к концу. В случае конфликта не расширять работу самовольно.

## Восстановление последующей сессии

Следующая задача должна начинаться с текста: «Прочитай C1 checkpoint и task brief; проверь head SHA, выполненные тесты и сделай только незавершённую конкретную операцию». Не просить Codex заново изучать весь Issue и историю PR.
