# NL Project 2.0 — архитектура физической топологии AutoCAD ↔ Project

**Дата:** 2026-08-30  
**Статус:** принятый источник topology для Repair 08; техническая реализация подтверждена Repair 08 report. Общая пользовательская приёмка остаётся незавершённой, см. [STATUS.md](../STATUS.md).

## 1. Назначение

Документ фиксирует текущую принятую архитектуру физической топологии NL Project 2.0 для планировочных DWG и Project.

Архитектура должна одновременно описывать:

- обычные кабельные линии;
- распределительные коробки `EL_BOX`;
- полевые устройства и их физические порты;
- RS-485;
- DALI;
- обычные и DALI-светильники;
- физические треки и светильники на треках;
- двустороннюю синхронизацию AutoCAD ↔ Project;
- минимальный planning-DWG contract без потери исходных инженерных данных;
- расчёт PoE-бюджета Ethernet-коммутаторов как Project/catalog-owned расчёт.

Точный набор ATTDEF каждого известного блока определяется отдельным документом [AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md).

### 1.1. Canonical block name и `DEVICE_NAME`

Физический тип planning block определяется его canonical block name. Отдельный ATTDEF `DEVICE_TYPE` в target contract не используется.

`DEVICE_NAME` сохраняется во всех блоках, где он предусмотрен справочником. Это свободное человекочитаемое описание конкретного изделия/исполнения и оно не выводится только из canonical block name или каталога.

Для `FRAME_n` количество постов выводится из canonical block name; отдельный ATTDEF `POSTS` не используется.

## 2. Разделение сущностей

Система должна различать четыре слоя данных:

```text
PHYSICAL OBJECT
    конкретная вставка физического блока в DWG

CABLE TOPOLOGY
    CableLine, topology points и физические CableSegment

BUS TOPOLOGY
    Bus, BUS_POINT_ID и физические BusSegment

FUNCTIONAL RELATIONS
    KEY_x, DALI_GROUP и другие логические связи, которые не являются физическим кабельным сегментом
```

Физическое размещение устройства внутри коробки само по себе не создаёт topology edge.

Коробка, внутри которой установлен RS-485 модуль, не должна включаться в RS-485 topology только из-за геометрического наложения блоков.

## 3. Обычная кабельная линия

### 3.1. `CableLine`

Нормализованная кабельная линия Project содержит как минимум:

```text
CABLE_ID        = XYY
BOARD           = щит, к которому относится линия
CABLE_TYPE      = тип физического монтажного кабеля
FUNCTION_GROUP  = функциональная группа линии
ROOT_ENDPOINT   = физическая точка начала линии
```

Отдельное поле `LINE_ROLE` не используется.

Роль линии, если она определяется подключением к конкретному физическому порту, должна выводиться из topology. Например, линия группы `POWER`, приходящая на `COM1` или `COM2` полевого реле, является линией питания силового контакта без отдельного `LINE_ROLE`.

### 3.2. `CABLE_ID`

Формат сохраняется:

```text
XYY[.ZZ]
```

- `XYY` идентифицирует одну физическую кабельную линию;
- `.ZZ` идентифицирует отдельную topology point / устройство внутри этой линии;
- `.ZZ` не создаёт новую CableLine.

`CABLE_ID` больше не означает только линию, физически выходящую из щита.

CableLine принадлежит определённому `BOARD`, но её физический источник может находиться:

- в щите;
- на выходном порту полевого устройства.

### 3.3. `BOARD`

`BOARD` означает принадлежность CableLine щиту в структуре Project.

`BOARD` не является непосредственным физическим источником каждого участка линии и не заменяет `ROOT_ENDPOINT` или `CABLE_SOURCE`.

### 3.4. `ROOT_ENDPOINT`

`ROOT_ENDPOINT` — физическая точка, от которой начинается CableLine.

`ROOT_ENDPOINT` является Project-owned / derived fact и не имеет отдельного ATTDEF в планировочных блоках.

Project должен выводить `ROOT_ENDPOINT` из принятой физической topology.

Если первая точка CableLine имеет:

```text
CABLE_SOURCE = 902.003/K1
```

то:

```text
ROOT_ENDPOINT = 902.003/K1
```

