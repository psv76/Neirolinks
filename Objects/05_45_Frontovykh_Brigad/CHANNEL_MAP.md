# Карта каналов — 05 45 Фронтовых бригад

Источник: [wb-webui (5).conf](Sources/wb-webui%20(5).conf). SHA256: `faa01dbfca6d15ea2fd82181d7fe0c53f7afbcbbd3b7e2a72af7cc453fbed9fe`.
Карта получена только из этого экспорта. Дата фиксации материалов: 2026-10-12; дата снятия экспорта неизвестна.

## Границы достоверности

- **Ф** — [Проверено] буквальная привязка и подпись есть в конфигурации WebUI. Это не подтверждение монтажа или работающего канала.
- **П** — [Предположение] физическое назначение следует из подписи; адрес устройства следует только из его имени.
- **Н** — [Не могу проверить] live, активный уровень, инверсия, NC/NO, задержка, клемма, модель модуля и связь со схемой неизвестны.
- MQTT-путь `/devices/<device>/controls/<control>` сформирован из WB ID; в экспорте это не отдельное поле и публикация брокером не проверена. Пробелы в control сохраняются.
- `MODULE.CHANNEL` по EIM пока не назначен: обозначений модулей DWG и кабельного журнала нет. `device_id.control_id` не подменяет проектный идентификатор.
- Тип `switch` — настройка отображения, а не свидетельство права записи, полярности или измеренного состояния.
- Для каждой строки действует **Ф / П / Н**. Поля `null` в JSON означают отсутствие сведений, не нулевое значение.

## Покрытие

| Показатель | Количество |
| --- | --- |
| dashboards | 7 |
| widgets | 17 |
| widget_channel_occurrences | 128 |
| separator_cells | 28 |
| svg_channel_occurrences | 123 |
| unique_channels | 134 |
| object_channels | 100 |
| object_discrete_channels | 98 |
| demo_service_channels | 34 |
| enabled_svg_write_occurrences | 26 |

Все ссылки (включая отключённые SVG-привязки) сохранены в [channel_map.json](Doc/channel_map.json) с JSON Pointer и исходными полями. Разделители не являются каналами.

## Группы оборудования по подписям

Связь виджет → dashboard подтверждена в JSON; связь с физическим оборудованием требует сверки. Числа К1–К7 и ВО1–ВО14 — набор подписей, не подтверждённая ведомость оборудования. Не выводить число камер из числа МО.

| Виджет | Подпись дословно | Панель | device_id | Каналов |
| --- | --- | --- | --- | --- |
| widget10 | МО1, К1, ВО1, ВО2 | Машинное отделение №1 | wb-gpio | 14 |
| widget11 | МО1, К2, ВО9, ВО10 | Машинное отделение №1 | wb-gpio | 14 |
| widget12 | МО2, К3, ВО3, ВО4 | Машинное отделение №2 | wb-mio-gpio_102:1 | 14 |
| widget13 | МО3, К4, ВО11, ВО12 | Машинное отделение №3 | wb-mio-gpio_103:1 | 14 |
| widget14 | МО3, К5, ВО5, ВО6 | Машинное отделение №3 | wb-mio-gpio_103:2 | 14 |
| widget15 | К6, ВО13, ВО14 | Машинное отделение №4 | wb-mio-gpio_104:1 | 14 |
| widget16 | К7, ВО7, ВО8 | Машинное отделение №4 | wb-mio-gpio_104:2 | 14 |
| widget17 | Камера 4 | Машинное отделение №4 | wb-ms_156 | 2 |

К6/К7 отнесены к МО4 по включению widget15/widget16 в dashboard `mo4`; в названиях самих виджетов МО не написано. «Камера 4» также находится на панели МО4, что не доказывает соответствие остальных камер номерам МО.

## Адреса и входы

`wb-gpio/EXT1_INx` и `EXT2_INx`: токены EXT1/EXT2 и номера входов прочитаны буквально. Это не Modbus-адреса. Соответствие физическим WBIO-DI-HVD16 и клеммам надо сверить с конфигурацией GPIO и монтажом.

`wb-mio-gpio_102:1`, `103:1`, `103:2`, `104:1`, `104:2`: числа 102/103/104 и 1/2 находятся в device_id. [Предположение] это адрес узла и номер модуля; реальные `slave_id`, порт RS-485 и состав модулей не подтверждены.

