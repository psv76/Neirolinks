# 05 16 Исеть — runtime-аудит Wiren Board

**Дата:** 03.09.2026  
**Снимок runtime:** 03.09.2026 00:11–00:18 +05  
**Контроллер:** `wirenboard-AFMEUYOT`  
**Режим:** только чтение; на контроллере ничего не изменялось в ходе аудита  
**Назначение:** установить фактическое состояние Wiren Board и отделить его от GitHub/проектной документации до продолжения архитектурного проектирования.

---

## 1. Источники и доказательность

Использованы два фактически снятых архива контроллера:

- `iset_wb_runtime_audit_20260903_001106.tar.gz` — systemd, версии пакетов, журналы за 24 часа, текущие значения критичных каналов;
- `iset_wb_runtime_full_20260903_001839.tar.gz` — реальные файлы `/etc/wb-rules`, `/etc/wb-rules-modules`, `wb-mqtt-serial.conf`, `wb-webui.conf`, `wb-mqtt-db.conf`, SHA256 и поиск критичных ссылок.

Для сравнения фактически прочитана текущая ветка `main` GitHub `psv76/Neirolinks`, каталог `objects/05_16_Iset`.

Маркировка:

- **[Проверено]** — прямо подтверждено runtime-файлом, журналом или текущим GitHub;
- **[Предположение]** — наиболее вероятное объяснение, не доказанное runtime-evidence;
- **[Не могу проверить]** — данных снимка недостаточно.

---

# 2. Краткий результат

## [Проверено]

1. Runtime Wiren Board **существенно отличается** от GitHub как минимум по notification/diagnostic слоям, serial topology, MQTT history, WebUI и состоянию Vilpe.
2. При этом основные действующие отопительные скрипты `Boiler_room.js`, `DHW_priority_manager.js`, `Floor_mixing_control.js`, `Heating_pumps_manager.js` **текстуально совпадают с текущим GitHub** после нормализации переводов строк.
3. `Basement_radiator_thermostat.js` отличается от GitHub только подтверждённым изменением стартовой уставки: **26 °C runtime против 21 °C GitHub**.
4. На контроллере работают новые, отсутствующие в GitHub модули:
   - `Heating_watchdog.js`;
   - `Heating_notifications.js`;
   - `Floor_performance_monitor.js`;
   - `Email_service.js`;
   - `/etc/wb-rules-modules/WBHelpers.js`.
5. `Vilpe_control` на живом WB **не работает**: файл находится как `Vilpe_control_v3.js.disabled`. Поэтому вывод прежнего аудита о *текущем* конфликте writers `Vilpe_control ↔ HA` надо скорректировать: такой конфликт заложен в логике файла при его включении, но **сейчас WB этот скрипт не исполняет**.
6. Фактические writers внутри активных `/etc/wb-rules`:
   - K1 → `DHW_priority_manager.js`;
   - K2 → `Heating_pumps_manager.js`;
   - K3 → `Basement_radiator_thermostat.js`;
   - K4 → `Heating_pumps_manager.js`;
   - K5 → **writer не найден**;
   - K6 → **writer не найден**;
   - OT11 `Heating Setpoint` → `DHW_priority_manager.js`;
   - клапан ТП `wb-mao4_131/Channel 1` → `Floor_mixing_control.js`.
7. В момент снимка:
   - K1 = ON;
   - K2 = OFF;
   - K3 = OFF;
   - K4 = OFF;
   - K5 = ON;
   - K6 = ON;
   - OT11 Heating Setpoint = 76 °C;
   - OT11 Heating Temperature = 66 °C;
   - OT11 Invalid Connection = 0;
   - OT12 Heating Temperature = 28 °C;
   - OT12 Invalid Connection = 0;
   - OT12 Heating Setpoint = `NO DATA`.
