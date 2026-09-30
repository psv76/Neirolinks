# Стратегия тестирования MVP NL Project 2.0

## Актуализация Repair 08

Обязательный contour включает exact parity всех 71 canonical definitions и ATTDEF sets; rejected names/removed tags; `DEVICE_NAME`; ordinary roots и concrete `CABLE_SOURCE`; three-way dual-projection cases с real conflict; MRM2/M1W2; DALI `.000` branch и RS-485 `.ZZZ` order; physical `BusSegment`/conduit once; track links без fake length; exact `LOAD_TYPE` allow-lists; migration clean/current/reopen/integrity; predecessor regression и один финальный default-marker full regression. Required skips для Repair 08 — `0`.

**Статус:** `APPROVED`  
**Дата фиксации:** 2026-08-04  
**Evidence policy update:** 2026-08-13

## 1. Цель

Стратегия определяет обязательные доказательства для изменений по текущему жизненному циклу репозитория. Нормативное ожидаемое поведение задают [docs/product](../product), [MVP_SCOPE.md](MVP_SCOPE.md), [TEST_OBJECT.md](TEST_OBJECT.md) и все 60 технических + 39 UI критериев [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md). Legacy-тесты не переносятся как product contract.

## 2. Инварианты тестового контура

- tests не читают и не пишут `D:\NLP` и его SQLite; любой такой доступ запрещён;
- production database не используется как test database;
- каждый test создаёт временную SQLite/fixture в test temp root и удаляет её штатным fixture lifecycle;
- tests независимы от порядка запуска и текущего пользовательского объекта;
- production catalog содержит только утверждённые данные; synthetic entities живут только в tests;
- коды `301`, `401`, `901`, `A01`, `A02`, `WB.01`, `05 44 Богданович` не участвуют в production dispatch;
- unit/integration tests не требуют AutoCAD, кроме явно помеченных live-CAD tests;
- любой test, проверяющий write failure, подтверждает rollback и отсутствие orphan rows;
- derived outputs проверяются по inputs + calculator version и могут быть пересчитаны после удаления cache.

## 2.1. Политика evidence

Все `AC-001…AC-060` и `UI-AC-001…UI-AC-039` обязательны. Предыдущий PASS не закрывает изменённые или ещё не проверенные требования. Колонка `Действие пользователя` в [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) описывает сценарий и public behavior, но не означает, что каждый критерий обязан быть физически выполнен пользователем вручную.

Для каждого AC определяется один тип evidence:

- `AUTOMATED` — сценарий полностью и достоверно воспроизводится unit/application/persistence/UI/E2E contour без test-only production branch;
- `MANUAL_REQUIRED` — требуется реальный внешний application/user interaction, которое нельзя достоверно заменить fixture/mock;
- `MIXED` — automated proof закрывает deterministic часть, manual smoke подтверждает внешний/UX слой.

Для каждого критерия в связанном Issue/PR фиксируются evidence type и concrete evidence. Ни один критерий не получает PASS только потому, что «похожий тест существует»: automated test должен воспроизводить тот же meaning/result. Mock-success не заменяет live CAD, когда критерий проверяет реальный AutoCAD behavior.

Manual acceptance — representative smoke рабочего процесса, а не интерактивный debugger и не отдельный ручной клик для каждого технического AC. Минимальный human contour задан [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) (раздел 4).

## 3. Уровни

### 3.1. Unit

Чистые domain/value-object/calculator tests без Qt, SQLAlchemy, filesystem и COM:

- identity/normalization/ranges/units;
- relation compatibility, exclusivity, capacity and cycles;
- LED cut/FFD/no-auto-split/remainder;
- PSU/load/ICL status and trace;
- RS-485/DALI/KNX topology;
- cable lengths and AV selection;
- DIN placement calculations;
- specification grouping/cost incompleteness.

### 3.2. Application

Use cases с fake ports/repositories:

- command validation and all-or-none behavior;
- draft vs blocking save;
- product replacement/passport upgrade mapping;
- relation/cable assignment separation;
- background result revision/precondition;
- sync diff/decision plan and user-visible trace.

### 3.3. Persistence integration

Real temporary SQLite + SQLAlchemy/Alembic:

- clean create and exact schema revision;
- FK/check/unique/partial unique constraints;
- `BEGIN IMMEDIATE`, commit/rollback and writer serialization;
- stale `row_version` rejection;
- all project-owned rows scoped by `project_id`;
- close/reopen semantic round-trip;
- clean and previous-revision migration;
- backup/restore + FK/integrity/schema checks;
- read/query operations leave file content/project revision unchanged.

### 3.4. Catalog contract

- exact identities/counts/release hash from [resources/catalogs/catalog_manifest.json](../../resources/catalogs/catalog_manifest.json), full payload parity with [docs/product/catalogs](../product/catalogs) and `AC-009` baseline;
- schema/content hashes and immutable release rules;
- full materialization for each passport;
- every product references exact compatible passport version;
- no unsupported/research candidates;
- catalog update does not mutate old instance;
- compatible replacement preserves resource IDs/links;
- structural upgrade blocks occupied removed resource.

