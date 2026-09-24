# Проверки NLI v0.1

## 0.1.3 — scoped standalone verify

[Проверено локально, 24.09.2026] 125 Python tests: 88 PASS, 37 SKIP
(Windows symlink privilege). Добавлены timestamped journal regressions для обоих
plugins: старая ERROR history не мешает standalone verify; каждый из шести
error patterns, возникший после начала file/runtime probes, блокирует verify;
здоровый давно запущенный 507 не требует нового startup marker. Для update
каждый pattern после restart вызывает rollback; rollback получает отдельную
новую границу и не наследует ошибки неуспешного update. Ошибки после explicit
rollback оставляют partial_failure/pending. Startup marker после restart
по-прежнему обязателен. Journal без явной границы fails closed, без systemctl
activation lookup. Standalone не создаёт state/log и не вызывает services.

CI также проверяет реальные upgrades 0.1.0 → 0.1.1 → 0.1.2 → 0.1.3, nodoc,
оба установленных компонента, сохранность config/state при reinstall и FIT
simulation. Итоговый green run/HEAD, artifact `neiro-nli-0.1.3-deb` и точный
SHA256 `.deb` публикуются в [PR #71](https://github.com/psv76/Neirolinks/pull/71).
Live WB не затрагивается; scoped verify не заменяет физическую приёмку и не
является мониторингом ошибок после завершения команды.

## 0.1.2 — самостоятельный pressure_makeup

[Проверено локально, 24.09.2026] 117 Python tests: 80 PASS, 37 SKIP
(Windows symlink privilege). Исходные 76 NLI/WB tests сохранены. Добавлены
standalone check/update/verify/rollback 507, exact no-final-LF baseline,
checksum/drift peer-компонентов, managed/unmanaged conflict, запрет HHM claim
507/A04, односторонние backup/rollback, accepted restart resets/normal ON,
runtime marker/controls/journal failures и config-only migration с сохранением
прочих reviewed entries. Весь component suite повторяется с canonical WB links.

Node VM исполняет exact baseline с fake dev/timers: 3 группы PASS (reset counters/
alarms, init OFF → ordinary evaluate ON, повторное возникновение alarms по inputs).
Никакой PersistentStorage для runtime полей не добавлено. HHM 67 main + 10
partial-ready групп, PersistentStorage 18+505, manifest 33 files PASS. Sandbox
boiler/gazebo PASS. Объектный 507, HHM и legacy installers не изменены.

[Linux CI 35971892009](https://github.com/psv76/Neirolinks/actions/runs/35971892009)
на checkpoint `0fc4b2099a91591d04d939c4358ee07557ddbc44` — SUCCESS: все 111
тестов того commit без skips; Node/HHM regressions; actual installed two-component
bootstrap/config migration, nodoc, independent update/rollback через fake WB,
reinstall и FIT simulation с сохранением config/pins/state/backups/pending/audit.
После checkpoint добавлены ещё 6 peer/standalone/restart tests и промежуточный
реальный upgrade 0.1.1 в CI цепочку 0.1.0 → 0.1.1 → 0.1.2.

Green CI **итогового HEAD**, artifact `neiro-nli-0.1.2-deb` и SHA256 конкретного
`neiro-nli_0.1.2_all.deb` публикуются в [PR #71](https://github.com/psv76/Neirolinks/pull/71).
Live WB не затрагивался. Следующий read-only smoke выполняется инженером по
[PRESSURE_MAKEUP.md](PRESSURE_MAKEUP.md): check hhm, затем check pressure_makeup.

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
Первый [Linux run 35963332056](https://github.com/psv76/Neirolinks/actions/runs/35963332056)
подтвердил все 76 unit tests без skips, HHM regressions и Debian upgrade/nodoc;
installed smoke обнаружил ошибку fixture: после review allowlist она повторно
использовала старый in-memory config. Исправлено повторным load_config как при
новом запуске CLI; ownership gate не изменён.
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
