# HM2 MixingController

Повторно используемый регулятор смесительного контура для Heating Manager 2.0 / `wb-rules`.

## Статус

- Источник алгоритма: фактически работающий регулятор смесительного узла тёплого пола объекта `05_16_Iset`, встроенный в `21_heating_floor_manager.js`.
- На Исети проверена сама step-hold механика регулирования и её работа с реальным смесительным узлом.
- Общий `MixingController.js` — новая объектонезависимая упаковка этой механики. Синтаксис проверен, но перед production на каждом новом объекте требуется объектная адаптация и ПНР.

Это **не классический PID** с коэффициентами `Kp/Ki/Kd`. Алгоритм — step-hold регулятор с двумя фазами `FAST` / `TRIM` и анализом фактического температурного тренда.

## Зачем вынесен отдельно

На разных объектах Heating Manager 2.0 может иметь несколько смесительных контуров. Общая механика регулирования не должна копироваться целиком в каждый объектный manager.

Разделение ответственности:

```text
объектный manager HM2
    ├─ определяет demand
    ├─ владеет насосом
    ├─ формирует target подачи
    ├─ проверяет interlock / safety / ownership
    ├─ публикует HM2 contract
    └─ вызывает MixingController
             └─ рассчитывает и пишет положение смесительного клапана
```

## Что делает MixingController

Регулятор поддерживает:

- deadband вокруг цели подачи;
- две фазы регулирования `FAST` и `TRIM`;
- размер шага в зависимости от ошибки;
- раздельную чувствительность на открытие и закрытие;
- выдержку после движения клапана;
- минимальную паузу между шагами;
- блокировку слишком быстрого разворота направления;
- анализ `dT/dt` и ожидание, если температура уже движется в нужную сторону;
- усиление реакции, если температура движется в неправильную сторону;
- контроль стагнации;
- ограничение минимального/максимального открытия;
- ограничение открытия после старта насоса (`startup cap`);
- запрет дополнительного открытия, если источник недостаточно горячий (`source guard`);
- проверку достоверности датчика подачи;
- закрытие клапана после устойчивого отказа датчика;
- жёсткий максимум температуры подачи;
- ручное удержание клапана для ПНР (`freeze/manualValvePct`).

## Что регулятор намеренно НЕ делает

`MixingController` не должен знать объектную гидравлику и поэтому не содержит:

- MQTT-адресов;
- номеров модулей и реле;
- названий помещений;
- погодной кривой конкретного объекта;
- фиксированной уставки подачи;
- логики зональных термостатов;
- логики запроса тепла котлу;
- арбитража HM2;
- управления насосом;
- готовых параметров ПНР конкретного объекта.

Целевую температуру `targetC` каждый объектный manager передаёт регулятору сам.

## Ownership

Один физический канал должен иметь одного писателя.

Если `MixingController` используется объектным manager, функции `writeValvePosition()` и `writeValveEnable()` этого manager должны быть единственным путём записи в соответствующие выходы клапана.

Сам модуль насосом не управляет. Насос остаётся owned объектным manager.

## Подключение

Файл модуля на Wiren Board:

```text
/etc/wb-rules-modules/MixingController.js
```

Подключение:

```js
var MixingController = require("MixingController");
```

Создание экземпляра:

```js
var mix = MixingController.create({
    initialValvePositionPct: 0,
    tuning: MIX_TUNING
}, {
    writeValvePosition: function (pct) {
        return hc.output(MIX_VALVE_POS, pct, CFG.outputsEnabled);
    },
    writeValveEnable: function (enabled) {
        return hc.output(MIX_VALVE_ENABLE, enabled, CFG.outputsEnabled);
    }
});
```

Один модуль допускает несколько независимых экземпляров — например отдельный controller для каждого смесительного контура.

## Вызов шага регулирования

Пример:

```js
var result = mix.step({
    now: hc.now(),
    enabled: true,
    pumpOn: pumpOn,
    supplyTempC: supplyTemp,
    sourceTempC: sourceTemp,
    targetC: requestedMixSupply,
    sensorOffsetC: 0,
    valveEnableOn: hc.bool(MIX_VALVE_ENABLE) === true,
    phaseMode: "auto",
    freeze: false,
    manualValvePct: 0
});
```

`step()` не нужно вызывать чаще рабочего периода, принятого объектным manager. Сам модуль таймеров `wb-rules` не создаёт.

## Результат `step()`

Возвращается объект текущего состояния:

```text
valvePositionPct
lastAcceptedValvePositionPct
phase
trendCPerMin
effectiveTargetC
sourceGuardActive
startupRemainingS
sensorFault
badSensorCount
alarmActive
alarmText
status
```

`status` — машинная причина текущего действия/ожидания, например:

```text
STEP_OPEN
STEP_CLOSE
DEADBAND_HOLD
STEP_HOLD_WAIT
POST_MOVE_SETTLE
TREND_OK_HOLD
SOURCE_GUARD_HOLD
REVERSE_LOCK_HOLD
POSITION_LIMIT_HOLD
SUPPLY_SENSOR_TRANSIENT_HOLD
SUPPLY_SENSOR_FAILSAFE_CLOSE
SUPPLY_HARD_MAX_SAFE_CLOSE
PUMP_OFF_SAFE_CLOSE
TARGET_NOT_READY_SAFE_CLOSE
OUTPUT_WRITE_REJECTED
```

Объектный manager решает, какие из этих состояний выводить в WebUI и какие переходы писать в журнал.

## Обязательный tuning

Модуль намеренно не содержит готовых объектных настроек. При создании экземпляра необходимо явно передать все параметры `tuning`:

```text
bandC
biasC
farErrorC
fastHoldColdS
fastHoldHotS
fastMinStepPct
fastMaxStepPct
trimHoldColdS
trimHoldHotS
trimMinStepPct
trimMaxStepPct
pctPerCCold
pctPerCHot
reverseLockS
trendOkCPerMin
trendSlowCPerMin
stagnationS
postMoveSettleS
minPosPct
maxPosPct
hardMaxC
supplyValidMinC
supplyValidMaxC
sensorBadLimit
sourceGuardEnabled
sourceMarginC
sourceValidMinC
sourceValidMaxC
startupCapEnabled
startupDurationS
startupMaxPosPct
enableRetryS
safeCloseOnDisable
```

Значения должны браться из подтверждённой гидравлики и ПНР текущего объекта. Настройки Исети не являются автоматическими настройками для Иволги или любого другого объекта.

## Граница безопасности

`MixingController` содержит локальные защиты самого регулирования, но не заменяет HM2 Safety Supervisor.

Объектный manager по-прежнему обязан отдельно проверять:

- допустимость запуска контура;
- валидность HM2 demand;
- разрешение арбитра;
- физическое владение выходами;
- подтверждение команд, если оно доступно;
- response watchdog теплопередачи;
- безопасное отключение насоса;
- общий source/safety contract.

При `pumpOn=false`, отсутствии цели или подтверждённой аварии датчика регулятор переводит клапан к безопасному закрытию согласно своему контракту.

## Перенос с Исети

Из `21_heating_floor_manager.js` в общий модуль вынесена только механика регулирования клапана.

В объектном manager остаются:

- demand зон;
- `path_ready`;
- владение насосом;
- HM2 permit;
- response watchdog;
- вычисление требуемой температуры источника;
- публикация атомарного consumer contract;
- конкретные MQTT-каналы;
- объектная tuning-конфигурация.

Такой разрез позволяет использовать один и тот же регулятор на нескольких смесительных контурах Иволги без переноса физических фактов Исети.
