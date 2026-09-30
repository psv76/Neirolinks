# Техническая архитектура NL Project 2.0

**Статус:** `APPROVED`  
**Основание:** принятые архитектурные решения ADR-001…ADR-007

**Дата фиксации:** 2026-08-04

## 1. Область действия

Документ определяет обязательную техническую архитектуру MVP. Предметные правила находятся в [docs/product](../product), границы — в [MVP_SCOPE.md](MVP_SCOPE.md), критерии — в [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md). Этот документ не разрешает миграцию данных NL Project 1.0 и не делает `D:\NLP` источником для версии 2.0.

Обязательные принципы:

- единственный источник инженерной истины — связанная модель проекта в новой SQLite 2.0;
- таблицы, карточки, граф, компоновка, проверки и спецификация являются представлениями модели;
- read operation не изменяет project data;
- production-логика не ветвится по артикулам, моделям, кодам `301`, `401`, `901`, `A01`, `A02`, `WB.01` или объекту `05 44 Богданович`;
- AutoCAD хранит планировочные данные, Project — внутренние цепи, AutoCAD Electrical — подробную монтажную схему;
- функции `OUT OF MVP` не становятся обязательными из-за наличия в 1.0.

## 2. Утверждённый стек и форма приложения

NL Project 2.0 — локальное Windows desktop-приложение в форме модульного монолита с портами и адаптерами.

| Область | Утверждённое решение |
|---|---|
| Runtime | CPython 3.13 x64; точная patch-версия фиксируется [runtime.lock.json](../../runtime.lock.json) |
| UI | PySide6 / Qt 6, Model/View |
| Persistence | одна локальная SQLite; SQLAlchemy 2.x; явный Unit of Work |
| Migrations | Alembic, одна линейная production-ветвь |
| AutoCAD | отдельный Python x64 STA bridge; COM через `pywin32`; versioned JSON-RPC по Windows named pipe |
| Tests | pytest и pytest-qt; уровни определены в [TEST_STRATEGY.md](TEST_STRATEGY.md) |
| Packaging | PyInstaller `onedir` + Windows installer |
| Dependencies | lock-файл с точными версиями и хешами; Windows CI/build runner |

Смешанный Python/.NET стек запрещён без нового явного решения пользователя.

```text
PySide6 views / view models
        ↓ commands and queries
application use cases / Unit of Work / operation coordinator
        ↓                              ↓
domain modules                  query/read-model services
        ↓                              ↓
SQLAlchemy repositories / SQLite 2.0

CadPort ⇄ local named pipe ⇄ STA AutoCAD bridge ⇄ COM ⇄ active DWG
```

## 3. Слои и зависимости

### 3.1. Domain

Сущности, value objects, инварианты и чистые вычисления. Domain не импортирует Qt, SQLAlchemy, Alembic, COM, filesystem/process API. Dispatch допустим по утверждённым `resource_kind`, `relation_kind` и `rule_kind`, но не по товару или проектному обозначению.

### 3.2. Application

Команды, запросы, use cases, DTO, Unit of Work и orchestration. Каждая write-команда имеет одну явную транзакционную границу. Query не запускает миграцию, materialization, sync, repair или иную запись.

### 3.3. Infrastructure

SQLite repositories, SQLAlchemy mappings, Alembic, config, logs, backup, filesystem и CAD transport. ORM-классы не являются domain-сущностями.

### 3.4. Presentation

PySide6 views/view models используют только application ports. UI не открывает SQLite и не содержит инженерных формул. Project settings и local UI preferences разделены.

### 3.5. Test support

Factories, fakes и fixtures находятся в тестовом контуре. Production database/catalog не содержит seed реального объекта или специальных тестовых цепочек.

## 4. Границы модулей

| Модуль | Владеет | Не владеет |
|---|---|---|
| `app_shell` | запуск, навигация, session state, coordination | предметные правила |
| `objects` | projects, buildings, rooms, settings, work sessions | CAD parsing, catalog |
| `catalog` | equipment catalog releases, passport/product versions | project instances |
| `cable_catalog` | versioned cable/HDMI product definitions and releases | equipment passports/products |
| `cad_sync` | scan, baseline, diff, apply/read-back protocol | COM transport, прямой SQL |
| `field_model` | field devices, shared topology/install points, physical keys, field ports, cable-line endpoint identity | внутренние связи аппаратов |
| `cables` | `CableSegment` graph, segment route facts, lengths/overrides, conduit identity and segment assignments, AV extensions | bus topology |
| `constructor` | instances, resources, relations, reservations, generic validation | product identity as logic |
| `distribution` | protection, switching, AC/DC, PSU, ICL | article-specific branches |
| `automation` | channels, LED/PWM, control/measurement chains | physical wiring diagram |
| `buses` | RS-485, DALI, KNX, branches, addresses | separate graph store |
| `panels` | boards, sections, rails, placements | separate equipment list |
| `specification` | derived rows, supply/cost queries | изменение project relations |
| `operations` | config, local profile/last-used, logs, backup, self-check, background operations | предметные fallback |

