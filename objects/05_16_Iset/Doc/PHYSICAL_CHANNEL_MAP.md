# Карта физических каналов объекта 05 16 Исеть Западная 26

Каноническое название объекта: **05 16 Исеть Западная 26**. Допустимые краткие названия: **Исеть**, **05 16 Исеть**, **Западная 26**.

Карта описывает физические устройства, входы, выходы, датчики и исполнительные механизмы. Виртуальные устройства, controls скриптов, диагностические параметры и программные состояния здесь не перечисляются.

## Оборудование

| Устройство / MQTT device | Тип | Интерфейс / порт | Адрес |
|---|---|---|---|
| `wb-gpio`, `wb-w1`, `power_status` | используемые встроенные интерфейсы Wiren Board | локальные GPIO, 1-Wire, питание | локальный контроллер |
| `wbe2-i-opentherm_12` | WBE2-I-OPENTHERM-FW-1.93 | `/dev/ttyMOD2` | 12 |
| `wbe2-i-opentherm_11` | WBE2-I-OPENTHERM-FW-1.93 | `/dev/ttyMOD3` | 11 |
| `wb-mr6cu_12` | WB-MR6CU | `/dev/ttyRS485-1` | 12 |
| `wb-mrm2-mini_19` | WB-MRM2-mini-NO-inputs | `/dev/ttyRS485-1` | 19 |
| `wb-map12e_35` | WB-MAP12E fw2 | `/dev/ttyRS485-1` | 35 |
| `wb-mr3_36` | WB-MR3 | `/dev/ttyRS485-1` | 36 |
| `wb-mr6cu_37` | WB-MR6CU | `/dev/ttyRS485-1` | 37 |
| `wb-msw-v4_45` | WB-MSW v.4 | `/dev/ttyRS485-1` | 45 |
| `wb-mr6c_46` | WB-MR6C | `/dev/ttyRS485-1` | 46 |
| `wb-msw-v4_61` | WB-MSW v.4 | `/dev/ttyRS485-1` | 61 |
| `wb-mr3_107` | WB-MR3 | `/dev/ttyRS485-1` | 107 |
| `breezart_lux_sb_115` | Breezart-Lux(SB) | `/dev/ttyRS485-1` | 115 |
| `wb-mao4_131` | tpl1_wb_mao4 | `/dev/ttyRS485-1` | 131 |
| `wb-msw-v4_202` | WB-MSW v.4 | `/dev/ttyRS485-1` | 202 |
| `wb-mao4_204` | tpl1_wb_mao4 | `/dev/ttyRS485-1` | 204 |
| `wb-msw-v4_209` | WB-MSW v.4 | `/dev/ttyRS485-1` | 209 |
| `wb-mr6cv3_4` | WB-MR6C v.3 | `/dev/ttyRS485-2` | 4 |
| `ONOKOM-AIR-HS-3-MB-B_6` | ONOKOM-AIR-HS-3-MB-B | `/dev/ttyRS485-2` | 6 |
| `ONOKOM-AIR-HS-3-MB-B_7` | ONOKOM-AIR-HS-3-MB-B | `/dev/ttyRS485-2` | 7 |
| `ONOKOM-AIR-HS-3-MB-B_8` | ONOKOM-AIR-HS-3-MB-B | `/dev/ttyRS485-2` | 8 |
| `ONOKOM-AIR-HS-3-MB-B_9` | ONOKOM-AIR-HS-3-MB-B | `/dev/ttyRS485-2` | 9 |
| `wb-msw-v4_22` | WB-MSW v.4 | `/dev/ttyRS485-2` | 22 |
| `wb-msw-v4_43` | WB-MSW v.4 | `/dev/ttyRS485-2` | 43 |
| `wb-msw-v4_47` | WB-MSW v.4 | `/dev/ttyRS485-2` | 47 |
| `wb-msw-v4_52` — датчик коридора | WB-MSW v.4 | `/dev/ttyRS485-2` | 52 |
| `wb-msw-v4_53` — датчик летней кухни | WB-MSW v.4 | `/dev/ttyRS485-2` | 53 |
| `wb-msw-v4_54` | WB-MSW v.4 | `/dev/ttyRS485-2` | 54 |
| `wb-msw-v4_64` | WB-MSW v.4 | `/dev/ttyRS485-2` | 64 |
| `wb-mr6cv3_70` | WB-MR6C v.3 | `/dev/ttyRS485-2` | 70 |
| `wb-mr6cv3_71` | WB-MR6C v.3 | `/dev/ttyRS485-2` | 71 |
| `wb-mr6cv3_72` | WB-MR6C v.3 | `/dev/ttyRS485-2` | 72 |
| `wb-msw-v4_106` | WB-MSW v.4 | `/dev/ttyRS485-2` | 106 |
| `wb-msw-v4_116` | WB-MSW v.4 | `/dev/ttyRS485-2` | 116 |
| `wb-mr6cv3_137` | WB-MR6C v.3 | `/dev/ttyRS485-2` | 137 |
| `modbus:195` | wb_mio | `/dev/ttyRS485-2` | 195 |
| `wb-mio-gpio_195:1` | WBIO-DI-WD-14 | `/dev/ttyRS485-2` | 195:1 |
| `wb-mio-gpio_195:2` | WBIO-DO-R1G-16 | `/dev/ttyRS485-2` | 195:2 |
| `wb-mcm8_199` | WB-MCM8 | `/dev/ttyRS485-2` | 199 |
| `wb-mao4_200` | tpl1_wb_mao4 | `/dev/ttyRS485-2` | 200 |
| `wb-mao4_220` | tpl1_wb_mao4 | `/dev/ttyRS485-2` | 220 |

