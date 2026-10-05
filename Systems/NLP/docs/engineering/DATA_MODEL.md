# Логическая модель данных MVP NL Project 2.0

## Актуализация — schema head `000000000013`

Ordinary cable truth остаётся в `cable_line` / `cable_point` / `cable_segment`. Concrete field endpoint хранится typed reference на `field_port`; `CABLE_SOURCE` и port occupancy — две reconciled projections одного edge, а `ROOT_ENDPOINT` — derived read-model field. Bus truth хранится отдельно: `bus.cable_type`, physical `bus_segment` и `bus_segment_conduit_assignment`. DALI/RS-485 `bus_segment` не дублируется в ordinary `cable_segment`. Канонический RS-485 point ID — `9YY.ZZZ`; `.000` зарезервирован для root.

**Статус:** `APPROVED`  
**Основание:** принятые архитектурные решения ADR-002/004/005

**Дата фиксации:** 2026-08-04

## 1. Граница и общие правила

Модель предназначена для новой единой SQLite NL Project 2.0. Она не копирует таблицы 1.0 и не предусматривает миграцию проектов 1.0.

- technical ID: application-generated UUID v4, lowercase canonical text;
- natural identifiers хранятся отдельно и имеют explicit scope uniqueness;
- все project-owned entities имеют `project_id`;
- изменяемые entities имеют `created_at_utc`, `updated_at_utc`, `row_version`;
- significant entities используют `ACTIVE | RETIRED`; destructive delete блокируется при ссылках;
- engineering decimals сохраняются точным decimal representation, не binary float;
- unknown — `NULL` с `knowledge_status/reason/source`, а не `0` или пустая строка;
- timestamps — UTC; timezone presentation не меняет факт;
- one fact — one owner — one authoritative table.

Повторяемые value objects: `Voltage(value,current_kind)`, `Range(min,max,unit)`, `PowerW`, `CurrentA`, `LengthM`, `WidthMm`, `EngineeringValue(value,unit,knowledge_status,source_kind)`, `SupplyScope`, `Severity`, `Completeness`.

## 2. Владение

```text
CatalogRelease
 ├─ PassportDefinition(version)
 │   ├─ PassportPropertyDefinition
 │   ├─ PassportResourceDefinition
 │   └─ PassportRuleDefinition
 └─ ProductDefinition(version) ──> exact PassportDefinition(version)

Project
 ├─ Building ──< Room
 ├─ Board ──< ProjectInstance ──< InstanceResource
 ├─ FunctionalRelation ──> InstanceResource × 2
 ├─ CableLine ──< CablePoint / CableLineAssignment / ConduitAssignment
 ├─ Bus ──< BusEndpoint / BusBranch / BusBranchPoint
 ├─ PanelSection ──< PanelRail ──< PanelPlacement
 ├─ DwgDocumentBinding ──< DwgScan / DwgBaseline / DwgSyncOperation
 └─ ProjectSetting / WorkSession / CommercialFact / OperationJournal
```

## 3. Catalog

### 3.1. `catalog_release`

`id`, unique `release_code`, `schema_version`, `content_sha256`, `installed_at_utc`, `status`. Published release immutable. Ровно один `ACTIVE` для новых выборов; retired releases сохраняются, пока на них ссылается проект.

### 3.2. `passport_definition`

Unique `(passport_key, version)`. Fields: name, equipment class, functional role, schema version, lifecycle, source reference, content hash. Published version immutable.

### 3.3. `passport_property_definition`

Unique `(passport_definition_id, property_key)`. Typed value/range/enum, unit, knowledge status, evidence/source.

### 3.4. `passport_resource_definition`

Unique `(passport_definition_id, resource_key, ordinal)`. Fields: resource kind, direction, medium, quantity/ordinal, electrical/signal properties, exclusivity, capacity, group key, display metadata. Display order is not identity.

### 3.5. `passport_rule_definition`

Unique `(passport_definition_id, rule_key)`. Fields: registered `rule_kind`, typed/versioned parameters, referenced resource keys. Executable code/expression is forbidden in catalog.

