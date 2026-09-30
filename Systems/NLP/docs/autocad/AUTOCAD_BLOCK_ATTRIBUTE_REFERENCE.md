# NL Project 2.0 — справочник атрибутов блоков AutoCAD
**Дата:** 2026-08-30  
**Редакция:** после полного аудита и принятых сокращений  
**Статус:** принятый exact reference для Repair 08, machine contract `3.0.0` / 71 definitions; статус пользовательской приёмки указан в `docs/STATUS.md`.
## 1. Назначение
Документ является рабочим справочником для редактирования canonical block definitions AutoCAD.
Правило использования:

> найти canonical block name → открыть его раздел → привести состав ATTDEF блока ровно к указанному `Exact ATTDEF set`.
В карточке каждого блока также указано, используется ли `LOAD_TYPE`, и если используется — приведён полный список зарегистрированных допустимых значений. В конце документа есть обратный индекс `LOAD_TYPE → canonical blocks`.
Этот reference описывает target contract, реализованный в Repair 08. Совместимость конкретного DWG требует отдельной проверки его definitions и данных; перенос не выполняет live-CAD приёмку.
## 2. Общие правила
### 2.1. Derived / Project-only, не ATTDEF planning block
```text
DWG_HANDLE
DEVICE_TYPE
POSTS
FUNCTION_GROUP
LINE_ROLE
ROOT_ENDPOINT
CABLE_LINK
BUS_LINK
BUS_ID
BUS_TYPE
DALI_SHORT_ADDRESS
hardware module/port codes (A34/Port1 и т.п.)
```
`DEVICE_TYPE` выводится из canonical block name. `POSTS` у `FRAME_n` также выводится из имени блока.
### 2.2. `DEVICE_NAME`
`DEVICE_NAME` сохраняется везде, где предусмотрен карточкой блока. Это свободное человекочитаемое описание конкретного изделия/исполнения и оно не считается derived только из canonical block name или каталога.
### 2.3. Legacy tags, отсутствующие в target definitions
```text
ID
KEY
SOURCE
OUT_1
OUT_2
OUT_3
OUT_4
OUT_5
IN (legacy EL_BOX input)
COMMENT
DEVICE_TYPE
POSTS
CABLE_LINK
BUS_LINK
```
`IN_1` / `IN_2` у `WB_MRM2_MINI` — physical port fields и не относятся к legacy `IN`.
### 2.4. `CABLE_SOURCE`
Допустимые формы включают:

```text
<empty>
BOX.010
331.02
902.003/K1
```

`902.003/K1` означает concrete physical endpoint: `<BUS_POINT_ID>/<PORT>`. У `SW_*` и `BTN_*` ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии задаётся `.ZZ`.
### 2.5. Port fields
Physical port ATTDEF (`COM1`, `COM2`, `K1`, `K2`, `IN_1`, `IN_2`, `W1`, `W2`) показывают непосредственно подключённую topology reference и остаются редактируемыми вручную. Если port field и downstream `CABLE_SOURCE` описывают один edge, parser выполняет reconciliation с предыдущим Project state; настоящий несовместимый конфликт попадает в `Требует внимания`.
Для `WB_MRM2_MINI` текущий target поддерживает один ordinary CableLine/CableSegment set для типового питания силовых контактов. `COM1` и `COM2` остаются отдельными физическими портами. Два независимых полных feed-set пока не вводятся.
### 2.6. Bus cable fields
Для блока с реальным входящим bus cable используются `BUS_CABLE_TYPE`, `BUS_MOUNT_WAY`, `BUS_GOFRA_TYPE`, `BUS_GOFRA_COLOR`, `BUS_GOFRA_ID`. `BUS_CABLE_TYPE` — line-owned свойство `BUS_ID`; остальные — route facts входящего `BusSegment`. Для track-connected DALI light route fields отдельного bus cable отсутствуют.
### 2.7. `LOAD_TYPE`
`LOAD_TYPE` сохраняется только у светильников/LED, розеток, кабельных выводов и щитов. Он удалён у `SW_*`, `BTN_*`, `SENSOR_*`, `WB_M1W2`, `WB_MAI2`, `FAN`, `AIR_VALVE`, `CONTROL_PANEL_*`, `TRACK_*`, `WB_MRM2_MINI`.
### 2.8. `PHASE` и `CALC_POWER`
`PHASE` удалён из обычных однофазных розеточных blocks и из `SOCKET_OUT_380V`: значение 1/3 выводится из canonical block name. `PHASE` сохраняется у `CABLE_OUTLET*`, `FAN`, `AIR_VALVE`.