Если topology не содержит полевого source endpoint и линия является обычной линией от щита, root относится к выходу этой CableLine в её `BOARD`.

Если root невозможно определить однозначно, Project не должен угадывать и должен пометить topology как требующую внимания.

### 3.5. `CABLE_SOURCE`

`CABLE_SOURCE` хранится на downstream topology point и означает непосредственный физический источник входящего обычного кабельного участка.

Допустимые формы:

```text
<empty>                прямой участок от root линии в щите
BOX.010                от физической коробки
331.02                 от обычной cable topology point
902.003/K1             от конкретного физического порта шинного устройства
```

Формат ссылки на физический порт устройства:

```text
<BUS_POINT_ID>/<PORT>
```

Пример:

```text
CABLE_SOURCE = 902.003/K1
```

означает, что непосредственным источником входящего кабельного участка является порт `K1` устройства `902.003`.

Ссылка на порт допустима только при существующем устройстве и допустимом порте его canonical block profile.

### 3.6. Групповые линии выключателей и кнопок

Для `SW_*` и `BTN_*` base `CABLE_ID=2YY` обозначает один физический кабель, а suffix `.ZZ` — физический порядок устройств по общей линии от щита.

Для этих canonical blocks отдельный ATTDEF `CABLE_SOURCE` не используется: порядок задаётся `CABLE_ID` suffix и не дублируется вторым source-of-truth.

### 3.7. Обычный физический `CableSegment`

Для входящего физического кабельного участка используются:

```text
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
```

Эти поля относятся к конкретному входящему сегменту, а не ко всей CableLine.

`CABLE_TYPE` и `BOARD` являются свойствами базовой CableLine и должны нормализоваться в Project как line-owned facts.

### 3.8. Внутренняя связь через трек

Внутренняя модель Project различает:

```text
CABLE_LINK = CABLE | TRACK
```

Отдельного ATTDEF `CABLE_LINK` в planning blocks нет.

Для текущего canonical block catalog значение определяется типом downstream блока:

- `LIGHT_TRACK_230V`, `LIGHT_TRACK_48V`, `LIGHT_TRACK_DALI_48V` получают питание через `TRACK`;
- внешнее подключение самого `TRACK_*` и остальные известные обычные кабельные подключения являются `CABLE`.

У участка `TRACK` нет отдельного монтажного кабеля, поэтому для самого участка `TRACK -> LIGHT_TRACK_*` не создаются метры `CABLE_TYPE` и не задаются `MOUNT_WAY` / `GOFRA_*`.

## 4. Физические порты полевых устройств

### 4.1. Общий принцип

Поля физических портов сохраняются в AutoCAD, чтобы при открытии свойств блока пользователь видел занятость портов и непосредственно подключённые точки.

Для известных устройств используются, в частности:

```text
COM1
COM2
K1
K2
IN_1
IN_2
W1
W2
```

Значение port ATTDEF содержит непосредственную topology reference на физически подключённую точку.

Допустимые значения зависят от направления и профиля порта и могут включать:

```text
130          прямое подключение к root CableLine 130
BOX.010      подключение к коробке
331.01       подключение к обычной cable topology point
<empty>      порт свободен / связь ещё не задана
```

Направление связи определяется самим профилем порта, а не форматом значения.

### 4.2. Пример полевого реле

Текущий типовой сценарий использует одну питающую CableLine для силовых контактов MRM2, при этом `COM1` и `COM2` остаются отдельными физическими портами.

```text
WB_MRM2_MINI
BUS_POINT_ID = 902.003
CABLE_ID = 130
CABLE_SOURCE = BOX.010
COM1 = BOX.010
COM2 = BOX.010
K1   = BOX.030
K2   = 701.01
```

При этом:

```text
BOX.010: CABLE_ID = 130
BOX.030: CABLE_ID = 331
701.01:  CABLE_ID = 701.01
```

Project восстанавливает физические связи и занятость портов:

```text
BOX.010 -> 902.003/COM1
BOX.010 -> 902.003/COM2
902.003/K1 -> BOX.030
902.003/K2 -> 701.01
```

Для downstream точки допускается зеркальная запись:

```text
BOX.030:
CABLE_SOURCE = 902.003/K1
```

Два независимых feed-set для `COM1` и `COM2` в текущем contract не вводятся.

### 4.3. Один edge — два редактируемых представления

Портовое поле источника и `CABLE_SOURCE` downstream точки могут одновременно описывать один и тот же topology edge.

Оба представления разрешено:

- заполнять вручную;
- изменять вручную;
- заполнять автоматически из Project.

Они не являются двумя независимыми physical edges.

Project хранит одну каноническую связь и должен выполнять deterministic reconciliation с предыдущим каноническим состоянием Project.

Минимальные правила reconciliation:

1. Если обе стороны описывают одну связь — `PASS`.
2. Если заполнена только одна сторона — связь принимается; при write-back вторая сторона может быть заполнена автоматически.
3. Если одна сторона изменилась относительно предыдущего Project state, а вторая осталась старой — изменённая сторона считается пользовательским изменением; после принятия Project синхронизирует вторую сторону.
4. Если обе стороны изменены и описывают одну новую связь — новая связь принимается.
5. Если обе стороны изменены несовместимо, либо при первичном импорте без предыдущего state содержат противоречащие связи, Project не должен угадывать. Создаётся topology conflict / `Требует внимания`.
6. После успешного merge write-back должен привести обе DWG-проекции канонической связи к согласованному состоянию.

## 5. Шинная сеть

### 5.1. `Bus`

В Project существует отдельная сущность:

```text
BUS_ID       = 9YY
BUS_TYPE     = RS485 / DALI / ...
ROOT_POINT   = 9YY.000
```

`BUS_ID` и `BUS_TYPE` не являются ATTDEF полевых planning blocks.

`BUS_ID` выводится из базовой части `BUS_POINT_ID`.

`BUS_TYPE` и аппаратная привязка `9YY.000` к конкретному модулю/порту принадлежат Project.

Planning DWG не хранит обозначения типа `A34/Port 1`.

### 5.2. `BUS_POINT_ID`

Формат:

```text
9YY.ZZZ
```

- `9YY` — identity физической шины;
- `.000` — обязательная root point аппаратного порта;
- `.001 ... .999` — полевые topology points.

`BUS_POINT_ID` не является:

- DALI short address;
- Modbus slave address;
- `DALI_GROUP_ID`.

### 5.3. DALI topology

DALI использует explicit branching topology.

Каждая полевая DALI point содержит:

```text
BUS_POINT_ID
BUS_SOURCE
```

Первая полевая точка должна ссылаться на root:

```text
BUS_POINT_ID = 905.001
BUS_SOURCE   = 905.000
```

Все последующие `BUS_SOURCE` должны ссылаться на существующую точку той же `BUS_ID`.

Пустой `BUS_SOURCE` не означает прямое подключение к порту.

### 5.4. RS-485 topology

Принятая policy NL Project для RS-485 — линейная topology.

```text
901.000  root
901.001  first field device
901.002  second field device
901.003  third field device
```

Физический порядок определяется числовым suffix `BUS_POINT_ID`.

`BUS_SOURCE` не используется для RS-485 как второй источник порядка и не входит в ATTDEF-set известных RS-485 field-device blocks.

Физическая коробка, в которой установлен RS-485 device, не включается в RS-485 topology автоматически.

### 5.5. Физический кабель шины

`BUS_CABLE_TYPE` является line-owned свойством всей `BUS_ID`.

Физические свойства конкретного входящего `BusSegment`:

```text
BUS_MOUNT_WAY
BUS_GOFRA_TYPE
BUS_GOFRA_COLOR
BUS_GOFRA_ID
```

Для field block с реальным внешним bus cable эти ATTDEF присутствуют и описывают входящий `BusSegment`.

Для точек, подключённых через встроенную шину трека, отдельный монтажный bus cable отсутствует и физические `BUS_*` route fields на таком light block не используются.

### 5.6. Внутренняя DALI-связь через трек

Внутренняя модель Project различает:

```text
BUS_LINK = CABLE | TRACK
```

Отдельного ATTDEF `BUS_LINK` в planning blocks нет.

Для текущего catalog:

- входящий DALI к `TRACK_DALI` является `CABLE`;
- `TRACK_DALI -> LIGHT_TRACK_DALI_48V` является `TRACK`;
- обычные DALI-светильники `LIGHT_*_DALI_230V` имеют входящий `CABLE`.

## 6. Коробки `EL_BOX`

Каждая физическая коробка имеет независимый:

```text
BOX_ID = BOX.xxx
```

`BOX_ID` не является `CABLE_ID` и не является `BUS_POINT_ID`.

Одна коробка может быть:

- только физическим объектом плана/спецификации;
- topology point обычной CableLine;
- topology point DALI;
- одновременно точкой обычной CableLine и DALI.

Physical-only box допускается с пустыми `CABLE_ID` и `BUS_POINT_ID`.

В ordinary cable topology одна коробка относится максимум к одной базовой CableLine `XYY`.

Не вводятся:

```text
HOST_BOX
INSTALLED_IN
BOX_ROLE
TOPOLOGY_STATUS
```

Факт геометрического нахождения M1W2/MRM2 внутри коробки не создаёт topology edge и не требует `HOST_BOX`.

## 7. Полевые реле и питание контактов

Отдельного `LINE_ROLE=FIELD_RELAY_FEED` нет.

`WB_MRM2_MINI` сохраняет реальные физические порты:

```text
COM1
COM2
K1
K2
IN_1
IN_2
```

Для текущего практического контракта блок также содержит **один** обычный набор `CableLine/CableSegment`:

```text
CABLE_ID
CABLE_TYPE
BOARD
CABLE_SOURCE
MOUNT_WAY
GOFRA_TYPE
GOFRA_COLOR
GOFRA_ID
```

Этот набор описывает типовой сценарий одной питающей CableLine для силовых контактов реле. `COM1` и `COM2` при этом остаются независимыми физическими портами и должны быть видны в свойствах блока.

Архитектура не запрещает аппаратно независимое питание `COM1` и `COM2`, но текущий planning-DWG contract **не вводит два отдельных полных набора параметров входящих CableSegment**. Поддержка двух независимых питающих CableLine с разными route facts откладывается до появления реального рабочего сценария.

Отходящие линии начинаются от конкретных физических портов, например:

```text
CABLE_SOURCE = 902.003/K1
CABLE_SOURCE = 902.003/K2
```

`ROOT_ENDPOINT` соответствующей CableLine Project выводит из topology.

Функциональная группа отходящей CableLine определяется её реальной нагрузкой. Один универсальный MRM2 может иметь выходы на разные функциональные группы.

## 8. Светильники и треки

### 8.1. Canonical light blocks

Приняты следующие canonical names:

```text
LIGHT_OUT_230V
LIGHT_IN_230V
LIGHT_OUT_DALI_230V
LIGHT_IN_DALI_230V
LIGHT_TRACK_230V
LIGHT_TRACK_48V
LIGHT_TRACK_DALI_48V
```

Семантика имени:

- `OUT` — накладной;
- `IN` — встраиваемый;
- `DALI` — светильник участвует в DALI bus topology;
- `TRACK` — физическое подключение светильника выполняется через трек;
- `230V` / `48V` — напряжение питания светильника.

Все семь являются отдельными светильниками. Тип, напряжение, наличие DALI и способ подключения определяются canonical block name; отдельный ATTDEF `DEVICE_TYPE` не используется.

### 8.2. Обычные 230 В светильники

```text
LIGHT_OUT_230V
LIGHT_IN_230V
```

имеют только ordinary cable topology и не содержат `BUS_*` ATTDEF.

### 8.3. Обычные DALI-светильники 230 В

```text
LIGHT_OUT_DALI_230V
LIGHT_IN_DALI_230V
```

одновременно имеют:

- ordinary power cable topology;
- DALI bus topology;
- отдельные физические route facts для power CableSegment и DALI BusSegment.

### 8.4. Трековые светильники

```text
LIGHT_TRACK_230V
LIGHT_TRACK_48V
LIGHT_TRACK_DALI_48V
```

не описывают отдельный монтажный кабель между треком и светильником.

Для них `CABLE_LINK=TRACK` выводится из canonical block name.