`site_power`, `heating` и `leak_protection` реализуются feature-пакетами поверх `constructor`, а не собственными системами связей.

## 5. Единая SQLite и транзакции

Одна SQLite содержит registry объектов, все новые проекты, versioned catalog и operation metadata. Все project-owned rows имеют `project_id`. Вне БД находятся только UI settings, logs, temp и backups в собственных каталогах 2.0.

Обязательные правила:

- `foreign_keys=ON`, `journal_mode=WAL`, заданный `busy_timeout`;
- один сериализованный writer queue в desktop-процессе;
- write use case использует короткий `BEGIN IMMEDIATE` и Unit of Work;
- длительный COM/read/calculation выполняется вне write transaction на immutable input snapshot;
- background worker не выполняет DB commit; результат применяется отдельной командой после проверки `project_revision`;
- изменяемые сущности имеют `row_version`; stale write отклоняется;
- недопустимая команда либо сохраняется целиком, либо полностью откатывается;
- UI draft не является persisted project state до успешного commit;
- read provider не создаёт строки, не исправляет данные и не пишет отчёты в source tree.

## 6. Universal constructor и derived state

### 6.1. Разные отношения

- `FunctionalRelation` соединяет два конкретных `InstanceResource` для питания, управления, сигнала или интерфейса.
- `CableLineAssignment` назначает импортированную кабельную линию выходному ресурсу и не заменяет внутреннюю relation.
- bus topology хранит bus/endpoints/branches/branch points; граф строится из этих фактов.

`CABLE_ID` не является техническим ключом внутренней связи.

### 6.2. Rules

Паспорт задаёт ресурсы, характеристики и параметры. Ядро содержит конечный registry универсальных rule families: direction/type/AC-DC/range compatibility, exclusivity/capacity, sum power/current, required path, address/port/slot uniqueness, branching policy, contact/coil/input ratings и supply scope.

LED packing и ICL assessment являются domain policies, выбираемыми по `rule_kind`. Добавление товара существующего rule kind не требует изменения Python core. Произвольный Python/SQL/expression в catalog запрещён.

Каждая проверка возвращает rule/version, severity/status, entity/resource references, actual/required values с единицами, последовательность вычислений и действие пользователя.

### 6.3. Persisted и derived

Persisted facts: исходные и явно принятые значения, projects/instances/resources/relations, manual overrides, sync baselines, user issue decisions и operation metadata, необходимая для восстановления/аудита.

Детерминированно вычисляются graph, validation results, LED packing, loads, specification и другие сводки. Cache допускается только с `input_revision` и `calculator_version`; он удаляем и не является источником истины.

Полная функциональная трасса также является derived read model. Она добавляет к persisted external relations только однозначные internal apparatus edges, подтверждённые machine-readable contract установленного паспорта: product-defined group identity, explicit input/output pairing, ordered paired resources, one-to-one ordinal pairing, series path, signal transform и resource group membership. Внутренние edges не разрешается выводить только из display name, article, project designation или номера тестовой линии.

Управляемый internal edge (`COM → relay output`, `power contact input → output`) несёт dependency refs на electronics/coil resources. Отсутствующая входящая relation зависимости даёт `INCOMPLETE`, а не фиктивный проход. `CableLineAssignment` добавляется в read model отдельным edge kind; physical bus topology не превращается в `FunctionalRelation`.

## 7. Catalog/version policy

- `CatalogRelease`, published passport versions и product versions immutable;
- canonical [docs/product/catalogs/equipment_passports.json](../product/catalogs/equipment_passports.json) и `products.json` являются нормативным versioned import payload для equipment catalog;
- Catalog installer валидирует payload/schema/hash и транзакционно устанавливает release в SQLite; после установки runtime читает equipment catalog только из SQLite, research JSON/XLSX не является runtime source;
- отдельный versioned cable/HDMI catalog использует собственные definitions/releases и не изменяет состав equipment release, объявленный manifest;
- project/instance хранит точную ссылку на версии;
- active release используется только для новых выборов;
- автоматическое обновление старого проекта на latest запрещено;
- upgrade instance выполняется явной командой с resource mapping preview;
- compatible product replacement внутри той же passport version сохраняет `InstanceResource.id` и links;
- structural passport change блокирует commit, пока occupied/removed resources не сопоставлены или связи не удалены явно.