`CALC_POWER` удалён из `SOCKET_ETHERNET`. Для `CONTROL_PANEL_*` PoE-мощность является Project/catalog-owned свойством выбранной модели панели и ATTDEF `CALC_POWER` не вводится.
### 2.9. Canonical rename / new blocks
```text
SENSOR_M1W2 -> WB_M1W2
SENSOR_MAI2 -> WB_MAI2

SOCKET_OUT_380V
CABLE_OUTLET_DALI
CABLE_OUTLET_FRAME_DALI
```
## 3. Canonical block catalog
В target reference включено **71** canonical block definitions.
- **Рамки:** `FRAME_1`, `FRAME_2`, `FRAME_3`, `FRAME_4`, `FRAME_5`, `FRAME_1_IP44`, `FRAME_2_IP44`, `FRAME_3_IP44`
- **Светильники:** `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`
- **Светодиодные линии:** `LIGHT_LED`, `LIGHT_LED_IP67`
- **Физические треки:** `TRACK_230V`, `TRACK_48V`, `TRACK_DALI`
- **Выключатели:** `SW_IN_1`, `SW_IN_2`, `SW_IN_3`, `SW_IN_4`, `SW_OUT_1`, `SW_OUT_2`, `SW_IN_1_IP44`, `SW_IN_2_IP44`, `SW_OUT_1_IP44`, `SW_OUT_2_IP44`
- **Кнопки:** `BTN_IN_1`, `BTN_IN_2`, `BTN_IN_3`, `BTN_IN_4`
- **Розетки:** `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`, `SOCKET_OUT_380V`, `SOCKET_ETHERNET`
- **Кабельные выводы:** `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`
- **Датчики:** `SENSOR_1WIRE`, `SENSOR_MSW`, `SENSOR_WATER`, `SENSOR_MOTION`
- **Оборудование:** `FAN`, `AIR_VALVE`
- **Панели управления:** `CONTROL_PANEL_4`, `CONTROL_PANEL_9`, `CONTROL_PANEL_10`, `CONTROL_PANEL_11`
- **Щиты:** `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`
- **Коробки:** `EL_BOX_OUT_100x100`
- **Полевые модули:** `WB_M1W2`, `WB_MAI2`, `WB_MRM2_MINI`
- **Логические блоки:** `DALI_GROUP`, `ROOM_NAME`

## 4. Exact ATTDEF sets и допустимые `LOAD_TYPE`
Если тег указан в `Exact ATTDEF set`, он должен существовать в canonical definition, даже если для конкретной вставки значение может быть пустым. Если тег не указан — в target definition этого блока его быть не должно.

### Рамки

#### `FRAME_1`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_2`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_3`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_4`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_5`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_1_IP44`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_2_IP44`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `FRAME_3_IP44`
Назначение/примечание: Монтажное изделие; cable/bus topology не создаёт.
Количество постов выводится из canonical block name; ATTDEF `POSTS` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Светильники

