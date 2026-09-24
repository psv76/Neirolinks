# NLI 0.1 — NEIROLINKS Installer / Updater

Постоянная Python 3 утилита обслуживания Wiren Board. Задача [#70](https://github.com/psv76/Neirolinks/issues/70), включая уточнение от 24.09.2026. NLI не запускается как daemon и не нужен отоплению во время работы. Нет SSH, cron, команд насосам/клапанам/OT, записи уставок или PersistentStorage.

## Границы выпуска

Поддерживается точный комплект HHM `3.0.0-FSE` Иволги из PR #65, commit `d75710dad93906af8869dcce48d26e14673b63fb`, отдельно для boiler/gazebo. Примеры manifest получены из Git blobs, а не Windows checkout: SHA проверяет **точные байты**, без нормализации скачанного payload.

[#68](https://github.com/psv76/Neirolinks/issues/68) создаёт будущий HHM 3.1; [#69](https://github.com/psv76/Neirolinks/issues/69) меняет observability; NLI не реализует эти отдельные изменения алгоритма. Для 3.1+ обязательно `health_contract=m1w2-health-v1` и read-only runtime control `*/sensor_health_contract` с таким значением в `verify.controls`. Это интеграционный контракт будущего manifest: текущий 3.0 такой контроль не имеет и не объявляется 3.1. Автор #68 должен предоставить проверенный manifest/контроль либо отдельную reviewed адаптацию plugin к фактическому контракту #68.

Полевые условия и физическая приёмка [#20](https://github.com/psv76/Neirolinks/issues/20) остаются отдельной работой. PASS тестов NLI не доказывает ход штока, проток, тепло или морозозащиту.

## Сборка и установка самой утилиты

На машине разработки, из корня репозитория:

```sh
python3 -B -m unittest discover -s NLI/tests -v
python3 -B NLI/tests/sandbox.py
python3 -B NLI/tools/build_deb.py
(cd NLI/dist && sha256sum -c neiro-nli_0.1.2_all.deb.sha256)
dpkg-deb --info NLI/dist/neiro-nli_0.1.2_all.deb
```

Build использует только stdlib; создаёт воспроизводимый Debian ar с control/data tar.gz, root ownership и `/usr/bin/nli` mode 0755. `SOURCE_DATE_EPOCH` задаёт timestamp (по умолчанию 0). Нет maintainer scripts, service units, restart при установке или зависимости HHM от пакета. CI проверяет `dpkg-deb` и установку в одноразовом Debian Trixie container.

В тестовом Debian/WB-окружении после проверки происхождения пакета:

```sh
sudo apt install ./neiro-nli_0.1.2_all.deb
nli --version
nli status
```

Пакет устанавливает Python sources в `/usr/lib/neiro-nli`, примеры в `/usr/share/neiro-nli/examples`, schema и bootstrap runbook в `/usr/share/neiro-nli/`. Они доступны при WB dpkg `path-exclude /usr/share/doc/*`. Config `/mnt/data/etc/neiro/nli/config.json` создаётся инженером и **не принадлежит пакету**; conffiles/maintainer scripts в 0.1.2 отсутствуют. Пока config не создан, CLI читает packaged `default-config.json` без записи на диск. При существующих данных и потерянном config либо настроенных старых данных 0.1.0 CLI требует разбор/миграцию, а не создаёт пустой профиль. HHM payload пакет **не устанавливает**. Библиотеки Python кроме stdlib не требуются. `systemd`/`mosquitto-clients` нужны только для WB probes/service actions. Штатный firmware updater — отдельный suggested пакет.

Полевой bootstrap, upgrade 0.1.0, conffile policy и переустановка после FIT: [WB_SMOKE.md](WB_SMOKE.md). После FIT executable/modules могут исчезнуть; переустановка `.deb` подхватывает persistent config/pins/state/backups/pending/audit. Это проверяется заменой rootfs в CI, не является утверждением о выполненной проверке FIT на реальном WB.

## Конфигурация и первичная миграция HHM

1. Сопоставить объект, фактический hostname и роль с `examples/config-boiler.json` или `config-gazebo.json`. Boiler hostname подтверждён installer-ами; hostname gazebo нужно получить на тестовом/целевом WB, он намеренно не выдуман. Изменение config выполняет инженер в отдельном согласованном окне.
2. Поместить проверенные manifest в `/mnt/data/etc/neiro/nli/releases/`, закрепить их SHA256 в `baseline` и `target`. Пример первоначально использует один и тот же релиз: это adoption точной установленной 3.0-базы с backup, а не обещание уже готовой 3.1.
3. Сверить все существующие JS в `/etc/wb-rules` и `/etc/wb-rules-modules`. В `unmanaged_rules` перечислить абсолютный путь → SHA256 **каждого** проверенного файла вне managed payload, включая 506/507 и чужие modules. Не генерировать allowlist вслепую: его смысл — review ownership. Неизвестный или изменённый JS блокирует check/update/verify; NLI не отключает такие файлы автоматически.
4. `nli check hhm` требует точного baseline. Отсутствующий/неизвестный live-файл — blocker, даже если его имя знакомо. При первоначальном внедрении HHM на пустом WB требуется отдельная процедура ПНР; NLI v0.1 обслуживает уже проверенный установленный HHM. Перенос старых HM2 writers и MQTT ACL не выполняется автоматически.
5. Согласовать окно: restart `wb-rules` влияет также на 507, хотя его файл не меняется. Перед остановкой: `pressure_makeup/active=0`, `A04/K1=0`, active `wb-mqtt-serial`, доступный wb-rules >=2.42.0, роли/файлы/ownership проверены. Значение давления не является gate. Беседка не владеет A04 и не опрашивает чужую подпитку.

Полный managed payload boiler: 500, 620, 600 и шесть HHM3 modules. Gazebo: 624 и HHM3Config/HHM3Wire/HHM3Runtime. 507, OT config, MQTT bridge, ACL, WebUI/Sprut config не входят в managed set. Файлы сохраняются и заменяются по одному атомарно при остановленном wb-rules.

Штатные WB links `/etc/wb-rules → /mnt/data/etc/wb-rules` и `/etc/wb-rules-modules → /mnt/data/etc/wb-rules-modules` разрешены только при точном абсолютном target. Manifests/backup metadata сохраняют логические `/etc/...` paths; чтение, backup и atomic replacement идут по persistent bytes. Другие links, junctions, ссылки внутри этих деревьев и traversal запрещены. Обычные каталоги поддерживаются для non-WB sandbox.

## Релизы

```sh
python3 -B NLI/tools/prepare_hhm.py \
  --commit d75710dad93906af8869dcce48d26e14673b63fb \
  --role boiler --output NLI/build/hhm
```

Это инструмент упаковки на developer machine. Он извлекает только роль из immutable Git blobs и проверяет текущую 3.0-версию; не подключается к WB. Повторить для gazebo. Для следующего 3.0 выпуска достаточно нового manifest/SHA, без нового installer script. Будущий 3.1 manifest должен содержать его реальный verify contract; legacy importer намеренно не придумывает его.

По умолчанию artifacts читаются только с `raw.githubusercontent.com/<repository>/<40-char-commit>/<source>`, проверяются SHA256 и размер. Redirect запрещён. Manifest сам по сети не подменяется: путь и hash задаёт локальная конфигурация инженера. Для offline bundles указать `payload_dir`, например `/opt/neiro/releases/release-123/payload`, сохранив относительные `source` пути. Содержимое проверяется теми же SHA. Нет GitHub credentials в NLI.

`manifest.schema.json` описывает структуру; `nli.manifest.validate` дополнительно проверяет path traversal, повторы, balanced services, допустимые actions. Trusted plugin проверяет объект/роль/файлы/контракт и не позволяет manifest ослабить HHM gates. В v0.1 набор managed paths между baseline и target должен совпадать: добавление/удаление файла требует отдельной reviewed migration policy.

`examples/notifications.json` — будущий generic files component, пока не настоящий опубликованный release. Регистрация `plugin=files`, `allowed_targets=[...]`, baseline/target pins; только `/etc/neiro/components/<component>/`, без services и shell hooks. Для webui/serial/packages понадобится новый reviewed Python policy, использующий тот же transaction engine; собственный apt/dpkg replacement не предусмотрен.

## CLI

```sh
nli status
nli check hhm
sudo nli update hhm
nli verify hhm
sudo nli rollback hhm
nli firmware check
sudo nli firmware update
sudo nli firmware recover
nli --json status
nli --config /mnt/data/etc/neiro/nli/config.json --json check hhm
```

`status/check/verify/firmware check` не создают lock/cache/state/history/pyc; результат только stdout/stderr. `check` проверяет preflight и payload в памяти, ничего не устанавливает. `verify` сверяет installed manifest (либо pinned baseline при первом внедрении), exact hashes/version, active services, fresh role frame, required controls, ownership inventory и ошибки журнала с последнего запуска wb-rules. Данные MQTT не доказывают физическую работу. Исторические runtime ошибки с момента активации дают conservative failure и требуют разбора инженером.

Update: preflight → managed backup → artifact checksum → повторный preflight → stop → atomic install → start/active → runtime verify → state/audit success. HHM останавливает только wb-rules, не wb-mqtt-serial. Postverify входит в транзакцию: ошибка вызывает rollback, а не предупреждение после success.

Rollback показывает `to_version`, проверяет SHA backup/metadata и текущий drift, проходит interlocks, останавливает services, восстанавливает только предыдущие managed bytes/mode/uid/gid, запускает и проверяет предыдущий manifest. Несколько successful updates сохраняют цепочку предыдущих релизов. Без previous release возвращается явная ошибка. Нет произвольного restore `/etc`, retained MQTT, PersistentStorage или команды `start_heating`.

Exit codes: 0 — success; 1 — failed/rolled_back/partial_failure/recovery_required; 3 — firmware inventory unavailable, честный результат без probing/flashing.

Пример sandbox adoption:

```text
NLI 0.1.2
object: 05_31_Ivolga_13
role: boiler
command: update
component: hhm
from_version: 3.0.0-FSE+d75710dad939
to_version: 3.0.0-FSE+d75710dad939
preflight: ok
backup: {'id': '<transaction-id>', 'metadata_sha256': '<sha256>'}
install: ok
verify: ok
rollback: not_run
RESULT: ok
```

## Audit, crash и восстановление

Mutation lock: `/mnt/data/var/lib/neiro/nli/mutation.lock`, kernel advisory lock; файл не удаляется. Crash автоматически освобождает lock. Before-action intent синхронно сохраняется в `pending.json` и `/mnt/data/var/log/neiro/nli/<id>.json`; каждый stop/start имеет intent/result, включая failure. Backup: `/mnt/data/var/lib/neiro/nli/backups/<id>/`, version/commit/current/target manifest, hashes, metadata. Для firmware сохраняется также raw per-device transcript. Никаких logs от read-only команд.

Ctrl-C update вызывает автоматический rollback. SIGKILL/power loss не может быть обработан программой: `status` показывает pending и `recovery_required`, новые updates запрещены. После устранения причины оператор запускает `nli rollback hhm`; проверяются interlocks и backup, допускается уже остановленный wb-rules и частично заменённый payload. Если backup/interlocks/verify не проходят, сохраняется `partial_failure`, без скрытого success. Инженер обеспечивает безопасное состояние объекта отдельно; NLI не делает физические команды в аварии. Не удалять `pending.json` ради обхода проверки.

Нет автоматического pruning backup/audit в v0.1. Планировать свободное место и хранение журналов; backup failure до остановки не затрагивает автоматику. При заполнении диска durable pending остаётся сигналом незавершённой операции.

Подробнее: [безопасность](SECURITY.md), [firmware](FIRMWARE.md), [результаты тестов](TEST_RESULTS.md).

## Переход от installer scripts

После принятия NLI и полевой проверки legacy становятся `install_502_readback_fix.sh`, `install_620_current_state_bool_fix.sh`, `install_hhm3_ui_cleanup.sh`, `install_hhm3_ui_cleanup_v2.sh`, `install_hhm3_legacy_json_purge.sh`, `install_diagnostics_feed_fix.sh` из HHM3_FSE/tools. Они сохраняются без изменений. Старый cold-slab HM2 installer относится к другой исторической системе и не является способом обновления HHM3 через NLI.

Унаследованные semantic-only base checks, предупреждения после успешного install и rollback без preflight не копируются: NLI требует exact reviewed hashes и включает verify/rollback в транзакцию. Текущий INSTALL PR #65 содержит исторические инструкции; для NLI используются этот manifest и runbook. Это не разрешение на live deployment.
