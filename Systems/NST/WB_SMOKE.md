# Проверка NST 2.0 на disposable rootfs

Не запускать CI smoke scripts на физическом WB. Scripts требуют `/.dockerenv` и специальную переменную CI.

- `tests/wb_clean_smoke.sh`: rootfs без NLI, установка реального `.deb`, hardware serial fixture, approved registry/deployment fixture, bootstrap config/components/object files, status/check/exact state. WB backend синтетический; физические сервисы не вызываются.
- `tests/wb_package_smoke.sh first`: историческая цепочка пакетов до NLI 0.1.9, реальные persistent config/state/backup/pending/audit, установка NST, явная миграция и проверка hashes/metadata.
- `tests/wb_package_smoke.sh fit`: новый rootfs с прежним `/mnt/data`, установка NST и rollback старой NLI точки.

Linux workflow запускает эти сценарии независимо, сохраняя regression/security/FIT проверки. Live Иволга не используется. Это проверка установки и восстановления, а не аппаратная приёмка WB.
