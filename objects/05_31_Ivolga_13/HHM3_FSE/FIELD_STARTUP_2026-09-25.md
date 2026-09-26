# Issue #68 / PR #73: cold-start proof после live-теста 25.09.2026

## Причина и исправление

Прежний localM1w2 требовал отдельные live numeric temperature и OK. Новый tracker wb-rules воспроизводит retained cache; serial при unchanged temperature/OK может не публиковать ничего. Поэтому здоровое устройство и мёртвый producer с тем же cache неразличимы для пассивного reader. Fix #75 c35ddbd исправил recovery уже admitted датчика, но не мог безопасно выдать initial admission. Прежняя попытка readiness за 30 s в NLI 0.1.7 была дополнительным ограничением; NLI 0.1.9 после #74/#79 installation-only, и runtime gate не возвращается.

Теперь новый instance получает дополнительное доказательство: коррелированный ответ на post-start `wb-mqtt-serial/port/Load` FC04 temperature и FC02 Sensor OK, через configured device_id. Ответы должны быть non-retained, текущего boot/id, своевременными, без RPC/Modbus ошибок и согласованными с доступными healthy local controls. Температура конечна и в диапазоне, аппаратный и локальный OK=1, оба #error пусты. Read подтверждает доступность устройства и содержимое регистров после старта; новую конверсию DS18B20 он не инициирует и не обещает. Никаких numeric republish и подмены cache нет.

Retained-only dead device не сможет ответить на новый read; cached controls не заменяют ответ. Запоздалые/retained/чужие replies не квалифицируют. Изменение local health state между чтениями отменяет proof. Runtime recovery #75 отделён от startup и по-прежнему не требует изменения numeric value. MSW, frame TTL, receiver, 507 и NLI core не изменены.

## Проверяемая семантика WB API

Исследован upstream wb-mqtt-serial commit `832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c`. Это source pin исследования, **не утверждение об установленной live версии**.