`wb-ms_156`: 156 — токен имени. [Предположение] адрес устройства; точную модель, серийный номер и место установки WebUI не устанавливает.

Во всех семи группах представлены входы 1–14. Наличие/занятость входов 15/16 по этому файлу неизвестны; считать их свободными нельзя. HP/LP здесь подписаны как дискретные аварии, а не числовые измерения давления. Аналоговые каналы давления в объектовых виджетах не найдены.

## Подробные объектовые каналы

JSON Pointer в последнем столбце относится к исходному конфигу. Все подписи сохранены без исправлений; для точного сохранения пробелов использовать JSON.

### widget10 — МО1, К1, ВО1, ВО2

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К1 / Наличие сети | wb-gpio/EXT1_IN1 | /devices/wb-gpio/controls/EXT1_IN1 | Ф / П / Н | /widgets/9/cells/1/id |
| Нормальная работа К1 / Работа К1 | wb-gpio/EXT1_IN2 | /devices/wb-gpio/controls/EXT1_IN2 | Ф / П / Н | /widgets/9/cells/2/id |
| Аварии К1 / Авария компрессора  | wb-gpio/EXT1_IN3 | /devices/wb-gpio/controls/EXT1_IN3 | Ф / П / Н | /widgets/9/cells/4/id |
| Аварии К1 / Авария РКС | wb-gpio/EXT1_IN4 | /devices/wb-gpio/controls/EXT1_IN4 | Ф / П / Н | /widgets/9/cells/5/id |
| Аварии К1 / Авария HP | wb-gpio/EXT1_IN5 | /devices/wb-gpio/controls/EXT1_IN5 | Ф / П / Н | /widgets/9/cells/6/id |
| Аварии К1 / Авария LP | wb-gpio/EXT1_IN6 | /devices/wb-gpio/controls/EXT1_IN6 | Ф / П / Н | /widgets/9/cells/7/id |
| Аварии К1 / Авария конденсатора | wb-gpio/EXT1_IN7 | /devices/wb-gpio/controls/EXT1_IN7 | Ф / П / Н | /widgets/9/cells/8/id |
| Аварии К1 / Авария РНПП | wb-gpio/EXT1_IN8 | /devices/wb-gpio/controls/EXT1_IN8 | Ф / П / Н | /widgets/9/cells/9/id |
| Работа воздухоохладителей / Работа ВО 1 | wb-gpio/EXT1_IN9 | /devices/wb-gpio/controls/EXT1_IN9 | Ф / П / Н | /widgets/9/cells/11/id |
| Работа воздухоохладителей / Работа ВО 2 | wb-gpio/EXT1_IN10 | /devices/wb-gpio/controls/EXT1_IN10 | Ф / П / Н | /widgets/9/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 1 | wb-gpio/EXT1_IN11 | /devices/wb-gpio/controls/EXT1_IN11 | Ф / П / Н | /widgets/9/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 2 | wb-gpio/EXT1_IN12 | /devices/wb-gpio/controls/EXT1_IN12 | Ф / П / Н | /widgets/9/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 1 | wb-gpio/EXT1_IN13 | /devices/wb-gpio/controls/EXT1_IN13 | Ф / П / Н | /widgets/9/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 2 | wb-gpio/EXT1_IN14 | /devices/wb-gpio/controls/EXT1_IN14 | Ф / П / Н | /widgets/9/cells/17/id |

