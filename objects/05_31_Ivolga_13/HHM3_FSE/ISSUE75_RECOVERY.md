> Исторический отчёт по отдельному fix #75 (c35ddbd). Ограничения release в последнем разделе описывают его исходную поставку. Текущий PR сохраняет fix, синхронизирован с NLI 0.1.9 и добавляет cold-start proof; актуальные release/acceptance: INSTALL.md и TEST_RESULTS.md.

# Issue #75: recovery квалифицированного локального M1W2

## Что доказано и что остаётся неизвестным

Прочитаны [Issue #75](https://github.com/psv76/Neirolinks/issues/75), его [дополнительный live comment](https://github.com/psv76/Neirolinks/issues/75#issuecomment-5831097530), #68 и PR #73. Evidence локализует FLOOR_SENSOR_INVALID в 624, а не receiver 500/bridge; serial restart произошёл после одного из invalid и не объясняет периодический дефект. RS485-2 warnings не относятся к 921.10 на RS485-1.

**Точная воспроизведённая причина длительного invalid в коде:** `localM1w2.read()` стирал `proof/seen/qualified` при временно missing control, ошибке, out-of-range или OK=0. После возврата нормального `dev` пустой proof оставался пустым; read опять возвращал STARTUP_VALIDATION. Только новый sample/определённый error-clear callback восстанавливал proof. `watchM1w2()` возвращал null при временно недоступном control, а getter exception helper также превращал в missing обоих controls. Длительный runtime fault таким образом ошибочно становился новой startup qualification.

Паттерн «qualified → один transient read → здоровые value/OK/error, но invalid до numeric republish» воспроизведён и устранён. **Какой именно transient вызвал каждый эпизод 25.09, по опубликованному capture доказать нельзя.** Там нет внутренних read/reset причин. Это не утверждение, что были доказаны physical fault, service restart, clock jump или скрытый bad sample. Добавлена адресная диагностика для следующего отдельно разрешённого наблюдения.

## Все прежние пути потери proof и новая политика

| Путь | Прежнее поведение | После исправления |
|---|---|---|
| Новый rules instance | Нет proof | Неизменно: оба live samples + синхронизация + healthy state |
| Clock назад | Сброс proof/seen/qualified | Сброс admission и обоих startup proofs сохранён |
| Неboolean retained metadata | Sticky unsupported, proof reset | Сохранено, admission отзывается |
| Retained value | Сброс proof/seen/qualified канала | Отдельный barrier, нужен live sample и совпадение с local cache |
| Live invalid value / OK=0 | proof false; qualified false | Немедленная блокировка; до обновления cache bad callback не игнорируется; восстановление current state после наблюдённого fault |
| Error callback | fault latch, proof false | Fault блокирует; prior admission не теряется; live clear или наблюдённый local error→clear восстанавливают |
| read missing / getter exception | proof/seen false | null сейчас; prior admission сохраняется; текущая доступная здоровая пара восстанавливается |
| read active local error | proof false | null сейчас; после local clear admitted датчик восстанавливается |
| read invalid/range/OK | proof false | null сейчас; после восстановления current state admitted датчик восстанавливается |

Admission не персистится. Startup и runtime recovery разделены явно, общая карта и все 20 M1W2 consumers используют один helper. Чистый local transient не меняет numeric measurement timestamp. Реальные fault по-прежнему дают null немедленно: pending bad callback и pending error до обновления dev нельзя снять старым здоровым cache. Retained error clearance не снимает live fault, включая callback-before-cache порядок. Нет нового TTL, heartbeat, RPC/bus access, зависимости от serial service restart или ручного re-arm.

`HHM3Runtime.read()` для M1W2 логирует только изменение phase/reason/cause, с owner и точным path, proof и revalidation flags. VALID recovery логируется info, invalid — warning. Это не новое управление выходами и не MQTT heartbeat. Последняя cause сохраняется в строке recovery, чтобы связать его с предшествовавшим fault. `CONTROL_MISSING`, `CONTROL_ERROR`, `VALUE_INVALID`, `SENSOR_NOT_OK`, `CONTROL_SYNC_WAIT`, `RETAINED_REVALIDATION`, `CLOCK_ROLLBACK`, `MQTT_METADATA_UNSUPPORTED` теперь различимы вместо одного consumer-level FLOOR_SENSOR_INVALID.

## Проверки

```text
node objects/05_31_Ivolga_13/HHM3_FSE/tests/m1w2-recovery-regressions.js --baseline
node objects/05_31_Ivolga_13/HHM3_FSE/tests/m1w2-recovery-regressions.js
```

Baseline — оба общих модуля из immutable `14354bc...`, остальной harness тот же. Результат: 4 PASS / 12 FAIL. Fix: 16 PASS / 0 FAIL. Проверены отсутствие/getter exception controls, local-only errors обоих каналов и их clear, OK 1→0→1, invalid и out-of-range, callback/cache ordering, retained revalidation и retained empty error в обоих порядках, новый instance/retained-only startup, 504 recovery без numeric publications и 10 минут без повторного flapping, вся карта house/boiler 411–420, адресная диагностика без повторов.

Прежние 67 core + 20 sensor-health + 10 partial-ready + PersistentStorage + 4 field-startup groups сохранены. Они покрывают стабильные 24 h, safety/thermal dwell, MSW 120 s, network 30 s/anti-replay, ownership, mixer continuity, исключение 507 и прочие правила. Новая suite добавлена в HHM CI. Physical acceptance из #75 не объявляется выполненной: live запрещён заданием.

## Файлы и release status

Production: `modules/HHM3Wire.js`, `modules/HHM3Runtime.js`.
Tests/CI: `tests/m1w2-recovery-regressions.js`, `.github/workflows/hhm3-fse-check.yml`.
Документы/SHA: этот файл, `SENSOR_HEALTH.md`, `TEST_RESULTS.md`, `INSTALL.md`, историческое уточнение в `FIELD_STARTUP_2026-09-25.md`, `manifest.json`.

Версия остаётся 3.1, контракт m1w2-health-v1. NLI, его release manifests/pins/workflow, 507, MSW/network TTL, receiver и individual consumer rules не изменены. Старые NLI manifests указывают на `14354bc...` и **не содержат исправление**. NLI pinned payload test обязан отказать при сравнении с новым source; его не ослабляли. Полный HHM suite должен быть green; NLI release consistency до отдельной разрешённой подготовки manifests — BLOCKED.

**Готовность к следующему live deploy: BLOCKED.** Требуются review этого fix, устранение/отдельное разрешение прежнего startup blocker #68 и подготовка нового immutable deployment payload в отдельно разрешённой задаче. Затем отдельно разрешённая live-проверка #75: длительное наблюдение 921.10 при normal value/OK/no error, отсутствие ложного FLOOR_SENSOR_INVALID, корректные fault/recovery без numeric change. Нельзя выдавать offline tests за этот результат. SSH, live WB, deploy/restart, OT/physical commands и merge не выполнялись.
