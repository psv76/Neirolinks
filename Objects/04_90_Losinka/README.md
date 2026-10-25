# 04 90 Лосиный (Losinka)

Новый объект NEIROLINKS, первичное обследование перед ПНР.

## Контроллер

| Поле | Значение |
|---|---|
| Аппаратный serial WB | `AGYPLABX` |
| Hostname | `wirenboard-AGYPLABX` |
| Fingerprint SHA256 (eMMC) | `76c94ff6919ed809325f8104c3242faad3543325aa4d5e1a074c1fc549341fa4` |
| NST | 2.5 |
| NEIROLINKS Tools | 1.0 |
| Профиль NST | [controllers/AGYPLABX.json](controllers/AGYPLABX.json) |
| Статус | **planned** — учтён в GitHub, не активирован для NST deployment |

`node=main` и `role=house` — **предварительное предположение для регистрации** по названиям комнатных датчиков. Назначение контроллера ещё требует подтверждения инженером. `capabilities=[]`; активных компонентов не назначено. Общий диагностический профиль `Systems/NST/diagnostics/controller-default-v1.json`.

## Начальная инвентаризация

По `wb-mqtt-serial.conf`: **16 записей Modbus** на двух включённых RS-485, среди них **15 с MQTT `id`** и **одна WB-MAI2-mini/CC, адрес 164, без `id`**. NST 2.5 в `hardware.json` посчитал только записи с `id`.

Оборудование: 4× WB-MR6CU, 1× WB-MWAC v2, 4× WB-MSW v4, 6× WB-M1W2, 1× WB-MAI2-mini/CC. Физическое присутствие устройств, работа шины и назначения каналов по архиву не проверяются.

- [CHANNEL_MAP.md](CHANNEL_MAP.md) — актуальная карта подписей физических и технических каналов, вопросы ПНР.
- [DEVICE_INVENTORY.csv](DEVICE_INVENTORY.csv) — таблица настроенных Modbus-устройств.
- [controllers/AGYPLABX.json](controllers/AGYPLABX.json) — плановая регистрация NST.

## Карта каналов из WB WebUI — второй архив

**Получено:** `nst onboarding channels`, архив `nst-onboarding-20261025T200417Z-31617e94.tar.gz`, SHA256 `1bafbf564e18b4b3ac6094f4f297db9190c21460046a0260bab1119f42acd570`, дата **2026-10-25 20:04:17 UTC**. Fingerprint и serial совпадают с зарегистрированным профилем; **7/7 внутренних SHA256 совпали**, `meta.warnings=[]`.

Карта включает **5 панелей и 18 виджетов**, в том числе demo: 77 привязок (70 уникальных каналов), 63 привязки с явной подписью (56 уникальных путей); MQTT metadata: 39 device ID и 300 control paths. **244 канала без явной подписи** — среди них множество служебных параметров, а не 244 неподключённых физических канала.

- [CHANNEL_MAP.md](CHANNEL_MAP.md) — текущая **поканальная** карта котельной, тёплого пола, климата, защиты от протечек, обнаруженных неподписанных каналов и вопросов ПНР.
- [UNLABELED_MODBUS_METADATA.csv](UNLABELED_MODBUS_METADATA.csv) — 102 retained MQTT control metadata настроенных Modbus-устройств без отдельной подписи из виджета; большинство не является физическими линиями.
- [WIDGET_CHANNELS.csv](WIDGET_CHANNELS.csv) — все 77 дословных привязок WB WebUI (сохранены повторы, пустые подписи, виджеты и панели).
- [DEVICE_INVENTORY.csv](DEVICE_INVENTORY.csv) — 16 записей устройств Modbus, включая аналоговый модуль без `id` в конфигурации.
- [controllers/AGYPLABX.json](controllers/AGYPLABX.json) — плановый NST профиль.

**Важно для ПНР:** 8 выходов тёплого пола находятся в виджете «Тёплый пол (выключен = греет)»; физическая инверсия не проверена. `A03/K3` подписан «Клапан подпитки». `A04/K1–K2` — «Kотел тен 1/2». В `A05/Input F2–F4` подписи обрываются на «Датчик протечки в». Датчик `902.07_M1W2_TEMP_NONE/External Sensor 1` находится и в группе «гостиная 3», и в виджете зоны кухни — требуется натурная проверка.

## Источники, регистрация и пределы достоверности

1. Первичный архив `nst-onboarding-20261025T195951Z-34ac5b84.tar.gz`, SHA256 `375e93c516508eded411672013487acdedea19517d0ff8c344fa88fd57d6173f`, UTC 2026-10-25 19:59:51, `mode=inventory`, проверки 4/4 OK.
2. Второй архив `nst-onboarding-20261025T200417Z-31617e94.tar.gz`, SHA256 указан выше, `mode=channels`, проверки 7/7 OK. Содержит `wb-webui.conf`, `widget-channels.csv`, `channel-map.json`, MQTT metadata.

Исходные архивы и полные конфиги **не публикуются** в публичном GitHub. Публикуются производные документы без секретов.

В конфигурации WB-MAI2-mini/CC (RS-485-2, slave 164) отсутствует `id`, поэтому NST 2.5 показал 15 настроенных Modbus-устройств; во втором архиве устройство видно в MQTT как `wb-mai2-mini_164`. Первый вход `input_1_current` подписан «датчик давления», но его калибровка/значение давления не подтверждены.

**Значение lifecycle `planned`:** профиль и реестр зарегистрированы в GitHub, но approved Platform и live NST controller state не изменены. **Не запускать `nst sync`, не активировать `active` до проверки реального назначения / компонентов и согласования.**
