# Топология шин данных NL Project 2.0

## 1. Назначение и границы

Документ описывает принятую Repair 08 модель физических шин. Exact DWG-поля определяет [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](../autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md), ownership и правила топологии — [CURRENT_TOPOLOGY_ARCHITECTURE.md](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md). Machine projection — [resources/autocad/block_contract.json](../../resources/autocad/block_contract.json); физическое хранение — migration `000000000011_topology_autocad_contract.py`. Диаграмма является представлением этих данных.

## 2. Идентификаторы и источники

`BUS_ID=9YY` — идентичность физической шины, `BUS_TYPE` — Project-owned тип шины. `9YY.000` — корневой физический endpoint конкретного аппаратного порта в Project, не протокольный DALI short address. Привязка root к WB-DALI3 (`DA1/DA2/DA3`) и WBE2-I-KNX (`KNX_PORT`) остаётся Project-owned.

Для **пассивных DALI коробок и прямых секций TRACK_DALI** `BUS_ID` становится **ATTDEF**: это принадлежность к шине, а не собственное имя точки. Собственная identity — `BOX_ID=BOX.xxx` или `TRACK_ID=TRACK.xxx`; `BUS_POINT_ID` им не присваивается. Адресуемые field devices DALI сохраняют `BUS_POINT_ID=9YY.ZZZ`. Для этих устройств `BUS_ID` выводится из префикса `BUS_POINT_ID`, а не хранится отдельным ATTDEF. Это сознательная замена старой физической модели пассивных точек, а не новое толкование DALI short address.

Существующие физические `BusSegment`/назначения труб сохраняют уникальные physical endpoint identities; переход старого DALI `BUS_POINT_ID` у пассивной точки к `BUS_ID` + `BOX_ID`/`TRACK_ID` требует проверяемого mapping и не переписывает реальные DWG/SQLite без отдельного разрешения.

## 3. Физический участок

Каждое соседство образует отдельный `BusSegment`. Ordinary `CableSegment` не используется для хранения участка шины. Отдельный пользовательский номер участку не присваивается. Полная длина — сумма уникальных физических участков; геометрия и conduit accounting определяются [22_CABLE_LENGTHS_AND_CONDUITS.md](22_CABLE_LENGTHS_AND_CONDUITS.md).

`BUS_CABLE_TYPE` принадлежит всей шине и должен быть согласован на её точках. `BUS_MOUNT_WAY` и `BUS_GOFRA_*` принадлежат входящему `BusSegment`. Один физический участок и его труба учитываются ровно один раз. Derived link `TRACK` не создаёт внешнюю длину кабеля или трубу. Полилинии DWG для задания топологии не требуются.

## 4. RS-485: линейный порядок

RS-485 не допускает ответвлений. После root `9YY.000` точки соединяются по числовому порядку трёхзначных суффиксов `.ZZZ`: например `902.000 → 902.001 → 902.003`. Пропуск ordinal не меняет правило порядка. Scan order и порядок вставок DWG не определяют соседство. ATTDEF `BUS_SOURCE` у RS-485 отсутствует.

## 5. DALI: явные связи

DALI поддерживает физическое ветвление. `BUS_SOURCE` у полевой DALI-точки содержит единственного immediate upstream родителя **в той же шине**: `9YY.000`, `BOX.xxx`, `TRACK.xxx` или допустимый адресуемый `9YY.ZZZ`. Для пассивной `EL_BOX`/`TRACK_DALI` принадлежность задаётся `BUS_ID=9YY`, а не `BUS_POINT_ID`. Для адресуемых field points остаются `BUS_POINT_ID` и `BUS_SOURCE`. Пустой `BUS_SOURCE` **не** означает root.

Например: `905.000 → BOX.023 → TRACK.001 → LIGHT_TRACK_DALI_48V (905.001)`. При этом `BOX.023` и `TRACK.001` **не** получают DALI short address. Для `LIGHT_TRACK_DALI_48V` связь `BUS_SOURCE=TRACK.001` — derived `TRACK` без монтажных метров; внешний DALI bus cable заканчивается на `TRACK.001`.

Отсутствующий upstream, чужая шина, цикл, двойной parent и недостижимая от root DALI-точка — ошибки. Ординалы field points не задают физического порядка ветвей и не подменяют `BUS_SOURCE`. DALI group membership и протокольные short addresses отдельны.

**Совместимость:** старые пассивные `BUS_POINT_ID` в DWG/Project нужно преобразовывать только по однозначной таблице соответствия `старый physical point → BOX_ID / TRACK_ID`; обратные ссылки `BUS_SOURCE` тоже должны быть обновлены. Если mapping неизвестен, ошибка явно показывается, а не исправляется угадыванием.

## 6. KNX: совместимые Project-правила

Для KNX сохраняется принятая явно заданная Project-модель ветвей с теми же правилами первой и последующих ветвей и трёхзначными адресами `9YY.ZZZ`. Она не получает автоматический порядок по ordinal. Эти правила не добавляют KNX ATTDEF в DWG-контракт: наличие DWG-поля определяется только exact machine/human reference. Привязка `KNX_PORT`, отдельная проверка питания, запрет повторных участков и обязательная достижимость точек сохраняются.

**KNX:** прежняя branch-модель Project сохраняется; новый DALI ATTDEF `BUS_ID` сам по себе не утверждает KNX-поля в AutoCAD.

## 7. Проверки

NL Project выявляет неверный формат адреса, несовпадающую шину, отсутствие источника/root, отсутствующий parent/endpoint, отсутствие пути от root, запрещённое RS-485 ветвление, DALI cycle/cross-bus/двойного parent, недопустимое начало дополнительной Project-ветви, повтор точки вне места ответвления и повтор участка. Неполнота не подменяется придуманными связями.

## 8. Представление

Диаграмма строится из canonical bus points/edges/branches и `BusSegment`; она не является вторым источником топологии. Mermaid допустим как средство отображения, но его текст не хранится как нормативная модель.

## 9. Связанные документы

- [20_AUTOCAD_BLOCK_CONTRACT.md](20_AUTOCAD_BLOCK_CONTRACT.md)
- [22_CABLE_LENGTHS_AND_CONDUITS.md](22_CABLE_LENGTHS_AND_CONDUITS.md)
- [25_DWG_SYNCHRONIZATION.md](25_DWG_SYNCHRONIZATION.md)
- [CURRENT_TOPOLOGY_ARCHITECTURE.md](../autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md)
- [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](../autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md)