#### `LIGHT_OUT_230V`
Назначение/примечание: Накладной 230 В; только ordinary cable topology.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_IN_230V`
Назначение/примечание: Встраиваемый 230 В; только ordinary cable topology.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_OUT_DALI_230V`
Назначение/примечание: Накладной 230 В DALI; power CableSegment + DALI BusSegment.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_IN_DALI_230V`
Назначение/примечание: Встраиваемый 230 В DALI; power CableSegment + DALI BusSegment.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_TRACK_230V`
Назначение/примечание: Трековый 230 В; link от физического трека выводится как TRACK; route fields отдельного кабеля отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_SOURCE
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_TRACK_48V`
Назначение/примечание: Трековый 48 В; link от физического трека выводится как TRACK; route fields отдельного кабеля отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_SOURCE
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_TRACK_DALI_48V`
Назначение/примечание: Трековый 48 В DALI; power и DALI links от трека выводятся как TRACK; route fields отдельных монтажных кабелей отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_SOURCE
BUS_POINT_ID
BUS_SOURCE
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_IN_IP44`
Назначение/примечание: Существующий специализированный non-DALI light block; имя сохраняется до отдельного решения о переименовании.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_OUT_IP54`
Назначение/примечание: Существующий специализированный non-DALI light block; имя сохраняется до отдельного решения о переименовании.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_LUSTRA`
Назначение/примечание: Существующий специализированный non-DALI light block; имя сохраняется до отдельного решения о переименовании.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_BRA`
Назначение/примечание: Существующий специализированный non-DALI light block; имя сохраняется до отдельного решения о переименовании.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_BRA_IP54`
Назначение/примечание: Существующий специализированный non-DALI light block; имя сохраняется до отдельного решения о переименовании.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

### Светодиодные линии

#### `LIGHT_LED`
Назначение/примечание: Линейное световое изделие.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
LENGTH
LED_TYPE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

#### `LIGHT_LED_IP67`
Назначение/примечание: Линейное световое изделие.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
LENGTH
LED_TYPE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `LIGHT_MAIN` — Основное освещение.
- `LIGHT_DECOR` — Декоративное освещение.
- `LIGHT_TECH` — Техническое освещение.
- `LIGHT_NIGHT` — Ночное освещение.
- `LIGHT_STREET` — Уличное освещение.

### Физические треки

#### `TRACK_230V`
Назначение/примечание: Физический трек 230 В; внешний вход — ordinary cable.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
LENGTH
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `TRACK_48V`
Назначение/примечание: Физический трек 48 В; внешний вход — ordinary cable.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
LENGTH
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `TRACK_DALI`
Назначение/примечание: Физический DALI-трек; отдельные external power CableSegment и DALI BusSegment.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_NAME
LENGTH
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Выключатели

#### `SW_IN_1`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_IN_2`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_IN_3`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
KEY_3
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_IN_4`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
KEY_3
KEY_4
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_OUT_1`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_OUT_2`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_IN_1_IP44`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_IN_2_IP44`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_OUT_1_IP44`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SW_OUT_2_IP44`
Назначение/примечание: Grouped switch policy сохраняется; physical order общей UTP определяется `.ZZ`.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Кнопки

#### `BTN_IN_1`
Назначение/примечание: Количество KEY_x соответствует числу клавиш.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `BTN_IN_2`
Назначение/примечание: Количество KEY_x соответствует числу клавиш.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `BTN_IN_3`
Назначение/примечание: Количество KEY_x соответствует числу клавиш.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
KEY_3
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `BTN_IN_4`
Назначение/примечание: Количество KEY_x соответствует числу клавиш.
ATTDEF `CABLE_SOURCE` отсутствует: физический порядок общей линии определяется `.ZZ` в `CABLE_ID`.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
KEY_1
KEY_2
KEY_3
KEY_4
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Розетки

