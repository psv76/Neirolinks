# MQTT и identity contracts

## 1. Зачем нужен project-owned alias

Нельзя строить внешнюю интеграцию на случайных аппаратных именах вида:

```text
wb-msw-v4_<modbus-id>
wb-m1w2_<modbus-id>
wb-mr6c_<modbus-id>
```

Аппаратный адрес может измениться при замене, перенумерации или восстановлении конфигурации.

Нужна цепочка:

```text
Project ID
→ project MQTT alias
→ WB controls
→ Sprut template recognition
→ Sprut SERIAL
→ Configurator matching
```

## 2. Project ID

Для проектных сенсорных устройств используется позиционный ID семейства:

```text
9xx.yy
```

Он описывает проектную позицию, а не текущий Modbus address.

## 3. WB-MSW

Формат MQTT-имени:

```text
9xx.yy_MSW_<PROFILE>
```

Профили:

| PROFILE | Temperature | Humidity | Motion | CO2 |
|---|---:|---:|---:|---:|
| `TH` | да | да | нет | нет |
| `THM` | да | да | да | нет |
| `M` | нет | нет | да | нет |
| `CO` | да | да | нет | да |
| `COM` | да | да | да | да |

Принято:

```text
CO  = Temperature + Humidity + CO2
COM = Temperature + Humidity + CO2 + Motion
```

Отдельный профиль только CO2 не используется.

Типовые WB controls:

```text
Temperature
Humidity
Motion
CO2
```

## 4. WB-M1W2

Формат:

```text
9xx.yy_M1W2_<W1>_<W2>
```

Где:

```text
W1 / W2 ∈ TEMP | LEAK | GERCON | NONE
```

Связь ролей:

| Роль | WB control | Sprut Service |
|---|---|---|
| W1 `TEMP` | `External Sensor 1` | `TemperatureSensor` |
| W2 `TEMP` | `External Sensor 2` | `TemperatureSensor` |
| W1 `LEAK` | `Input 1` | `LeakSensor` |
| W2 `LEAK` | `Input 2` | `LeakSensor` |
| W1 `GERCON` | `Input 1` | `ContactSensor` |
| W2 `GERCON` | `Input 2` | `ContactSensor` |
| `NONE` | — | ничего |

Один физический M1W2 может давать несколько независимых логических Accessory.

SERIAL логического Accessory:

```text
<device-alias>/<control>
```

Рекомендуемая template-архитектура — не отдельный JSON на каждую комбинацию W1/W2, а role templates:

```text
W1_TEMP
W1_LEAK
W1_GERCON
W2_TEMP
W2_LEAK
W2_GERCON
```

## 5. Relay channels

Стабильная identity relay Accessory:

```text
<stable-relay-device-alias>/<control>
```

Например структурно:

```text
<device-alias>/K4
```

Функцию нагрузки нельзя кодировать в SERIAL. Переименование `Свет`, `Вентилятор` и т. п. не должно менять identity.

Нельзя автоматически трактовать все `K*` как `Lightbulb`: физически такой канал может управлять светом, вентилятором, насосом, сервоприводом, клапаном или технологическим контактором.

Тип пользовательского Sprut Service должен определяться Project-owned назначением канала или явным template whitelist.

## 6. Virtual thermostats

Технические имена:

```text
NL_simple_thermostat_<ZONE>
NL_combo_thermostat_<ZONE>
NL_climate_thermostat_<ZONE>
```

Текущий template contract ожидает трёхзначный номер зоны:

```text
NL_simple_thermostat_[0-9]{3}
NL_combo_thermostat_[0-9]{3}
NL_climate_thermostat_[0-9]{3}
```

## 7. SERIAL forms, поддержанные baseline

```text
MSW physical Accessory:
9xx.yy_MSW_<PROFILE>

M1W2 logical Accessory:
9xx.yy_M1W2_<W1>_<W2>/<control>

Relay logical Accessory:
<device-alias>/<control>

Virtual thermostat:
NL_<type>_thermostat_<ZONE>
```

## 8. Запрещённые постоянные зависимости

Не использовать как business identity:

```text
Sprut accessoryId
Sprut serviceId
Sprut roomId
Modbus address
пользовательское имя
```