Production catalog содержит только утверждённые identities release из [resources/catalogs/catalog_manifest.json](../../resources/catalogs/catalog_manifest.json) и его payload. Нормативные JSON в [docs/product/catalogs](../product/catalogs) должны соответствовать этому payload. Research XLSX/JSON не являются runtime source.

## 8. AutoCAD boundary

### 8.1. Bridge

Bridge — отдельный Python x64 STA process. Он не знает путь SQLite, не использует repositories и не вызывает `Save`/`SaveAs`. Protocol имеет version, correlation ID, deadline, typed request/result/error. Неизвестная protocol version отклоняется.

При изменении CAD bridge обязателен read-only контур проверки:

1. подключение к AutoCAD;
2. timeout;
3. принудительное завершение bridge;
4. повторный запуск и reconnect;
5. доказательство отсутствия записи в DWG и SQLite.

Неуспех обязательной bridge-проверки блокирует соответствующее изменение PR; перенос COM в основной процесс запрещён.

### 8.2. Read/sync

Bridge создаёт immutable scan snapshot. Application нормализует только контракт 2.0 и строит three-way diff `Project ↔ baseline ↔ DWG`. Пользователь явно выбирает разрешённые DWG→Project changes; они применяются одной project transaction.

`CABLE_TYPE`, `BOARD`, базовый `CABLE_ID` и `LED_TYPE` (для LED) имеют line-level reconciliation. `MOUNT_WAY`/`GOFRA_*` имеют owner-aware reconciliation по входящему `CableSegment`/topology point и никогда не распространяются автоматически на остальные сегменты базовой линии. Используется одна cable/LED/conduit model без отдельной route-section подсистемы. Project-only data сохраняются.

### 8.3. Project→DWG

Application создаёт closed allow-list write plan. Bridge повторно проверяет document identity, handle, block kind и expected old value, выполняет write в AutoCAD undo group и read-back. Baseline обновляется только после успешного read-back. Пользователь сохраняет DWG сам. Частичный внешний результат фиксируется idempotent operation journal и показывается пользователю; distributed transaction не имитируется.

## 9. UI, связи и граф

Основной task-oriented путь создания связи утверждён:

```text
контекст выбранной линии/устройства/незавершённого шага
→ совместимые доступные цели с user-facing labels и причинами недоступности
→ понятный preview действия
→ одна команда commit
```

Generic constructor и полная technical trace находятся в `Инженерных подробностях`; presentation не удаляет их, но не использует как основной рабочий путь. Drag-and-drop допускается только дополнительно. Навигация должна переходить от cable line к resource и обратно без создания связи.

Оболочка и spreadsheet-контракт определены [14_WORKING_USER_INTERFACE.md](../product/14_WORKING_USER_INTERFACE.md). Для таблиц application предоставляет typed read models и команды допустимых изменений; presentation не вычисляет engineering rules и не превращает view/filter state в Project facts.

Согласованная массовая операция строится как `selection snapshot → application plan → full validation/preview → один Unit of Work`. Commit применяет весь план либо откатывает его целиком. Last-used preference читается из локального application profile только после domain filtering и не является скрытым auto-selection. Предметные правила принадлежат [15_CONTROLLED_BULK_OPERATIONS.md](../product/15_CONTROLLED_BULK_OPERATIONS.md).

Граф read-only для структуры модели, selection-aware и зависит от `TopologyRendererPort`. Позиции/свёртка узлов могут храниться как UI layout metadata; узлы и рёбра всегда производны.

При предложении сменить renderer выполняется одинаковый prototype на полном `TEST_OBJECT` для Qt-native graphics scene и WebView. Сравниваются время типовой связи, число действий, читаемость, keyboard path, startup time, package size и полный объект. Результат фиксируется в связанном Issue/PR. Qt-native является базовым вариантом; переход к WebView допускается только при доказанном преимуществе и отдельном явном подтверждении пользователя. До этого структура renderer остаётся за port.

## 10. Config, logs, background и backup

- project settings находятся в SQLite;
- local UI state — versioned JSON в `%LOCALAPPDATA%\NL Project 2.0`, atomic replace;
- глобальный last-used preference хранится там же как versioned user/app setting, действует между проектами и никогда не записывается в Project как инженерное решение;
- logs — structured JSONL с rotation, correlation ID, operation, duration, result и redaction;
- пользователь видит operation log без stack trace; crash data находятся только в собственном каталоге 2.0;
- temp/log/backup/generated не пишутся рядом с кодом, в [docs/product](../product) или `D:\NLP`;
- cancellation не оставляет partial project write; stale background result отбрасывается по revision.

