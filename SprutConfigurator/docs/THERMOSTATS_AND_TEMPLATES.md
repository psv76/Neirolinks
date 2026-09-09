# Термостаты и Sprut templates

## 1. Общая граница

Термостат является виртуальным устройством Wiren Board.

```text
датчики
→ WB thermostat engine
→ physical outputs / equipment
→ MQTT virtual device
→ Sprut template
→ Sprut UI
```

Граница:

```text
WB    = логика, защиты, физические команды
Sprut = UI, уставки, режимы, presentation
```

## 2. Базовые типы thermostat contract

```text
SIMPLE
COMBO
CLIMATE
```

Технические имена:

```text
NL_simple_thermostat_XXX
NL_combo_thermostat_XXX
NL_climate_thermostat_XXX
```

### SIMPLE

Один управляющий temperature signal + один или несколько синхронных heating outputs.

MQTT controls:

```text
temperature
target_temperature
target_state
current_state
```

`SIMPLE` может использовать air- или floor-sensor; Sprut contract от физической природы датчика не зависит.

### COMBO

Воздух + пол.

MQTT controls baseline:

```text
air_temperature
floor_temperature
target_temperature
target_state
current_state
floor_min_temperature
floor_max_temperature
```

Зрелая WB-логика предусматривает degraded modes:

- оба датчика недоступны → закрыть heating outputs;
- нет air, есть floor → работать по floor hold;
- есть air, нет floor → работать по air.

Один логический thermostat может управлять несколькими синхронными physical outputs.

### CLIMATE

Нагрев + охлаждение.

Дополнительный control:

```text
cooling_temperature
```

Режимы:

```text
OFF
HEAT
COOL
AUTO
```

Equipment-specific AC timers, fan/vanes policies относятся к WB engine и не должны автоматически считаться универсальными Project defaults.

## 3. Общие template rules

Template должен создавать минимальный корректный Accessory.

Нежелательная модель:

```text
создать всё возможное
→ потом вручную скрывать лишнее
```

Предпочтительная модель:

```text
template создаёт нужную entity shape
→ Configurator применяет declarative presentation contract
```

Template не должен:

- назначать объектовые комнаты;
- кодировать пользовательские имена конкретного объекта;
- содержать инженерную автоматику;
- зависеть от Sprut runtime ID;
- создавать Services «на всякий случай».

## 4. Heating templates в репозитории

### `Templates/Sprut/Heating/NL_simple_thermostat.json`

Статус baseline:

```text
FIELD VERIFIED
```

Создаёт `Thermostat`.

### `Templates/Sprut/Heating/NL_combo_thermostat.json`

Статус baseline:

```text
FIELD VERIFIED
```

Текущий baseline template создаёт:

```text
Thermostat
TemperatureSensor "Пол"
```

Options требуют рабочей семантики `init: true`; именно этот вариант прошёл полевую validation.

### `Templates/Sprut/Heating/NL_climate_thermostat.json`

Статус на момент фиксации:

```text
IMPLEMENTED / NEEDS RECHECK
```

В текущем repository snapshot options всё ещё содержат `init: false`. Поэтому CLIMATE нельзя считать field-verified до отдельной проверки.

## 5. WB-MSW template family

Приняты profiles:

```text
TH
THM
M
CO
COM
```

Базовая mapping-модель:

| Profile | Baseline Services |
|---|---|
| TH | TemperatureSensor + HumiditySensor |
| THM | TemperatureSensor + HumiditySensor + MotionSensor |
| M | MotionSensor |
| CO | TemperatureSensor + HumiditySensor + CO2Sensor |
| COM | TemperatureSensor + HumiditySensor + CO2Sensor + MotionSensor |

Полевым применением подтверждены как минимум сценарии TH/THM. Полнота общего каталога template-файлов в GitHub должна проверяться отдельно от факта полевой работы установленного Sprut.

## 6. WB-M1W2 template family

Рекомендуемые role templates:

```text
W1_TEMP
W1_LEAK
W1_GERCON
W2_TEMP
W2_LEAK
W2_GERCON
```

Полевым применением подтверждены как минимум роли:

```text
W1_TEMP
W1_LEAK
W2_TEMP
```

Остальные роли требуют отдельного field test перед статусом FIELD VERIFIED.

## 7. Relay templates

Универсальная маска всех relay `K* → Lightbulb` запрещена архитектурно.

Для object-specific whitelist допустим объектовый template в `objects/<object>/Templates/Sprut/`.

В общем решении тип relay channel должен определяться функциональным назначением из Project model или эквивалентного явного контракта.

## 8. Статусы template

Использовать:

- `FIELD VERIFIED` — принят Sprut и проверен на реальном объекте;
- `IMPLEMENTED / NEEDS RECHECK` — файл существует, но текущий вариант требует повторной проверки;
- `REQUIRED` — контракт определён, template ещё не реализован/не сохранён;
- `OBJECT-SPECIFIC` — сознательно привязан к одному объекту.

## 9. Definition of FIELD VERIFIED

Перед присвоением статуса:

1. понятный model/modelIds;
2. минимальный состав Services;
3. отсутствие лишних Services;
4. корректный SERIAL в DISCOVER;
5. Configurator может однозначно сопоставить Service contract;
6. remove/rediscover test;
7. DRY RUN;
8. APPLY;
9. VERIFY;
10. файл и contract зафиксированы в GitHub.

## 10. Важное замечание о будущем presentation

Текущие template shape и Configurator v0.2.2 — baseline, а не вечная схема UI.

Если следующая задача подтверждает более чистую presentation model, общие template contracts и документация должны быть обновлены по результатам реальной проверки, а не заранее объявлены готовыми.