### widget11 — МО1, К2, ВО9, ВО10

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К2 / Наличие сети | wb-gpio/EXT2_IN1 | /devices/wb-gpio/controls/EXT2_IN1 | Ф / П / Н | /widgets/10/cells/1/id |
| Нормальная работа К2 / Работа К2 | wb-gpio/EXT2_IN2 | /devices/wb-gpio/controls/EXT2_IN2 | Ф / П / Н | /widgets/10/cells/2/id |
| Аварии К2 / Авария компрессора | wb-gpio/EXT2_IN3 | /devices/wb-gpio/controls/EXT2_IN3 | Ф / П / Н | /widgets/10/cells/4/id |
| Аварии К2 / Авария РКС | wb-gpio/EXT2_IN4 | /devices/wb-gpio/controls/EXT2_IN4 | Ф / П / Н | /widgets/10/cells/5/id |
| Аварии К2 / Авария HP | wb-gpio/EXT2_IN5 | /devices/wb-gpio/controls/EXT2_IN5 | Ф / П / Н | /widgets/10/cells/6/id |
| Аварии К2 / Авария LP | wb-gpio/EXT2_IN6 | /devices/wb-gpio/controls/EXT2_IN6 | Ф / П / Н | /widgets/10/cells/7/id |
| Аварии К2 / Авария конденсатора | wb-gpio/EXT2_IN7 | /devices/wb-gpio/controls/EXT2_IN7 | Ф / П / Н | /widgets/10/cells/8/id |
| Аварии К2 / Авария РНПП | wb-gpio/EXT2_IN8 | /devices/wb-gpio/controls/EXT2_IN8 | Ф / П / Н | /widgets/10/cells/9/id |
| Работа воздухоохладителей / Работа ВО 9 | wb-gpio/EXT2_IN9 | /devices/wb-gpio/controls/EXT2_IN9 | Ф / П / Н | /widgets/10/cells/11/id |
| Работа воздухоохладителей / Работа ВО 10 | wb-gpio/EXT2_IN10 | /devices/wb-gpio/controls/EXT2_IN10 | Ф / П / Н | /widgets/10/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 9 | wb-gpio/EXT2_IN11 | /devices/wb-gpio/controls/EXT2_IN11 | Ф / П / Н | /widgets/10/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 10 | wb-gpio/EXT2_IN12 | /devices/wb-gpio/controls/EXT2_IN12 | Ф / П / Н | /widgets/10/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 9 | wb-gpio/EXT2_IN13 | /devices/wb-gpio/controls/EXT2_IN13 | Ф / П / Н | /widgets/10/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 10 | wb-gpio/EXT2_IN14 | /devices/wb-gpio/controls/EXT2_IN14 | Ф / П / Н | /widgets/10/cells/17/id |

### widget12 — МО2, К3, ВО3, ВО4

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К3 / Наличие сети | wb-mio-gpio_102:1/IN1 | /devices/wb-mio-gpio_102:1/controls/IN1 | Ф / П / Н | /widgets/11/cells/1/id |
| Нормальная работа К3 / Работа К3 | wb-mio-gpio_102:1/IN2 | /devices/wb-mio-gpio_102:1/controls/IN2 | Ф / П / Н | /widgets/11/cells/2/id |
| Аварии К3 / Авария компрессора | wb-mio-gpio_102:1/IN3 | /devices/wb-mio-gpio_102:1/controls/IN3 | Ф / П / Н | /widgets/11/cells/4/id |
| Аварии К3 / Авария РКС | wb-mio-gpio_102:1/IN4 | /devices/wb-mio-gpio_102:1/controls/IN4 | Ф / П / Н | /widgets/11/cells/5/id |
| Аварии К3 / Авария HP | wb-mio-gpio_102:1/IN5 | /devices/wb-mio-gpio_102:1/controls/IN5 | Ф / П / Н | /widgets/11/cells/6/id |
| Аварии К3 / Авария LP | wb-mio-gpio_102:1/IN6 | /devices/wb-mio-gpio_102:1/controls/IN6 | Ф / П / Н | /widgets/11/cells/7/id |
| Аварии К3 / Авария конденсатора | wb-mio-gpio_102:1/IN7 | /devices/wb-mio-gpio_102:1/controls/IN7 | Ф / П / Н | /widgets/11/cells/8/id |
| Аварии К3 / Авария РНПП | wb-mio-gpio_102:1/IN8 | /devices/wb-mio-gpio_102:1/controls/IN8 | Ф / П / Н | /widgets/11/cells/9/id |
| Работа воздухоохладителей / Работа ВО 3 | wb-mio-gpio_102:1/IN9 | /devices/wb-mio-gpio_102:1/controls/IN9 | Ф / П / Н | /widgets/11/cells/11/id |
| Работа воздухоохладителей / Работа ВО 4 | wb-mio-gpio_102:1/IN10 | /devices/wb-mio-gpio_102:1/controls/IN10 | Ф / П / Н | /widgets/11/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 3 | wb-mio-gpio_102:1/IN11 | /devices/wb-mio-gpio_102:1/controls/IN11 | Ф / П / Н | /widgets/11/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 4 | wb-mio-gpio_102:1/IN12 | /devices/wb-mio-gpio_102:1/controls/IN12 | Ф / П / Н | /widgets/11/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 3 | wb-mio-gpio_102:1/IN13 | /devices/wb-mio-gpio_102:1/controls/IN13 | Ф / П / Н | /widgets/11/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 4 | wb-mio-gpio_102:1/IN14 | /devices/wb-mio-gpio_102:1/controls/IN14 | Ф / П / Н | /widgets/11/cells/17/id |

