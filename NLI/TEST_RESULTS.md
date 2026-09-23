# Проверки NLI v0.1

[Проверено локально, 24.09.2026] Windows, Python 3.12 (bundled runtime), Node.js. Все NLI тесты изолированы TemporaryDirectory/fake WB; live deploy/SSH/physical commands не выполнялись.

| Проверка | Результат |
|---|---|
| Python unittest | 50 tests: 49 PASS, 1 SKIP (Windows symlink privilege) |
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

[Не проверено локально] В Windows нет WSL/dpkg-deb. Workflow `NLI v0.1` выполняет Linux symlink test, `dpkg-deb --info/--contents` и установку в disposable Debian Trixie container. Фактический результат CI будет дополнен после push. Никакая проверка не является доказательством реального WB runtime, физического тепла, bootloader recovery или полевого принятия.

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