8. K5 и K6 были **включены при отсутствии найденного локального wb-rules writer**. Источник их команд снимком не установлен.
9. Второй OpenTherm электрического котла ID12 реально подключён и отвечает, но ни один активный object script его не использует.
10. Email-уведомления **фактически работают**. В журнале есть подтверждённые успешные SMTP-сессии `sSMTP ... Sent mail`.
11. Старый стандартный `alarms.conf` на живом объекте пуст. Текущий notification path реализован отдельными JS-модулями через Email.
12. `wb-cloud-agent` реально работает в instance-units `wb-cloud-agent@wirenboard.cloud`, `...metrics@...`, `...frpc@...`.

---

# 3. Runtime платформы

## 3.1. Система

**[Проверено]**

```text
hostname: wirenboard-AFMEUYOT
OS: Debian GNU/Linux 11 (bullseye)
kernel: Linux 6.8.0-wb158
architecture: arm64
uptime на 03.09.2026 00:11: 31 день 15 часов
```

## 3.2. Ключевые версии

| Компонент | Runtime |
|---|---:|
| `wb-rules` | 2.40.0 |
| `wb-rules-system` | 1.13.5 |
| `wb-mqtt-serial` | 2.248.1-wb100 |
| `wb-mqtt-db` | 2.9.3 |
| `wb-mqtt-db-cli` | 1.4.8 |
| `wb-mqtt-w1` | 2.3.1 |
| `wb-cloud-agent` | 1.7.2 |
| Mosquitto | 2.0.20-1-wb102 |
| WB WebUI | 2.208.1 |

## 3.3. Сервисы

**[Проверено]** На момент снимка активны:

- `wb-rules.service`;
- `wb-mqtt-serial.service`;
- `wb-mqtt-db.service`;
- `wb-mqtt-w1.service`;
- `mosquitto.service`;
- `wb-cloud-agent@wirenboard.cloud.service`;
- `wb-cloud-agent-metrics@wirenboard.cloud.service`;
- `wb-cloud-agent-frpc@wirenboard.cloud.service`;
- стандартные WB backend/configuration services.

`wb-rules` работает с 02.09.2026 01:54:47 +05. После этого рестарта `all rule files are loaded`, синтаксических/загрузочных ошибок object scripts не обнаружено.

Перед рестартом при hot reload новых notification-файлов были временные ошибки `unexisting control heating_notifications/active_count`; после полного рестарта они исчезли.

---

# 4. Реальный состав `/etc/wb-rules`

## 4.1. Активные JS

**[Проверено]** Движок видит 12 `.js` файлов:

1. `Basement_radiator_thermostat.js`
2. `Boiler_room.js`
3. `DHW_priority_manager.js`
4. `Email_service.js`
5. `Floor_mixing_control.js`
6. `Floor_performance_monitor.js`
7. `Heating_notifications.js`
8. `Heating_pumps_manager.js`
9. `Heating_watchdog.js`
10. `Light_4.js`
11. `Master-Light.js`
12. `rules.js` — штатный пустой placeholder

Модуль:

- `/etc/wb-rules-modules/WBHelpers.js`.

## 4.2. Отключённые файлы

- `Vilpe_control_v3.js.disabled`;
- `299__input_detector.js.disabled`.

**[Проверено]** Эти файлы не являются активными object rules из-за расширения `.disabled`.

---

# 5. Runtime ↔ GitHub

Для основных текстовых файлов выполнено точное сравнение содержимого через контрольный hash текста после нормализации CRLF/LF.

