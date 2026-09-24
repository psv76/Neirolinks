# NLI 0.1.5: bootstrap и восстановление после FIT

Для уже настроенного boiler после smoke 0.1.1 использовать [PRESSURE_MAKEUP.md](PRESSURE_MAKEUP.md): сохранить существующий config/allowlist, явно зарегистрировать pressure_makeup, затем check hhm и check pressure_makeup. Ниже — только первоначальный bootstrap при отсутствии config.

Это runbook для отдельного согласованного полевого окна, а не автоматический deploy.
Пакет не устанавливает HHM, не содержит maintainer scripts и не перезапускает сервисы.
Smoke заканчивается на **read-only `nli check hhm`, затем `nli check pressure_makeup`**. Не выполнять update,
rollback, firmware update/recover или restart в рамках этого smoke.

## Проверка пакета и upgrade 0.1.0 → 0.1.5

Использовать `neiro-nli_0.1.5_all.deb` из artifact `neiro-nli-0.1.5-deb`
конкретного зелёного CI run, указанного вместе с SHA256 в PR #71. Сначала
сверить SHA256 с независимым значением в PR; checksum-файл рядом с пакетом
сам по себе не доказывает происхождение. Команды ниже выполнять в каталоге
с обоими проверенными файлами, от root (или через sudo для install/apt).

```sh
sha256sum -c neiro-nli_0.1.5_all.deb.sha256
test "$(hostname)" = wirenboard-ABF62SL
test "$(readlink /etc/wb-rules)" = /mnt/data/etc/wb-rules
test "$(readlink /etc/wb-rules-modules)" = /mnt/data/etc/wb-rules-modules
findmnt /mnt/data
systemctl show wb-rules wb-mqtt-serial -p Id -p ActiveEnterTimestampMonotonic
apt install ./neiro-nli_0.1.5_all.deb
nli --version
nli --json status
systemctl show wb-rules wb-mqtt-serial -p Id -p ActiveEnterTimestampMonotonic
test -r /usr/share/neiro-nli/examples/config-boiler.json
test -r /usr/share/neiro-nli/examples/hhm-boiler-3.0.json
test -r /usr/share/neiro-nli/manifest.schema.json
```

Ожидание: версия `0.1.5`, status `ok`, timestamps сервисов не изменились.
На ещё не настроенном NLI команды status/check/verify/firmware check не создают
`/mnt/data/etc/neiro/nli`, `/mnt/data/var/lib/neiro/nli`, `/mnt/data/var/log/neiro/nli`.
Проверить отсутствие этих каталогов **до bootstrap**, если их не было до upgrade.
`check/verify hhm` без конфигурации завершаются ошибкой, а не создают её.

## Первый bootstrap из установленного пакета

Применять только если persistent config отсутствует и нет старых настроенных
данных NLI. Если config/state уже существуют, сохранить их и перейти к проверке,
**не копировать поверх**. При `LEGACY_MIGRATION_REQUIRED` сначала выполнить
reviewed migration из раздела ниже. Выполнять блок с `set -e`, чтобы любой
неуспешный guard остановил копирование.

```sh
set -e
test ! -e /mnt/data/etc/neiro/nli/config.json
test ! -e /mnt/data/var/lib/neiro/nli
test ! -e /mnt/data/var/log/neiro/nli
install -d -m 0755 /mnt/data/etc/neiro/nli/releases
test ! -e /mnt/data/etc/neiro/nli/releases/hhm-boiler-3.0.json
install -m 0644 /usr/share/neiro-nli/examples/hhm-boiler-3.0.json /mnt/data/etc/neiro/nli/releases/hhm-boiler-3.0.json
test ! -e /mnt/data/etc/neiro/nli/releases/pressure-makeup-boiler-1.0.json
install -m 0644 /usr/share/neiro-nli/examples/pressure-makeup-boiler-1.0.json /mnt/data/etc/neiro/nli/releases/pressure-makeup-boiler-1.0.json
install -m 0600 /usr/share/neiro-nli/examples/config-boiler.json /mnt/data/etc/neiro/nli/config.json
sha256sum /mnt/data/etc/neiro/nli/releases/hhm-boiler-3.0.json
```

Manifest SHA256: `1fb788c6c848cb12f23d81d5bcb93982587fe953e719d3dc2b00ba3a8d202630`.
Config уже задаёт `05_31_Ivolga_13`, `boiler`, `wirenboard-ABF62SL`;
baseline = target = exact HHM `3.0.0-FSE+d75710dad939`, commit
`d75710dad93906af8869dcce48d26e14673b63fb`. Это не HHM 3.1.
Второй manifest задаёт baseline=target pressure_makeup `1.0`; его hash и
provenance описаны в [PRESSURE_MAKEUP.md](PRESSURE_MAKEUP.md).

