# Обёртка штатного WB firmware updater

Изучены официальные [CLI](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb-mcu-fw-updater), [update_monitor.py](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb_mcu_fw_updater/update_monitor.py) и [package init](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/wb_mcu_fw_updater/__init__.py), чтение 24.09.2026. Git blob CLI на момент анализа: `91d705e6de165970d5a87669b34c7ed9c282364f`. Это исследование источника, не утверждение об установленной версии на WB.

`update-all` обновляет firmware и может обновлять bootloader, затем восстанавливать application firmware. В актуальной реализации отдельный путь `decide_bootloader_action` выбирает такой update; recovery внутри массового update также может проверить bootloader. `recover-all` восстанавливает firmware устройств в bootloader через штатную recovery logic. `--force` автоматически отвечает Yes, поэтому NLI его не использует. `--allow-downgrade`, erase settings, прямой `update-bl` и собственный flasher в NLI отсутствуют.

При default pyserial backend штатная утилита может приостановить пользователей serial ports (`SIGSTOP`) и возобновить их через atexit (`SIGCONT`). NLI не маскирует это как безостановочную операцию. Потеря питания/SIGKILL upstream может не выполнить atexit: инженер должен проверить драйвер/связь, не запускать следующий updater вслепую. NLI сам не останавливает wb-mqtt-serial для component update.

## Check

`nli firmware check` определяет supported version/CLI без ручных pins, читает наличие `/usr/bin/wb-mcu-fw-updater`, package version через dpkg-query, hash script и наличие известных command names; проверяет `/proc` на текущий updater/flasher. Не запускает и не импортирует updater, даже для help. В исследованном CLI нет inventory/dry-run. Library `probe_all_devices` обращается к Modbus; поиск UART settings и firmware helpers не имеют достаточного чистого read-only контракта для NLI. Поэтому результат **unavailable**, exit 3, compatibility=supported при прошедшей policy: список доступных обновлений неизвестен. Это не «все устройства актуальны» и не ошибка отопления. Новый доказуемо read-only API требует отдельного audited adapter.

## Update / recover

NLI 0.1.8 содержит reviewed policy: package version **1.16.0**, executable Git blob
`91d705e6de165970d5a87669b34c7ed9c282364f` из официального upstream CLI.
Допускаются штатные Debian shebang rewrite `#!/usr/bin/python3` и
`#! /usr/bin/python3`; перед проверкой Git blob они нормализуются к upstream
`#!/usr/bin/env python3`. Проверяются dpkg package ownership и runtime-часть
`dpkg --verify wb-mcu-fw-updater` (включая package modules). Расхождения только
в `/usr/share/doc/wb-mcu-fw-updater/` не блокируют firmware policy, потому что
не участвуют в выполнении updater; любые runtime-расхождения по-прежнему
блокируются. Подмена executable/изменённый runtime package блокируются.
Object pins approved_executable_sha256 / approved_package_version больше не нужны
и не используются; старые поля config можно оставить до отдельного review config.
Неизвестная новая/старая version блокируется: поддержку добавляют выпуском NLI,
оператор получает `nli self-update`, а не требование вручную вписать hash.

Проверка совместимости не доказывает функциональную пригодность firmware для
конкретного объекта. Поддерживается только reviewed CLI `update-all` / `recover-all`
с `--debug`; автоматические ответы/force/allow-downgrade не добавляются.
Исследование source не является live test установленного updater.

Команда требует interactive stdin, показывает bootloader/serial notice, просит ввести `firmware-update` либо `firmware-recover`. Затем сохраняются интерактивные вопросы официального CLI; NLI не отвечает на них. Prompt без newline пересылается по chunks, чтобы оператор его видел. Весь stdout/stderr updater сохраняется в transaction transcript с fsync; native лог по устройствам доступен даже если parser не знает новый формат.

Exit 0 upstream недостаточен: текущая batch implementation может завершиться с нулевым кодом при оставшихся failed devices. NLI разбирает итоговые counts, выделяет строки devices и возвращает partial_failure для disconnected/stuck/not recovered/skipped/unsupported; неизвестный summary — unverified, не success. stdout/stderr и transcript являются источником подробностей.

Ctrl-C получает upstream; NLI держит lock до завершения дочернего процесса, не убивает flasher по timeout и не запускает автоматический retry. При собственном SIGTERM родитель ждёт child, чтобы не освободить lock посреди flash. SIGKILL/power loss оставляет pending. `firmware recover` может явно продолжить прерванную firmware операцию после проверки отсутствия running updater и повторного подтверждения оператора; pending component update так не обходится. Firmware backup/rollback невозможен средствами NLI: previous hardware firmware и bootloader не обещаются восстановимыми.

Ни одна из этих команд не запускалась на реальных WB в рамках #70; automated tests используют только fake backend/runner. Параллельные сторонние root-запуски должны быть исключены организационно, см. SECURITY.md.

В 0.1.8 partial/unverified summary сохраняет durable firmware pending, а не только
журнал; продолжение через explicit firmware recover. Только verified success
очищает pending и запускает retention. Успешные transcripts ограничены 20 на
компонент; failed/partial/recovery evidence сохраняется. Bootloader behavior 1.16.0
описан в [официальном changelog](https://github.com/wirenboard/wb-mcu-fw-updater/blob/master/debian/changelog).