## Освещение

| Модуль / адрес | Канал MQTT | Помещение / группа | Назначение |
|---|---|---|---|
| `wb-mr6c_46` | `wb-mr6c_46/K4` | Свет улица | 35 Фасад |
| `wb-mr6c_46` | `wb-mr6c_46/K5` | Свет улица | Въездная группа |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/Input 1` | Выключатели | большая клавиша (лестница) |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/Input 2` | Выключатели | Клавиша ближе к входу (бра) |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/Input 3` | Выключатели | Средняя клавиша |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K1` | Свет прихожая | 1 Лестница |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K2` | Свет прихожая | 3 Бра прихожая |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K3` | Свет прихожая | 2 Верхний свет |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K4` | Свет кухня-гостиная | 5 Бра у стола |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K5` | Свет кухня-гостиная | 6 Трек кухня |
| `wb-mr6cv3_4` | `wb-mr6cv3_4/K6` | Свет кухня-гостиная | 7 Люстра на кухне |
| `wb-mr6cv3_70` | `wb-mr6cv3_70/K1` | Свет кухня-гостиная | 9 Люстра гостиная |
| `wb-mr6cv3_70` | `wb-mr6cv3_70/K2` | Свет мастер-спальня | 12 Свет гардероб |
| `wb-mr6cv3_70` | `wb-mr6cv3_70/K3` | Свет мастер-спальня | 13 Свет спальня (трек) |
| `wb-mr6cv3_70` | `wb-mr6cv3_70/K5` | Свет мастер-спальня | 16 Верхний свет мастер с/у |
| `wb-mr6cv3_71` | `wb-mr6cv3_71/K1` | Свет коридор и санузел | 19 Свет санузел |
| `wb-mr6cv3_71` | `wb-mr6cv3_71/K3` | Свет сауна | 22,23 Свет комната отдыха |
| `wb-mr6cv3_71` | `wb-mr6cv3_71/K4` | Свет сауна | 24 Бра комната отдыха |
| `wb-mr6cv3_71` | `wb-mr6cv3_71/K5` | Свет сауна | 25 Свет душевая |
| `wb-mr6cv3_71` | `wb-mr6cv3_71/K6` | Свет сауна | 26 Свет парилка |
| `wb-mr6cv3_72` | `wb-mr6cv3_72/K1` | Свет кабинет | 21 Основной свет (треки) |
| `wb-mr6cv3_72` | `wb-mr6cv3_72/K2` | Свет улица | 29 Фасад терраса |
| `wb-mr6cv3_72` | `wb-mr6cv3_72/K3` | Свет улица | 30 Люстра терраса |

