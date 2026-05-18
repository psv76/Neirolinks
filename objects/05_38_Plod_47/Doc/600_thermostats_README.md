# 600_thermostats.js

Зональные термостаты Wiren Board для Sprut.hub.

Скрипт создаёт виртуальные термостаты WB, управляет отоплением зон через сервоприводы, а в climate-зонах дополнительно управляет охлаждением через кондиционеры ONOKOM. Критичная логика отопления, охлаждения, защитных пауз и исполнительных команд остаётся в `wb-rules`; Sprut.hub используется как интерфейс пользователя, уставки, режимы и отображение состояния.

## Роли системы

```text
WB        = логика отопления/охлаждения, защиты, исполнительные команды, системный журнал
Sprut.hub = интерфейс пользователя, уставки, режимы, отображение
```

Сценарии Sprut.hub не должны напрямую управлять сервоприводами, `Active mode`, `Target temperature`, `Horizontal vanes` или `Smart fan speed` кондиционеров, потому что для этих физических каналов писателем является этот скрипт.

## Типы виртуальных термостатов

Сохранены существующие имена виртуальных устройств:

```text
NL_simple_thermostat_[0-9]{3}
NL_combo_thermostat_[0-9]{3}
NL_climate_thermostat_[0-9]{3}
```

### `NL_simple_thermostat`

Простой термостат для зон, которые работают только по полу.

Существующие controls не переименованы:

```text
target_state
temperature
target_temperature
current_state
```

### `NL_combo_thermostat`

Комбинированный термостат для зон с логикой воздух + пол.

Существующие controls не переименованы:

```text
target_state
air_temperature
target_temperature
state
floor_temperature
floor_min_temperature
floor_max_temperature
current_state
```

### `NL_climate_thermostat`

Климатический термостат для зон с отоплением через пол и охлаждением через кондиционер ONOKOM.

Режимы `target_state`:

```text
0 = OFF
1 = HEAT
2 = COOL
3 = AUTO
```

Режимы `current_state`:

```text
0 = OFF
1 = HEAT
2 = COOL
```

Существующие controls не переименованы:

```text
target_state
air_temperature
target_temperature
cooling_temperature
state
floor_temperature
floor_min_temperature
floor_max_temperature
ac_vanes_control
saved_horizontal_vanes
ac_min_on_timer_sec
ac_min_off_timer_sec
ac_manual_pause_timer_sec
ac_timer_status
current_state
```

Добавлены controls ночного режима:

```text
ac_night_mode_enabled = Ночной режим кондиционера, switch, по умолчанию включен
ac_night_fan_speed    = Ночная скорость вентилятора, range 0...7, по умолчанию 1
ac_night_mode_status  = Статус ночного режима, text readonly
```

## Зоны скрипта

| ID | Контекст | Модель | Виртуальное устройство | Сервоприводы |
|---|---|---|---|---|
| 601 | гостевая | `NL_combo_thermostat` | `NL_combo_thermostat_601` | `wb-mr6cu_218/K1` |
| 602 | душевая | `NL_simple_thermostat` | `NL_simple_thermostat_602` | `wb-mr6cu_218/K2` |
| 603 | кухня | `NL_simple_thermostat` | `NL_simple_thermostat_603` | `wb-mr6cu_218/K3` |
| 604 | выход на террасу | `NL_simple_thermostat` | `NL_simple_thermostat_604` | `wb-mr6cu_218/K4` |
| 605 | гостиная | `NL_climate_thermostat` | `NL_climate_thermostat_605` | `wb-mr6cu_218/K5` |
| 606 | прихожая | `NL_simple_thermostat` | `NL_simple_thermostat_606` | `wb-mr6cu_218/K6` |
| 607 | детская справа | `NL_combo_thermostat` | `NL_combo_thermostat_607` | `wb-mr6cu_224/K1`, `wb-mr6cu_224/K2` |
| 609 | детская слева | `NL_combo_thermostat` | `NL_combo_thermostat_609` | `wb-mr6cu_224/K3`, `wb-mr6cu_224/K4` |
| 611 | гардероб | `NL_simple_thermostat` | `NL_simple_thermostat_611` | `wb-mr6cu_224/K5` |
| 612 | спальня | `NL_climate_thermostat` | `NL_climate_thermostat_612` | `wb-mr6cu_224/K6` |
| 613 | ванная | `NL_simple_thermostat` | `NL_simple_thermostat_613` | `wb-mr6cu_219/K1` |

## Каналы, которые пишет скрипт

### Сервоприводы отопления

```text
wb-mr6cu_218/K1
wb-mr6cu_218/K2
wb-mr6cu_218/K3
wb-mr6cu_218/K4
wb-mr6cu_218/K5
wb-mr6cu_218/K6
wb-mr6cu_224/K1
wb-mr6cu_224/K2
wb-mr6cu_224/K3
wb-mr6cu_224/K4
wb-mr6cu_224/K5
wb-mr6cu_224/K6
wb-mr6cu_219/K1
```