#### `SOCKET_IN`
Назначение/примечание: DEVICE_NAME сохраняется: один canonical block может соответствовать разным конкретным изделиям/цветам/вариантам.
Однофазность выводится из canonical block name; ATTDEF `PHASE` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_LIVING_LOW` — Бытовые розетки жилых помещений с обычной нагрузкой.
- `SOCKET_LIVING_MEDIUM` — Бытовые розетки с повышенной нагрузкой.
- `SOCKET_CONTROL_LOW` — Управляемая розетка с небольшой нагрузкой.
- `SOCKET_CONTROL_MEDIUM` — Управляемая розетка с повышенной нагрузкой.
- `SOCKET_KITCHEN_MEDIUM` — Розетки кухонного фартука.
- `SOCKET_KITCHEN_HIGH` — Выделенная линия мощного кухонного оборудования.

#### `SOCKET_IN_IP44`
Назначение/примечание: DEVICE_NAME сохраняется: один canonical block может соответствовать разным конкретным изделиям/цветам/вариантам.
Однофазность выводится из canonical block name; ATTDEF `PHASE` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_LIVING_LOW` — Бытовые розетки жилых помещений с обычной нагрузкой.
- `SOCKET_LIVING_MEDIUM` — Бытовые розетки с повышенной нагрузкой.
- `SOCKET_CONTROL_LOW` — Управляемая розетка с небольшой нагрузкой.
- `SOCKET_CONTROL_MEDIUM` — Управляемая розетка с повышенной нагрузкой.
- `SOCKET_KITCHEN_MEDIUM` — Розетки кухонного фартука.
- `SOCKET_KITCHEN_HIGH` — Выделенная линия мощного кухонного оборудования.

#### `SOCKET_OUT`
Назначение/примечание: DEVICE_NAME сохраняется: один canonical block может соответствовать разным конкретным изделиям/цветам/вариантам.
Однофазность выводится из canonical block name; ATTDEF `PHASE` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_LIVING_LOW` — Бытовые розетки жилых помещений с обычной нагрузкой.
- `SOCKET_LIVING_MEDIUM` — Бытовые розетки с повышенной нагрузкой.
- `SOCKET_CONTROL_LOW` — Управляемая розетка с небольшой нагрузкой.
- `SOCKET_CONTROL_MEDIUM` — Управляемая розетка с повышенной нагрузкой.
- `SOCKET_KITCHEN_MEDIUM` — Розетки кухонного фартука.
- `SOCKET_KITCHEN_HIGH` — Выделенная линия мощного кухонного оборудования.

#### `SOCKET_OUT_IP54`
Назначение/примечание: DEVICE_NAME сохраняется: один canonical block может соответствовать разным конкретным изделиям/цветам/вариантам.
Однофазность выводится из canonical block name; ATTDEF `PHASE` отсутствует.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_LIVING_LOW` — Бытовые розетки жилых помещений с обычной нагрузкой.
- `SOCKET_LIVING_MEDIUM` — Бытовые розетки с повышенной нагрузкой.
- `SOCKET_CONTROL_LOW` — Управляемая розетка с небольшой нагрузкой.
- `SOCKET_CONTROL_MEDIUM` — Управляемая розетка с повышенной нагрузкой.
- `SOCKET_KITCHEN_MEDIUM` — Розетки кухонного фартука.
- `SOCKET_KITCHEN_HIGH` — Выделенная линия мощного кухонного оборудования.