### 3.5. CAD contract

Three contours:

1. synthetic validator fixtures without AutoCAD;
2. recorded sanitized protocol responses through fake bridge;
3. separately marked live AutoCAD tests using temporary test DWG when needed.

Test DWG geometry may be deliberately simple/arbitrary. It validates the CAD protocol and 2.0 machine-readable block contract and is not a canonical UGO library or source of product rules.

Changes to the CAD bridge require a read-only robustness contour: connect, timeout, kill, restart/reconnect, zero DWG/SQLite writes. A failed required check blocks the corresponding PR change.

CAD test matrix covers malformed block/layer/attributes, document identity, idempotent scan, three-way diff, explicit DWG→Project apply, closed Project→DWG allow-list, line-wide `CABLE_TYPE`/`BOARD`/base `CABLE_ID`/`LED_TYPE`, segment-owned `MOUNT_WAY`/`GOFRA_*`, rejection of `MIX`, `EL_BOX`/`CABLE_SOURCE` graph validation, shared multi-mechanism `SOCKET` point, grouped `2YY` physical-key order/wire capacity, WB-MRM2/WB-M1W2 field ports, conduit creation/grouping, key-level identity, frame/mechanism/IP44 checks, target preconditions, owner-aware write-back/read-back, partial external failure and no autosave.

### 3.6. UI

pytest-qt and controlled UI fixtures cover:

- launch/close/fatal startup error;
- registry/card/navigation and timer;
- draft/validation/commit feedback;
- line/device/incomplete-step → compatible target filter with labels → understandable preview → one commit;
- keyboard path and focus continuity;
- free/occupied resources and reason unavailable;
- cable↔resource navigation;
- consistent refresh across views;
- local UI settings separate from project settings;
- background progress/cancel without UI freeze.
- approved `Линии` layout: table top, card bottom, horizontal splitter, no permanent right card;
- inline edit, Tab/Shift+Tab/Enter/Esc/arrows, copy/paste, fill-down, multi-select, bulk edit, search/sort/filter and restored view;
- `Готово` / `Требуется действие` / `Нужны данные` / `Ошибка проекта` with reason, impact, action and navigation;
- cable journal, validation center and operation journal as separate same-model views;
- physical key → separate input, including WB-MCM8 `Input 1`…`Input 8` labels;
- reserve, safe duplicate, numbering only new and global last-used behavior;
- protection/power/output/input bulk plans: homogeneous selection, full preview, deterministic mapping and all-or-none commit;
- generic constructor and full technical trace only in engineering details.

### 3.7. Renderer comparison

A proposed renderer change compares identical `TopologyReadModel` and full TEST_OBJECT for Qt-native and WebView prototypes. Record:

- median time and actions for typical link/navigation task;
- readability at overview/detail scales;
- keyboard-only completion;
- cold/warm startup impact;
- installed package size delta;
- render/update on full object;
- accessibility/error/packaging findings.

Qt-native is base. WebView requires documented advantage and explicit user approval. Structural model tests are renderer-independent.

### 3.8. End-to-end and acceptance

Технический automated contour не заменяет отдельную UI acceptance. Codex не должен pre-seed finished chains в реальный пользовательский Project и не должен редактировать production DB напрямую. Перед пользовательской приёмкой проходят full automatic suite, `AC-001`…`AC-060` и все обязательные `UI-AC-*`; затем пользователь без сопровождения выполняет representative workflow.

Real-user smoke обязан подтвердить representative workflows, где fixture недостаточна: live DWG reconciliation/no-autosave/conflict, одна AC/control chain, одна DC/LED chain, одна physical bus topology, semantic reopen и чтение итоговой trace/specification. Остальные deterministic критерии могут быть закрыты автоматикой при полном соответствии их ожидаемому результату.

## 4. Coverage by MVP area

| Area | Required test levels | Acceptance evidence |
|---|---|---|
| app/independence | integration, packaging, smoke | clean launch; no `D:\NLP` access |
| object/rooms/time | unit, app, DB, UI | create/edit/switch/reopen/time |
| catalog/instances/resources | contract, app, DB | manifest/payload parity, full resources, replacement |
| DWG/field sync | validator, fake bridge, live CAD, DB, UI | CAD-004..006, no autosave |
| cables/lengths/PND/AV | unit, DB, UI | length precedence, bulk rollback, AV identity |
| constructor/checks | unit, app, DB | universal chains, blocking violations, trace |
| distribution/PSU/ICL | unit, app, UI | AC/DC paths, capacity, five statuses |
| automation/LED | unit, app, DB, UI | channels, cut/FFD/coils, power/current |
| buses/graph | unit, DB, renderer, UI | topology rules and graph equivalence |
| site/heating/leak | post-MVP deferred | future activation требует отдельного catalog/acceptance decision |
| DIN | unit, DB, UI | overlap/width/external/unknown |
| specification/cost | unit, query, UI | source trace, grouping, supply, unknown cost, physical mechanisms, mounting-box demand, configurable WB-MSW |
| operations | fault, performance, backup/restore | cancel/recovery/retention/self-check |
| persistence overall | DB, migration, E2E | semantic close/reopen and integrity |