| Файл | Runtime ↔ GitHub | Комментарий |
|---|---|---|
| `Boiler_room.js` | **идентичен** | Текущая проблемная anti-cycle/monitor логика есть и в GitHub |
| `DHW_priority_manager.js` | **идентичен** | K1 + OT11 writer |
| `Floor_mixing_control.js` | **идентичен** | Единственный writer клапана ТП |
| `Heating_pumps_manager.js` | **идентичен** | K2/K4 от NO-приводов |
| `Basement_radiator_thermostat.js` | **отличается** | Runtime default 26 °C; GitHub 21 °C; замена только этой строки даёт точное совпадение hash |
| `Light_4.js` | **идентичен** | |
| `Master-Light.js` | **идентичен** | |
| `Vilpe_control.js` | **не совпадает и runtime отключён** | В GitHub активный `Vilpe_control.js`; на WB более крупный/поздний `Vilpe_control_v3.js.disabled` |
| `Heating_watchdog.js` | **нет в GitHub** | Runtime-only |
| `Heating_notifications.js` | **нет в GitHub** | Runtime-only |
| `Floor_performance_monitor.js` | **нет в GitHub** | Runtime-only |
| `Email_service.js` | **нет в GitHub** | Runtime-only |
| `WBHelpers.js` | **нет в GitHub** | Runtime-only |
| `wb-mqtt-serial.conf` | **отличается** | См. раздел 6 |
| `wb-mqtt-db.conf` | **отличается** | Runtime содержит новую диагностическую группу |
| `wb-webui.conf` | **отличается** | Runtime актуализирован частично, но содержит stale `heating_ui_*` |
| `alarms.conf` | **принципиально отличается** | GitHub — Telegram alarms; runtime standard alarms пуст |

### Вывод

**[Проверено]** GitHub пригоден как источник основной отопительной логики, но **не является as-built snapshot контроллера**. Любое архитектурное решение обязано опираться на runtime либо после изменения синхронизировать repository.

---

# 6. Фактическая serial topology и drift GitHub

## 6.1. Критичные устройства

**[Проверено]** Runtime:

- RS-485-1: MR6CU37, Breezart115 и отопительные/датчиковые модули;
- `/dev/ttyMOD2`: WBE2-I-OPENTHERM ID12, `Электрический котёл`, `heating_options=1`;
- `/dev/ttyMOD3`: WBE2-I-OPENTHERM ID11, `Газовый котёл`, `boiler_mode=3`, `heating_options=0`;
- MR6CU37 имеет `outputs_restore_state=1`.

**[Не могу проверить]** Семантика `outputs_restore_state=1` для фактического поведения K1–K6 после blackout отдельно не испытывалась; из одного поля конфигурации вывод о безопасном состоянии делать нельзя.

## 6.2. Существенные отличия RS-485-2 от GitHub

GitHub содержит:

```text
MSW 107
MR6CU 56
MSW 49
Onokom 91, 92, 93, 94
```

Runtime вместо этого содержит:

```text
Onokom 6, 7, 8, 9
MSW 106
MSW 52
wb_mio 195
```

При этом основные модули `4/70/71/72`, `195:1`, `195:2`, `200`, `220`, `64`, `137`, `43`, `199` сохранены.

**[Проверено]** Таким образом, GitHub serial map явно устарел относительно контроллера.

В runtime WebUI уже используется `ONOKOM-AIR-HS-3-MB-B_8` и `wb-msw-v4_106`; GitHub WebUI этих новых ID не содержит.

---

# 7. Фактический ownership критичных каналов WB

## 7.1. K1…K6

| Канал | Runtime-роль | Найденный активный writer | Текущее значение 00:18 | Статус ownership |
|---|---|---|---:|---|
| `wb-mr6cu_37/K1` | насос БКН | `DHW_priority_manager.js` | 1 | **подтверждён** |
| `wb-mr6cu_37/K2` | насос ТП | `Heating_pumps_manager.js` | 0 | **подтверждён** |
| `wb-mr6cu_37/K3` | насос цоколя | `Basement_radiator_thermostat.js` | 0 | **подтверждён, временный** |
| `wb-mr6cu_37/K4` | насос жилой зоны | `Heating_pumps_manager.js` | 0 | **подтверждён** |
| `wb-mr6cu_37/K5` | рециркуляция ГВС | **не найден** | 1 | **критический пробел** |
| `wb-mr6cu_37/K6` | насос вентиляции / преднагрева ПВУ | **не найден** | 1 | **критический пробел** |

`Boiler_room.js` читает все K1…K6, но физически ими не управляет.

### K5

**[Проверено]** Ни один активный object script в `/etc/wb-rules` и `/etc/wb-rules-modules` не содержит writer K5. В момент двух последовательных снимков K5 = ON.