- [Документированный RPC Modbus](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/README.md): device_id берёт port/protocol/slave из конфигурации; HEX response, error=null при успехе, total_timeout; API предназначен для разовых операций.
- [JSON schema](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/wb-mqtt-serial-rpc-port-load-request.schema.json) и [handler](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/rpc/rpc_port_handler.cpp): параметры запроса и разрешение configured device_id.
- [Driver list](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/rpc/rpc_port_driver_list.cpp): поиск configured device, AddTask в serial client. Не угадываются port, baud или slave address.
- [Modbus task](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/rpc/rpc_port_load_modbus_serial_client_task.cpp): CheckPortOpen, MakePDU, traits->Transaction, ExtractResponseData, OnResult; истечение срока и ошибки идут в failure. Это реальный bus read, не cached register value.
- [Device access](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/serial_client_device_access_handler.cpp): PrepareToAccess(nullptr) не вызывает device PrepareSession. Альтернативный device/Load не выбран: legacy subdevices ограничены, PrepareSession способен включать continuous read записью регистра. Выбранный HHM route генерирует только FC04/FC02, без payload записи; bus arbitration и дополнительная нагрузка чтений остаются реальными.
- [Legacy M1W2 template](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/templates/config-wb-m1w2.json) и [v3 template](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/templates/config-wb-m1w2_v3-multiple_w1.json.jinja): input 7/8, s16 scale 0.0625, error 0x7fff; discrete 16/17. Поддержаны native и round_to=0.05; произвольные custom scale/offset fail-closed.
- [Официальный RPC client](https://github.com/wirenboard/python-mqtt-rpc/blob/1b49daa253fb8d0641c877907419d5e6201c49e9/mqttrpc/client.py): `/rpc/v1/{driver}/{service}/{method}/{client_id}`, `/reply`, params/id envelope.
- [wb-rules v2.46.5 tracker](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/wbrules/engine.go): cache replay retained=true; публичный cache сам по себе не timestamp успешного hardware poll.

Один outstanding RPC на consumer, максимум три попытки на sensor за эпизод qualification, пауза 60 s после неудачи, deadline 10 s на stage. После qualification опрос прекращается. Это не heartbeat, не TTL workaround, не увеличение NLI timeout. Не гарантируется общий startup срок при занятой/неисправной шине. При отсутствии capability датчик остаётся invalid с диагностикой POST_START_PROOF; установка NLI от этого не откатывается.

## Regression и следующий controlled retry

`cold-start-proof-regressions.js --baseline` использует Wire/Runtime из c35ddbd: 4 PASS / 3 FAIL. Исправленный runtime: 7 PASS. Отдельная аппаратная модель отвечает только на реальные запросы формы документированного RPC, не публикует sensor controls. Проверены новые instances, retained unchanged state, оба restart ordering 500→620/620→500, все 20 mapped sensors, согласованность 500/620/624/600 и house receiver. Negative cases: dead/no response, retained/wrong/late/reboot reply, error/exception/malformed, unavailable controls, OK=0, #error, sentinel/range, mismatch, metadata unsupported и clock rollback. Source-level доказательство API дополняет simulation; C++ driver и физическая шина в тесте не исполняются.

#75 suite: old14354 baseline 4 PASS / 12 FAIL; fixed 16 PASS. Полные результаты: TEST_RESULTS.md. Точные release pins и SHA — NLI/releases. Версия остаётся 3.1.

`field-startup-regressions.js` сохраняет четыре исторические проверки passive cache/receiver. `--acceptance` теперь запускает положительный cold-start suite; старый заведомо красный passive probe доступен как `--passive-acceptance`. `--verify-baseline` относится только к историческому investigation commit 9f90f17, не к текущему fix.

Следующее live окно требует отдельного разрешения. План: INSTALL.md; проверить поддерживаемую serial capability, exact installed manifests, proof для unchanged sensors, отсутствие ложного FLOOR_SENSOR_INVALID при длительном runtime и корректное fault/recovery. Установленная serial версия, реальные timings шины и физическое поведение этой офлайн работой не подтверждены. SSH/deploy/restart/OT/physical commands не выполнялись.

## A. Receiver: причина наблюдения live пока не установлена

В тесте настоящие 620 и 500 работают с persisted settings, retained physical controls, общими tracker subscriptions и API-профилем wb-rules 2.46.5. Использованы session=29 и все шесть точных времён из комментария; полные JSON frames генерирует 620. Это **не** raw live capture: полных groups, фактических callback retained/qos, receiver receive timestamps и локальных clocks в комментарии нет.

| Порядок загрузки | Первый принятый seq | Первый ready seq | Время ready | От старта |
|---|---:|---:|---:|---:|
| 500 → 620 | 1 | 2 | 1790323104779 | 5726 ms |
| 620 → 500, seq1 потерян до подписки | 2 | 4 | 1790323114554 | 15501 ms |

На прежнем runtime `14354bc...` оба варианта дают `дом NORMAL`. Seq2→seq3 разделены 4863 ms, поэтому во втором порядке seq3 ещё не ready — это правильная выдержка 5 s. Тест печатает `first/firstSent/session/seq/sent/received/barrier/lastNow/ready/reason` после каждого кадра; доступ к closure внедряется только в тестовую копию module source.

House frame не имеет верхнеуровневых valid/reason: после ready внутренний reason может быть undefined; `500.linkState()` отображает NORMAL, а usable frame определяется fresh/ready. Это не объясняет STARTUP_VALIDATION в live и не изменялось догадкой.

Проверены [DefineMqttTracker/newTrackHandler](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/wbrules/engine.go#L1963): cached replay идёт только вновь присоединившемуся tracker с retained=true; действующим tracker передаётся исходный flag. Кэшируются также live payloads, но это не превращает каждую следующую публикацию в retained. Harness моделирует точные подписки HHM; полную конкурентную Go/MQTT-среду он не исполняет.

**Нельзя заявить FAIL-before/PASS-after для A.** При подтверждённых в комментарии заголовках и предполагаемых valid body / false callback / монотонных clocks старый receiver уже проходит. Для точного диагноза нужны сохранённые полные frames seq1..6, wb-rules log исключений, порядок загрузки, и именно callback 500: topic, retained и его тип, qos, Date.now, return accept, read state. Одного внешнего `mosquitto_sub` недостаточно для доказательства доставки в callback. Если этих данных нет в сохранённом capture, их получение потребует отдельного согласованного диагностического сеанса; в этой работе он не запускался.
