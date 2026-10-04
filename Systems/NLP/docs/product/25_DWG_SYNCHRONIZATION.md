# NL Project 2.0 — контракт синхронизации с DWG

## 1. Канонический engine

Sync сохраняет P0_003 three-way owner-aware engine:

```text
immutable observation batch
→ exact validation
→ normalized owner facts/topology plans
→ baseline / Project / DWG classification
→ deterministic sync proposal
→ atomic Project apply или exact DWG write/read-back
```

Внутренние baseline, change class, owner kind и proposal необходимы для корректности engine, но не являются обязательными пользовательскими понятиями обычного рабочего сценария.

Owners: insertion planning facts; CableLine (`BOARD`, `CABLE_TYPE`); CableSegment (`CABLE_SOURCE`, ordinary route); bus (`BUS_CABLE_TYPE`, Project-owned root/type); BusSegment (`BUS_SOURCE` where applicable, bus route); physical ports; control keys. Derived/retired values не являются editable planning owners.

Downstream `CABLE_SOURCE=<BUS_POINT_ID>/<PORT>` и reciprocal output-port value — две editable projections одного canonical edge. Previous accepted Project baseline resolves one-side changes and consistent two-side changes. Incompatible two-side change emits `DUAL_PROJECTION_REQUIRES_ATTENTION`, blocks only dependent operation and never chooses silently. Materialization updates one CableSegment by target endpoint and synchronizes the opposite projection.

Ordinary topology uses `CABLE_SOURCE=<empty>|BOX.NNN|XYY.ZZ|9YY.ZZZ/PORT`; root derives from canonical source endpoint. DALI uses `.000` root and explicit branching; RS-485 uses numeric `.ZZZ` without `BUS_SOURCE`. Physical BusSegment route and ordinary CableSegment route remain independent. Track links create no external cable/conduit.

Project-to-DWG may write only a Project-originated/resolved value that is both in the closed allow-list and present in the exact ATTDEF set of the observed Repair08 canonical block. It never emits retired tags/names or Project-derived type/post/link/root/bus facts. Binding, revision, Handle, name/layer and exact read-back are mandatory.

Exact names/ATTDEF and topology semantics are owned by [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](../autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md) and [CURRENT_TOPOLOGY_ARCHITECTURE.md](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). Machine contract version is `3.0.0` with 71 definitions.

## 2. Обычный пользовательский workflow «Обновить»

Команда `Обновить` запускает обычную синхронизацию текущего Project с подтверждённым target DWG. Нажатие команды является явным запуском sync, но не разрешает системе угадывать конфликт, ambiguous identity, отсутствующую dependency или owner-forbidden write.

После scan/classification:

- изменилось только в DWG → допустимое изменение автоматически применяется `DWG → Project`;
- изменилось только в Project → допустимое shared field автоматически передаётся `Project → DWG`;
- обе стороны изменились к одному значению → дополнительное решение пользователя не требуется;
- обе стороны изменились по-разному → настоящий конфликт, пользователь выбирает `Оставить Project` или `Оставить DWG`;
- invalid/ambiguous/missing dependency/owner-forbidden/structurally blocked state → проблема, требующая отдельного действия;
- room canonicalization, когда требуется явная привязка существующего Room, остаётся отдельным пользовательским действием.

Обычный успешный sync не показывает общий per-field preview. Внутренний deterministic proposal остаётся частью engine и test boundary, но пользователь видит только итог или элементы, которые нельзя решить безопасно автоматически.

Если изменений нет, результат — `Актуально`.

После автоматического/явного применения UI показывает компактный итог: сколько фактов принято из DWG, сколько передано в DWG и остались ли элементы, требующие решения.

Project-to-DWG изменяет открытый документ только через разрешённый write/read-back contract. **DWG автоматически не сохраняется.** Если запись изменила открытый DWG, UI явно показывает состояние `DWG не сохранён` / `DWG изменён · не сохранён` до внешнего сохранения пользователем.

## 3. Проблемы и конфликты

Окно решения открывается только когда после автоматической части остаются:

- true two-side conflicts;
- invalid/ambiguous facts;
- missing insertion/source/bus-root dependency;
- structural/atomic group blockers;
- room canonicalization;
- runtime/apply/write error.

Для true conflict показываются пользовательская сущность/поле и два рабочих значения — Project и DWG — с явным выбором стороны.

Для проблемы показываются причина, затронутая сущность и прямое действие, если оно определено. Пользовательский UI не требует понимать `ChangeClass`, `owner_kind`, UUID или internal field path.

Проблема синхронизации не исчезает только потому, что окно решения закрыто. Если она относится к рабочему факту, основной workspace должен показывать локальный `!` в соответствующей колонке и вести к той же причине/действию.

## 4. Selective apply и identity коробок

Identity физических коробок определяется [topology contract, §6](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). При base-only `CABLE_ID` normalization должна различать box points по `BOX_ID`, включая owners входящих сегментов и source references. Существующие suffixed point identities и их accepted baselines сохраняются. Однозначная ранее сохранённая base-only box point переиспользуется при apply; неоднозначную объединённую точку нельзя автоматически разделять с угадыванием принадлежности старых edges.

Selective/automatic apply должен разрешать source dependency из полного validated snapshot и существующей topology Project, сохраняя domain boundaries. Уже принятый source endpoint можно переиспользовать без изменения source point. Невыбранные/заблокированные новые insertions, CableLine и их topology не должны импортироваться автоматически ради dependency. Если нужного endpoint/physical port ещё нет в Project, dependent operation остаётся проблемой с идентификатором источника и требуемым действием. Уже принятые insertions не входят в набор новых insertions для atomic line import; неразрешённые новые строки продолжают блокировать частичный импорт этой группы.

Самостоятельная линия из щита имеет пустой `CABLE_SOURCE`; ordinary box/point не создаёт новый независимый кабель другой CableLine. Межлинейный выход через реальный physical port использует line-owned `FIELD_PORT` endpoint принимающей CableLine со ссылкой на project-owned порт источника. Это typed endpoint representation сохраняет FK без требования одинакового `CABLE_ID` у source device и downstream point.

Каждый Project apply остаётся atomic UnitOfWork: commit только после успешной materialization и всех записей, исключение — полный rollback. Presentation показывает явную ошибку и не выполняет ложную ветку успеха/refresh. Неожиданное исключение записывается в журнал с техническими подробностями, а основной UI-текст содержит понятное сообщение без Python traceback.

## 5. Канонизация существующего помещения

Если у принятой активной вставки отсутствует `field_device.room_id`, а `BUILDING` / `ROOM` однозначно разрешаются в существующее помещение Project по правилам [11_OBJECT_AND_ROOM_MODEL.md](11_OBJECT_AND_ROOM_MODEL.md), sync должен сохранить это как отдельное действие `Привязать помещение`, даже при равенстве текстового evidence и baseline.

Привязка выполняется только после явного выбора пользователя. Операция одной room canonicalization не принимает другие заблокированные факты DWG и не материализует unrelated topology.

Канонизация сохраняет исходный текст DWG как evidence и записывает устойчивый `room_id`. Она не создаёт здания/помещения, не угадывает ambiguous/unresolved room и не подменяет three-way classification изменений имён `ROOM` / `BUILDING`. Существующая room relation остаётся источником Project-имён, включая Project rename, DWG rename и `BOTH_CHANGED_CONFLICT`.

После успешной привязки зависимые derived lengths могут быть пересчитаны из уже принятых Project facts. Pending/unselected DWG geometry или route facts не должны импортироваться только ради такого пересчёта.