**[Не могу проверить]** Источник команды может быть HA, ручное управление, сохранённое состояние выхода или иной механизм вне исследованного object code.

### K6

**[Проверено]** Ни один активный object script в `/etc/wb-rules` и `/etc/wb-rules-modules` не содержит writer K6. K6 = ON в обоих снимках.

`Boiler_room.js` только отображает K6 как `vent`.

`Vilpe_control_v3.js.disabled` вообще не использует K6: он относится к вытяжке/заслонкам, а не является доказательством writer насоса преднагрева.

**[Не могу проверить]** Кто реально отдаёт команды K6. Это остаётся главным физическим ownership gap.

---

# 8. OpenTherm и два котла

## 8.1. Газовый котёл OT11

**[Проверено]**

- OpenTherm connection была валидна в момент снимка;
- `Heating Setpoint = 76 °C`;
- `Heating Temperature = 66 °C`;
- физический writer setpoint внутри активных object scripts только один: `DHW_priority_manager.js`.

Однако системно exclusive ownership не обеспечен: физический MQTT control остаётся writable другими клиентами/ручным интерфейсом при наличии прав.

## 8.2. Электрический котёл OT12

**[Проверено]**

- OT12 зарегистрирован и включён в `wb-mqtt-serial`;
- `Invalid Connection = 0`;
- `Heating Temperature = 28 °C` в момент снимка;
- `Heating Setpoint` по запросу snapshot вернул `NO DATA`;
- ни один активный object script OT12 не читает и не пишет.

### Вывод

Подключение электрического котла **реально**, но автоматическая архитектура резерва на WB **не реализована в доступном active ruleset**.

**[Не могу проверить]** Возможно ли управление электрическим котлом из HA и как устроен его контактор/interlock — без HA/runtime внешнего слоя данных нет.

---

# 9. Скрытая управляющая связь в `Boiler_room.js`

**[Проверено]** Runtime-файл идентичен GitHub и содержит:

```javascript
if (readNum("dhw_priority_mgr/normal_setpoint") !== minSp)
    dev["dhw_priority_mgr/normal_setpoint"] = minSp;
```

Следовательно, `Boiler_room.js` **не является чистым monitor-only модулем**.

Его anti-cycle параметры:

```text
minimum supply: 52 °C default
band: 7 K
minimum pause: 6 min
pause setpoint: 15 °C
```

`DHW_priority_manager.js` затем использует эту настройку как обычную OT-уставку/normal target. Это фактическая межмодульная управляющая цепочка:

```text
Boiler_room anti-cycle
       ↓ writes
DHW normal_setpoint
       ↓
DHW_priority_manager
       ↓ writes
OT11 Heating Setpoint
```

Это подтверждает архитектурную проблему, из-за которой был начат Heating Manager 2.0.

---

# 10. Насосы K2/K4 и зависимость от внешних зональных приводов

**[Проверено]** `Heating_pumps_manager.js` считает NO-приводы так:

```text
0 / false = открыт = есть heat demand
1 / true  = закрыт
```

K2 определяется по `K12…K16`, K4 — по `K1…K11` модуля `wb-mio-gpio_195:2`.

Критичная особенность runtime-кода:

```javascript
function hpmReadBool(path) {
  try { return hpmToBool(dev[path]); }
  catch (e) { return false; }
}
```

а `undefined/null` также преобразуются в `false`.

Следовательно, **потеря/отсутствие значения привода семантически не отличена от команды «контур открыт»**. Такой input способен создать heat demand и включить K2/K4.

Это не означает, что именно так сейчас происходит, но fail-safe contract входов здесь архитектурно неоднозначен.

---

# 11. Тёплый пол: управление и operational evidence

## 11.1. Ownership

**[Проверено]** Физический writer:

- `wb-mao4_131/Channel 1 Switch`;
- `wb-mao4_131/Channel 1 Dimming Level`;

только `Floor_mixing_control.js` среди active object scripts.

`Boiler_room.js`, watchdog и performance monitor эти каналы читают.

