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

- [CHANNEL_MAP.md](CHANNEL_MAP.md) — предварительная карта устройств и задачи поканального обследования.
- [DEVICE_INVENTORY.csv](DEVICE_INVENTORY.csv) — таблица настроенных Modbus-устройств.
- [controllers/AGYPLABX.json](controllers/AGYPLABX.json) — плановая регистрация NST.

## Источник и ограничения

Архив `nst-onboarding-20261025T195951Z-34ac5b84.tar.gz` (SHA256 `375e93c516508eded411672013487acdedea19517d0ff8c344fa88fd57d6173f`), время **2026-10-25 19:59:51 UTC**, `mode=inventory`, `warnings=[]`, внутренние проверки SHA256 **4/4 OK**.

Архив **не содержит `wb-webui.conf`, `widget-channels.csv`, `channel-map.json` или MQTT metadata**. Поэтому названия выходов из виджетов пока недоступны. Исходный архив не публикуем в репозитории.

Для полноценной карты: **NEIROLINKS → Сервис → Собрать карту** (`nst onboarding channels`). Полученный архив позволит привязать подписи виджетов к MQTT-каналам и отметить неподписанное.

Регистрация `planned` не меняет сам контроллер. **Не выполнять `nst sync` и не переводить профиль в `active` до проверки назначения и отдельного approved Platform release.**
