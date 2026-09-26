# m1w2-health-v1

## API и выбранная квалификация

Проверен исходный wb-rules **v2.46.5**, commit `de67bb2159766a1e1491597e01ed50b82d4c1c73`:
- [README, dev/#error и trackMqtt](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/README.md)
- [scripts/lib.js, getDevValue](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/scripts/lib.js)
- [engine.go, DefineMqttTracker/newTrackHandler](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/wbrules/engine.go)

dev читает локальную модель controls, включая #error; существование/complete не доказывает текущий опрос. trackMqtt callback содержит boolean retained. При присоединении нового tracker к существующей подписке engine воспроизводит кэш с retained=true. Кэш не допускается как startup proof.

Для проверки recovery изучен [wb-mqtt-serial serial_port_driver.cpp](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/serial_port_driver.cpp), commit `832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c`: драйвер публикует channel errors, а при успешном чтении с неизменным значением может публиковать только изменившийся error. Это исследование API, не утверждение о версии serial на WB.

## Автомат состояний

1. Новый экземпляр не квалифицирован. Допускаются два доказательства: для temperature и Sensor OK отдельно получены non-retained значения, либо завершён коррелированный post-start serial RPC read обоих аппаратных регистров (описан ниже). Пустой error, retained OK=1/температура и периодическое чтение dev не квалифицируют startup.
2. После первого успешного синхронизированного read сохраняется admission **только в памяти этого экземпляра rules**. Live numeric temperature не обязана повторяться. Каждый read проверяет доступные controls, отсутствие ошибок temperature/health, finite temperature в диапазоне и точный OK (true/1/"1"). Admission не означает, что неисправный текущий control можно использовать.
3. При startup и после retained barrier требуется совпадение live sample с локальной моделью. При обычном runtime recovery уже admitted датчика нового sample не требуется: восстановившееся current state возвращает VALID. Краткая потеря cache/getter exception, локальные ошибки, invalid numeric и OK=0 дают null, но не стирают admission. Плохой live callback блокирует до отражения fault в cache/его восстановления либо исправного live sample; старый здоровый cache до обновления не стирает fault.
4. Ошибка блокирует затронутый канал. Callback error до обновления cache защёлкнут консервативно: снимается live error clear либо, для admitted датчика, после наблюдения локального error и последующего локального clear. Retained empty не снимает live fault в обоих порядках callback/cache. Для startup одного error clear недостаточно.
5. OK 0→1 / восстановление диапазона/доступности controls восстанавливают admitted датчик автоматически; re-arm и numeric change не нужны. Retained value ставит отдельный barrier затронутого канала: требуется новый live sample и синхронизация с dev либо новый post-start serial proof. Clock rollback сбрасывает admission и оба startup proofs.
6. Неизвестный/nonboolean retain flag даёт sticky RUNTIME_UNSUPPORTED, как у прежнего транспорта. Ни TTL датчика, ни искусственный heartbeat не вводятся.

Issue #75: [причина, все пути сброса, regression и границы live-доказательства](ISSUE75_RECOVERY.md). `watchM1w2()` теперь пишет только переходы health state в штатный log: owner/path, STARTUP/RUNTIME, reason/cause и barriers; дополнительного MQTT heartbeat нет.

## Post-start proof без numeric republish

После replay нового rules instance HHM делает ограниченную серию read-only RPC к `wb-mqtt-serial/port/Load` по настроенному `device_id`. FC04 читает input register 7/8 (s16, scale 1/16), затем FC02 — discrete input 16/17 (Sensor OK). Адрес выбирается только для явно mapped External Sensor 1/2. Запрос не меняет controls и не вызывает numeric MQTT callback. Read подтверждает состояние аппаратных регистров на момент транзакции, а не новую конверсию DS18B20.

Reply обязан иметь точные topic/id текущего boot, retained=false, error=null, корректный HEX, неистёкший deadline и неизменившуюся revision локального health state. Temperature должна совпадать с local control точно в native scale либо после штатного `round_to=0.05`; OK обязан быть 1, оба local #error пусты, оба controls доступны. Sentinel 0x7fff, диапазон, несогласованные значения, ошибки RPC и неподдерживаемый API не квалифицируют. Нестандартные scale/offset не поддерживаются и дают fail-closed.

Один outstanding запрос на consumer, не более трёх попыток на sensor в эпизоде startup/revalidation. Между неудачами 60 s, deadline каждого запроса 10 s; это ограничения транспорта, не sensor TTL и не NLI readiness timeout. После qualification RPC прекращаются; #75 runtime recovery остаётся state-based. При исчерпании попыток сохраняется invalid до нормального live proof или нового instance; бесконечного опроса нет. Clock rollback отменяет outstanding proof и требует нового. PersistentStorage хранит только монотонный номер boot, admission туда не записывается.

Retained-only dead device не отвечает на новый аппаратный read и не получает admission даже при healthy cache. Отдельно retained flag без поддерживаемой семантики остаётся sticky RUNTIME_UNSUPPORTED. Runtime после admission опирается на штатные errors/OK работающего драйвера; новая независимая диагностика молчащего сервиса не вводится. Точные API/source и воспроизводимые проверки: [FIELD_STARTUP_2026-09-25.md](FIELD_STARTUP_2026-09-25.md).

## Температурные защиты

`io.at()` для M1W2 хранит время numeric MQTT publication либо принятого аппаратного proof; сам proof не увеличивает numeric seq. Для остальных датчиков семантика времени прежняя. Новый `io.observedAt()` для M1W2 возвращает время успешного чтения **квалифицированного локального состояния**, не время физического измерения. Только thermal dwell/observation в 500 и source используют его. Пороги, hysteresis, выдержки и ownership сохранены; invalid health прерывает охлаждение. HHM3Circuit получает supplyAt как время этой проверки. Clock/gap handling остаётся прежним.

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