## Климат в помещениях

| Модуль / адрес | Канал MQTT | Помещение / группа | Назначение |
|---|---|---|---|
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/AC connected` | Климат сауна | Кондиционер подключен |
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/Active` | Климат сауна | Состояние |
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/Indoor air temperature` | Климат сауна | Температура воздуха в помещении |
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/Mode` | Климат сауна | Режим |
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/Target temperature` | Климат сауна | Целевая температура |
| `ONOKOM-AIR-HS-3-MB-B_6` | `ONOKOM-AIR-HS-3-MB-B_6/Thermostat state` | Климат сауна | Состояние термостата |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/AC connected` | Климат кабинет | Кондиционер подключен |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/Active` | Климат кабинет | Состояние |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/Indoor air temperature` | Климат кабинет | Температура воздуха в помещении |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/Mode` | Климат кабинет | Режим |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/Target temperature` | Климат кабинет | Целевая температура |
| `ONOKOM-AIR-HS-3-MB-B_7` | `ONOKOM-AIR-HS-3-MB-B_7/Thermostat state` | Климат кабинет | Состояние термостата |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/AC connected` | Климат гостиная | Кондиционер подключен |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/Active` | Климат гостиная | Состояние |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/Indoor air temperature` | Климат гостиная | Температура воздуха в помещении |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/Mode` | Климат гостиная | Режим |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/Target temperature` | Климат гостиная | Целевая температура |
| `ONOKOM-AIR-HS-3-MB-B_8` | `ONOKOM-AIR-HS-3-MB-B_8/Thermostat state` | Климат гостиная | Состояние термостата |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/AC connected` | Климат мастер-спальня | Кондиционер подключен |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/Active` | Климат мастер-спальня | Состояние |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/Indoor air temperature` | Климат мастер-спальня | Температура воздуха в помещении |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/Mode` | Климат мастер-спальня | Режим |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/Target temperature` | Климат мастер-спальня | Целевая температура |
| `ONOKOM-AIR-HS-3-MB-B_9` | `ONOKOM-AIR-HS-3-MB-B_9/Thermostat state` | Климат мастер-спальня | Состояние термостата |
| `wb-msw-v4_106` | `wb-msw-v4_106/Current Motion` | Климат на жилом этаже | Санузел движение |
| `wb-msw-v4_106` | `wb-msw-v4_106/Humidity` | Климат на жилом этаже | Санузел влажность |
| `wb-msw-v4_106` | `wb-msw-v4_106/Temperature` | Климат на жилом этаже | Санузел температура |
| `wb-msw-v4_116` | `wb-msw-v4_116/Air Quality (VOC)` | Климат гостиная | Качество воздуха (VOC) |
| `wb-msw-v4_116` | `wb-msw-v4_116/CO2` | Климат гостиная | Уровень CO₂ |
| `wb-msw-v4_116` | `wb-msw-v4_116/Current Motion` | Климат гостиная | Текущее движение |
| `wb-msw-v4_116` | `wb-msw-v4_116/Humidity` | Климат гостиная | Влажность |
| `wb-msw-v4_116` | `wb-msw-v4_116/Illuminance` | Климат гостиная | Освещенность |
| `wb-msw-v4_116` | `wb-msw-v4_116/Temperature` | Климат гостиная | Температура |
| `wb-msw-v4_202` | `wb-msw-v4_202/Current Motion` | Климат в цокольном этаже | Склад движение |
| `wb-msw-v4_202` | `wb-msw-v4_202/Humidity` | Климат в цокольном этаже | Склад влажность |
| `wb-msw-v4_202` | `wb-msw-v4_202/Temperature` | Климат в цокольном этаже | Склад температура |
| `wb-msw-v4_209` | `wb-msw-v4_209/Air Quality (VOC)` | Климат в цокольном этаже | Гараж VOC |
| `wb-msw-v4_209` | `wb-msw-v4_209/Current Motion` | Климат в цокольном этаже | Гараж движение |
| `wb-msw-v4_209` | `wb-msw-v4_209/Humidity` | Климат в цокольном этаже | Гараж влажность |
| `wb-msw-v4_209` | `wb-msw-v4_209/Temperature` | Климат в цокольном этаже | Гараж температура |
| `wb-msw-v4_22` | `wb-msw-v4_22/Air Quality (VOC)` | Климат кабинет | Качество воздуха (VOC) |
| `wb-msw-v4_22` | `wb-msw-v4_22/CO2` | Климат кабинет | Уровень CO₂ |
| `wb-msw-v4_22` | `wb-msw-v4_22/Current Motion` | Климат кабинет | Текущее движение |
| `wb-msw-v4_22` | `wb-msw-v4_22/Humidity` | Климат кабинет | Влажность |
| `wb-msw-v4_22` | `wb-msw-v4_22/Illuminance` | Климат кабинет | Освещенность |
| `wb-msw-v4_22` | `wb-msw-v4_22/Temperature` | Климат кабинет | Температура |
| `wb-msw-v4_43` | `wb-msw-v4_43/Current Motion` | Климат на жилом этаже | Прихожая движение |
| `wb-msw-v4_43` | `wb-msw-v4_43/Humidity` | Климат на жилом этаже | Прихожая влажность |
| `wb-msw-v4_43` | `wb-msw-v4_43/Temperature` | Климат на жилом этаже | Прихожая температура |
| `wb-msw-v4_45` | `wb-msw-v4_45/Current Motion` | Климат в цокольном этаже | Серверная движение |
| `wb-msw-v4_45` | `wb-msw-v4_45/Humidity` | Климат в цокольном этаже | Серверная влажность |
| `wb-msw-v4_45` | `wb-msw-v4_45/Temperature` | Климат в цокольном этаже | Серверная температура |
| `wb-msw-v4_47` | `wb-msw-v4_47/Humidity` | Климат мастер-спальня | Влажность гардероб |
| `wb-msw-v4_47` | `wb-msw-v4_47/Temperature` | Климат мастер-спальня | Температура гардероб |
| `wb-msw-v4_52` | `wb-msw-v4_52/Current Motion` | Климат на жилом этаже | Коридор движение |
| `wb-msw-v4_52` | `wb-msw-v4_52/Humidity` | Климат на жилом этаже | Коридор влажность |
| `wb-msw-v4_52` | `wb-msw-v4_52/Temperature` | Климат на жилом этаже | Коридор температура |
| `wb-msw-v4_53` | `wb-msw-v4_53/Air Quality (VOC)` | Летняя кухня | Качество воздуха (VOC) |
| `wb-msw-v4_53` | `wb-msw-v4_53/CO2` | Летняя кухня | Уровень CO₂ |
| `wb-msw-v4_53` | `wb-msw-v4_53/Current Motion` | Летняя кухня | Движение |
| `wb-msw-v4_53` | `wb-msw-v4_53/Humidity` | Летняя кухня | Влажность |
| `wb-msw-v4_53` | `wb-msw-v4_53/Illuminance` | Летняя кухня | Освещённость |
| `wb-msw-v4_53` | `wb-msw-v4_53/Temperature` | Летняя кухня | Температура |
| `wb-msw-v4_54` | `wb-msw-v4_54/Humidity` | Климат мастер-спальня | Влажность душевая |
| `wb-msw-v4_54` | `wb-msw-v4_54/Temperature` | Климат мастер-спальня | Температура душевая |
| `wb-msw-v4_61` | `wb-msw-v4_61/Current Motion` | Климат в цокольном этаже | Коридор цоколь движение |
| `wb-msw-v4_61` | `wb-msw-v4_61/Humidity` | Климат в цокольном этаже | Коридор цоколь влажность |
| `wb-msw-v4_61` | `wb-msw-v4_61/Temperature` | Климат в цокольном этаже | Коридор цоколь температура |
| `wb-msw-v4_64` | `wb-msw-v4_64/Current Motion` | Климат на жилом этаже | Душевая движение |
| `wb-msw-v4_64` | `wb-msw-v4_64/Humidity` | Климат на жилом этаже | Душевая влажность |
| `wb-msw-v4_64` | `wb-msw-v4_64/Temperature` | Климат на жилом этаже | Душевая температура |