### Кондиционеры ONOKOM

Гостиная:

```text
ONOKOM-AIR-GR-3-MB-B_10/Active mode
ONOKOM-AIR-GR-3-MB-B_10/Target temperature
ONOKOM-AIR-GR-3-MB-B_10/Horizontal vanes
ONOKOM-AIR-GR-3-MB-B_10/Smart fan speed
```

Спальня:

```text
ONOKOM-AIR-GR-3-MB-B_20/Active mode
ONOKOM-AIR-GR-3-MB-B_20/Target temperature
ONOKOM-AIR-GR-3-MB-B_20/Horizontal vanes
ONOKOM-AIR-GR-3-MB-B_20/Smart fan speed
```

`Horizontal vanes` пишется только если включён `ac_vanes_control`. `Smart fan speed` пишется только в ночном режиме при входе в охлаждение или при переходе день → ночь во время активного охлаждения.

## Каналы, которые читает скрипт

### Датчики зон

Скрипт читает датчики воздуха и пола, указанные в конфигурации зон:

```text
wb-msw-v4_67/Temperature
wb-msw-v4_203/Temperature
wb-msw-v4_142/Temperature
wb-msw-v4_140/Temperature
wb-m1w2_121/External Sensor 1
wb-m1w2_121/External Sensor 2
wb-m1w2_128/External Sensor 2
wb-m1w2_108/External Sensor 1
wb-m1w2_108/External Sensor 2
wb-m1w2_123_2/External Sensor 1
wb-m1w2_120/External Sensor 1
wb-m1w2_126/External Sensor 1
wb-m1w2_126/External Sensor 2
wb-m1w2_150/External Sensor 1
wb-m1w2_150/External Sensor 2
```

### Кондиционеры и ночной режим

```text
ONOKOM-AIR-GR-3-MB-B_10/AC connected
ONOKOM-AIR-GR-3-MB-B_10/Active mode
ONOKOM-AIR-GR-3-MB-B_10/Target temperature
ONOKOM-AIR-GR-3-MB-B_10/Horizontal vanes
ONOKOM-AIR-GR-3-MB-B_20/AC connected
ONOKOM-AIR-GR-3-MB-B_20/Active mode
ONOKOM-AIR-GR-3-MB-B_20/Target temperature
ONOKOM-AIR-GR-3-MB-B_20/Horizontal vanes
day_night/is_night
```

`Indoor air temperature` и `Thermostat state` оставлены в конфигурации ONOKOM как существующие каналы кондиционера, но исполнительные решения скрипта принимаются по датчикам зоны WB.

## Климатические зоны

### 605 — гостиная

```text
воздух:       wb-msw-v4_203/Temperature
пол:          wb-m1w2_123_2/External Sensor 1
сервопривод:  wb-mr6cu_218/K5
кондиционер: ONOKOM-AIR-GR-3-MB-B_10
```

### 612 — спальня

```text
воздух:       wb-msw-v4_140/Temperature
пол:          wb-m1w2_150/External Sensor 1
сервопривод:  wb-mr6cu_224/K6
кондиционер: ONOKOM-AIR-GR-3-MB-B_20
```

## Логика AUTO

В AUTO climate-зона выбирает между нагревом пола, поддержанием пола, ожиданием и охлаждением:

```text
воздух ниже target_temperature с гистерезисом → режим нагрева пола
воздух между уставками → поддержание пола по floor_min_temperature
воздух выше cooling_temperature с гистерезисом → охлаждение кондиционером
```

Отопление и охлаждение взаимоисключающие:

```text
если греем пол → кондиционер OFF
если охлаждаем → сервопривод пола закрыт
```

## Уставки нагрева и охлаждения

В climate-термостате есть две разные уставки:

```text
target_temperature  = Порог нагрева / основная пользовательская уставка
cooling_temperature = Порог охлаждения
```

Скрипт защищает объект от старых или случайно завышенных значений `cooling_temperature`. Если порог охлаждения оказался ниже безопасного зазора или выше `target_temperature + 2°C`, он приводится к понятному значению:

```text
cooling_temperature = target_temperature + 1°C
```

Это предотвращает ситуацию, когда пользователь видит `22°C`, а кондиционер получает `30–31°C` как `Target temperature`. Коррекция записывается обратно в control `cooling_temperature` и логируется как `НАСТРОЙКА=Порог охлаждения скорректирован`.

## Охлаждение и таймеры

Минимальное время работы охлаждения:

```javascript
var AC_MIN_ON_TIME_MS = 10 * 60 * 1000;
```

Минимальная пауза между повторными включениями:

```javascript
var AC_MIN_OFF_TIME_MS = 10 * 60 * 1000;
```

Ручная пауза после внешнего выключения кондиционера:

```javascript
var AC_MANUAL_OFF_PAUSE_MS = 2 * 60 * 60 * 1000;
```

Таймеры отображаются в виртуальном climate-термостате:

```text
ac_min_on_timer_sec       = Таймер работы охлаждения, сек
ac_min_off_timer_sec      = Пауза между включениями, сек
ac_manual_pause_timer_sec = Ручная пауза охлаждения, сек
ac_timer_status           = Статус таймеров охлаждения
```

Таймеры хранятся в памяти процесса `wb-rules`; после перезапуска `wb-rules` они не восстанавливаются из постоянного хранилища.

## Ручная пауза после внешнего выключения

Точно определить выключение с пульта нельзя, поэтому скрипт определяет событие как «кондиционер выключен извне» по условиям:

```text
WB ожидал, что кондиционер работает в COOL
WB сам не отправлял команду OFF
Active mode стал 0
зона всё ещё хочет охлаждение
```

После такого события скрипт ставит ручную паузу охлаждения на 2 часа и не включает кондиционер обратно до окончания таймера. Пауза снимается по истечении времени или при явном изменении `target_state` пользователем.

## Горизонтальные жалюзи

Controls:

```text
ac_vanes_control       = Контроль жалюзи
saved_horizontal_vanes = Запомненное положение жалюзи
```

По умолчанию `ac_vanes_control` выключен. Если контроль выключен, WB вообще не пишет в `Horizontal vanes` и не перетирает пользовательское положение жалюзи.

Если контроль включён:

```text
при первом старте охлаждения WB ставит Horizontal vanes в saved_horizontal_vanes
стартовое безопасное положение = 5
если пользователь изменил жалюзи на фиксированное положение 2...6, оно запоминается
следующий автоматический старт охлаждения использует запомненное значение
жалюзи не принуждаются каждую минуту
```

Значения `0` и `1` не используются как запомненное положение для автоматического старта:

```text
0 = остановить качание / не выбирать положение
1 = качание
2...6 = фиксированные положения жалюзи
```

## Ночной режим кондиционера

Источник признака ночи:

```text
day_night/is_night
```

Канал создаётся скриптом `objects/05_38_Plod_47/etc/wb-rules/290_day_night.js`.

Controls climate-термостата:

```text
ac_night_mode_enabled = Ночной режим кондиционера, по умолчанию true
ac_night_fan_speed    = Ночная скорость вентилятора, по умолчанию 1
ac_night_mode_status  = Статус ночного режима
```

Значения `Smart fan speed` ONOKOM:

```text
0 = Auto
1 = Quiet mode / тихий режим
2 = 1 скорость
3 = 2 скорость
4 = 3 скорость
5 = 4 скорость
6 = 5 скорость
7 = Turbo
```

Логика:

```text
если зона входит в охлаждение и сейчас ночь → Smart fan speed = ac_night_fan_speed
если охлаждение уже активно и наступила ночь → Smart fan speed = ac_night_fan_speed
если день → скорость вентилятора не трогается
если пользователь изменил скорость днём → WB её не перетирает
ночью WB может один раз вернуть тихий режим при входе в охлаждение или при переходе день → ночь
```

Если `day_night/is_night` недоступен, кондиционеры продолжают работать, но скорость вентилятора не управляется. В журнал пишется `ОШИБКА=Канал ночного режима недоступен` один раз, а `ac_night_mode_status` показывает причину.

## Логирование

Скрипт пишет события в системный журнал `wb-rules`.

Формат:

```text
[система][скрипт][контекст]; ТИП=событие; параметр=значение
```

Примеры:

```text
[отопление][600_thermostats][гостиная]; КОМАНДА=Включить охлаждение кондиционера; причина=авто: воздух выше порога охлаждения; канал=ONOKOM-AIR-GR-3-MB-B_10/Active mode; значение в канал=2
```

```text
[отопление][600_thermostats][спальня]; СОСТОЯНИЕ=Охлаждение поставлено на ручную паузу; причина=кондиционер выключен извне; таймер=7200
```

```text
[отопление][600_thermostats][спальня]; КОМАНДА=Установить тихую скорость кондиционера; причина=ночной режим охлаждения; канал=ONOKOM-AIR-GR-3-MB-B_20/Smart fan speed; значение в канал=1
```

Важно: `КОМАНДА` в журнале означает попытку записи в канал WB/MQTT. Это не физическое подтверждение, что сервопривод или кондиционер уже выполнил команду.

Штатная периодическая синхронизация раз в минуту не логируется как `WATCHDOG`; `WATCHDOG` зарезервирован для аварийной логики.

## Проверка после установки

Положить файл на контроллер:

```text
/etc/wb-rules/600_thermostats.js
```

Проверить синтаксис:

```bash
node --check /etc/wb-rules/600_thermostats.js
```

Перезапустить `wb-rules`:

```bash
systemctl restart wb-rules
```

Смотреть журнал:

```bash
journalctl -u wb-rules -f | grep "600_thermostats"
```

Проверить climate-зоны:

```text
NL_climate_thermostat_605
NL_climate_thermostat_612
```
