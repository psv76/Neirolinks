# Saturn Heat1 + DHW2 (Wiren Board)

Шаблон предназначен для диспетчеризации Saturn-PLC через WB в архитектуре:

Saturn (Modbus RTU) → RAW `wb-mqtt-serial` → `wb-rules` → виртуальные устройства `Отопление` и `ГВС`.

## Файлы

- `Saturn_Heat1_DHW2_RAW.json` — RAW шаблон устройства Saturn.
- `620_saturn_heat1_dhw2.js` — скрипт `wb-rules` для разбиения на отопление/ГВС.
- `SATURN_Heat1_DHW2_Integration.md` — интеграционная памятка.

## Подключение одного Saturn

1. Добавить устройство по шаблону `Saturn_Heat1_DHW2_RAW.json` в `wb-mqtt-serial.conf`.
2. Назначить `device id` RAW, например: `saturn_lower_raw`.
3. Задать Modbus-адрес Saturn.
4. Положить `620_saturn_heat1_dhw2.js` в `/etc/wb-rules/`.
5. Проверить, что появились устройства:
   - `saturn_lower_heating`
   - `saturn_lower_dhw`

## Подключение двух Saturn

Создать два RAW устройства с разными `slave_id` и `id`:

- `saturn_lower_raw` (нижние этажи)
- `saturn_upper_raw` (верхние этажи)

Скрипт уже поддерживает оба устройства через массив `SATURN_CONTROLLERS`.

## Важно

Точные адреса сервисных регистров `S1_ID`, `S2_ID`, `V_battery` нужно подтвердить по реальной карте Modbus на объекте перед пуском.
