# Проверки NLI v0.1

## 0.1.1 — полевые WB-блокеры PR #71

[Проверено локально, 24.09.2026] 76 Python tests: 56 PASS, 20 SKIP
(19 тестов canonical WB symlink layout и прежний symlink test требуют Linux/
Windows symlink privilege). Исходные 51 тест сохранены; изменены только пути
durable NLI data. Exact Git blob sandbox boiler/gazebo PASS, сборка 0.1.1 и
reproducibility/layout проверки PASS. HHM: 67 main + 10 partial-ready groups,
PersistentStorage 18+505 и manifest 33 files PASS. Изменений HHM/507 нет.

Новые unit cases проверяют canonical roots, literal wrong/relative/chained
targets, nested symlink file/directory, symlink managed file, missing persistent
target, traversal, drift, реальные изменённые bytes после update и восстановление
mode/uid/gid после rollback. Весь HHM suite повторяется на WB layout, включая
строгий unmanaged inventory, untouched 507 и preflight/rollback failures.
Проверены no-write default config, приоритет persistent config, missing/corrupt
config, запрет silent legacy fallback и повторное открытие pending/backup/audit.

CI workflow дополнительно выполняет реальную установку `.deb` в disposable
Debian Trixie c WB `path-exclude /usr/share/doc/*`: upgrade 0.1.0 → 0.1.1,
сохранность modified obsolete conffile, bootstrap из **установленных** runtime
examples без Git checkout, canonical links, exact HHM blobs, fake WB services,
строгий ownership gate, update/rollback. Reinstall сравнивает hash/mode/uid/gid
всех `/mnt/data` файлов, включая config/pins/state/backups/pending/audit. Второй
чистый container с тем же `/mnt/data` моделирует потерю rootfs/FIT и проверяет
reuse данных и явное восстановление pending через fake backend.

Результат CI **итогового HEAD**, имя artifact `neiro-nli-0.1.1-deb` и SHA256
конкретного `neiro-nli_0.1.1_all.deb` публикуются в [PR #71](https://github.com/psv76/Neirolinks/pull/71).
Локальная Windows-сборка не подменяет CI artifact. Полевая проверка 0.1.1 и
реальный FIT не выполнялись. Второй read-only smoke: [WB_SMOKE.md](WB_SMOKE.md).

## Исторические проверки 0.1.0

[Проверено локально, 24.09.2026] Windows, Python 3.12 (bundled runtime), Node.js. Все NLI тесты изолированы TemporaryDirectory/fake WB; live deploy/SSH/physical commands не выполнялись.

| Проверка | Результат |
|---|---|
| Python unittest | 51 tests: 50 PASS, 1 SKIP (Windows symlink privilege) |
| Sandbox CLI на exact Git blobs PR #65 | boiler и gazebo: status/check/update/verify/rollback PASS |
| Firmware check | unavailable/exit 3, без disk writes и updater execution |
| Firmware wrapper update/recover | fake runner PASS для обеих ролей, partial failures/unknown summary/Ctrl-C recovery проверены |
| Crash after replacement | отдельный subprocess exit 73, durable pending, explicit rollback PASS |
| Lock | два независимых процесса, exclusive mutation PASS |
| Debian package | собран; ar/tar layout, permissions, no service hooks и повторная идентичная сборка PASS |
| HHM main regression | 67 groups PASS |
| HHM partial-ready | 10 groups PASS |
| HHM PersistentStorage | 18+505 PASS |
| HHM existing manifest | 33 files PASS, aggregate `74be3523fce1f2ed4db442c764597c6446f4660716078d52329ed76b1bdc990f` |
| Existing 502 installer shell syntax | bash -n PASS; installer не изменён |
| Whitespace | git diff --check PASS |

Core coverage: malformed/duplicate manifest fields, unknown component, role/hostname, mutable release, checksums, offline/interrupted download, before-mutation drift/interlock failure, stop/start/install/verify failures, automatic rollback, corrupted backup/metadata, previous release chain, crash recovery, path traversal, local target allowlist, concurrent processes.

HHM coverage: 507 byte-preservation and exclusion from backup, pressure not gate, active/unknown makeup and A04 block, interlock recheck after download, strict role payload separation, local writer inventory, fresh frame/runtime journal failure, read-only verify, conditional 3.1 health attestation.

[Проверено в Linux CI] [Run 35919438626](https://github.com/psv76/Neirolinks/actions/runs/35919438626), commit `13837f95bd0deaa3698debd24c9a1bfe0dff5e27`: SUCCESS. Python 3.13: все 50 тестов того commit PASS, включая symlink; sandbox обеих ролей PASS; `dpkg-deb --info/--contents` PASS; установка в disposable Debian Trixie через apt PASS, `/usr/bin/nli --version` и `nli --json status` PASS, read-only status не создал `/var/lib/neiro/nli` и `/var/log/neiro/nli`. Сохранён CI artifact `neiro-nli-deb`.

После этого добавлены явная зависимость `ca-certificates` и тест hostname gate firmware; актуальный suite содержит 51 тест. Статус проверки итогового SHA опубликован в [draft PR #71](https://github.com/psv76/Neirolinks/pull/71). Первая CI установка выявила отсутствующие directory entries в Debian data tar; исправлено, regression проверяет все parent directories.

[Не проверено] Реальный WB runtime, физическое тепло, bootloader recovery и полевое принятие. В Windows нет WSL/dpkg-deb; проверка настоящей Debian установки выполнена только в изолированном CI container.

Команды:

```sh
python3 -B -m unittest discover -s NLI/tests -v
python3 -B NLI/tests/sandbox.py
python3 -B NLI/tools/build_deb.py
node objects/05_31_Ivolga_13/HHM3_FSE/tests/run.js
node objects/05_31_Ivolga_13/HHM3_FSE/tests/partial-ready-regressions.js
node objects/05_31_Ivolga_13/HHM3_FSE/tests/persistent-storage-regressions.js
node objects/05_31_Ivolga_13/HHM3_FSE/tests/manifest.js --check
```
