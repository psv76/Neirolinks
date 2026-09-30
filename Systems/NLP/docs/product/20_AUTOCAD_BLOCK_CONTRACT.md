# Блоки планировки AutoCAD NL Project 2.0

## Active Repair08 contract (normative)

Текущий machine contract: `3.1.0`, ровно 71 canonical definition. Machine `route_rules` проецирует принятые способы прокладки из [22_CABLE_LENGTHS_AND_CONDUITS.md](22_CABLE_LENGTHS_AND_CONDUITS.md), включая `В брусе` для ordinary и bus route fields. Exact canonical names, ATTDEF sets и `LOAD_TYPE` allow-lists определяет [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](../autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md); topology/ownership определяет соседний [CURRENT_TOPOLOGY_ARCHITECTURE.md](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). Machine projection — [resources/autocad/block_contract.json](../../resources/autocad/block_contract.json); расхождение с exact reference является ошибкой parity.

Target planning ATTDEF не содержат `DEVICE_TYPE`, `POSTS`, global `SOURCE`, исходящие box fields, `CABLE_LINK`, `BUS_LINK`, `LINE_ROLE`, `ROOT_ENDPOINT`, `BUS_ID`, `BUS_TYPE`. Эти значения Project-owned/derived. `DEVICE_NAME` остаётся пользовательским planning fact.

`CABLE_ID` задаёт самостоятельную CableLine/point; `CABLE_SOURCE` на downstream point задаёт immediate upstream `<empty> | BOX.NNN | XYY.ZZ | 9YY.ZZZ/PORT`. `EL_BOX` имеет independent `BOX_ID`; box может быть physical-only, cable-only, bus-only или dual-network. Switch/button order задаёт только numeric `.ZZ`, без `CABLE_SOURCE`. Global source, box suffix topology и outgoing box projections являются только retired legacy input и никогда не target-valid/writeable.

Physical ports `COM1/COM2/K1/K2/IN_1/IN_2/W1/W2` — editable projections canonical edges. Reciprocal port/`CABLE_SOURCE` uses previous Project baseline: one changed side wins deterministically; consistent two-side change passes; incompatible change = `DUAL_PROJECTION_REQUIRES_ATTENTION`, no silent winner. `WB_MRM2_MINI` has one feeder set and independent ports; `WB_M1W2` has `W1/W2`.

Bus identity: `BUS_POINT_ID=9YY.ZZZ`, reserved root `9YY.000`; `BUS_ID/BUS_TYPE` не ATTDEF. DALI uses explicit `BUS_SOURCE` branching without cross-bus/cycles. RS-485 has no `BUS_SOURCE`, order is `.ZZZ`. `BUS_CABLE_TYPE` is line-owned; `BUS_MOUNT_WAY/BUS_GOFRA_*` belong to incoming `BusSegment`. Derived `CABLE_LINK/BUS_LINK=TRACK` creates no fake external cable/conduit.

Exact canonical successors include `LIGHT_*_230V`, `WB_M1W2`, `WB_MAI2` and four ordinary/DALI cable-outlet variants. Retired generic light/sensor names are input-only explicit aliases and never emitted. Ordinary lights/outlets have no bus fields; DALI 230 V variants have independent ordinary+bus networks; track lights contain no route facts for internal track links. Socket/phase/PoE boundaries follow exact reference.

Project-to-DWG intersects its closed allow-list with the exact ATTDEF set, performs exact read-back and never saves DWG automatically.

## Единицы координат и длины

Для DWG, используемого NL Project 2.0, одна единица координат `X` и `Y` должна соответствовать `1 мм`. NL Project должен интерпретировать считанные значения `X` и `Y` как миллиметры.

Системная переменная AutoCAD `INSUNITS` не должна использоваться NL Project как коэффициент пересчёта координат. Значение `INSUNITS=0` само по себе не запрещает обработку DWG. Если фактическая геометрия DWG выполнена в другом масштабе, DWG должен быть приведён к масштабу `1 drawing unit = 1 мм` до использования в NL Project.

Вертикальное положение устройства задаётся атрибутом `MOUNT_HEIGHT` в миллиметрах от чистого пола. Для расчётов NL Project использует `MOUNT_HEIGHT` как координату по высоте.

`LENGTH` линейного изделия в DWG задаётся в миллиметрах; значение не пересчитывается по эвристике масштаба.