## 5. Blocking-save matrix

Automated tests must prove rollback for each blocking violation from MVP:

- duplicate project instance designation;
- double assignment of exclusive resource;
- incompatible voltage;
- input→input;
- output→output;
- power cycle;
- reference to deleted instance.

Separate tests prove that incomplete but otherwise valid draft with errors/warnings can persist. Deleting an instance with links requires confirmation and then removes instance/links in one transaction.

## 6. Universal chain matrix

Before using TEST_OBJECT codes, tests verify universal rules on synthetic instances for:

- AC power through passive/switching resources;
- DC power through PSU;
- controlled relay/coil with electronics and COM separated;
- 0–10 V and 4–20 mA range compatibility;
- discrete input/output;
- one-to-one interface;
- exclusive and shared/capacity resources;
- line assignment separate from internal relation;
- linear and branched buses.

No fixture name may affect expected rule selection.

## 7. Migration tests

Each Alembic revision has:

1. clean upgrade to head;
2. upgrade from immediate predecessor;
3. schema/constraint assertions;
4. data transformation assertions if applicable;
5. failure injection and recovery/unchanged-source evidence;
6. FK/integrity check and reopen;
7. report entry with revision, reason and test result.

Downgrade is required only when the migration contract explicitly declares it safe. Absence of downgrade must fail safely and be documented; it is never simulated by deleting data.

## 8. Backup tests

Test database only:

- verified pre-migration backup;
- daily backup only at first successful close of changed DB;
- retention selects 14 daily, 8 weekly, 12 monthly without deleting selected overlaps incorrectly;
- pre-migration backup retained until successful verification;
- manual backup excluded from automatic deletion;
- restore to separate temp directory and semantic reopen;
- corrupted copy rejected without changing active DB.

## 9. Performance and stability

Measurements use recorded dataset size and hardware/runtime metadata. Required measurements: cold/warm startup, object open, full validation, graph rebuild, fixture scan/diff, main view switch, spreadsheet edit/bulk preview/commit, backup/restore, package cold start. Числовые UI thresholds устанавливаются только после рабочего прототипа: сначала измеряется baseline на representative dataset, затем пользователь принимает exact criteria до final UI acceptance. Оптимизации требуют profiler/query evidence.

Investigate nondeterministic failures and repeat the full suite when needed to verify their cause. Any nondeterministic failure is a failure, not a retry-success.

## 10. Canonical commands

Repository wrappers in `tools` resolve the interpreter declared by [runtime.lock.json](../../runtime.lock.json). Underlying canonical commands:

```powershell
python -m compileall src tests tools
python -m pytest
python -m pytest -m "not live_cad and not manual_acceptance"
python -m pytest -m live_cad
```

Wrapper names, environment setup and locked runtime are documented in [DEVELOPMENT.md](../DEVELOPMENT.md), [runtime.lock.json](../../runtime.lock.json) and [tools/_common.ps1](../../tools/_common.ps1). Production tasks run compile/static architecture checks, applicable focused tests, then the full non-manual suite. Live CAD and manual acceptance run only when explicitly required and permitted.

## 11. Reporting

Verification evidence in the related PR records:

- exact commands and environment/runtime versions;
- passed/failed/skipped counts per contour;
- reasons for skips; mandatory tests cannot be skipped for `PASSED`;
- migration revisions and DB fixture paths (temp only);
- live external app/manual steps separately from automated tests;
- failures and whether any write occurred;
- evidence IDs/paths;
- `D:\NLP`/SQLite invariant.

No test may report fabricated success. A failed required test prevents readiness of the corresponding PR until its cause is resolved.

## 12. Release gates

Жизненный цикл определяется [Development_lifecycle_standard.md](../../../../EIM/Standards/Development_lifecycle_standard.md): Issue → branch → implementation/docs/tests → PR → review → merge. Незамерженный PR является кандидатом. Migration PR не создаёт Release.

- Для изменения обязательны applicable focused tests и полный non-live/non-manual regression; обязательные failures/skips исключают `PASSED`.
- Для пользовательского MVP обязательны все 60 технических и 39 UI acceptance criteria, допустимое evidence и representative manual acceptance раздела 4 [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).
- Перед Release обязательна независимая проверка в clean environment без исправлений, smoke из immutable release directory, manifest/hash и installer checks.
- Approved Release публикуется отдельно по lifecycle standard; технический PASS и merge сами по себе не объявляют выполненную user acceptance и не разрешают выпуск.