## Отопление (котельная)

| Модуль / адрес | Канал MQTT | Помещение / группа | Назначение |
|---|---|---|---|
| `wb-mao4_131` | `wb-mao4_131/Channel 1 Dimming Level` | Котельная | Положение клапана подмеса тёплого пола, 0–10 В |
| `wb-mao4_131` | `wb-mao4_131/Channel 1 Switch` | Котельная | Клапан подмеса тёплого пола |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K1` | Коллектор радиаторов | 01. Конвектор кабинет |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K10` | Коллектор радиаторов | 10. Радиатор гостевой санузел |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K11` | Коллектор радиаторов | 11. Конвектор мастер спальня |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K12` | Коллектор тёплого пола | 01. Теплый пол мастер санузел |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K13` | Коллектор тёплого пола | 02. Теплый пол гостевой санузел |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K14` | Коллектор тёплого пола | 03. Теплый пол душевая |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K15` | Коллектор тёплого пола | 04. Теплый пол летняя кухня |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K16` | Коллектор тёплого пола | 05. Теплый пол прихожая |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K2` | Коллектор радиаторов | 02. Конвектор летняя кухня |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K3` | Коллектор радиаторов | 03. Радиатор летняя кухня дизайнерский |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K4` | Коллектор радиаторов | 04. Радиаторы коридор |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K5` | Коллектор радиаторов | 05. Конвектор мастер-санузел |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K6` | Коллектор радиаторов | 06. Конвектор гостиная |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K7` | Коллектор радиаторов | 07. Радиаторы гостиная + лестница |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K8` | Коллектор радиаторов | 08. Радиатор входная группа |
| `wb-mio-gpio_195:2` | `wb-mio-gpio_195:2/K9` | Коллектор радиаторов | 09. Радиаторы кухня |
| `wb-mr6cu_37` | `wb-mr6cu_37/K1` | Насосы в котельной (факт) | Насос бойлера косвенного нагрева |
| `wb-mr6cu_37` | `wb-mr6cu_37/K2` | Насосы в котельной (факт) | Насос контура тёплого пола |
| `wb-mr6cu_37` | `wb-mr6cu_37/K3` | Насосы в котельной (факт) | Насос отопления цоколя |
| `wb-mr6cu_37` | `wb-mr6cu_37/K4` | Насосы в котельной (факт) | Насос отопления жилого этажа |
| `wb-mr6cu_37` | `wb-mr6cu_37/K5` | Насосы в котельной (факт) | Насос рециркуляции ГВС |
| `wb-mr6cu_37` | `wb-mr6cu_37/K6` | Насосы в котельной (факт) | Насос водяного преднагрева приточной установки |
| `wb-w1` | `wb-w1/28-00000fd6a9ad` | Сырые значения датчиков температуры 1-Wire | улица |
| `wb-w1` | `wb-w1/28-00000fd7811a` | Котельная / бойлер БКН | Температура бойлера БКН |
| `wb-w1` | `wb-w1/28-00000fdeed15` | Сырые значения датчиков температуры 1-Wire | радиаторы цоколь |
| `wb-w1` | `wb-w1/28-00000ff8446c` | Сырые значения датчиков температуры 1-Wire | Подача от котла |
| `wb-w1` | `wb-w1/28-00000ff86391` | Сырые значения датчиков температуры 1-Wire | Радиаторы жилой зоны |
| `wb-w1` | `wb-w1/28-00000ff8a3d5` | Сырые значения датчиков температуры 1-Wire | теплый пол |
| `wbe2-i-opentherm_11` | `wbe2-i-opentherm_11/Heating Setpoint` | Газовый котёл | Уставка температуры отопления BAXI ECO4S 18F |
| `wbe2-i-opentherm_11` | `wbe2-i-opentherm_11/Heating Temperature` | Газовый котёл | Температура теплоносителя BAXI ECO4S 18F |
| `wbe2-i-opentherm_11` | `wbe2-i-opentherm_11/Invalid Connection` | Газовый котёл | Состояние связи OpenTherm |
| `wbe2-i-opentherm_12` | `wbe2-i-opentherm_12/Heating Setpoint` | Электрический котёл | Уставка температуры отопления |
| `wbe2-i-opentherm_12` | `wbe2-i-opentherm_12/Heating Temperature` | Электрический котёл | Температура теплоносителя |
| `wbe2-i-opentherm_12` | `wbe2-i-opentherm_12/Invalid Connection` | Электрический котёл | Состояние связи OpenTherm |

## Вентиляция

| Модуль / адрес | Канал MQTT | Помещение / группа | Назначение |
|---|---|---|---|
| `breezart_lux_sb_115` | `breezart_lux_sb_115/fan_performance` | Приточная вентиляция Breezart 1 | Производительность вентилятора |
| `breezart_lux_sb_115` | `breezart_lux_sb_115/setpoint_fan_performance` | Приточная вентиляция Breezart 1 | Уставка производительности вентилятора (%) |
| `wb-gpio` | `wb-gpio/EXT1_K1` | Вытяжная вентиляция Breezart 2 | Заслонка вытяжки из гаража |
| `wb-gpio` | `wb-gpio/EXT1_K2` | Вытяжная вентиляция Breezart 2 | Заслонка вытяжки из тех помещения |
| `wb-mao4_131` | `wb-mao4_131/Channel 2 Dimming Level` | Приточная вентиляция Breezart 1 | Открытие клапана в парилку |
| `wb-mao4_131` | `wb-mao4_131/Channel 2 Switch` | Приточная вентиляция Breezart 1 | Клапан приточки в парилку |
| `wb-mao4_131` | `wb-mao4_131/Channel 3 Dimming Level` | Приточная вентиляция Breezart 1 | Открытие клапана в кабинет |
| `wb-mao4_131` | `wb-mao4_131/Channel 3 Switch` | Приточная вентиляция Breezart 1 | Клапан приточки в кабинет |
| `wb-mao4_131` | `wb-mao4_131/Channel 4 Dimming Level` | Приточная вентиляция Breezart 1 | Открытие клапана в гостиную |
| `wb-mao4_131` | `wb-mao4_131/Channel 4 Switch` | Приточная вентиляция Breezart 1 | Клапан приточки в гостиную |
| `wb-mao4_200` | `wb-mao4_200/Channel 1 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана душа и сауны |
| `wb-mao4_200` | `wb-mao4_200/Channel 1 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки из душа и сауны |
| `wb-mao4_200` | `wb-mao4_200/Channel 2 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана с/у мастер спальни |
| `wb-mao4_200` | `wb-mao4_200/Channel 2 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки из с\у и гардероба в мастер-спальне |
| `wb-mao4_200` | `wb-mao4_200/Channel 3 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана гостиной |
| `wb-mao4_200` | `wb-mao4_200/Channel 3 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки из гостиной |
| `wb-mao4_200` | `wb-mao4_200/Channel 4 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана в гостевой |
| `wb-mao4_200` | `wb-mao4_200/Channel 4 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки из санузла гостевой |
| `wb-mao4_204` | `wb-mao4_204/Channel 2 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана сауны |
| `wb-mao4_204` | `wb-mao4_204/Channel 2 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки в сауне |
| `wb-mao4_204` | `wb-mao4_204/Channel 3 Dimming Level` | Приточная вентиляция Breezart 1 | Открытие клапана в спальню |
| `wb-mao4_204` | `wb-mao4_204/Channel 3 Switch` | Приточная вентиляция Breezart 1 | Клапан приточки в спальню |
| `wb-mao4_220` | `wb-mao4_220/Channel 1 Dimming Level` | Вытяжная вентиляция Vilpe | Открытие клапана кабинета |
| `wb-mao4_220` | `wb-mao4_220/Channel 1 Switch` | Вытяжная вентиляция Vilpe | Клапан вытяжки из кабинета |
| `wb-mao4_220` | `wb-mao4_220/Channel 2 Dimming Level` | Вытяжная вентиляция Vilpe | Скорость вентилятора Vilpe |
| `wb-mao4_220` | `wb-mao4_220/Channel 2 Switch` | Вытяжная вентиляция Vilpe | Вентилятор Vilpe на крыше |

## Электроснабжение

| Модуль / адрес | Канал MQTT | Помещение / группа | Назначение |
|---|---|---|---|
| `power_status` | `power_status/Vin` | Power Supply | Input Voltage |
| `power_status` | `power_status/working on battery` | Power Supply | On Battery |
| `wb-gpio` | `wb-gpio/EXT1_K10` | Управление питанием потребителей | Электрический котёл |
| `wb-gpio` | `wb-gpio/EXT1_K11` | Управление питанием потребителей | Печка в сауне |
| `wb-gpio` | `wb-gpio/EXT1_K9` | Управление питанием потребителей | Мастер контактор |
| `wb-map12e_35` | `wb-map12e_35/Ch 1 Irms L1` | На вводе | Кан 1 Irms L1 |
| `wb-map12e_35` | `wb-map12e_35/Ch 1 Irms L2` | На вводе | Кан 1 Irms L2 |
| `wb-map12e_35` | `wb-map12e_35/Ch 1 Irms L3` | На вводе | Кан 1 Irms L3 |
| `wb-map12e_35` | `wb-map12e_35/Ch 1 Total P` | На вводе | Кан 1 сумм. P |
| `wb-map12e_35` | `wb-map12e_35/Ch 2 Irms L1` | Сауна | Ток печи сауны, фаза L1 |
| `wb-map12e_35` | `wb-map12e_35/Ch 2 Irms L2` | Сауна | Ток печи сауны, фаза L2 |
| `wb-map12e_35` | `wb-map12e_35/Ch 2 Irms L3` | Сауна | Ток печи сауны, фаза L3 |
| `wb-map12e_35` | `wb-map12e_35/Ch 2 Total P` | Сауна | Суммарная мощность печи сауны |
| `wb-map12e_35` | `wb-map12e_35/Urms L1` | На вводе | Urms L1 |
| `wb-map12e_35` | `wb-map12e_35/Urms L2` | На вводе | Urms L2 |
| `wb-map12e_35` | `wb-map12e_35/Urms L3` | На вводе | Urms L3 |
| `wb-mio-gpio_195:1` | `wb-mio-gpio_195:1/IN1` | Пожарная сигнализация | Если отключено - пожар в сауне |
| `wb-mr3_107` | `wb-mr3_107/K2` | Управление воротами | Ворота в гараж |
| `wb-mr3_107` | `wb-mr3_107/K3` | Управление воротами | Въездные ворота |
| `wb-mr3_36` | `wb-mr3_36/K1` | Управление питанием потребителей | Розетки уличные |
| `wb-mr3_36` | `wb-mr3_36/K3` | Управление питанием потребителей | Внешний блок кондиционеров |
| `wb-mrm2-mini_19` | `wb-mrm2-mini_19/K1` | Управление питанием потребителей | Контроллер купели |