Для `LIGHT_TRACK_DALI_48V` также `BUS_LINK=TRACK` выводится из canonical block name.

### 8.5. Физические треки

Физические изделия трека остаются отдельными canonical blocks:

```text
TRACK_230V
TRACK_48V
TRACK_DALI
```

`TRACK_DALI` принимает внешний силовой кабель и внешний DALI cable как две независимые физические сети.

Внешние physical route facts заканчиваются на блоке самого трека. Светильники на треке не дублируют эти route fields.

### 8.6. Ранее существовавшие generic names

В target contract generic names:

```text
LIGHT_IN
LIGHT_OUT
```

заменяются соответственно на:

```text
LIGHT_IN_230V
LIGHT_OUT_230V
```

Остальные существующие специализированные light names, для которых отдельное переименование не принималось, сохраняются в каталоге и считаются обычными non-DALI light blocks до отдельного решения.

## 9. Кабельные выводы

Чтобы ordinary cable outlet не содержал лишний bus-набор, приняты четыре canonical blocks:

```text
CABLE_OUTLET
CABLE_OUTLET_FRAME
CABLE_OUTLET_DALI
CABLE_OUTLET_FRAME_DALI
```

`CABLE_OUTLET` и `CABLE_OUTLET_FRAME` описывают только ordinary cable topology.

`CABLE_OUTLET_DALI` и `CABLE_OUTLET_FRAME_DALI` одновременно описывают ordinary cable topology и DALI bus topology, включая физические параметры входящего DALI BusSegment.

Фиктивный DALI cable outlet возле каждого DALI-светильника не создаётся: реальный DALI light/track block сам является bus point.

## 10. DALI logical data

Physical DALI topology не определяет логическую группу управления.

Должны оставаться отдельными:

```text
BUS_POINT_ID       physical topology identity
DALI short address protocol/configuration identity
DALI_GROUP_ID      logical group identity
```

Изменение DALI group или protocol short address не должно менять `BUS_POINT_ID`.

Фиктивный `CABLE_OUTLET` рядом с каждым DALI-светильником не требуется. Реальный DALI light / track block сам может владеть `BUS_POINT_ID`.

`CABLE_OUTLET` сохраняется только для реальной физической точки подключения, у которой нет другого подходящего физического owner block.

## 11. `LOAD_TYPE`, розетки и функциональные классификаторы

`LOAD_TYPE` остаётся только там, где он несёт самостоятельную функциональную классификацию, не выводимую из canonical block name:

- светильники и LED-линии;
- розетки;
- кабельные выводы;
- электрощиты.

`LOAD_TYPE` не используется у `SW_*`, `BTN_*`, `SENSOR_*`, `WB_M1W2`, `WB_MAI2`, `FAN`, `AIR_VALVE`, `CONTROL_PANEL_*`, `TRACK_*`, `WB_MRM2_MINI`.

Для обычных однофазных розеточных blocks ATTDEF `PHASE` не используется; однофазность выводится из canonical block name.

Добавлен canonical block:

```text
SOCKET_OUT_380V
```

Он обозначает трёхфазную розетку открытой установки. `PHASE=3` выводится из canonical block name и отдельным ATTDEF не хранится. Суффикс `OUT` сохраняется, чтобы в будущем при реальном сценарии можно было ввести `SOCKET_IN_380V`.

Для `SOCKET_OUT_380V` зарегистрированы два `LOAD_TYPE`:

```text
SOCKET_KITCHEN_3PH
SOCKET_EQUIPMENT
```

`SOCKET_KITCHEN_3PH` — трёхфазная розетка кухонного оборудования/электроплиты; `SOCKET_EQUIPMENT` — трёхфазная розетка другого оборудования.

`SOCKET_ETHERNET` не содержит `CALC_POWER` и `PHASE`.

### 11.1. PoE power budget

Мощность PoE-панелей `CONTROL_PANEL_*` не хранится в planning DWG через `CALC_POWER`. Она является Project/catalog-owned свойством выбранной модели панели.

Project должен уметь рассчитывать PoE budget выбранного Ethernet-коммутатора как минимум по суммарной мощности PoE-потребителей и доступному PoE budget выбранной модели коммутатора. Обычные Ethernet-розетки в PoE power budget как нагрузка не включаются.

