# Локальная проверка 18.10.2026

- Четыре JSON-файла разобраны (3 шаблона и отфильтрованный DISCOVER).
- ReadOnly: topicSet отсутствует; все характеристики write=false.
- Candidate/Probe: пути записи ограничены enabled/on и reset_alarm/on, retain=false задан. Это статическая проверка наличия параметра, не доказательство его поддержки сервером.
- Probe regex совпадает только с lastochka_pressure_makeup_probe и не совпадает с рабочим lastochka_pressure_makeup.
- Шаблоны не содержат физического K5; все C_Option read-only; reset не имеет topicGet и содержит SwitchOffTime=0.1.
- YAML прошёл штатный validate_plan_structure_v2 без изменения Configurator. bridge.alice отсутствует.
- Полный исходный DISCOVER разобран: 111 Accessory / 356 Service; 111 непустых уникальных serial.

## DRY RUN на приложенном DISCOVER

`ok=false`, изменений 0, одна ожидаемая ошибка:

- lastochka_pressure_makeup: Accessory с таким SERIAL не найден.

Это корректная блокировка: native `wb:lastochka_pressure_makeup` существует, новый MQTT Accessory с ожидаемым serial `lastochka_pressure_makeup` ещё не создан. Нельзя менять serial на native только ради успешного DRY RUN: схема и write-права другая. После создания MQTT-кандидата нужен fresh DISCOVER и сверка реального serial.

Валидность JSON/YAML не равна проверке схемы импорта Sprut 3.0 beta. Принятие retain/data, авто-OFF, отсутствие повторов, подтверждение кнопки, доступность и live-значения НЕ проверены. Probe не выполнялся; подключений к WB/Sprut, публикаций MQTT и APPLY не было.