### widget13 — МО3, К4, ВО11, ВО12

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К4 / Наличие сети | wb-mio-gpio_103:1/IN1 | /devices/wb-mio-gpio_103:1/controls/IN1 | Ф / П / Н | /widgets/12/cells/1/id |
| Нормальная работа К4 / Работа К4 | wb-mio-gpio_103:1/IN2 | /devices/wb-mio-gpio_103:1/controls/IN2 | Ф / П / Н | /widgets/12/cells/2/id |
| Аварии К4 / Авария компрессора | wb-mio-gpio_103:1/IN3 | /devices/wb-mio-gpio_103:1/controls/IN3 | Ф / П / Н | /widgets/12/cells/4/id |
| Аварии К4 / Авария РКС | wb-mio-gpio_103:1/IN4 | /devices/wb-mio-gpio_103:1/controls/IN4 | Ф / П / Н | /widgets/12/cells/5/id |
| Аварии К4 / Авария HP | wb-mio-gpio_103:1/IN5 | /devices/wb-mio-gpio_103:1/controls/IN5 | Ф / П / Н | /widgets/12/cells/6/id |
| Аварии К4 / Авария LP | wb-mio-gpio_103:1/IN6 | /devices/wb-mio-gpio_103:1/controls/IN6 | Ф / П / Н | /widgets/12/cells/7/id |
| Аварии К4 / Авария конденсатора | wb-mio-gpio_103:1/IN7 | /devices/wb-mio-gpio_103:1/controls/IN7 | Ф / П / Н | /widgets/12/cells/8/id |
| Аварии К4 / Авария РНПП | wb-mio-gpio_103:1/IN8 | /devices/wb-mio-gpio_103:1/controls/IN8 | Ф / П / Н | /widgets/12/cells/9/id |
| Работа воздухоохладителей / Работа ВО 11 | wb-mio-gpio_103:1/IN9 | /devices/wb-mio-gpio_103:1/controls/IN9 | Ф / П / Н | /widgets/12/cells/11/id |
| Работа воздухоохладителей / Работа ВО 12 | wb-mio-gpio_103:1/IN10 | /devices/wb-mio-gpio_103:1/controls/IN10 | Ф / П / Н | /widgets/12/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 11 | wb-mio-gpio_103:1/IN11 | /devices/wb-mio-gpio_103:1/controls/IN11 | Ф / П / Н | /widgets/12/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 12 | wb-mio-gpio_103:1/IN12 | /devices/wb-mio-gpio_103:1/controls/IN12 | Ф / П / Н | /widgets/12/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 11 | wb-mio-gpio_103:1/IN13 | /devices/wb-mio-gpio_103:1/controls/IN13 | Ф / П / Н | /widgets/12/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 12 | wb-mio-gpio_103:1/IN14 | /devices/wb-mio-gpio_103:1/controls/IN14 | Ф / П / Н | /widgets/12/cells/17/id |