Инженер должен прочитать и проверить все unmanaged JS в обоих каталогах
правил/modules, затем вручную записать проверенные логические `/etc/...` paths
и SHA256 в `components.hhm.unmanaged_rules` persistent config. Пустой allowlist
на реальном объекте ожидаемо блокирует посторонние writers, включая 506; 507 уже принадлежит pressure_makeup.
Не генерировать доверенный список автоматически и не добавлять hash только ради
прохождения check. HHM читает 507 для inventory, но не изменяет и не backup-ит его. Отдельный pressure_makeup обслуживает только 507.

```sh
nli --json status
nli --json check hhm
nli --json check pressure_makeup
```

Ожидание после review: `preflight=ok`, `final_status=ok`, exit 0, нет новых
state/log/lock файлов. Check скачивает immutable payload в память, требует сеть
к raw.githubusercontent.com и проверяет SHA, exact live bytes, ownership,
hostname, runtime prerequisites и OFF interlocks. Любой drift/unknown writer/
неподтверждённый OFF/ошибка сети — STOP и разбор причины, без обхода gate.
Сохранить stdout/stderr и коды возврата для отчёта; не запускать update.

## Persistence, conffiles и FIT

| Данные | Расположение |
|---|---|
| Config и pinned manifests | `/mnt/data/etc/neiro/nli/` |
| Installed state, pending, backups, lock | `/mnt/data/var/lib/neiro/nli/` |
| Audit и raw firmware transcripts | `/mnt/data/var/log/neiro/nli/` |
| Переустанавливаемый executable/modules | `/usr/bin/nli`, `/usr/lib/neiro-nli/` |
| Переустанавливаемые runtime examples/schema/runbook | `/usr/share/neiro-nli/` |

NLI 0.1.5 не содержит conffiles: config создаётся инженером, хранится отдельно
и не принадлежит dpkg. `apt install --reinstall` и удаление пакета не стирают
persistent config/pins/history. Старый conffile 0.1.0 `/etc/neiro/nli/config.json`
может остаться как obsolete conffile dpkg; NLI игнорирует только его точное
штатное `unconfigured` содержимое. Пакет не удаляет и не мигрирует этот файл.

FIT может удалить **executable**, modules, runtime examples и запись пакета из
rootfs. NLI не обещает, что сам исполняемый файл переживает FIT. Перед FIT:
сохранить проверенные `.deb` и SHA256 в `/mnt/data/neiro/nli-bootstrap/` и
внешнюю резервную копию durable NLI data; заранее обеспечить совместимый Python
и Debian dependencies после firmware update. Это отдельная операция инженера.
После FIT проверить mounted `/mnt/data`, canonical links и прежний hostname;
переустановить проверенный пакет, не выполнять bootstrap поверх config:

```sh
cd /mnt/data/neiro/nli-bootstrap
sha256sum -c neiro-nli_0.1.5_all.deb.sha256
apt install --reinstall ./neiro-nli_0.1.5_all.deb
nli --version
nli --json status
```

NLI автоматически читает прежний config/state/history. При pending сообщает
`recovery_required`; не удалять pending, не считать reinstall восстановлением
HHM. Rollback — отдельное согласованное действие после разбора причины и
проверки interlocks. Отсутствующий config при наличии pins/state/logs — ошибка,
а не новый пустой профиль. CI моделирует потерю rootfs свежим Debian container
с тем же `/mnt/data`, а не настоящим FIT на WB.

## Если 0.1.0 уже был настроен

Зафиксированный полевой smoke остановился до настройки; для него миграция
данных не требуется. Если на другом контроллере есть настроенный старый
`/etc/neiro/nli/config.json`, `/var/lib/neiro/nli` или `/var/log/neiro/nli`, NLI
0.1.5 выдаёт `LEGACY_MIGRATION_REQUIRED` до bootstrap. Инженер отдельно:

1. Исключает конкурирующий процесс NLI, сохраняет внешнюю копию всех трёх
   каталогов вместе с metadata; проверяет отсутствие конфликтующих persistent
   данных. Не объединяет две истории и не удаляет pending.
2. Копирует config/releases, state/backups/pending и audit в соответствующие
   `/mnt/data/...` каталоги с сохранением bytes/mode/uid/gid. В config меняет
   пути baseline/target на persistent paths, сохраняя hash самих manifests.
3. Проверяет pinned hashes и все backup metadata/blob hashes, права доступа;
   использует status для проверки сохранённой версии, pending и истории.
   Старые audit records сохраняются дословно, включая исторические пути.

При существующем persistent config он имеет приоритет. `--config` допускает
только пути внутри `/mnt/data/etc/neiro/nli/`. Обновление live HHM и восстановление
незавершённой старой транзакции не входят во второй read-only smoke.