### 3.6. `product_definition`

Unique `(product_key, version)`, exact passport version FK. Fields: manufacturer, series, model, article, name, physical dimensions, DIN width, package/coil facts, parameters used by Project, supply defaults, evidence and lifecycle. `(normalized_manufacturer, normalized_article)` is unique only when article is known.

### 3.7. Version rules

Published rows are immutable. Correction creates a version. Active catalog change does not mutate old projects. Runtime catalog contains exactly the approved identities declared by [resources/catalogs/catalog_manifest.json](../../resources/catalogs/catalog_manifest.json) and its payload. Research data must be explicitly transformed and validated before becoming a catalog release.

## 4. Project and organization

### 4.1. `project`

`id`, unique active `project_code`, name, approved card fields, active catalog release, lifecycle, `project_revision`, timestamps. Project code is never an FK.

### 4.2. `building`

Owner project. Unique `(project_id, normalized_code)`. Name, order and approved building properties.

### 4.3. `room`

Owner building. Unique `(building_id, normalized_name)` according to product identity `Здание + Название`. Concrete floor-base mark in millimetres relative to finished-floor zero, room height and approved display/color facts.

### 4.4. `project_setting`

Owner project. Key from closed registry, typed value. Only settings affecting project meaning/output. Window geometry/filter state is not stored here.

### 4.5. `work_session`

Owner project. Start/stop UTC, active/idle intervals, close/recovery reason. One active session per application instance. Recovery appends an explicit record and never silently rewrites elapsed history.

### 4.6. Local application profile

Глобальные пользовательские preferences интерфейса и last-used хранятся в локальном versioned application profile вне Project. Они не являются engineering facts, не влияют на воспроизводимость проекта и не переносятся в проектный файл. Невалидная ссылка на отсутствующий каталоговый вариант удаляется/игнорируется без изменения Project.

## 5. Boards, instances and resources

### 5.1. `board`

Owner project. Unique active `(project_id, designation)`. Board kind, room/location, title, lifecycle. `BOARD_AV` is an ordinary approved board kind/designation, not a special schema.

### 5.2. `project_instance`

Owner project; optional board/room. Unique active `(project_id, designation)`. Exact passport version, optional exact product version, supply scope, lifecycle, notes and approved instance parameters. Product must reference the same passport version.

### 5.3. `instance_resource`

Owner instance. Unique `(project_instance_id, resource_key, ordinal)`. Source passport/resource version, kind/direction/medium and reproducibility snapshot. Resource ID is stable through compatible product replacement.

Для `PRODUCT_DEFINED` групп materialization snapshot содержит детерминированные `group_key`, `group_ordinal`, `point_ordinal`, `group_count` и `points_per_group`, вычисленные только из machine-readable grouping паспорта и параметров выбранного товара. Это не отдельный persisted graph. При чтении snapshot прежнего runtime те же значения могут быть детерминированно получены из сохранённых passport/product facts без repair/write.

### 5.4. `product_selection_history`

Old/new product versions, command ID, actor/time and compatibility result. Current selection remains on instance; history is not a second source.

### 5.5. Replacement/upgrade

- same passport version: change product reference after compatibility validation; keep resource IDs/links;
- new passport version without structural change: explicit mapping by stable resource key/ordinal, keep mapped IDs, revalidate;
- structural change: preview `mapped/added/removed/changed`; occupied removed resource blocks commit until explicit user action;
- auto-map by display name/order and auto-update to latest are forbidden.

## 6. Constructor relations

### 6.1. `functional_relation`

`id`, `project_id`, registered `relation_kind`, `source_resource_id`, `target_resource_id`, typed parameters, command/timestamps/version.

Constraints: same project, active endpoints, allowed directions/types/media/ranges, no forbidden self-loop, canonical duplicate prevention. Relation never dispatches by product/article/designation.

### 6.2. `resource_reservation`

Resource, reservation kind, slot/address/quantity and owner relation/assignment. Partial unique indexes enforce exclusive outputs and address/port/slot uniqueness where expressible. Sum capacity is validated in the same Unit of Work.

