# NLP 3.0 · #235 · архитектурная сверка и implementation gates

> **Статус:** инженерный audit target-контракта в draft [PR #236](https://github.com/psv76/Neirolinks/pull/236). Это **не** доказательство работы 3.1.0 на текущем `main`, не green CI и не разрешение мигрировать рабочую БД/DWG.
>
> **Вход разработчику:** [Issue #237](https://github.com/psv76/Neirolinks/issues/237); принятые решения [#216](https://github.com/psv76/Neirolinks/issues/216), [#234](https://github.com/psv76/Neirolinks/issues/234), [#235](https://github.com/psv76/Neirolinks/issues/235). Source of truth: `main` и после принятия — канонические документы `Systems/NLP/docs/autocad/`, `docs/product/`, `resources/autocad/`. Не возобновлять предметное обсуждение решений, приведённых здесь.

## Принятое и запрещённое

| Сущность | Обязательная семантика |
| --- | --- |
| Пассивная `EL_BOX_OUT_100x100` в DALI | `BOX_ID=BOX.NNN` — physical identity; `BUS_ID=9YY` — принадлежность вместо `BUS_POINT_ID`; `BUS_SOURCE` — реальный upstream; один дополнительный `CABLE_TRANSIT` |
| Пассивный `TRACK_DALI` | `TRACK_ID=TRACK.NNN` — physical identity; `BUS_ID=9YY` вместо `BUS_POINT_ID`; `BUS_SOURCE` указывает на root/box/track/addressable upstream |
| `TRACK_230V` и `TRACK_48V` | `TRACK_ID=TRACK.NNN`, `TRACK_MOUNT_WAY` — отдельно от кабельного `MOUNT_WAY`, динамическая физическая `LENGTH` в мм |
| Адресуемые DALI lights | `BUS_POINT_ID=9YY.ZZZ` (проектная identity), actual short address — отдельно; на физическом треке внутренние `CABLE_SOURCE/BUS_SOURCE=TRACK.NNN` = **TRACK** link без монтажного Cable/BusSegment |
| Транзит | `CABLE_TRANSIT=301;302` / `301-1;302` в одной ATTDEF коробки; не электрическая коммутация и 0 box termination; **только однозначная линейная последовательность** физических коробок по данному пути. При неоднозначной ветви — `Требует внимания`, не создавать guessed segment/meters/Conduit и не стирать подтверждённую topology |
| Питание | Внешняя силовая линия **230 В → `3YY`**, **48 В → `4YY`** независимо от DALI. Отдельный внешний PSU заканчивает 230 В и начинает другую физическую 48 В связь; контракт новых PSU-блоков не утверждён и не подменяется псевдо-узлом |

## Доказанные технические несоответствия текущего `main` (выполнение #237)

| Приоритет | Реальная точка в коде / документах | Текущий gap | Целевая работа / тест |
| --- | --- | --- | --- |
| P0 | `cad_contract/validator.py` — `_function_group()` | Требует ровно один group по layer; у `TRACK_DALI` допустимы обе 3YY/4YY на DALI layer, текущий код их не различает по фактической силовой линии | Только для указанного physical TRACK profile безопасно разрешать группу по **непустому корректному `CABLE_ID`**, с кросс-проверкой слоя/напряжения, без ослабления валидатора других типов; 301/401 проходят, другие группы отвергаются |
| P0 | `cad_contract/validator.py` — обработка `BUS_POINT_ID`, `BUS_SOURCE` | DALI bus point создаётся лишь при непустом `BUS_POINT_ID`; источнику DALI требуется формат `9YY.ZZZ` | Различать пассивные `BUS_ID/BOX_ID/TRACK_ID` и адресуемые `BUS_POINT_ID`, проверять cross-bus, cycles, двойных parent, root, duplicate physical ID и source `BOX.NNN/TRACK.NNN`; не менять RS-485/KNX |
| P0 | `cad_sync/reconciliation.py`: `if payload.bus_point_id and payload.bus_id and payload.bus_type` | Пассивный DALI узел без `BUS_POINT_ID` пропадает из `BusPointPlan` | Ввести typed physical identity/ownership и построение `BusSegment` по `BUS_SOURCE`, не создавать протокольных адресов и не терять endpoint IDs |
| P0 | `cad_sync/service.py`: закрытый список полей на старте | Нет `TRACK_ID`, `TRACK_MOUNT_WAY`, `CABLE_TRANSIT`, для пассивного `BUS_ID` нет безопасной DWG ownership/roundtrip | Расширить **owner-aware** чтение/запись и миграцию; повторный sync no-op и сохранение ручных assignments/overrides; не закрывать/сохранять AutoCAD автоматически |
| P0 | `cad_sync/workflow.py`: missing bus roots из `BUS_POINT_ID` | `BUS_ID` из пассивного DWG игнорируется, possible auto-import с потерей root-dependency | Обрабатывать DALI `BUS_ID` из пассивных nodes; import dependency only when resolved root same bus; отсутствие root блокирует нужные компоненты без удаления чужих |
| P0 | `cad_contract/models.py` | Read payload уже содержит `bus_id` и `box_id`, но нет физического `track_id` / transit topology plans | Перенос typed identities в normalization, route ownership, persisted segment IDs; не трактовать physical `BUS_ID` как unique point |
| P1 | `resources/autocad/block_contract.json` | 3.0.0 имеет `BUS_ID` в global forbidden и `TRACK_DALI` только на 4YY. В candidate 3.1.0 исправлены forbidden и dual 3YY/4YY groups, exact ATTDEF | При implementation тестировать loader + validator против нового JSON, без слепого повышения версии и с ретросовместимостью |
| P1 | `resources/autocad/block_contract.schema.json` | Историческая schema отставала от содержимого (лишний required `conditional_attributes`, missing реальные поля families). Исправлена **только на target ветке** | Schema 2020-12 validation, exact 71 definitions, all required profile tags, no profile/global forbidden collisions; schema обязательно поставлять вместе с JSON |
| P1 | `tests/cad_contract/test_catalog.py`; `test_repair08_contract.py`; fixture `repair08_exact_attdef_sha256.json` | Жёстко закрепляют 3.0.0, old exact ATTDEF и Project-only `BUS_ID` | Обновить **на этапе кода** тесты для 3.1.0. Сохранить отдельные regression fixtures старого DWG/3.0.0; не переписать втихую исторические данные с новым смыслом |
| P1 | `docs/product/20_AUTOCAD_BLOCK_CONTRACT.md`, `22_CABLE_LENGTHS_AND_CONDUITS.md` | Ошибочное переопределение высот, `+0,5 м` в брусе, проценты от `L_base`, underbox-only endpoints | В draft #236 согласованы с Q05/Q04/Q08: высоты от чистого пола (уточнение пользователя 23.10.2026), `R=G×(1+P_nonlinearity+P_bypass)`, терминальные запасы отдельно, TIMBER +0,5 отменён. Кодовую реализацию брать из зависимого draft PR #231, не дублировать |
| P1 | `cables/recalculation.py`, `buses/recalculation.py`, `specification/service.py` | Legacy allowances, root/box/endpoint heuristics и shared-Conduit accounting | Интегрировать Q01–Q11 и draft PR #218/#231/#230; transit не начисляет splice; внешние TRACK cables до insertion point; 2 BUS/ordinary в общей трубе без дублирования |
| P1 | AutoCAD COM / динамические физические TRACK blocks | `ATTDEF LENGTH` сам по себе не связывает значение с Stretch; опасен массовый `ATTSYNC` | Авторизованный Windows AutoCAD acceptance на **копии**: definition/INSERT, Extend/Rotate/Stretch, ATTRIB readback, сохранённые динамические свойства, backup/rollback; отдельное [TechDocs #2](https://github.com/psv76/NEIROLINKS-TechDocs/issues/2) |

## Acceptance (конкретные тесты, без будущих переопределений)

**Технический gate высот H1:** пользователь 23.10.2026 подтвердил действующие
определения документа 11/AC-002/AC-033: MOUNT_HEIGHT от чистого пола, отрицательное
основание B в настройках помещений NLP, потолок C=R×1000. Нового предметного
ввода или конвертации высот не требуется. Ошибочную формулу B+R×1000 из #231
не переносить. Нужны 6 м и AC-033 8,4 м, независимость CEILING от B,
missing H/R и multi-owner regression, ordinary/BUS parity. B обязателен для
FLOOR, но не для CEILING. [Исправленный аудит H1](ISSUE_235_GATE1_RESIDUAL_AUDIT.md).
Остальная работа #218/#231 сохраняется; runtime-код в #236 не меняется.

1. `TRACK_DALI`, `CABLE_ID=301` и физический 230 V input на слое TRACK_DALI → `LIGHTING_230V` / 3YY; `CABLE_ID=401` и 48 V input → `LIGHTING_LED` / 4YY; `CABLE_ID=501` → ошибка. Для 230 V и 48 V разный конец у отдельного PSU, когда такой профиль будет утверждён.
2. `BOX.023` с `BUS_ID=905`, `BUS_SOURCE=905.000`; `TRACK.001` с `BUS_ID=905`, `BUS_SOURCE=BOX.023`; `LIGHT_TRACK_DALI_48V` c `BUS_POINT_ID=905.001`, `BUS_SOURCE=TRACK.001`. Никакой `BUS_POINT_ID` на пассивных BOX/TRACK и никакого protocol short address на них; `CABLE_SOURCE=TRACK.001` у light не создаёт монтажную длину.
3. `301-1` у `BOX.010` и `301-2` у `BOX.020` в **однозначном** физическом пути разбивают кабель на реальные геометрические участки, не создавая электрического расключения / запаса у коробки. `301` в единственной транзитной BOX также принимается.
4. Несколько ветвей ordinary `CableLine` и неопределённая branch-membership транзитной BOX → `Требует внимания`; спорные `CableSegment`/длины/Conduit не строить автоматически. Достоверная electrical topology и подтверждённые назначения остаются неизменными; однозначные участки считаются независимо.
5. Три разных root из щита × 3,00 м = 9,00 м щитового запаса; нет специальной `+0,5 м` для TIMBER; шина не получает один `0,5 м` на сегмент. Два `G=1,10` при (5%+10%) округляются **один раз** в `3 м`.
6. Один физический общий `Conduit` с равными `{A,B}` для ordinary и BUS учитывается в спецификации **один раз**; частичные/недоказанные совпадения не создают общую трубу.
7. Legacy 3.0.0 DWG с пассивным `BUS_POINT_ID=905.003` и downstream `BUS_SOURCE=905.003` мигрирует в `BUS_ID=905`, физический `BOX_ID` и `BUS_SOURCE=BOX.xxx` только при проверенном mapping. Неоднозначность → без записи/переноса с потерей данных.

## Границы

- Draft branch #236 описывает **целевой** контракт, а **не runtime support**. Его JSON сейчас не должен оказаться в production `main` без обновлённого validator/parser/tests #237.
- Qt production вариант «Трассы» B, спецификация, math и physical bounds реализуются с учётом существующих зависимых PR #218–#231, а не всё в одном PR.
- Изменение schema head/catalog release → проверка фактической рабочей БД по принятому gate только после backup и отдельного разрешения. Существующий контроллер/AutoCAD не трогать.
- Если в процессе кода/живой проверки окажется необходим новый предметный выбор, зафиксировать его в #235; не подставлять фиктивные значения и не маркировать тесты PASSED без реального прогона.