Backup policy:

- verified backup перед каждой migration;
- ежедневный backup при первом успешном закрытии изменённой БД;
- ручная команда backup;
- retention: 14 ежедневных, 8 еженедельных, 12 ежемесячных;
- pre-migration backup хранится отдельно до успешной проверки upgrade;
- manual backups не удаляются автоматической retention policy.

## 11. Migrations

Alembic использует линейные ревизии. Filename: `<12-digit-sequence>_<short_slug>.py`; `revision`, `down_revision`, назначение и affected entities обязательны. Migration не запускается из query/read path.

Порядок upgrade:

1. read schema metadata без записи;
2. отказ, если schema новее приложения;
3. verified pre-migration backup;
4. controlled migration до целевой версии;
5. `foreign_key_check`, `integrity_check`, schema check и smoke reopen;
6. при ошибке рабочая БД не объявляется обновлённой; восстановление выполняется только явной operation.

Data migration должна быть детерминированной и иметь отдельные tests. Исправление данных при обычном чтении запрещено.

## 12. Packaging и распространение

Текущий [tools/build.ps1](../../tools/build.ps1) задаёт reproducible `onedir` build contour. Windows installer pipeline должен поддерживать цифровую подпись. Внутренний MVP допускается без подписи; внешнее распространение запрещено до подписи installer. Автоматическое сетевое обновление в MVP отсутствует; upgrade versioned и явный.

## 13. Трассировка IN MVP

| № | Область | Module / authoritative data | Application / view  |
|---:|---|---|--- |
| 1 | независимое приложение/SQLite | shell, persistence | bootstrap/shell  |
| 2–4 | object lifecycle, card, rooms, time | objects/project hierarchy/work sessions | registry/cards/timer  |
| 5–6 | DWG scan/sync | cad_sync scans/baselines; field_model | sync/conflict review  |
| 7–8 | lengths/conduits | cables facts/assignments | cable/conduit views  |
| 9–12 | catalog→instance/resources | catalog/constructor | catalog/instance/resource views  |
| 13 | internal relations | constructor relations/reservations | link picker/trace  |
| 14 | cable assignment | field_model assignment | assignment panel  |
| 15–16 | domain sections/checks | all domain facts | specialized views/validation center  |
| 17–18 | distribution/PSU | distribution instances/relations/load facts | distribution/PSU views  |
| 19 | LED | automation line/segments/selections | LED workspace  |
| 20 | ICL | ordinary instances/relations/parameters | ICL trace  |
| 21–23 | RS-485, DALI/KNX, graph | buses/endpoints/branches; layout metadata only | topology editor/renderer  |
| 24 | DIN | panels/rails/placements | panel layout  |
| 25 | AV/BOARD_AV | boards/cable AV extensions | AV workspace  |
| 26 | specification/cost | supply/price/input facts | derived specification  |
| 27 | save/close/reopen | all authoritative tables | lifecycle coordinator  |

Проверки определяет [TEST_STRATEGY.md](TEST_STRATEGY.md), acceptance — [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md); точный объём изменения и доказательства фиксируются в связанном Issue/PR.

## 14. Запреты архитектуры

Запрещены:

- доступ 2.0 к изменяемым данным/SQLite/DWG 1.0;
- feature-owned SQLite/JSON stores;
- read-side writes, startup repair и materialization при просмотре;
- второй persisted source для graph/specification/validation/load;
- COM из UI, domain или repository;
- прямой SQL вне infrastructure;
- arbitrary executable catalog rules;
- silent defaults для неизвестных инженерных значений;
- автоподбор PSU/ICL и special-case для тестовых обозначений;
- самостоятельное расширение согласованного объёма Issue.

Числовые UI performance thresholds не задаются архитектурой до рабочего прототипа. После прототипа фиксируются сценарии измерения и baseline, а exact thresholds принимаются пользователем до final UI acceptance.

Изменения выполняются по [Development_lifecycle_standard.md](../../../../EIM/Standards/Development_lifecycle_standard.md): Issue → branch → implementation/docs/tests → PR → review → merge. Рабочая ветка и незамерженный PR — кандидат; текущее принятое интегрированное состояние находится в main/Systems/NLP. Migration PR не создаёт Release и не подтверждает пользовательскую приёмку.
