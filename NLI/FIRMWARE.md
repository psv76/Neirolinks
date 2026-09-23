# Обёртка штатного WB firmware updater

Изучены официальные [CLI](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb-mcu-fw-updater), [update_monitor.py](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb_mcu_fw_updater/update_monitor.py) и [package init](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb_mcu_fw_updater/__init__.py), чтение 24.09.2026. Git blob CLI на момент анализа: `91d705e6de165970d5a87669b34c7ed9c282364f`. Это исследование источника, не утверждение об установленной версии на WB.

`update-all` обновляет firmware и может обновлять bootloader, затем восстанавливать application firmware. В актуальной реализации отдельный путь `decide_bootloader_action` выбирает такой update; recovery внутри массового update также может проверить bootloader. `recover-all` восстанавливает firmware устройств в bootloader через штатную recovery logic. `--force` автоматически отвечает Yes, поэтому NLI его не использует. `--allow-downgrade`, erase settings, прямой `update-bl` и собственный flasher в NLI отсутствуют.

При default pyserial backend штатная утилита может приостановить пользователей serial ports (`SIGSTOP`) и возобновить их через atexit (`SIGCONT`). NLI не маскирует это как безостановочную операцию. Потеря питания/SIGKILL upstream может не выполнить atexit: инженер должен проверить драйвер/связь, не запускать следующий updater вслепую. NLI сам не останавливает wb-mqtt-serial для component update.

## Check

`nli firmware check` читает наличие `/usr/bin/wb-mcu-fw-updater`, package version через dpkg-query, hash script и наличие известных command names; проверяет `/proc` на текущий updater/flasher. Не запускает и не импортирует updater, даже для help. В исследованном CLI нет inventory/dry-run. Library `probe_all_devices` обращается к Modbus; поиск UART settings и firmware helpers не имеют достаточного чистого read-only контракта для NLI. Поэтому результат **unavailable**, exit 3: список доступных обновлений неизвестен. Это не «все устройства актуальны» и не ошибка отопления. Новый доказуемо read-only API требует отдельного audited adapter.

## Update / recover

В config добавить `firmware.approved_executable_sha256` (hash установленного reviewed script) и `firmware.approved_package_version` (точный dpkg version). Значения заранее не выдуманы. При смене package/script необходимо снова изучить поведение, особенно bootloader, argument support и формат summary. Для v0.1 допустимы только штатные `update-all`/`recover-all` с `--debug`: этот флаг нужен для INFO summary/per-device transcript, upstream default WARNING может скрыть результат.

Команда требует interactive stdin, показывает bootloader/serial notice, просит ввести `firmware-update` либо `firmware-recover`. Затем сохраняются интерактивные вопросы официального CLI; NLI не отвечает на них. Prompt без newline пересылается по chunks, чтобы оператор его видел. Весь stdout/stderr updater сохраняется в transaction transcript с fsync; native лог по устройствам доступен даже если parser не знает новый формат.

Exit 0 upstream недостаточен: текущая batch implementation может завершиться с нулевым кодом при оставшихся failed devices. NLI разбирает итоговые counts, выделяет строки devices и возвращает partial_failure для disconnected/stuck/not recovered/skipped/unsupported; неизвестный summary — unverified, не success. stdout/stderr и transcript являются источником подробностей.

Ctrl-C получает upstream; NLI держит lock до завершения дочернего процесса, не убивает flasher по timeout и не запускает автоматический retry. При собственном SIGTERM родитель ждёт child, чтобы не освободить lock посреди flash. SIGKILL/power loss оставляет pending. `firmware recover` может явно продолжить прерванную firmware операцию после проверки отсутствия running updater и повторного подтверждения оператора; pending component update так не обходится. Firmware backup/rollback невозможен средствами NLI: previous hardware firmware и bootloader не обещаются восстановимыми.

Ни одна из этих команд не запускалась на реальных WB в рамках #70; automated tests используют только fake backend/runner. Параллельные сторонние root-запуски должны быть исключены организационно, см. SECURITY.md.
