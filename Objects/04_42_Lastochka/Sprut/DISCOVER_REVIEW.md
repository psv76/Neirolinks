# DISCOVER 18.10.2026: проверенные факты

Источник: `sprut_discover_20261018_104429.json`; SHA-256: `d8f741e25721e09f1f0e06851ca1811b54f438fa61533f6a0090e7ce1ad040b0`.
Весь JSON разобран: 111 Accessory, 356 Service, 10 комнат; serial заполнены и уникальны.
Прошивка из FirmwareRevision: `3.0.0b_20131/8621`. Yandex: unavailable.

## Связанные устройства

| aId | serial | modelId | Комната | online |
|---|---|---|---|---|
| 88 | `wb-mr6cu_196/K5` | `MR6CU` | Котельная | True |
| 113 | `wb-mai2-mini_46/Current input 2 (mA)` | `WB-MAI2-mini` | Новая комната | True |
| 179 | `wb:lastochka_pressure_makeup` | `` | Котельная | False |

## Сервисы и несистемные значения

| aId / sId / cId | Сервис | Характеристика | Значение снимка | write | statusVisible |
|---|---|---|---|---|---|
| 88/13/15 | Switch: Клапан подкачки | On | `{"boolValue": false}` | True | True |
| 113/13/15 | C_AmpereMeter: Амперметр | C_Ampere | `{"doubleValue": 0}` | False | True |
| 179/13/15 | ContactSensor: Аварийная блокировка | ContactSensorState | `{"intValue": 0}` | False | True |
| 179/16/18 | Switch: Авторежим | On | `{"boolValue": false}` | True | True |
| 179/19/21 | C_Option: Причина запрета подпитки | C_String | `{"stringValue": ""}` | True | False |
| 179/22/24 | C_Option: Ток датчика 414 мА | C_Double | `{"doubleValue": 6.704999923706055}` | True | False |
| 179/25/27 | ContactSensor: Цикл подпитки | ContactSensorState | `{"intValue": 0}` | False | True |
| 179/28/30 | C_Option: Циклов за 1 час | C_Double | `{"doubleValue": 3}` | True | False |
| 179/31/33 | C_Option: Циклов за 24 часа | C_Double | `{"doubleValue": 3}` | True | False |
| 179/34/36 | Switch: Разрешить подпитку | On | `{"boolValue": false}` | True | True |
| 179/37/39 | C_Option: Причина аварии | C_String | `{"stringValue": ""}` | True | False |
| 179/40/42 | C_Option: Последнее событие | C_String | `{"stringValue": ""}` | True | False |
| 179/43/45 | ContactSensor: Низкое давление | ContactSensorState | `{"intValue": 0}` | False | True |
| 179/46/48 | Switch: Остановить и заблокировать | On | `{"boolValue": false}` | True | True |
| 179/49/51 | C_Option: Поправка датчика 414 бар | C_Double | `{"doubleValue": -0.20000000298023224}` | True | False |
| 179/52/54 | C_Option: Давление котла с поправкой бар | C_Double | `{"doubleValue": 0.8140000104904175}` | True | False |
| 179/55/57 | C_Option: Импульсов в цикле | C_Double | `{"doubleValue": 0}` | True | False |
| 179/58/60 | C_Option: Давление датчика 414 бар | C_Double | `{"doubleValue": 1.0140000581741333}` | True | False |
| 179/61/63 | ContactSensor: Команда клапану ON | ContactSensorState | `{"intValue": 0}` | False | True |
| 179/64/66 | Switch: Сброс аварий и блокировки | On | `{"boolValue": false}` | True | True |
| 179/67/69 | ContactSensor: Ошибка датчика | ContactSensorState | `{"intValue": 0}` | False | True |

Полный список характеристик связанных устройств, включая AccessoryInformation, — в DISCOVER_RELEVANT_2026-10-18.json.

## Выводы и границы доказанности

- Найден ровно один Accessory с явной идентичностью lastochka_pressure_makeup: aId 179, 19 пользовательских сервисов + AccessoryInformation. Пользователь подтвердил автоматическое создание встроенной интеграцией Wiren Board. Это не объектовый MQTT-template.
- Только aId 179 имеет online=false среди всех 111 Accessory. Это подтверждает флаг недоступности Sprut, но не причину и не отсутствие данных на брокере.
- В снимке сохранены pressure_bar ≈0.814 бар, raw_pressure_bar ≈1.014 бар, offset ≈−0.2 бар и ток ≈6.705 мА. Поправка арифметически согласуется. Времени последнего MQTT обновления нет: значения нельзя назвать актуальными live-показаниями.
- Оба разрешения false; alarm/sensor_alarm/low_pressure_alarm/cycle_active/relay_command_on = 0; fault/block_reason/last_event пусты. В каноническом скрипте при отключении ожидается block_reason «Отключено в интерфейсе». Несогласованность допускает старый кэш, неполное сопоставление или старую схему, но не доказывает ни одну причину.
- state_text, next_action, open_left_s, pause_left_s, restart_left_s, low_confirm_left_s, start_threshold_bar, target_threshold_bar в устройстве не представлены. Поэтому текущее состояние нельзя подменить пустым last_event.
- C_Double давления, тока, счётчиков и C_String текстов имеют write=true, хотя эти controls в №414 readonly. DISCOVER показывает разрешение UI, а не доказательство успешной записи WB.
- reset_alarm и manual_close представлены Switch/On, а не подтверждёнными однократными командами. Их topicSet, retain, auto-off и поведение при reconnect отсутствуют в экспорте.
- Самого физического входа 1 (input_1_value / input_1_current) по явной идентичности в DISCOVER нет. Найден только второй вход модуля: aId 113, Current input 2 (mA), C_Ampere=0 A. Это НЕ датчик давления №414. Скрытые связи виртуальных Accessory по этому экспорту восстановить нельзя.
- aId 88 / wb-mr6cu_196/K5: онлайн, Switch/On=false, write=true, visible=true в «Котельной». Уже существует интерфейс прямой команды клапану. Новый шаблон его не создаёт, но также не отзывает старое разрешение. Скрытие плитки не является запретом записи.

Причина «Нет ответа» не установлена. Проверить привязку C_Online/доступности именно native-интеграции, метаданные virtual device и журнал контроллера. Не выставлять принудительно online=true, не публиковать фиктивный availability и не менять MQTT настройки на основании одного флага.

## Канонический №414

Код прочитан целиком; алгоритм не изменён. pressure_bar уже содержит raw/1000 + offset. В Sprut повторный пересчёт не нужен. Для работы одновременно нужны enabled и auto_mode. Пользователь управляет только enabled; auto_mode оставляется инженерным разрешением WB и показывается read-only.

reset_alarm очищает latchedFault, историю частоты, счётчик импульсов и задержки ДО tick(). Это не «отклонение самого сброса при любой опасности»: после очистки tick заново блокирует/оценивает управление. При нормальных данных, обоих разрешениях и низком давлении возможно немедленное начало цикла. Нельзя обещать, что кнопка только гасит индикатор или сохраняет лимиты. В сценарии для заказчика нужно явное подтверждение полного сброса.

## Подход Иволги

Использованы структура modelIds/services/link, явное write=false и C_Option/C_Double из `Objects/05_31_Ivolga_13/Sprut/Templates/05_31_Ivolga_Kotel_Gas_Boiler_ReadOnly.json`; отображение через visible/status — из YAML v7. Идентичности Иволги не перенесены. Configurator не создаёт Accessory, не меняет MQTT связи или write-права и не реализует кнопку. Общий код Configurator не изменяется.