### widget14 — МО3, К5, ВО5, ВО6

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К5 / Наличие сети | wb-mio-gpio_103:2/IN1 | /devices/wb-mio-gpio_103:2/controls/IN1 | Ф / П / Н | /widgets/13/cells/1/id |
| Нормальная работа К5 / Работа К5 | wb-mio-gpio_103:2/IN2 | /devices/wb-mio-gpio_103:2/controls/IN2 | Ф / П / Н | /widgets/13/cells/2/id |
| Аварии К5 / Авария компрессора | wb-mio-gpio_103:2/IN3 | /devices/wb-mio-gpio_103:2/controls/IN3 | Ф / П / Н | /widgets/13/cells/4/id |
| Аварии К5 / Авария РКС | wb-mio-gpio_103:2/IN4 | /devices/wb-mio-gpio_103:2/controls/IN4 | Ф / П / Н | /widgets/13/cells/5/id |
| Аварии К5 / Авария HP | wb-mio-gpio_103:2/IN5 | /devices/wb-mio-gpio_103:2/controls/IN5 | Ф / П / Н | /widgets/13/cells/6/id |
| Аварии К5 / Авария LP | wb-mio-gpio_103:2/IN6 | /devices/wb-mio-gpio_103:2/controls/IN6 | Ф / П / Н | /widgets/13/cells/7/id |
| Аварии К5 / Авария конденсатора | wb-mio-gpio_103:2/IN7 | /devices/wb-mio-gpio_103:2/controls/IN7 | Ф / П / Н | /widgets/13/cells/8/id |
| Аварии К5 / Авария РНПП | wb-mio-gpio_103:2/IN8 | /devices/wb-mio-gpio_103:2/controls/IN8 | Ф / П / Н | /widgets/13/cells/9/id |
| Работа воздухоохладителей / Работа ВО 5 | wb-mio-gpio_103:2/IN9 | /devices/wb-mio-gpio_103:2/controls/IN9 | Ф / П / Н | /widgets/13/cells/11/id |
| Работа воздухоохладителей / Работа ВО 6 | wb-mio-gpio_103:2/IN10 | /devices/wb-mio-gpio_103:2/controls/IN10 | Ф / П / Н | /widgets/13/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 5 | wb-mio-gpio_103:2/IN11 | /devices/wb-mio-gpio_103:2/controls/IN11 | Ф / П / Н | /widgets/13/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 6 | wb-mio-gpio_103:2/IN12 | /devices/wb-mio-gpio_103:2/controls/IN12 | Ф / П / Н | /widgets/13/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 5 | wb-mio-gpio_103:2/IN13 | /devices/wb-mio-gpio_103:2/controls/IN13 | Ф / П / Н | /widgets/13/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 6 | wb-mio-gpio_103:2/IN14 | /devices/wb-mio-gpio_103:2/controls/IN14 | Ф / П / Н | /widgets/13/cells/17/id |

### widget15 — К6, ВО13, ВО14

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К6 / Наличие сети | wb-mio-gpio_104:1/IN1 | /devices/wb-mio-gpio_104:1/controls/IN1 | Ф / П / Н | /widgets/14/cells/1/id |
| Нормальная работа К6 / Работа К6 | wb-mio-gpio_104:1/IN2 | /devices/wb-mio-gpio_104:1/controls/IN2 | Ф / П / Н | /widgets/14/cells/2/id |
| Аварии К6 / Авария компрессора | wb-mio-gpio_104:1/IN3 | /devices/wb-mio-gpio_104:1/controls/IN3 | Ф / П / Н | /widgets/14/cells/4/id |
| Аварии К6 / Авария РКС | wb-mio-gpio_104:1/IN4 | /devices/wb-mio-gpio_104:1/controls/IN4 | Ф / П / Н | /widgets/14/cells/5/id |
| Аварии К6 / Авария HP | wb-mio-gpio_104:1/IN5 | /devices/wb-mio-gpio_104:1/controls/IN5 | Ф / П / Н | /widgets/14/cells/6/id |
| Аварии К6 / Авария LP | wb-mio-gpio_104:1/IN6 | /devices/wb-mio-gpio_104:1/controls/IN6 | Ф / П / Н | /widgets/14/cells/7/id |
| Аварии К6 / Авария конденсатора | wb-mio-gpio_104:1/IN7 | /devices/wb-mio-gpio_104:1/controls/IN7 | Ф / П / Н | /widgets/14/cells/8/id |
| Аварии К6 / Авария РНПП | wb-mio-gpio_104:1/IN8 | /devices/wb-mio-gpio_104:1/controls/IN8 | Ф / П / Н | /widgets/14/cells/9/id |
| Работа воздухоохладителей / Работа ВО 13 | wb-mio-gpio_104:1/IN9 | /devices/wb-mio-gpio_104:1/controls/IN9 | Ф / П / Н | /widgets/14/cells/11/id |
| Работа воздухоохладителей / Работа ВО 14 | wb-mio-gpio_104:1/IN10 | /devices/wb-mio-gpio_104:1/controls/IN10 | Ф / П / Н | /widgets/14/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 13 | wb-mio-gpio_104:1/IN11 | /devices/wb-mio-gpio_104:1/controls/IN11 | Ф / П / Н | /widgets/14/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 14 | wb-mio-gpio_104:1/IN12 | /devices/wb-mio-gpio_104:1/controls/IN12 | Ф / П / Н | /widgets/14/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 13 | wb-mio-gpio_104:1/IN13 | /devices/wb-mio-gpio_104:1/controls/IN13 | Ф / П / Н | /widgets/14/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 14 | wb-mio-gpio_104:1/IN14 | /devices/wb-mio-gpio_104:1/controls/IN14 | Ф / П / Н | /widgets/14/cells/17/id |