#### `SOCKET_OUT_380V`
Назначение/примечание: Трёхфазная розетка открытой установки; PHASE=3 выводится из canonical block name.
Трёхфазность (`PHASE=3`) выводится из canonical block name. Суффикс `OUT` обозначает открытую установку.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_KITCHEN_3PH` — Трёхфазная розетка кухонного оборудования / электроплиты.
- `SOCKET_EQUIPMENT` — Трёхфазная розетка другого оборудования.

#### `SOCKET_ETHERNET`
Назначение/примечание: DEVICE_NAME сохраняется: один canonical block может соответствовать разным конкретным изделиям/цветам/вариантам.
ATTDEF `CALC_POWER` и `PHASE` отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `SOCKET_ETHERNET` — Информационная розетка Ethernet.

### Кабельные выводы

#### `CABLE_OUTLET`
Назначение/примечание: Обычный физический кабельный вывод; DALI BUS_* в этом block отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `CABLE_BOILER` — Подключение котла.
- `CABLE_HVAC` — Подключение вентиляционного или климатического оборудования.
- `CABLE_HEAT` — Подключение отопительного оборудования.
- `CABLE_TECH` — Подключение другого стационарного оборудования.
- `CABLE_LIGHT_DECOR` — Вывод декоративного освещения.
- `CABLE_LIGHT_TECH` — Вывод технического освещения.
- `CABLE_LIGHT_NIGHT` — Вывод ночного освещения.
- `CABLE_LIGHT_STREET` — Вывод уличного освещения.

#### `CABLE_OUTLET_FRAME`
Назначение/примечание: Обычный физический кабельный вывод в рамке; DALI BUS_* в этом block отсутствуют.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `CABLE_BOILER` — Подключение котла.
- `CABLE_HVAC` — Подключение вентиляционного или климатического оборудования.
- `CABLE_HEAT` — Подключение отопительного оборудования.
- `CABLE_TECH` — Подключение другого стационарного оборудования.
- `CABLE_LIGHT_DECOR` — Вывод декоративного освещения.
- `CABLE_LIGHT_TECH` — Вывод технического освещения.
- `CABLE_LIGHT_NIGHT` — Вывод ночного освещения.
- `CABLE_LIGHT_STREET` — Вывод уличного освещения.

#### `CABLE_OUTLET_DALI`
Назначение/примечание: Физический кабельный вывод с одновременной ordinary cable topology и DALI bus topology.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `CABLE_BOILER` — Подключение котла.
- `CABLE_HVAC` — Подключение вентиляционного или климатического оборудования.
- `CABLE_HEAT` — Подключение отопительного оборудования.
- `CABLE_TECH` — Подключение другого стационарного оборудования.
- `CABLE_LIGHT_DECOR` — Вывод декоративного освещения.
- `CABLE_LIGHT_TECH` — Вывод технического освещения.
- `CABLE_LIGHT_NIGHT` — Вывод ночного освещения.
- `CABLE_LIGHT_STREET` — Вывод уличного освещения.

#### `CABLE_OUTLET_FRAME_DALI`
Назначение/примечание: Кабельный вывод в рамке с одновременной ordinary cable topology и DALI bus topology.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `CABLE_BOILER` — Подключение котла.
- `CABLE_HVAC` — Подключение вентиляционного или климатического оборудования.
- `CABLE_HEAT` — Подключение отопительного оборудования.
- `CABLE_TECH` — Подключение другого стационарного оборудования.
- `CABLE_LIGHT_DECOR` — Вывод декоративного освещения.
- `CABLE_LIGHT_TECH` — Вывод технического освещения.
- `CABLE_LIGHT_NIGHT` — Вывод ночного освещения.
- `CABLE_LIGHT_STREET` — Вывод уличного освещения.

### Датчики

#### `SENSOR_1WIRE`
Назначение/примечание: Обычная sensor CableLine.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SENSOR_MSW`
Назначение/примечание: RS-485 device; BUS_SOURCE отсутствует, порядок задаёт BUS_POINT_ID.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BUS_POINT_ID
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SENSOR_WATER`
Назначение/примечание: Обычная sensor CableLine.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `SENSOR_MOTION`
Назначение/примечание: Обычная sensor CableLine.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Оборудование

#### `FAN`

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `AIR_VALVE`

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
CALC_POWER
PHASE
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Панели управления

#### `CONTROL_PANEL_4`
PoE-мощность не хранится в DWG через `CALC_POWER`; она определяется выбранной моделью панели в Project/catalog.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `CONTROL_PANEL_9`
PoE-мощность не хранится в DWG через `CALC_POWER`; она определяется выбранной моделью панели в Project/catalog.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `CONTROL_PANEL_10`
PoE-мощность не хранится в DWG через `CALC_POWER`; она определяется выбранной моделью панели в Project/catalog.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `CONTROL_PANEL_11`
PoE-мощность не хранится в DWG через `CALC_POWER`; она определяется выбранной моделью панели в Project/catalog.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Щиты

#### `BOARD_IN`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

#### `BOARD_OUT`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

#### `BOARD_OUT_IP44`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

#### `BOARD_OUT_IP54`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

#### `BOARD_OUT_IP67`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

#### `BOARD_PANEL`
Назначение/примечание: BOARD_ID — собственная identity щита.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOARD_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
LOAD_TYPE
LOAD_NAME
CALC_POWER
COMMENT_1
COMMENT_2
```