Техническая `resource_reservation` фиксирует фактическую занятость relation/assignment и не используется для пользовательского `РЕЗЕРВ`. Явный пользовательский резерв хранится отдельным project fact `user_reserve` с typed target (`INSTANCE_RESOURCE` либо `PROJECT_INSTANCE`), actor/time и необязательной заметкой. Активный резерв исключает target из обычных кандидатов, но не создаёт relation/assignment и не считается физической занятостью.

### 6.3. Validation trace

Validation result is derived DTO. Persisted audit trace, where required, contains rule/version, input entity IDs, normalized operands, outcome and command correlation. It does not replace relation or facts.

### 6.4. Производная полная функциональная трасса

Read model полной трассы объединяет три типизированных, но не смешиваемых вида рёбер:

1. persisted `functional_relation` между конкретными ресурсами;
2. derived internal apparatus edge из machine-readable passport/resource/grouping contract;
3. persisted `cable_line_assignment` как конечный переход к полевой линии.

Internal edge имеет behavior `PASS_THROUGH`, `DISTRIBUTION`, `TRANSFORM`, `BUFFERED_TRANSFORM` или `CONTROLLED`, rule ID и состояние обязательных зависимостей. Он не записывается в отдельную таблицу и полностью восстанавливается из установленного каталога, `ProjectInstance`, `InstanceResource` и relations. Физическая bus topology в этот graph не преобразуется.

## 7. DWG and field model

### 7.1. `dwg_document_binding`

Owner project. App UUID, normalized last-known path, adapter document signature/fingerprint, user-confirmed binding time/status. Path/handle is not primary identity; mismatch requires explicit rebind.

### 7.2. `dwg_scan`

Immutable metadata: binding, scan ID, adapter/protocol/contract version, timestamps, document facts, content hash and status. Partial/failed scan is not applied.

### 7.3. `dwg_observation`

Unique `(scan_id, handle)`. Effective block name, layer/space, placement facts required by the DWG contract (`X/Y`), raw attributes, optional definition metadata required for validation (for example attribute-definition tags or dynamic-block flag) and diagnostics. Raw values are preserved without guesses; normalized observations are typed child facts.

Графические примитивы определения блока и визуальная геометрия УГО не являются project facts и не сохраняются как часть предметной модели.

### 7.4. `field_device` and optional product configuration

`field_device` owner project. Technical ID, approved block kind, room/location and normalized fields, optional DWG binding. Unique active `(dwg_document_id, entity_handle)`. Handle is not PK.

A field device may additionally have `field_device_product_selection` (or equivalent typed extension): exact passport/product version, normalized evidence-backed configuration options, supply scope and lifecycle. This does not create a `ProjectInstance` automatically. For configurable `SENSOR_MSW`, selected WB-MSW v.4 options are stored here and participate in specification grouping.

### 7.5. `cable_line`, `cable_point` and `cable_segment`

`cable_line`: project technical ID, system kind, approved designation/base `CABLE_ID`, line-owned `CABLE_TYPE`/`BOARD`, lifecycle and source identity. Natural identity follows product documents; internal FK uses UUID. A line may be linear or branching.

`cable_point` is a physical topology/install point of one `cable_line`, not a synonym for one DWG insertion. It has stable technical ID, point kind, location/height and optional logical identity (`XYY.ZZ`, `BOX_ID=BOX.NNN` or internal endpoint identity). One point may contain several physical `field_device` rows, for example several `SOCKET` mechanisms with the same allowed `XYY.ZZ`. Membership is represented explicitly (`cable_point_field_device` or equivalent join); one physical insertion is never merged or deleted because it shares the same installation point.

`cable_segment` is an internal physical edge of one base line between two adjacent topology points/endpoints. It has stable technical ID, `cable_line_id`, source/target endpoint references, segment route facts and calculation revision. It has no user-facing `CABLE_ID`. The same physical edge is counted once even when it is traversed by more than one logical path in a branching line.