### widget16 — К7, ВО7, ВО8

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
| Нормальная работа К7 / Наличие сети | wb-mio-gpio_104:2/IN1 | /devices/wb-mio-gpio_104:2/controls/IN1 | Ф / П / Н | /widgets/15/cells/1/id |
| Нормальная работа К7 / Работа К7 | wb-mio-gpio_104:2/IN2 | /devices/wb-mio-gpio_104:2/controls/IN2 | Ф / П / Н | /widgets/15/cells/2/id |
| Аварии К7 / Авария компрессора | wb-mio-gpio_104:2/IN3 | /devices/wb-mio-gpio_104:2/controls/IN3 | Ф / П / Н | /widgets/15/cells/4/id |
| Аварии К7 / Авария РКС | wb-mio-gpio_104:2/IN4 | /devices/wb-mio-gpio_104:2/controls/IN4 | Ф / П / Н | /widgets/15/cells/5/id |
| Аварии К7 / Авария HP | wb-mio-gpio_104:2/IN5 | /devices/wb-mio-gpio_104:2/controls/IN5 | Ф / П / Н | /widgets/15/cells/6/id |
| Аварии К7 / Авария LP | wb-mio-gpio_104:2/IN6 | /devices/wb-mio-gpio_104:2/controls/IN6 | Ф / П / Н | /widgets/15/cells/7/id |
| Аварии К7 / Авария конденсатора | wb-mio-gpio_104:2/IN7 | /devices/wb-mio-gpio_104:2/controls/IN7 | Ф / П / Н | /widgets/15/cells/8/id |
| Аварии К7 / Авария РНПП | wb-mio-gpio_104:2/IN8 | /devices/wb-mio-gpio_104:2/controls/IN8 | Ф / П / Н | /widgets/15/cells/9/id |
| Работа воздухоохладителей / Работа ВО 7 | wb-mio-gpio_104:2/IN9 | /devices/wb-mio-gpio_104:2/controls/IN9 | Ф / П / Н | /widgets/15/cells/11/id |
| Работа воздухоохладителей / Работа ВО 8 | wb-mio-gpio_104:2/IN10 | /devices/wb-mio-gpio_104:2/controls/IN10 | Ф / П / Н | /widgets/15/cells/12/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 7 | wb-mio-gpio_104:2/IN11 | /devices/wb-mio-gpio_104:2/controls/IN11 | Ф / П / Н | /widgets/15/cells/14/id |
| Аварии воздухоохладителей / Авария ТЭНов ВО 8 | wb-mio-gpio_104:2/IN12 | /devices/wb-mio-gpio_104:2/controls/IN12 | Ф / П / Н | /widgets/15/cells/15/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 7 | wb-mio-gpio_104:2/IN13 | /devices/wb-mio-gpio_104:2/controls/IN13 | Ф / П / Н | /widgets/15/cells/16/id |
| Аварии воздухоохладителей / Авария вентилятора ВО 8 | wb-mio-gpio_104:2/IN14 | /devices/wb-mio-gpio_104:2/controls/IN14 | Ф / П / Н | /widgets/15/cells/17/id |

### widget17 — Камера 4

| Раздел / сигнал дословно | WB ID | MQTT topic (выведен) | Достоверность | Источник |
| --- | --- | --- | --- | --- |
|  / Температура | wb-ms_156/Temperature | /devices/wb-ms_156/controls/Temperature | Ф / П / Н | /widgets/16/cells/0/id |
|  / Влажность | wb-ms_156/Humidity | /devices/wb-ms_156/controls/Humidity | Ф / П / Н | /widgets/16/cells/1/id |

## Демонстрационные и служебные каналы

Не входят в карту холодильного оборудования. Сохранены для полноты экспорта. Наличие ссылок на network/system не раскрывает фактические IP или serial контроллера.