**Допустимые `LOAD_TYPE`:**

- `BOARD_METER` — Щит учёта.
- `BOARD_IN` — Вводно-распределительный щит.
- `BOARD_IN_AVR` — Вводной щит с АВР.
- `BOARD_DISTRIBUTION` — Распределительный щит или щит освещения.
- `BOARD_AVR` — Щит АВР.
- `BOARD_SCS` — Слаботочный щит или СКС.

### Коробки

#### `EL_BOX_OUT_100x100`
Назначение/примечание: Может быть physical-only, cable point, DALI point или обе topology memberships одновременно.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BOX_ID
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_SOURCE
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Полевые модули

#### `WB_M1W2`
Назначение/примечание: RS-485 модуль WB-M1W2; W1/W2 показывают непосредственно подключённые topology references.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BUS_POINT_ID
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_NAME
W1
W2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `WB_MAI2`
Назначение/примечание: RS-485 модуль WB-MAI2; BUS_SOURCE отсутствует, порядок задаёт BUS_POINT_ID.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
BUS_POINT_ID
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_NAME
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `WB_MRM2_MINI`
Назначение/примечание: RS-485 модуль реле. Один ordinary CableLine/CableSegment set описывает текущую типовую питающую линию силовых контактов; `COM1`/`COM2`/`K1`/`K2`/`IN_1`/`IN_2` остаются отдельными physical port ATTDEF.
Два независимых полных feed-set для `COM1` и `COM2` в текущем target contract не вводятся.

**Exact ATTDEF set:**

```text
DEVICE_NAME
BUILDING
ROOM
MOUNT_HEIGHT
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
BUS_POINT_ID
BUS_CABLE_TYPE
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
LOAD_NAME
COM1
COM2
K1
K2
IN_1
IN_2
COMMENT_1
COMMENT_2
```

**`LOAD_TYPE`:** не используется в этом canonical block.

### Логические блоки

#### `DALI_GROUP`
Назначение/примечание: Логическая группа DALI; не физическое устройство.

**Exact ATTDEF set:**

```text
DALI_GROUP_ID
```

**`LOAD_TYPE`:** не используется в этом canonical block.

#### `ROOM_NAME`
Назначение/примечание: Нет NL Project data ATTDEF.

**Exact ATTDEF set:**

`<нет NL Project data ATTDEF>`

**`LOAD_TYPE`:** не используется в этом canonical block.

## 5. Обратный индекс `LOAD_TYPE` → canonical blocks

### `BOARD_AVR`

Щит АВР.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `BOARD_DISTRIBUTION`

Распределительный щит или щит освещения.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `BOARD_IN`

Вводно-распределительный щит.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `BOARD_IN_AVR`

Вводной щит с АВР.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `BOARD_METER`

Щит учёта.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `BOARD_SCS`

Слаботочный щит или СКС.

Допустимые blocks: `BOARD_IN`, `BOARD_OUT`, `BOARD_OUT_IP44`, `BOARD_OUT_IP54`, `BOARD_OUT_IP67`, `BOARD_PANEL`.

### `CABLE_BOILER`

Подключение котла.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_HEAT`

Подключение отопительного оборудования.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_HVAC`

Подключение вентиляционного или климатического оборудования.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_LIGHT_DECOR`

Вывод декоративного освещения.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_LIGHT_NIGHT`

Вывод ночного освещения.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_LIGHT_STREET`

Вывод уличного освещения.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_LIGHT_TECH`

