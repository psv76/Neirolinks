# NLP #237 — D12: физические участки CABLE_TRANSIT и расчёт без guessed topology

## Scope

Source of truth: `docs/product/22_CABLE_LENGTHS_AND_CONDUITS.md` §§3.1/4/5/8–12,
`docs/autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md` §6, Issues #235/#237.

D11 `TransitAudit` определяет доказуемый **single-electrical-edge** путь.
D12 проектирует для него отдельные `PhysicalTransitSpan`:

`ordinary source → BOX.NNN → [BOX.NNN] → ordinary target`.

Эти spans — **не** `cable_segment` и **не** electrical `CABLE_SOURCE` edges.
Два соседних участка одной непрерывной жилы не создают расключения,
получателя, электрического контакта, нового кабеля или запас в коробке.

## Read-only backend

- `ScanProposal.physical_transit_routes` содержит детерминированные пары физических
  границ из D11 без чтения/изменения рабочей SQLite.
- Для branched/multiple physical paths, повторяющихся/неверных BOX и непроверенных
  источников — только `REVIEW` и **ноль** generated spans.
- `measure_physical_transit` принимает *отдельно и явно* утверждённый способ
  прокладки/Conduit для **каждого** физического участка, verified Project/BOX
  geometry evidence обоих концов и утверждённую политику резервов/процентов/
  округления. Отсутствие хотя бы одного входа выдаёт `REVIEW`, не подставляет
  default и не сохраняет числовое значение.
- Предварительная геометрия использует высоты AutoCAD от чистого пола,
  B с отрицательным знаком для FLOOR, C=R×1000 для CEILING и
  чистую геометрию TIMBER без legacy +0,5 м.
- Проценты применяются один раз к сумме *чистой геометрии* spans.
  Termination/reserve суммы задаются отдельно и не начисляются за транзит BOX.
  Округление линии выполняется один раз после суммирования.
- Conduit допускается по валидным `GOFRA_TYPE/GOFRA_ID` только с явно
  подтверждённым per-span назначением. Один `GOFRA_ID` с разными физическими
  `{A,B}` получает `TRANSIT_CONDUIT_BOUNDARY_CONFLICT` и не суммируется как
  одна труба. Общая труба с доказанно одинаковыми границами показывается
  один раз по designation; никакого автоматического numbering или assignment.
- Любая `MEASURED` здесь означает **чисто расчётный preview**, а не persisted
  Project fact, пользовательскую приёмку или разрешение применять связь.

## Зависимости и незакрытые ворота

D12 **не** модифицирует `cable_segment`, `conduit`,
`conduit_segment_assignment`, `cable_point`, `field_device` или DWG.
Отсутствующая в CAD per-side `MOUNT_WAY/GOFRA_*` не восстанавливается из
общего атрибута транзита. `main`, действующая SQLite, DWG и AutoCAD не
меняются; версия/схема/каталог не выпускаются.

Для следующего **persistence/apply** gate нужны:
1. Канонический owner-specific тип физического transit waypoint и span,
   не подменяющий electrical endpoints существующих CableSegment.
2. Безопасный schema successor/миграция + verified backup + catalog successor
   (если требуется) + startup smoke **на реальной базе после отдельного
   разрешения**, restore test и legacy collision/rollback.
3. UI для явного назначения per-side route/conduit и approved mapping SHA,
   selective apply/partial scan без удаления исторических маршрутов.
4. Объединение с уже написанным Q04/Q05/Q08 #218/#231 и Q03/Q06 общими
   трубами ordinary/BUS; не встраивать параллельный устаревший калькулятор.
5. Полный locked regression + Windows/AutoCAD/реальная DWG приёмка.

Ветку и PR сохранять Draft до перечисленных ворот. Issue #235/#237 OPEN.