В Demo SVG есть 26 включённых write-привязок к восьми уникальным каналам: `wb-gpio/A1_OUT`–`A4_OUT`, `5V_OUT`, `V_OUT`, `buzzer/enabled`, `system/Reboot`. Это факт настроек UI, а не доказательство подключения выходов к холодильным установкам. Исходник является архивом, не подготовленным для развёртывания интерфейсом «только мониторинг».

| WB ID | MQTT topic (выведен) | Подписи / применения | Достоверность |
| --- | --- | --- | --- |
| power_status/Vin | /devices/power_status/controls/Vin | Input Voltage; read | Ф / Н |
| power_status/working on battery | /devices/power_status/controls/working on battery | On Battery | Ф / Н |
| wb-gpio/V_OUT | /devices/wb-gpio/controls/V_OUT | Vout Switch; write; style | Ф / Н |
| buzzer/enabled | /devices/buzzer/controls/enabled | ; write; style; visible | Ф / Н |
| network/Ethernet IP | /devices/network/controls/Ethernet IP | Ethernet 1; read; style | Ф / Н |
| network/Ethernet 2 IP | /devices/network/controls/Ethernet 2 IP | Ethernet 2; read; style | Ф / Н |
| network/Wi-Fi IP | /devices/network/controls/Wi-Fi IP | ; read; style; visible | Ф / Н |
| network/Wi-Fi 2 IP | /devices/network/controls/Wi-Fi 2 IP | ; read; visible; style | Ф / Н |
| network/GPRS IP | /devices/network/controls/GPRS IP | WWAN; read; style | Ф / Н |
| wb-adc/A1 | /devices/wb-adc/controls/A1 | Input Voltage; read | Ф / Н |
| wb-gpio/A1_IN | /devices/wb-gpio/controls/A1_IN | Input State; style | Ф / Н |
| wb-gpio/A1_OUT | /devices/wb-gpio/controls/A1_OUT | Output Switch; write; visible; style | Ф / Н |
| system/HW Revision | /devices/system/controls/HW Revision | ; read | Ф / Н |
| system/Short SN | /devices/system/controls/Short SN | Serial Number; read | Ф / Н |
| system/Batch No | /devices/system/controls/Batch No |  | Ф / Н |
| system/Current uptime | /devices/system/controls/Current uptime | Uptime; read | Ф / Н |
| hwmon/Board Temperature | /devices/hwmon/controls/Board Temperature | ; read | Ф / Н |
| hwmon/CPU Temperature | /devices/hwmon/controls/CPU Temperature | ; read | Ф / Н |
| wb-adc/A2 | /devices/wb-adc/controls/A2 | Input Voltage; read | Ф / Н |
| wb-gpio/A2_IN | /devices/wb-gpio/controls/A2_IN | Input State; style | Ф / Н |
| wb-gpio/A2_OUT | /devices/wb-gpio/controls/A2_OUT | Output Switch; write; style | Ф / Н |
| wb-adc/A3 | /devices/wb-adc/controls/A3 | Input Voltage; read | Ф / Н |
| wb-gpio/A3_IN | /devices/wb-gpio/controls/A3_IN | Input State; style | Ф / Н |
| wb-gpio/A3_OUT | /devices/wb-gpio/controls/A3_OUT | Output Switch; write; style | Ф / Н |
| wb-adc/A4 | /devices/wb-adc/controls/A4 | Input Voltage; read | Ф / Н |
| wb-gpio/A4_IN | /devices/wb-gpio/controls/A4_IN | Input State; style | Ф / Н |
| wb-gpio/A4_OUT | /devices/wb-gpio/controls/A4_OUT | Output Switch; write; style | Ф / Н |
| wb-gpio/5V_OUT | /devices/wb-gpio/controls/5V_OUT | Output Switch; write; style | Ф / Н |
| wb-adc/Vin | /devices/wb-adc/controls/Vin | read | Ф / Н |
| wb-adc/5Vout | /devices/wb-adc/controls/5Vout | read | Ф / Н |
| system/Release name | /devices/system/controls/Release name | read | Ф / Н |
| system/Release suite | /devices/system/controls/Release suite | read | Ф / Н |
| system/Reboot | /devices/system/controls/Reboot | write | Ф / Н |
| buzzer/volume | /devices/buzzer/controls/volume | read | Ф / Н |