Вывод технического освещения.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `CABLE_TECH`

Подключение другого стационарного оборудования.

Допустимые blocks: `CABLE_OUTLET`, `CABLE_OUTLET_FRAME`, `CABLE_OUTLET_DALI`, `CABLE_OUTLET_FRAME_DALI`.

### `LIGHT_DECOR`

Декоративное освещение.

Допустимые blocks: `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`, `LIGHT_LED`, `LIGHT_LED_IP67`.

### `LIGHT_MAIN`

Основное освещение.

Допустимые blocks: `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`, `LIGHT_LED`, `LIGHT_LED_IP67`.

### `LIGHT_NIGHT`

Ночное освещение.

Допустимые blocks: `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`, `LIGHT_LED`, `LIGHT_LED_IP67`.

### `LIGHT_STREET`

Уличное освещение.

Допустимые blocks: `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`, `LIGHT_LED`, `LIGHT_LED_IP67`.

### `LIGHT_TECH`

Техническое освещение.

Допустимые blocks: `LIGHT_OUT_230V`, `LIGHT_IN_230V`, `LIGHT_OUT_DALI_230V`, `LIGHT_IN_DALI_230V`, `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V`, `LIGHT_IN_IP44`, `LIGHT_OUT_IP54`, `LIGHT_LUSTRA`, `LIGHT_BRA`, `LIGHT_BRA_IP54`, `LIGHT_LED`, `LIGHT_LED_IP67`.

### `SOCKET_CONTROL_LOW`

Управляемая розетка с небольшой нагрузкой.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

### `SOCKET_CONTROL_MEDIUM`

Управляемая розетка с повышенной нагрузкой.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

### `SOCKET_EQUIPMENT`

Трёхфазная розетка другого оборудования.

Допустимые blocks: `SOCKET_OUT_380V`.

### `SOCKET_ETHERNET`

Информационная розетка Ethernet.

Допустимые blocks: `SOCKET_ETHERNET`.

### `SOCKET_KITCHEN_3PH`

Трёхфазная розетка кухонного оборудования / электроплиты.

Допустимые blocks: `SOCKET_OUT_380V`.

### `SOCKET_KITCHEN_HIGH`

Выделенная линия мощного кухонного оборудования.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

### `SOCKET_KITCHEN_MEDIUM`

Розетки кухонного фартука.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

### `SOCKET_LIVING_LOW`

Бытовые розетки жилых помещений с обычной нагрузкой.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

### `SOCKET_LIVING_MEDIUM`

Бытовые розетки с повышенной нагрузкой.

Допустимые blocks: `SOCKET_IN`, `SOCKET_IN_IP44`, `SOCKET_OUT`, `SOCKET_OUT_IP54`.

## 6. Проверка definition перед сохранением
1. Имя definition точно совпадает с canonical name.
2. В block присутствуют все и только ATTDEF из `Exact ATTDEF set`.
3. `DEVICE_TYPE`, `POSTS`, legacy `SOURCE`, `OUT_*`, `CABLE_LINK`, `BUS_LINK` не остаются скрытыми ATTDEF.
4. `DEVICE_NAME` не удаляется там, где указан карточкой блока.
5. Значение `LOAD_TYPE`, если поле есть, входит в список допустимых значений этой же карточки.
6. `SW_*` / `BTN_*` не содержат `CABLE_SOURCE`; порядок общей линии задаёт `.ZZ`.
7. Physical port fields остаются отдельными ATTDEF согласно profile.
8. DALI-capable ordinary field blocks содержат полный физический bus-cable набор.
9. Track-connected light blocks не содержат route fields несуществующего монтажного участка `TRACK -> LIGHT`.
10. После изменения definition существующие INSERT синхронизируются штатными средствами AutoCAD перед parser test.

## 7. Связанный документ

Архитектурный смысл этих полей и parser reconciliation определены в `CURRENT_TOPOLOGY_ARCHITECTURE.md`.
