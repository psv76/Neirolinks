# Issue #68 / PR #73: исследование startup после live-теста 25.09.2026

Исторический отчёт относится к investigation commit `9f90f17`. Последующее [исправление runtime recovery по #75](ISSUE75_RECOVERY.md) меняет Wire/Runtime, но не решает описанный здесь startup blocker. Поэтому режим `--verify-baseline` из этого отчёта применим к 9f90f17, а не к исправленному HEAD; для воспроизведения старого recovery defect использовать новую suite с `--baseline`.

**Verdict: BLOCKED. Исправленного release нет.** Это воспроизводимые результаты расследования, не отчёт об устранении обоих дефектов. Основание — [live comment](https://github.com/psv76/Neirolinks/pull/73#issuecomment-5829076012). Работа выполнена офлайн; live WB, SSH, deploy, restart, OT и merge не выполнялись. NLI 30 s, readiness и rollback не менялись.

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

## B. M1W2: воспроизведено ограничение существующего startup proof

`localM1w2()` требует live value отдельно для temperature и OK. После общего restart уже сохранённые value=20, OK=1, error='' этого не дают. Число, пришедшее раньше OK, также не квалифицирует пару. При следующей неизменной публикации через 60 s readiness за 30 s не обеспечивается. Это объясняет механизм незавершённой qualification, но точный порядок каждого live floor callback из комментария восстановить нельзя.

Исследован публичный [control API wb-rules 2.46.5](https://github.com/wirenboard/wb-rules/blob/de67bb2159766a1e1491597e01ed50b82d4c1c73/wbrules/esengine.go#L315). `getValue()/getError()` и dev value/#error не предоставляют timestamp успешного Modbus poll. Внутренняя completeness и retained информация не является доступным свежим аппаратным доказательством. Никаких выдуманных getControl().isComplete()/isRetained() в runtime не добавлено.

[wb-mqtt-serial UpdateValueAndError](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/serial_port_driver.cpp#L324) при неизменном числе/ошибке может ничего не публиковать. При PublishOnlyOnChange error-only callback появляется при изменении ошибки, а не при каждом успешном poll. Поэтому пустой старый error или повторное чтение dev не доказывают новый poll. Указанный serial commit — исследованный upstream, **не установленная версия live**. Интервал 60 s — сценарий regression, не измеренное значение live-конфига 25.09.

Тест строит два одинаковых наблюдаемых состояния: здоровый опрашиваемый M1W2 без публикаций до +60 s и недоступный producer со старым retained-кэшем без новых сообщений. За первые 29999 ms публичные observations совпадают. Алгоритм на этих данных не может принять первый и отвергнуть второй. Это архитектурная граница пассивного proof, а не повод признать retained fresh.

Возможный новый источник доказательства исследован: serial RPC [device/Load](https://github.com/wirenboard/wb-mqtt-serial/blob/832fb9dbfad19a9fd283599ae9ad7e8c163d5f0c/src/rpc/rpc_device_load_task.cpp) читает регистры, выполняя PrepareSession и bus access. Это активное чтение, не дополнительное свойство control cache. Его не добавляли скрытно: неизвестна фактическая serial версия/поддержка этого API на объекте, не доказаны bounds полного required set <30 s и отсутствие нежелательных bus effects. Для продолжения нужен подтверждённый поддерживаемый источник успешного post-start poll (свежий ответ, корреляция с текущим запуском, оба канала, errors, timeout и fail-closed). Это отдельное архитектурное решение; пользователь просил вынести такое противоречие, а не менять контракт догадкой.

## Воспроизведение и предел результата

Из корня репозитория:

```text
node objects/05_31_Ivolga_13/HHM3_FSE/tests/field-startup-regressions.js
node objects/05_31_Ivolga_13/HHM3_FSE/tests/field-startup-regressions.js --verify-baseline
node objects/05_31_Ivolga_13/HHM3_FSE/tests/field-startup-regressions.js --acceptance
```

Обычный режим: 4 группы PASS, включая сохранение blocker и fail-safe. `--verify-baseline`: пятая проверка byte equality исследованных 500/620/Wire/Runtime с 14354bc; не постоянное требование к будущему fix. `--acceptance`: exit 1, `BLOCKED: healthy retained/unchanged M1W2 must qualify before 30 s`. Эта acceptance пока красная; её не объявляем устранённой посредством expected-failure. CI запускает явно названные investigation tests, а не этот release acceptance probe. После исправления потребуется заменить blocker assertions положительной acceptance для обеих ролей и всех требуемых ошибок, сохранив отрицательный retained-only сценарий.

Runtime bytes и NLI role manifests сохранены. Новый runtime commit и новые role SHA отсутствуют: выпускать прежний blocker под новым pin было бы вводящим в заблуждение. Существующие manifests **не deployable**:

| Role | Runtime commit | Manifest SHA256 (без изменений) |
|---|---|---|
| boiler | 14354bcf1e0033c51f02f0b242bea8aa7fa29e4e | 3c17f811f1580306c440143de958d723d26bb3ed7151f81991d4b957d0a2eb09 |
| gazebo | 14354bcf1e0033c51f02f0b242bea8aa7fa29e4e | 7c3f5a0323d5dbc611d9820985ec6681b1940d5fedbbce9f828215ab00c7bd0a |

Изменённые файлы: tests/harness.js, tests/field-startup-regressions.js, этот отчёт, INSTALL.md, TEST_RESULTS.md, SENSOR_HEALTH.md, manifest.json и два CI workflow. HHM aggregate manifest пересчитан для тестов/документации; это не новый deployment payload.

## Будущий controlled smoke — только после снятия blocker

1. Сначала установить причину A и реализовать доказанный proof B; получить FAIL на прежнем runtime и PASS acceptance <30 s на новом, включая оба порядка запуска, 500/620/600 agreement и недоступный retained-only device.
2. Закрепить новый runtime, regenerate оба role manifests/SHA при версии 3.1, пройти CI обоих roles. Проверить согласованное окно, baseline/backup/rollback и отдельно разрешённый live capture.
3. При отдельно разрешённой попытке 3.0→3.1 сохранить сырые callbacks/frames/runtime с начала окна. Критерий: дом NORMAL, required M1W2 valid, readiness <30 s без изменения NLI; затем >120 s стабильного состояния и диагностика 411–420. Не вызывать нагрев/первичный пуск для проверки.
4. Любой timeout/STARTUP_VALIDATION/fault оставляет штатный autorollback; сохранить evidence и не повторять update автоматически. До выполнения первых двух пунктов повторный smoke не рекомендован.