`floor_mixing_ctrl/valve_position` в самом virtual device объявлен `readonly: true`; это диагностическая копия команды, а не физическая обратная связь положения.

## 11.2. Повторяющееся отсутствие технологической реакции

За 24 часа watchdog зафиксировал несколько эпизодов:

- 02.09 01:13 — до финального рестарта diagnostics;
- 09:04;
- 09:31;
- 11:43;
- 21:00;
- 23:04.

Типовой факт:

```text
K2 command = ON
valve command = 45…80 %
source sufficiently hot
floor supply far below 32 °C setpoint
rise за 10 минут < 0.5 K
```

После части эпизодов технологическая реакция позднее восстанавливалась.

**[Проверено]** Это доказывает повторяемый *симптом отсутствия/резкого ухудшения передачи тепла при наличии управляющих команд*.

**[Не могу проверить]** Это не доказывает конкретную физическую причину: насос, питание насоса, воздух/гидравлика, трёхходовой клапан, привод или иной дефект.

---

# 12. 1-Wire: подтверждённая системная нестабильность

За период после запуска diagnostics зарегистрировано три массовых сбоя всех 6 используемых температурных датчиков:

| Начало | Alarm | Восстановление |
|---|---|---|
| 02:04:39 | 02:05:09 | 02:12:19 |
| 03:12:39 | 03:13:09 | 03:34:29 |
| 06:58:19 | 06:58:49 | 07:02:09 |

Каждый раз одновременно недоступны:

- бойлер;
- цоколь;
- улица;
- подача ТП;
- жилая зона;
- подача от котла.

**[Проверено]** Это bus-wide failure, а не единичный датчик.

---

# 13. Уведомления — фактическое состояние

## 13.1. Старый `alarms.conf`

**[Проверено]** Runtime `/etc/wb-rules/alarms.conf`:

```json
{
  "alarms": [],
  "deviceName": "alarms",
  "deviceTitle": "Alarms",
  "recipients": []
}
```

То есть GitHub Telegram configuration сейчас **не используется как runtime source уведомлений**.

## 13.2. Email

Активны:

```text
WBHelpers.js
Email_service.js
Heating_notifications.js
Heating_watchdog.js
```

`Heating_notifications.js` маршрутизирует 9 alarm states:

- boiler fault;
- OT invalid connection;
- low pressure;
- overheat;
- no heat pickup;
- poor circulation;
- DHW poor heating;
- DHW manager alarm;
- floor controller alarm.

`Heating_watchdog.js` **сам напрямую отправляет email** для:

- отсутствия технологической реакции ТП;
- массовой потери 1-Wire;
- их восстановлений.

`Floor_performance_monitor.js` email не отправляет.

### Архитектурный вывод

**[Проверено]** Notification responsibility уже разделена между двумя паттернами:

```text
canonical alarm flag → Heating_notifications → Email
```

и

```text
watchdog event → direct WBHelpers.sendAlert/sendRestore
```

То есть единого объектового event/notification contract пока нет.

## 13.3. Доставка

В журнале подтверждены SMTP-ответы `Sent mail`. За исследованный период ошибок SMTP-send по grep не найдено.

Пример фактически подтверждённой отправки:

```text
02.09 23:53:59
[05 16 Исеть] АВАРИЯ — Бойлер не греется
sSMTP: Sent mail ... 221 2.0.0
```

**[Проверено]** Сейчас настроен один сервисный email-получатель. Адрес заказчика в runtime helper не добавлен.

---

# 14. Журналирование и история

## 14.1. `wb-rules` journal

Старые core scripts почти не создают decision trace. Новые diagnostics используют принятый формат сообщений и уже позволяют видеть:

```text
command/condition → start watch → alarm → recovery
```

Это существенное улучшение runtime по сравнению с GitHub snapshot.

## 14.2. `wb-mqtt-db`

Runtime содержит новую группу `Отопление - диагностика`, отсутствующую в GitHub.

В неё включены:

- DHW pause/mode/settings;
- anti-cycle state;
- K10…K16 приводов;
- watchdog states/events;
- email notification state;
- floor performance states/events.

