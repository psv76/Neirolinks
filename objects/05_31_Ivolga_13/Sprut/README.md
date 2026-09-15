# Sprut — 05 31 Иволга 13

Объектовая папка Sprut.hub для **05 31 Иволга 13**.

Здесь хранятся:

- актуальный desired-state YAML объекта;
- объектовые кастомные шаблоны Sprut;
- объектовые решения по presentation, комнатам и Alice/Yandex bridge.

Общий механизм Sprut Configurator хранится отдельно в корне репозитория: `SprutConfigurator/`.

## Актуальный план Котельной

Текущий последний инкремент для инженерного хаба `Котельная`:

```text
05_31_Ivolga_sprut_kotel_v7_boiler_pressure.yaml
```

Он фиксирует финальное presentation газового котла после live DISCOVER **2026-09-15 11:28:26** (`Ivolga_kotel_sprut_14.json`):

- Accessory `Газовый котёл`, serial `wbe2-i-opentherm_11/Heating Temperature`, переносится в комнату `Котёл`;
- основной сервис `Thermostat` остаётся видимым;
- физическое давление отопления берётся с `905.3/input_1_value` и публикуется вторым сервисом `C_Option` / `C_Double` **внутри того же Accessory котла**;
- единица давления — `Бар`;
- сервис `Давление` скрыт с рабочего стола (`visible=false`), но остаётся доступным внутри карточки `Газовый котёл`;
- `Thermostat` и `Давление` исключаются из Alice/Yandex bridge.

Ключевое решение по давлению: для этого конкретного котла **не используется OpenTherm Water Pressure** — реальное давление приходит с отдельного аналогового датчика через `905.3/input_1_value`. Проверено на live Sprut: cross-device `topicGet` из boiler-template работает и даёт актуальное значение, например `1.4 Бар`.

Отдельный template `05_31_Ivolga_Kotel_Heating_Pressure.json` больше не используется и удалён, чтобы Sprut не создавал второй самостоятельный Accessory давления. Старый `05_31_Ivolga_sprut_kotel_v6_pressure_hidden.yaml` также удалён как устаревший.

После перехода на финальную схему старый live Accessory давления с serial `905.3/input_1_value`, оставшийся от экспериментов, нужно удалить вручную один раз; после удаления отдельного pressure-template он больше не создаётся.

Другие подтверждённые решения хаба Котельной:

- `A06/K1` — `Навес`; `A06/K2..K6` — наружное освещение; виртуальный Accessory `661` — мастер `Улица`;
- `A07` — `Ввод воды`; LeakSensor'ы собраны в комнате `Вода`;
- `A03/K3` и `A03/K5` используют общий read-only template `05_31_Ivolga_Kotel_Heating_Pump_Only.json`;
- температуры подачи радиаторных контуров представлены отдельными виртуальными TemperatureSensor `682` и `683`;
- насосы, подмесы, технические температуры и давление не выдаются в Alice; наружное освещение и мастер `661` — выдаются.

## Актуальный план Дома

Канонический рабочий файл:

```text
05_31_Ivolga_sprut_dom_v3.yaml
```

Формат:

```text
format_version: 2
```

План предназначен для Sprut Configurator v0.3.0 и новее с поддержкой:

- `Service.visible`;
- `Characteristic.statusVisible`;
- Alice/Yandex bridge policy.

Последний live DISCOVER, использованный при сверке: **2026-09-11 23:34:34**.

На live Sprut Дома подтверждены 18 актуальных зональных термостатов:

```text
005 006 007 008 009 010
601 602 603
606 607 608 609 610 611 612 613 614
```

Старые `NL_combo_*`, а также `011`, `604`, `615`, `620`, `621` в актуальной схеме не используются.

## Presentation жилых комнат

Базовое правило:

```text
Воздух:
- Thermostat visible = true
- CurrentHeatingCoolingState statusVisible = true
- CurrentTemperature statusVisible = true
- Alice = true

Пол:
- Thermostat visible = true
- CurrentHeatingCoolingState statusVisible = false
- CurrentTemperature statusVisible = false
- Alice = false

Humidity:
- service visible = false
- CurrentRelativeHumidity обычно statusVisible = true
- Alice = false
```

Физические TemperatureSensor, которые дублируют температуру уже представленного термостата, скрываются.

Объектовое исключение: для кухни в комнате `Гостиная` температура и влажность `903.01_MSW_TH` скрыты и из плиток, и из status room по пользовательскому решению.

## Подтверждённые объектовые решения

- Все кухонные сущности остаются в комнате Sprut `Гостиная`.
- `A12/K2` «Свет коридор» находится в `Гостиная`.
- `A12/K3` «Бра коридор» после проверки на объекте подтверждён как `Гостиная`.
- Для `903.03_MSW_TH` сервисы названы `Температура кладовка` и `Влажность кладовка`.
- `NL_simple_thermostat_611` называется `Пол гостиная`.
- `NL_simple_thermostat_612` называется `Пол кухня`.

### Вентилятор постирочной

Физический канал:

```text
A12/K6
```

через релейный MQTT-template определяется Sprut как `Lightbulb`. Эта физическая плитка намеренно скрыта и исключена из Alice.

Для пользовательского интерфейса вручную создан виртуальный аксессуар Sprut:

```text
serial: 503
name: Вентилятор
room: Постирочная
service: FanBasic
```

Виртуальный `FanBasic` связан с `A12/K6`, видим пользователю и включён в Alice.

Важно: Sprut Configurator **не создаёт** виртуальный Accessory `503`; он может только привести presentation уже существующего Accessory к YAML. Поэтому при восстановлении Sprut с нуля виртуальный вентилятор сначала создаётся вручную в Sprut, затем применяется YAML.

## Проверенный цикл применения

10.09.2026 первая настройка Дома через v0.3.0 завершилась:

```text
APPLY 312/312
VERIFY PASSED
PASSED=61
FAILED=0
```

После этого вручную были уточнены помещение `Бра коридор`, подписи кладовки и представление вентилятора. Текущий `05_31_Ivolga_sprut_dom_v3.yaml` фиксирует уже эти решения и содержит 62 цели, включая существующий виртуальный `503`.

Перед очередным APPLY всегда выполнять:

```text
DISCOVER
→ загрузить YAML
→ DRY RUN
→ проверить diff и errors=0
→ APPLY
→ VERIFY
```

## Templates

Объектовый набор хранится в:

```text
Templates/
```

Типовой thermostat-template также остаётся в общей библиотеке репозитория:

```text
Templates/Sprut/Heating/NL_simple_thermostat.json
```

Копия, необходимая для восстановления именно этого объекта, сохранена и в объектовой папке `Sprut/Templates/`.

Старый object snapshot `Doc/SprutConfigurator/v0.2.2` удалён из рабочей структуры, чтобы его `format_version: 1` и старая combo-схема не воспринимались как актуальный desired state. История файла остаётся в Git, а общий frozen baseline v0.2.2 — в `SprutConfigurator/reference/v0.2.2/`.

## Источники истины

Для физики и зонального отопления:

```text
../README.md
../HEATING_CHANNEL_MAP.md
../THERMOSTAT_MAP.md
../Wirenboard/wb-rules/620_thermostats.js
```

Для фактического состояния Sprut при любых сомнениях использовать свежий DISCOVER, а не старый YAML или архивный snapshot.
