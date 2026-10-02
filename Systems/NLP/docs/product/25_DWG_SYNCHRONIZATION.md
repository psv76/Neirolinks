# NL Project 2.0 — контракт синхронизации с DWG

## Active Repair08 synchronization contract (normative)

Sync сохраняет P0_003 three-way owner-aware engine: immutable observation batch -> exact validation -> normalized owner facts/topology plans -> baseline/Project/DWG classification -> deterministic preview -> explicit atomic apply или exact write plan/read-back. DWG автоматически не сохраняется.

Owners: insertion planning facts; CableLine (`BOARD`, `CABLE_TYPE`); CableSegment (`CABLE_SOURCE`, ordinary route); bus (`BUS_CABLE_TYPE`, Project-owned root/type); BusSegment (`BUS_SOURCE` where applicable, bus route); physical ports; control keys. Derived/retired values не являются editable planning owners.

Downstream `CABLE_SOURCE=<BUS_POINT_ID>/<PORT>` и reciprocal output-port value — две editable projections одного canonical edge. Previous accepted Project baseline resolves one-side changes and consistent two-side changes. Incompatible two-side change emits `DUAL_PROJECTION_REQUIRES_ATTENTION`, blocks only dependent selected operation and never chooses silently. Materialization updates one CableSegment by target endpoint and synchronizes the opposite projection.

Ordinary topology uses `CABLE_SOURCE=<empty>|BOX.NNN|XYY.ZZ|9YY.ZZZ/PORT`; root derives from canonical source endpoint. DALI uses `.000` root and explicit branching; RS-485 uses numeric `.ZZZ` without `BUS_SOURCE`. Physical BusSegment route and ordinary CableSegment route remain independent. Track links create no external cable/conduit.

Project-to-DWG may write only a Project-originated/resolved value that is both in the closed allow-list and present in the exact ATTDEF set of the observed Repair08 canonical block. It never emits retired tags/names or Project-derived type/post/link/root/bus facts. Binding, revision, Handle, name/layer and exact read-back are mandatory.

Exact names/ATTDEF and topology semantics are owned by [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](../autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md) and [CURRENT_TOPOLOGY_ARCHITECTURE.md](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). Machine contract version is `3.0.0` with 71 definitions.

## Selective apply и identity коробок

Identity физических коробок определяется [topology contract, §6](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). При base-only `CABLE_ID` normalization должна различать box points по `BOX_ID`, включая owners входящих сегментов и source references. Существующие suffixed point identities и их accepted baselines сохраняются. Однозначная ранее сохранённая base-only box point переиспользуется при явном apply; неоднозначную объединённую точку нельзя автоматически разделять с угадыванием принадлежности старых edges.

Selective apply должен разрешать source dependency из полного validated snapshot и существующей topology Project, сохраняя выбор пользователя. Уже принятый source endpoint можно переиспользовать без изменения невыбранной source point. Невыбранные новые insertions, CableLine и их topology не должны импортироваться автоматически ради dependency. Если нужного endpoint/physical port ещё нет в Project, apply завершается явной доменной ошибкой с идентификатором источника и предложением сначала принять источник или выбрать его вместе с downstream point. Уже принятые insertions не входят в набор новых insertions для atomic line import; неразрешённые новые строки продолжают блокировать частичный импорт этой группы.

Самостоятельная линия из щита имеет пустой `CABLE_SOURCE`; ordinary box/point не создаёт новый независимый кабель другой CableLine. Межлинейный выход через реальный physical port использует line-owned `FIELD_PORT` endpoint принимающей CableLine со ссылкой на project-owned порт источника. Это существующее typed endpoint representation сохраняет FK без требования одинакового `CABLE_ID` у source device и downstream point.

Apply остаётся одной UnitOfWork: commit только после успешной materialization и всех записей, исключение — полный rollback. Presentation должна показывать явную ошибку apply и не выполнять ветку успеха/refresh. Неожиданное исключение записывается в журнал с техническими подробностями, а основной UI-текст содержит понятное сообщение без Python traceback.

## Канонизация существующего помещения

Если у принятой активной вставки отсутствует `field_device.room_id`, а неизменённые `BUILDING` / `ROOM` однозначно разрешаются в существующее помещение Project по правилам [11_OBJECT_AND_ROOM_MODEL.md](11_OBJECT_AND_ROOM_MODEL.md), preview должен явно предложить привязку помещения даже при равенстве текстового evidence и baseline. Привязка выполняется только после выбора пользователем; операция одной привязки не принимает другие невыбранные факты DWG и не материализует topology.

Канонизация сохраняет исходный текст DWG как evidence и записывает устойчивый `room_id`. Она не создаёт здания/помещения, не угадывает ambiguous/unresolved room и не подменяет three-way classification изменений имён `ROOM` / `BUILDING`. Существующая room relation остаётся источником Project-имён, включая Project rename, DWG rename и BOTH_CHANGED_CONFLICT. Привязка и sync evidence сохраняются в одной транзакции; устаревший preview требует повторного сканирования.
