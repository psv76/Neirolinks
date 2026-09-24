# HHM 3.1.0 — программная проверка Issue #68

База: `1668c32d7187f0a59ccdea5d5b7da10f14f9660f`. Проверки выполняются локально/CI, без WB, SSH и физических writes. Harness моделирует control cache, MQTT callbacks, два WB, ownership и принятые команды; не подтверждает гидравлику.

## Выполнено локально

- `node tests/run.js`: 67 групп основной модели, review/MAO4/2.40 regressions PASS.
- `node tests/partial-ready-regressions.js`: 10 групп PASS, включая 502, локальные faults и mixer continuity.
- `node tests/persistent-storage-regressions.js`: PASS, 18+505 настройки и restart без повторного ввода.
- `node tests/sensor-health-regressions.js`: 19 групп PASS. Stable 24 h без публикаций, редкие изменения, retained-only startup и empty errors, OK flapping/recovery, errors обоих controls, missing/invalid/range, callback/cache ordering, clock rollback, 20-channel mapping, 10 минут совместной работы 500/620/624 без M1W2 publications, MSW/frame TTL, thermal stop/cooling/recovery, диагностика 411–420 и отсутствие нового interlock от 412.

Базовые tests не заменены новыми: прежние негативные сценарии и ownership остаются обязательными. Модель по умолчанию публикует неизменные значения раз в 60 с; новые health tests отдельно полностью прекращают temperature и OK публикации после qualification, продолжая MSW и frames.

Python/NLI локально: 160 tests — 123 PASS, 37 SKIP (Windows symlink privilege). Первый запуск унаследовал NO_COLOR=1/TERM=dumb и выявил зависимость существующего CLI color-test от окружения; повтор в изолированном test process с обычным TERM и без NO_COLOR прошёл. Пользовательские настройки и код NLI не менялись. Exact-507 Node regression также PASS.

## Release и NLI

`node tests/manifest.js --check` проверяет полный HHM release; NLI role manifests дополнительно содержат exact-byte SHA всех production files, включая внешнюю 600 диагностику. `NLI/tests/test_hhm31.py` проверяет pinned bytes против текущего runtime, reproducible build и обязательную аттестацию обоих roles. `NLI/tests/sandbox.py` проверяет offline migration 3.0→3.1 и rollback к точным исходным bytes на fake WB. NLI policies, transaction engine и 0.1.6 package version не изменены.

Итог Python/NLI и ссылки CI фиксируются в draft PR по фактическому результату финального HEAD. Windows может пропускать тесты, требующие прав создания symlink; Linux CI обязан выполнить их без пропусков.

## Границы

Физическое подключение, Modbus polling на живом объекте, silent failure самого драйвера без публикации ошибок, точность датчиков, безопасный путь циркуляции, положение клапанов и CH-only OFF с сохранением ГВС не доказываются моделью. Runtime опирается на штатную доставку control errors от работающего локального драйвера; искусственный heartbeat или изменение polling configuration не добавлены. Полевую приёмку выполнять отдельно по INSTALL.md. Исторические ограничения wb-rules 2.40 остаются в ISSUE61.md.
