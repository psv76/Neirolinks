# HHM 3.5 — точечная доработка operator journal после live 3.4

Основание: #69, #81, #94 и live export системного журнала Иволги 29.09.2026 после штатного обновления HHM 3.3 → 3.4 через NLI 0.1.9.

## Что подтвердил live 3.4

Переход источника отработал правильно:

```text
Появился запрос
→ команда Current Boiler Mode=1 «Зима ЦО + ГВС»
→ readback=1
→ Heating Setpoint

Нет запроса
→ команда Current Boiler Mode=0 «Ожидание»
→ readback=0
```

Обычный `OUTPUT_TRANSITION` spam и повторяющийся хвост «положение штока / вращение насоса / расход = Не измеряется» исчезли.

## Что обнаружено

1. До первого readback mode=1 одна и та же команда могла попасть в operator journal дважды за несколько сотен миллисекунд.
2. В pump/hot-port строке одновременно присутствовали два поля `причина=`: общий «Штатный переход» и фактическая причина команды.
3. Штатный прогрев источника отображался как `WARNING ... код=NORMAL; причина=, источник ещё холодный`.
4. Таймеры отображались как абстрактные `ТАЙМЕР=Начало ожидания` / `Окончание ожидания`, хотя оператору нужен конкретный процесс.

## Изменения 3.5

- повторная запись того же boiler mode до readback не создаёт повторную operator-команду;
- повторные технические write attempts не выдаются за новые пользовательские события;
- pump/hot-port command содержит ровно одно поле `причина=`;
- ведущий разделитель в warning нормализуется;
- обычный «источник ещё холодный» при `NORMAL` преобразуется в INFO:
  `СОСТОЯНИЕ=Ожидание прогрева источника; код=SOURCE_WARMING; причина=Температура источника ниже требуемой`;
- остальные реальные warnings/errors не понижаются;
- generic `TIMER_STARTED/TIMER_FINISHED` заменены операторскими кодами:
  - `TIMER_ZONE_OPEN_STARTED`;
  - `TIMER_ZONE_OPEN_FINISHED`;
  - `TIMER_ZONE_OPEN_CANCELLED`;
  - `TIMER_PUMP_POSTRUN_STARTED`;
  - `TIMER_PUMP_POSTRUN_FINISHED`;
  - `TIMER_PUMP_POSTRUN_CANCELLED`;
  - `TIMER_INTERRUPTED`.

## Что не меняется

- алгоритм отопления;
- Current Boiler Mode contract 0/1;
- порядок mode=1 → readback → Heating Setpoint;
- MAO4 output/readback contract;
- postrun durations;
- Sensor Health;
- thermal protection;
- ownership outputs;
- NLI 0.1.9 transaction engine.

## Отдельно от HHM

В live export также наблюдались повтор целого блока журнала и управляющие байты. Это не исправляется HHM 3.5: проблема относится к представлению/экспорту системного журнала.

Сообщение `wb-mqtt-db: Group data limit is reached` также является отдельной задачей хранения истории и не относится к HHM logging.

## Acceptance

- одна operator-команда mode=1 до подтверждения readback;
- одна operator-команда mode=0 до подтверждения readback;
- ровно одно `причина=` в pump/hot-port command;
- штатный source warm-up — INFO, не WARNING/NORMAL;
- прямые timer texts без «Начало/Окончание ожидания» для выбега;
- все HHM3 regressions green;
- NLI 0.1.9 видит approved 3.5 как обновление 3.4 → 3.5.