### 11.2. Canonical rename полевых модулей

Canonical names:

```text
SENSOR_M1W2 -> WB_M1W2
SENSOR_MAI2 -> WB_MAI2
```

Эти blocks являются полевыми WB-модулями, а не generic sensor blocks.

## 12. AutoCAD и Project: граница ответственности

### 12.1. Planning DWG хранит

- canonical block name;
- canonical block name, `DEVICE_NAME` и physical placement fields;
- ordinary cable identity/topology, когда она относится к блоку;
- bus point/topology, когда она относится к блоку;
- physical route facts входящих cable/bus segments;
- значения физических портов предусмотренных профилем устройства;
- `KEY_x`, comments и другие field-device facts согласно block reference.

### 12.2. Project хранит / нормализует

- `CableLine`;
- `Bus`;
- `BOARD` ownership;
- `ROOT_ENDPOINT`;
- `FUNCTION_GROUP`;
- `CABLE_LINK` и `BUS_LINK` как derived model facts;
- hardware binding `9YY.000 -> concrete module/port`;
- `BUS_TYPE`;
- DALI short addresses;
- DALI group membership;
- канонические topology edges;
- reconciliation state и topology conflicts;
- `DWG_HANDLE` как техническую identity INSERT;
- equipment/product/resource data.

Planning DWG не должен хранить конкретные внутренние обозначения щита типа `A34/Port 1` как часть bus topology.

## 13. Валидация

Project должен как минимум выявлять:

- duplicate `BOX_ID`;
- duplicate `BUS_POINT_ID`;
- field block с `BUS_POINT_ID=9YY.000`;
- DALI `BUS_SOURCE` из другой `BUS_ID`;
- DALI cycle/ring/mesh;
- `CABLE_SOURCE` на отсутствующий `BOX_ID`, `XYY.ZZ` или `<BUS_POINT_ID>/<PORT>`;
- ссылку на несуществующий port canonical block profile;
- cycle/double parent в ordinary cable topology;
- конфликт line-owned `BOARD` / `CABLE_TYPE`;
- конфликт line-owned `BUS_CABLE_TYPE`;
- несовместимые port-field и `CABLE_SOURCE` representations одного edge;
- route facts у track-connected light, где отдельного монтажного сегмента нет;
- попытку включить physical-only box в RS-485 topology по геометрическому наложению;
- `CABLE_SOURCE` у `SW_*` / `BTN_*`, где порядок должен задаваться только `.ZZ`;
- неизвестный или недопустимый для canonical block `LOAD_TYPE`;
- legacy `SOURCE`, `.RKn`, `OUT_1...OUT_5`, `DEVICE_TYPE`, `POSTS`, `CABLE_LINK`, `BUS_LINK`, если они присутствуют как ATTDEF target planning blocks.

## 14. Legacy, заменяемый этой архитектурой

В target contract не используются:

```text
SOURCE
XYY.RKn
OUT_1
OUT_2
OUT_3
OUT_4
OUT_5
LINE_ROLE
DEVICE_TYPE (как ATTDEF planning block)
POSTS       (как ATTDEF FRAME_n; значение выводится из имени блока)
CABLE_LINK  (как ATTDEF)
BUS_LINK    (как ATTDEF)
BUS_ID      (как повторный ATTDEF полевого блока)
BUS_TYPE    (как ATTDEF полевого блока)
BUS_SOURCE=<empty> как обозначение DALI root
```

`CABLE_ID=9YY...` больше не является универсальным способом хранения bus identity: bus topology использует `BUS_POINT_ID=9YY.ZZZ`.

Legacy canonical names `SENSOR_M1W2` и `SENSOR_MAI2` заменены на `WB_M1W2` и `WB_MAI2`. Ordinary `CABLE_OUTLET`/`CABLE_OUTLET_FRAME` больше не содержат DALI bus-поля; для DALI используются отдельные `CABLE_OUTLET_DALI` / `CABLE_OUTLET_FRAME_DALI`.

## 15. Связанный документ

Точный target ATTDEF set каждого известного canonical block определяется в:

[AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md](AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md).