Также сохранена физическая группа `Отопление` с K1…K6, OT11, температурами и подмесом.

**[Проверено]** `wb-mqtt-db` активен и пишет данные; journal показывает штатное достижение channel row limits и удаление/ротацию старых точек.

## 14.3. Cloud

**[Проверено]** Cloud Agent и metrics collector активны. Поэтому прежнее «cloud-agent не подтверждён» надо считать исправленным.

**[Не могу проверить]** Сам snapshot не содержит серверную конфигурацию Timescale/Grafana и не доказывает конкретный retention в облаке.

---

# 15. Вентиляция: важная коррекция предыдущего системного аудита

## 15.1. Vilpe

**[Проверено]** На live WB `Vilpe_control_v3.js.disabled`.

Следовательно:

- WB сейчас **не исполняет** эту логику;
- она не является текущим writer `wb-mao4_220/Channel 2`;
- она не является текущим writer пяти drying damper channels.

GitHub, напротив, содержит активный `Vilpe_control.js`, поэтому repository описывает не фактический runtime.

### Коррекция

Предыдущий системный аудит правильно обнаружил потенциальное пересечение HA ownership и Vilpe writes в коде, но **неверно трактовать его как действующий runtime conflict на 03.09.2026**. Пока файл disabled, conflict не активен.

## 15.2. Breezart

**[Проверено]** Breezart ID115 активен в `wb-mqtt-serial`; за сутки зарегистрирован единичный Modbus timeout, после которого service продолжил работу.

В WebUI доступны прямые controls производительности Breezart и приточных заслонок.

**[Не могу проверить]** Runtime WB не содержит object rule, который связывает Breezart heat demand с K6.

---

# 16. WebUI как отдельная поверхность управления

**[Проверено]** Dashboard `Насосы в котельной (факт)` содержит физические writable `switch` для K1…K6.

Это означает, что правило «один writer» сейчас является соглашением между скриптами, но не технически закрытым ownership: оператор с правом записи в WB WebUI может вручную изменить физический output.

WebUI также содержит:

- прямые controls приточных/вытяжных заслонок;
- Breezart setpoint;
- настройки DHW manager;
- настройки floor controller.

При этом сохраняются stale widgets `heating_ui_floor/*` и `heating_ui_alarms/*`, для которых активного provider-script в runtime не найдено.

---

# 17. MQTT и внешний writer / Home Assistant

За 24 часа Mosquitto journal содержит:

- WB internal clients;
- cloud metrics;
- подключения WB WebUI через Wiren Board Cloud/удалённые IP;
- временные localhost clients от диагностических команд.

**[Не могу проверить]** В этом 24-часовом фрагменте не зафиксирован новый connect/reconnect с очевидным именем Home Assistant.

Это **не доказывает отсутствие HA**:

- MQTT connection HA могла быть установлена раньше начала выбранного окна;
- интеграция может использовать иной протокол/посредник;
- client ID может не содержать `homeassistant`.

Поэтому owner внешних writes по одному broker journal определить нельзя.

---

# 18. Коррекции к `05_16_ISET_SYSTEM_ARCHITECTURE_AUDIT.md`

После runtime-аудита предыдущий документ требуется читать с поправками:

| Ранее | Runtime-коррекция |
|---|---|
| Email не подтверждён | **Email подтверждён и работает** |
| Notification runtime описывался через GitHub Telegram `alarms.conf` | **Runtime standard alarms пуст; работает отдельный Email stack** |
| `Vilpe_control.js` считается действующим | **Runtime Vilpe disabled** |
| HA ↔ Vilpe writer conflict описан как текущий | **Сейчас потенциальный, но не активный из-за disabled Vilpe** |
| GitHub как основной снимок scripts/config | **Core heating scripts почти совпадают, но configs/diagnostics заметно ушли вперёд** |
| Cloud/Grafana transport не подтверждён | **wb-cloud-agent + metrics подтверждены; server-side Grafana всё ещё отдельно** |
| K6 writer неизвестен | **Подтверждено runtime-поиском: неизвестен и при этом K6=ON** |
| Electric boiler физически существует | **Дополнительно подтверждена живая OT12 связь: Invalid Connection=0, Heating Temperature=28 °C** |

