# Issue #216 — физическая труба в спецификации (Q03/Q06/Q08)

**Scope:** узкий repair источников количества в `specification/service.py`. Source of truth до review/merge — `main/Systems/NLP`. Принятые Q01–Q11 и вариант UI «Трассы» B не меняются.

## Дефект / воспроизведение

До исправления спецификация формировала независимые источники:

1. `_conduit_sources`: `CONDUIT` со значением `conduit.length_m_decimal` (в том числе ручное `USER_CONFIRMED`).
2. `_bus_conduit_sources`: по **каждому** `bus_segment.gofra_type` добавляла `BUS_SEGMENT_CONDUIT` с количеством `bus_segment.length_m_decimal` — фактически длиной кабельного сегмента, не уникальной физической трубы.

Для одной общей `Conduit` 10 м и одного назначенного BUS-сегмента 5 м оба источника группировались по одному `item_key`, давая **15 м вместо 10 м**. Два BUS-сегмента в одной трубе приводили к тому же двойному/тройному учёту. Фильтр `path_json.origin=AUTO_BUS_SEGMENT` дополнительно исключал ряд физических труб из первичного источника.

## Новый принцип (только спецификация)

- Любая активная физическая `Conduit` — **один** источник `SpecificationSource(source_kind="CONDUIT", source_id=conduit.id)`, независимо от числа ordinary/BUS сегментов и legacy `origin`. Параллельные разные `Conduit.id` считаются раздельно.
- Длина источника — подтверждённое `conduit.length_m_decimal`; если `NULL`, количество остаётся **неизвестным**, создаётся `CONDUIT_LENGTH_REQUIRED`. Никакой BUS-геометрией и никакой догадкой по `GOFRA_ID` его не заполнять.
- `USER_CONFIRMED` и пользовательская `specification_override.quantity_correction_decimal` на конкретной Conduit применяются **как раньше**, без переписывания Project-длины. Нельзя превращать эту логику в скрытый пересчёт и нельзя снимать ручную корректировку при наличии BUS.
- Для BUS-сегмента с действующей FK-связью `bus_segment_conduit_assignment → ACTIVE Conduit` отдельный источник трубы **не выпускается**: он уже представлен `Conduit.id`.
- Для BUS-сегмента с данными `GOFRA_*`, но без физического назначения, либо с назначением на неактивную/отсутствующую Conduit, выводится **отдельный** `BUS_SEGMENT_CONDUIT` с `quantity=None` и блокирующая `CONDUIT_ASSIGNMENT_REQUIRED`. Это не 5 м «догадочной» трубы и не часть подтверждённого итога. `BUS TRACK` не создаёт источник трубы.
- Для ordinary CableSegment с assignment на неактивную/отсутствующую Conduit выводится аналогичный `CABLE_SEGMENT_CONDUIT` с неизвестной длиной и диагностикой. Обычный unassigned CableSegment без заявленной физической трубы остаётся обычным состоянием, не выдумывается материал.
- Все запросы Project-scoped; используются **существующие** FK assignment tables без нового RouteSection или второй модели физической трубы.

## Не входит в этот PR

- Новый расчёт финальной длины Conduit по Q08, выводы Q04, высоты Q05, транзит через physical-only EL_BOX (Q02) и техническая допустимость совместной ordinary/BUS прокладки (Q03/Q06).
- Исправление legacy DWG атрибутов или изменение sync/assignment сервисов. Missing `GOFRA_ID` не служит доказательством отсутствия физической трубы; при отсутствии FK недостаточность данных показана.
- Live SQLite, DWG, AutoCAD и принятие полевой топологии на конкретном объекте. Никаких migrations/schema/catalog changes.

## Приёмочные сценарии

`tests/specification/test_physical_conduit_spec_216.py` использует синтетическую SQLite через штатную `DatabaseManager` (schema head, FK enforced) и настоящий `SpecificationService.build`.

Проверяет: воспроизведение 15→10; две BUS на одну трубу; две параллельные Conduit; `AUTO_BUS_SEGMENT` с подтверждённой ручной длиной; legacy BUS без FK (количество неизвестно); физическая труба без установленной длины; BUS/ordinary назначения на RETIRED Conduit (видимая диагностика).
