# m1w2-health-v1

## API и выбранная квалификация

Проверен исходный wb-rules **v2.46.5**, commit `de67bb2159766a1e1491597e01ed50b82d4c1c73`:
- [README, dev/#error и trackMqtt](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/README.md)
- [scripts/lib.js, getDevValue](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/scripts/lib.js)
- [engine.go, DefineMqttTracker/newTrackHandler](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/wbrules/engine.go)

dev читает локальную модель controls, включая #error; существование/complete не доказывает текущий опрос. trackMqtt callback содержит boolean retained. При присоединении нового tracker к существующей подписке engine воспроизводит кэш с retained=true. Кэш не допускается как startup proof.

Для проверки recovery изучен [wb-mqtt-serial serial_port_driver.cpp](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/serial_port_driver.cpp), commit `832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c`: драйвер публикует channel errors, а при успешном чтении с неизменным значением может публиковать только изменившийся error. Это исследование API, не утверждение о версии serial на WB.

## Автомат состояний

1. Новый экземпляр не квалифицирован. Для temperature и Sensor OK отдельно требуется non-retained значение. Пустой error, retained OK=1/температура и периодическое чтение dev не квалифицируют startup.
2. Live numeric temperature не обязана повторяться. При чтении нужны: оба доказательства, доступные controls, отсутствие ошибок temperature/health, finite temperature в диапазоне и точный OK (true/1/"1").
3. MQTT callback и локальная модель могут обновляться в разном порядке. До совпадения их значений read возвращает null. Не сочетать новое доказательство с предыдущим числом в cache.
4. Ошибка блокирует затронутый канал. Retained error консервативно блокирует; retained empty не стирает live fault. Non-retained error clear восстанавливает ранее подтверждённый live канал при прежнем валидном значении. Для канала, не видевшего live value после запуска, одного error clear недостаточно.
5. OK=0, invalid numeric, пропавший control или диапазон вне допуска дают null. OK 0→1 / валидный numeric event восстанавливают автоматически; re-arm нет. Retained values после live отзывают допуск соответствующего канала. Clock rollback сбрасывает оба startup proofs.
6. Неизвестный/nonboolean retain flag даёт sticky RUNTIME_UNSUPPORTED, как у прежнего транспорта. Ни TTL датчика, ни искусственный heartbeat не вводятся.

При выключенном переиздании неизменных значений начальная квалификация может ждать естественного live изменения; это намеренный отказ доверять retained-only состоянию. Ошибка/недоступность устройства обрабатывается через штатные channel errors и Sensor OK. Полностью молчащий неисправный драйвер, который не сообщает ошибок, этим state-based контрактом не обнаруживается. Не обещается новая независимая диагностика service liveness.

## Температурные защиты

`io.at()` остаётся временем numeric MQTT publication. Новый `io.observedAt()` для M1W2 возвращает время успешного чтения **квалифицированного локального состояния**, не время физического измерения. Только thermal dwell/observation в 500 и source используют его. Пороги, hysteresis, выдержки и ownership сохранены; invalid health прерывает охлаждение. HHM3Circuit получает supplyAt как время этой проверки. Clock/gap handling остаётся прежним.

MSW/OT/readback продолжают использовать HHM3Wire.sensor и 120000 ms TTL. Frames сохраняют TTL 30000 ms, session/seq, anti-replay и revalidation. Настройки bridge и Sprut не меняются.

## Явная карта

Всего 20 пар: 9 floor дома + 10 котельной + 1 gazebo. Диапазоны consumers сохранены: floor −20..70; boiler control −20..110; диагностический слой −40..120. Различие диапазонов диагностики и управления существовало до 3.1.

| Temperature | Sensor OK |
|---|---|
| 903.09_TEMP_NONE/External Sensor 1 | 903.09_TEMP_NONE/External Sensor 1 OK |
| 902.11_M1W2_TEMP_NONE/External Sensor 1 | 902.11_M1W2_TEMP_NONE/External Sensor 1 OK |
| 902.09_M1W2_TEMP_NONE/External Sensor 1 | 902.09_M1W2_TEMP_NONE/External Sensor 1 OK |
| 902.06_M1W2_TEMP_NONE/External Sensor 1 | 902.06_M1W2_TEMP_NONE/External Sensor 1 OK |
| 902.04_M1W2_LEAK_TEMP/External Sensor 2 | 902.04_M1W2_LEAK_TEMP/External Sensor 2 OK |
| 902.13_M1W2_LEAK_TEMP/External Sensor 2 | 902.13_M1W2_LEAK_TEMP/External Sensor 2 OK |
| 902.02_M1W2_TEMP_NONE/External Sensor 1 | 902.02_M1W2_TEMP_NONE/External Sensor 1 OK |
| 903.02_M1W2_LEAK_TEMP/External Sensor 2 | 903.02_M1W2_LEAK_TEMP/External Sensor 2 OK |
| 903.06_M1W2_LEAK_TEMP/External Sensor 2 | 903.06_M1W2_LEAK_TEMP/External Sensor 2 OK |
| wb-m1w2_170/External Sensor 1 | wb-m1w2_170/External Sensor 1 OK |
| wb-m1w2_170/External Sensor 2 | wb-m1w2_170/External Sensor 2 OK |
| wb-m1w2_141/External Sensor 1 | wb-m1w2_141/External Sensor 1 OK |
| wb-m1w2_141/External Sensor 2 | wb-m1w2_141/External Sensor 2 OK |
| wb-m1w2_167/External Sensor 1 | wb-m1w2_167/External Sensor 1 OK |
| wb-m1w2_167/External Sensor 2 | wb-m1w2_167/External Sensor 2 OK |
| wb-m1w2_121/External Sensor 1 | wb-m1w2_121/External Sensor 1 OK |
| wb-m1w2_173/External Sensor 1 | wb-m1w2_173/External Sensor 1 OK |
| wb-m1w2_173/External Sensor 2 | wb-m1w2_173/External Sensor 2 OK |
| wb-m1w2_166/External Sensor 1 | wb-m1w2_166/External Sensor 1 OK |
| 921.10_TEMP_NONE/External Sensor 1 | 921.10_TEMP_NONE/External Sensor 1 OK |

Не включены пустые входы wb-m1w2_121/External Sensor 2, wb-m1w2_164/External Sensor 1/2 и wb-m1w2_166/External Sensor 2. Датчик 412 читает только 600; он не становится новым interlock источника или соседних контуров.