---

# 19. Что сейчас нельзя считать установленным

## [Не могу проверить]

1. Кто посылает команды K5.
2. Кто посылает команды K6.
3. Фактическая runtime-логика Home Assistant.
4. Работает ли K6 по сигналу Breezart, HA, ручному состоянию или другому алгоритму.
5. Алгоритм аварийного ввода электрического котла.
6. Кто пишет OT12 setpoint, если такой writer вообще существует.
7. Кто сейчас пишет воздушные заслонки при disabled Vilpe.
8. Реальные retained/availability/fail-safe semantics HA-команд.
9. Физическое вращение насосов — Kx=1 доказывает только состояние/команду выходного канала, не движение воды.
10. Фактическое положение 0–10 В клапана — `%` является командой, не feedback.

---

# 20. Приоритеты следующего шага

## P0 — установить K5/K6 и внешние writers

До новой архитектуры Heating Manager нужно пассивно получить:

- историю K5/K6;
- command topics `/on`;
- текущие MQTT TCP clients;
- correlation K6 ↔ Breezart state;
- полный system-wide search K5/K6 вне object `/etc/wb-rules`.

## P0 — снять live state контрактов отопления

Нужен один snapshot MQTT:

- `dhw_priority_mgr/*`;
- `boiler_room_boiler/ch_pause_*`;
- `heating_pumps_mgr/*`;
- `floor_mixing_ctrl/*`;
- K1…K6;
- K1…K16 zonal actuator outputs;
- OT11/OT12;
- Breezart key states.

Это позволит зафиксировать не только код, но и сохранённые operator settings.

## P1 — синхронизация repository

До серьёзного refactor необходимо решить, что является canonical source:

```text
live WB → verified export → GitHub
```

Сейчас GitHub нельзя использовать для deploy «как есть» без риска отката runtime diagnostics, serial map и notification stack.

## P1 — Home Assistant

Доступ к HA желателен, но **не является блокером для дальнейшего пассивного исследования WB**. Если доступ не будет получен, границу HA всё равно можно сузить по внешним writes и MQTT/network evidence со стороны WB.

---

# 21. Решение по Heating Manager 2.0 после этого снимка

## [Проверено]

К production-разработке Heating Manager 2.0 переходить рано.

Причина уже не только в неизвестной логике setpoint. Runtime подтвердил более широкий набор архитектурных зависимостей:

```text
HA/внешние zones
    ↓
NO actuators
    ↓
WB K2/K4 pump manager

DHW manager ← Boiler_room anti-cycle
    ↓
OT11 setpoint

Breezart / внешний слой
    ↓ ?
K6

второй котёл OT12
    ↓ ?
резервная теплогенерация
```

Перед проектированием центрального thermal coordinator необходимо как минимум закрыть два вопроса:

1. **K6 / вентиляционный преднагрев**;
2. **электрический котёл OT12 / резервный источник**.

Иначе новая «центральная» архитектура снова будет описывать только часть реальной системы.

---

# 22. Итог

## [Проверено]

Runtime-аудит подтвердил, что текущая WB-система не является хаотичным набором неизвестных файлов: основные writers K1–K4 и клапана ТП теперь установлены точно, core отопительные скрипты сверены с GitHub, notification stack и реальные diagnostics найдены.

Одновременно обнаружены четыре ключевых as-built факта, которых не было в первом Heating Manager design:

1. **K6 включён, но его runtime writer неизвестен.**
2. **Электрический котёл OT12 жив и подключён, но не входит в active WB automation.**
3. **HA-зависимые зональные outputs являются входами WB pump manager, а missing value семантически равен «открыто».**
4. **Runtime repository drift существенен: configs и infrastructure нельзя восстанавливать из GitHub без предварительной синхронизации.**

Следующая работа должна быть не новой логикой котла, а **закрытием границы внешнего управления и источников тепла на фактическом объекте**.