Segment-owned route facts are `MOUNT_WAY`, `GOFRA_TYPE`, `GOFRA_COLOR` and visible `GOFRA_ID`/conduit binding according to [22_CABLE_LENGTHS_AND_CONDUITS.md](../product/22_CABLE_LENGTHS_AND_CONDUITS.md). `CABLE_TYPE` and `BOARD` remain line-owned.

### 7.6. `field_port` and `cable_line_assignment`

`field_port` belongs to one `field_device` and represents an explicitly supported external functional port such as `WB_MRM2_MINI.K1/K2/IN_1/IN_2` or `WB_M1W2.W1/W2`. Identity is `(field_device_id, port_tag)`. Port kind/direction comes from the canonical block/device contract; free-form ports are forbidden. `WB_MRM2_MINI` has one feeder on `COM1`; `COM2`, `K1` and `K2` are independent bidirectional relay-common/relay ports, not a second feeder set.

`cable_line_assignment` links a cable line endpoint to a compatible physical source/target. The endpoint reference is typed and may address an `instance_resource` or an approved `field_port`; it is not `functional_relation`. A base line may therefore start in a board resource or at a field-device output without introducing a global DWG `SOURCE` attribute. Uniqueness/capacity rules belong to the referenced resource/port kind.

### 7.7. Sync facts

- `dwg_baseline`: accepted normalized Project-field/DWG-field value, scan and revision;
- `dwg_sync_operation`: immutable direction/selection/result/correlation journal;
- `dwg_sync_change`: field path, baseline/project/dwg values, class, decision, apply/read-back;
- `dwg_write_receipt`: target preconditions, written/read-back value and no-save confirmation.

Baseline changes only after successful apply/read-back. Missing DWG data does not erase Project-only facts.

### 7.8. Physical control keys and input assignments

`field_control_key` принадлежит `field_device` и имеет уникальную идентичность `(field_device_id, key_tag)`, где `key_tag` — один из фактически присутствующих `KEY_1`…`KEY_4`. Хранятся нормализованная функциональная цель (`cable_line` либо `dali_group`), DWG origin/baseline и lifecycle.

`control_key_input_assignment` связывает ровно один `field_control_key` с одним совместимым эксклюзивным входным `instance_resource`. Один физический key занимает один input; один input не назначается двум keys. Разные keys могут иметь одну функциональную цель. Эта связь не сворачивается в агрегированное управление и не заменяется `functional_relation`.

## 8. Cables, lengths, conduits and AV

### 8.1. `cable_length_fact`

One per base line: calculated length with source/revision, additional length, optional full manual override and rounding policy. Automatic calculated length is the sum of unique `cable_segment` lengths. Effective/final cable length follows [22_CABLE_LENGTHS_AND_CONDUITS.md](../product/22_CABLE_LENGTHS_AND_CONDUITS.md): `manual_full` when present; otherwise calculated segment sum + additional length + applicable source/project cable reserve; otherwise `INCOMPLETE`. Cable reserve/additional/manual full length do not change geometric conduit length.

### 8.2. `conduit` / `conduit_segment_assignment`

`conduit` owner project: immutable technical ID, unique visible `GOFRA_ID`, numeric project number, Russian type with catalog/nominal size, color, independent nullable stored length, optional exact product selection, supply scope and creation provenance. The visible suffix is derived from type by the centralized mapping in [22_CABLE_LENGTHS_AND_CONDUITS.md](../product/22_CABLE_LENGTHS_AND_CONDUITS.md); it is not an independent editable value.

`conduit_segment_assignment` connects one `cable_segment` to zero or one conduit; one conduit may contain multiple segments from one or several lines. A branching line may therefore use different conduits on different segments. Pre-existing shared `GOFRA_ID` denotes one physical conduit and is not duplicated per line/segment.

