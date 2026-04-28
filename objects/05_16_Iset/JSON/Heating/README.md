# 05_16_Iset / Heating

## Состав папки

```
objects/05_16_Iset/JSON/Heating/
  Boiler_room.js
  DHW_priority_manager.js
  Floor_mixing_control.js
  Heating_pumps_manager.js
  Basement_radiator_thermostat.js
  README.md
```

## Назначение файлов

- **Boiler_room.js**  
  Мониторинг и диагностика котельной: состояния, температуры, OpenTherm, диагностические флаги.

- **DHW_priority_manager.js**  
  Логика приоритета ГВС. Управляет только:
  - насосом бойлера `wb-mr6cu_37/K1`;
  - уставкой котла `wbe2-i-opentherm_11/Heating Setpoint`;
  - межмодульным сигналом `dhw_priority_mgr/heating_pause_mode` (+ `heating_pause_active`).

- **Floor_mixing_control.js**  
  Регулятор узла подмеса тёплого пола. Отвечает за управление клапаном подмеса и использует насос ТП как входной признак работы контура.

- **Heating_pumps_manager.js**  
  Единый менеджер насосов отопления жилой части:
  - `wb-mr6cu_37/K2` (тёплый пол);
  - `wb-mr6cu_37/K4` (радиаторы жилого этажа).
  Учитывает `heating_pause_mode`.

- **Basement_radiator_thermostat.js**  
  Временный термостат цоколя (до переноса в Home Assistant):
  - управляет `wb-mr6cu_37/K3`;
  - учитывает `heating_pause_mode`.

## Распределение писателей по насосам

- `K1` → **DHW_priority_manager.js**
- `K2` → **Heating_pumps_manager.js**
- `K3` → **Basement_radiator_thermostat.js**
- `K4` → **Heating_pumps_manager.js**

## Связь модулей

1. `DHW_priority_manager.js` формирует приоритет ГВС и публикует `heating_pause_mode`.
2. `Heating_pumps_manager.js` и `Basement_radiator_thermostat.js` читают `heating_pause_mode` и выключают отопительные насосы при `priority_heat`/`restore`.
3. `Floor_mixing_control.js` работает в своей зоне ответственности (подмес ТП) и не должен получать второго писателя в каналы клапана.
4. `Boiler_room.js` остаётся мониторинговым модулем и не подменяет управляющие сценарии.

## Временные решения

- **Basement_radiator_thermostat.js** — временный модуль для цоколя.  
  После переноса логики в Home Assistant должен быть удалён, а управление `K3` передано в HA.

## Что проверить после установки на контроллер

1. Скрипты загружаются в `wb-rules` без ошибок.
2. Нет конфликтов писателей по `K1/K2/K3/K4`.
3. `heating_pause_mode` корректно переключается и читается управляющими модулями.
4. Реакция насосов:
   - `K1` — по логике ГВС;
   - `K2/K4` — по `Heating_pumps_manager.js`;
   - `K3` — по временному термостату цоколя.
5. Узел подмеса работает штатно (`Floor_mixing_control.js`, без конфликтов писателей в каналы клапана).