For a dedicated automatically created conduit, geometric length is derived from the assigned physical segment(s) without cable reserve, additional cable length or full manual cable override. A shared/pre-existing conduit may retain an explicit independent nullable length according to [22_CABLE_LENGTHS_AND_CONDUITS.md](../product/22_CABLE_LENGTHS_AND_CONDUITS.md). Bulk edits are all-or-none. One physical conduit remains one specification instance regardless of the number of contained segments/lines.

`MOUNT_WAY`, `GOFRA_TYPE`, `GOFRA_COLOR` and `GOFRA_ID` are segment-owned facts and are preserved in owner-aware DWG baseline/reconciliation. A line-wide duplicate of these facts is forbidden as a second source of truth.

### 8.3. Cable/HDMI catalog

Кабельный и HDMI-каталог является отдельным versioned catalog и **не входит** в equipment release, объявленный в [resources/catalogs/catalog_manifest.json](../../resources/catalogs/catalog_manifest.json).

Минимальные сущности:

- `cable_catalog_release` — immutable published release;
- `cable_product_definition` — stable product identity/version, category (`SPEAKER_CABLE|HDMI|OTHER_APPROVED_CABLE`), manufacturer/model/article, technical properties and lifecycle;
- для HDMI хранится factory length как свойство конкретного product version;
- пользовательское добавление создаёт validated draft/version и после publish становится новым release; существующие project selections продолжают ссылаться на точную версию.

Canonical equipment `product_definition` не используется для AV-кабеля. Runtime source после установки — SQLite; packaged catalog files могут быть только import payload/seed для release, а не параллельным runtime source.

### 8.4. AV

AV identity is scoped by approved `BOARD/CABLE_ID`. `av_cable_profile` and `cable_line_product_selection` are typed extensions. `cable_line_product_selection` ссылается на exact `cable_product_definition` version. HDMI product replacement preserves cable line ID/endpoints/DWG binding. AV does not enter power checks or DIN placement.

## 9. Loads, LED, PSU and ICL

### 9.1. `load_requirement`

Exactly one typed owner: cable line or project instance. Power/current/voltage facts, source (`DWG|PROJECT|PASSPORT|CALCULATED`), knowledge status and override history. Accepted DWG value becomes an editable Project fact; effective load is derived.

### 9.2. `led_line_profile` / `led_segment`

Profile one-to-one with cable line: `MONO|CCT|RGB|RGBW`, voltage, channels, power/metre, exact tape product version and supply scope. `LED_TYPE` хранит Project value, DWG baseline/origin и sync state по [25_DWG_SYNCHRONIZATION.md](../product/25_DWG_SYNCHRONIZATION.md); `MIX` не является допустимым Project/DWG значением. Segment has stable ID, requested length, order/zone and explicit user split. Long segment is never auto-split.

Cut rounding, FFD bins, remainders and purchase coils are deterministic output from segments plus exact cut/coil facts and calculator version. Missing facts yield `INCOMPLETE`.

### 9.3. PSU and ICL

Both are ordinary project instances/resources. AC/DC path is functional relations. Load assessment derives from connected consumers. ICL is manually created. Its five canonical statuses and trace are derived; no PSU/ICL auto-selection is stored or performed.

## 10. Buses and topology

### 10.1. `bus`

Owner project. Bus kind `RS485|DALI|KNX`, designation, root/controller resource, topology policy and lifecycle.

### 10.2. `bus_endpoint`

Bus + resource, role, optional address, order and branch. Membership/address uniqueness is scoped by bus kind.

### 10.3. `bus_branch` / `bus_branch_point`

DALI/KNX use ordered branches and points. RS-485 forbids branch rows and requires one ordered endpoint sequence.

### 10.4. `dali_group` / `dali_group_member`

`dali_group` принадлежит Project и одной физической шине DALI, а через `bus.root_resource_id` — конкретному порту источника. `group_key` в формате `D.YYY` уникален в Project. `dali_group_member` связывает группу только с endpoint-resource той же физической DALI-шины. Геометрия блока `DALI_GROUP` не является источником membership.

### 10.5. Graph/layout

Graph structure is `TopologyReadModel` from project facts. Only `graph_layout_preference(view_key,node_id,x,y,collapsed)` may persist. Cache key includes `project_revision` and `calculator_version`; deleting cache never loses meaning.

## 11. Panel layout

`panel_section` owner board; `panel_rail` owner section with order/usable width; `panel_placement` connects rail and instance with start/width/orientation/status. Overlap and capacity are validated transactionally. External/non-panel/customer equipment without panel execution is not placed. Unknown width remains incomplete.

`assembly_material_fact` stores only accepted material inputs/manual corrections with reason; derived quantities come from functional distribution. Internal material does not masquerade as a product instance.

## 12. Specification and cost

Authoritative inputs: exact product selections, cable/conduit/AV selections and lengths, LED purchase inputs, supply scope, commercial facts and accepted material overrides.

`commercial_fact`: product/material reference, exact price/currency/effective date/source. Unknown differs from zero. `specification_override` contains only allowed scope/note/inclusion/quantity correction with reason.

Specification and cost rows are derived and grouped by exact product version/supply scope/unit. Deleting a source removes its derived row. No independent editable specification table is allowed.

## 13. Issues and operations

`validation_issue_state` stores only acknowledgement/waiver/reason/actor/time and applicable rule/input revision. The issue result is recomputed.

`operation_journal` stores command ID/type, project revision before/after, correlation, status, timestamps and non-sensitive summary. It is not event sourcing.

`background_job` stores operational status/input revision/result reference. Result applies through a command only when preconditions remain current.

`bulk_operation_receipt` хранит command ID, тип согласованного массового действия, выбранные owners, preview fingerprint, Project revision before/after и итог. Сами новые instances/relations/assignments остаются единственными предметными facts; receipt не является их копией.

## 14. Transaction boundaries

| Command | Mutated aggregate(s) | Mandatory pre-commit checks |
|---|---|---|
| create project | project + initial settings | unique code, active catalog |
| instantiate passport | instance + all resources | full materialization, unique designation |
| replace product | instance + history | exact passport/product compatibility |
| upgrade passport | instance/resources/relations | explicit mapping; no orphan occupied resource |
| create relation | relation + reservations | endpoints, type/range, capacity, exclusivity, cycles |
| assign cable | assignment + reservation | line/output compatibility and uniqueness |
| assign physical key | key assignment + reservation | key/input compatibility, exclusivity, user reserve |
| controlled bulk action | весь previewed набор instances/relations/assignments + receipt | однородный selection, актуальная revision, совместимость, capacity, reserve, уникальная нумерация; all-or-none |
| apply DWG→Project | selected facts + baseline + journal | same scan/baseline/project revisions; all-or-none |
| confirm Project→DWG | baseline + receipt | successful bridge read-back |
| bulk conduit edit | conduits/assignments + synchronized line facts | all selected rows valid; visible IDs and shared assignments remain consistent |
| place on DIN | placement(s) | product size, compatibility, no overlap |
| save supply/cost fact | typed fact | units/currency/source; unknown ≠ zero |

## 15. Integrity requirements

- FK everywhere; cross-project references forbidden;
- `CHECK` for enums, ranges and non-negative engineering values;
- `UNIQUE` for natural scopes, materialized resources and reservations;
- exactly-one-owner facts use typed owner tables or enforced owner constraints;
- cascade only inside inseparable aggregate; referenced destructive action blocks;
- schema revision and catalog schema version are separate;
- `foreign_key_check` and `integrity_check` are mandatory self-checks;
- no startup/read repair, hidden cleanup or feature-owned storage.

## 16. Migration contract

Физическую schema определяет последовательность Alembic migrations. Каждый последующий schema change для действующих IN-MVP функций требует Alembic revision, impact statement, backup, clean-upgrade test, upgrade from previous revision, integrity checks and reopen. Feature-local JSON/SQLite fallback is forbidden.

Current physical storage is defined by [src/nl_project_2/persistence/migrations/versions](../../src/nl_project_2/persistence/migrations/versions) and schema tests. Schema changes follow the repository Issue → branch → PR → review → merge lifecycle.
