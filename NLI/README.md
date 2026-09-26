# NLI 0.1.8 — NEIROLINKS Installer / Updater

NLI устанавливает release, а не проверяет алгоритмы отопления. Нет daemon/cron,
автоматического ночного update или runtime dependency HHM. Задача #74 продолжает
принятый #70 / PR #71; HHM algorithms, 507 и #68 не изменяются.


## Операционная политика deployment

С 26.09.2026 NLI принят как штатный installer/updater для **всех управляемых WB NEIROLINKS**.
Новые controlled deployments и последующие обновления managed components выполняются
через NLI после reviewed initial adoption конкретного контроллера. Ручная замена
managed JS-файлов не является нормальным способом обновления и допускается только
как отдельно согласованная recovery/аварийная процедура.

Первичная установка NLI сама по себе не регистрирует текущие файлы как доверенный
baseline: existing live bytes и unmanaged rules сначала инвентаризируются и review,
после чего фиксируются exact manifest/config. Нельзя автоматически доверять
неизвестным файлам только потому, что они уже находятся на контроллере.

## Первичная установка NLI

На контроллере, где NLI ещё нет или runtime NLI потерян после FIT, используется
standalone bootstrap из **фиксированного published approved release**, а не
Actions artifact и не mutable `main`:

```sh
python3 -c "import urllib.request; exec(urllib.request.urlopen('https://github.com/psv76/Neirolinks/releases/download/nli-approved-0.1.8/install-nli.py').read(), {'__name__':'__main__'})"
```

Bootstrap работает без установленного NLI: через GitHub API выбирает последний
published/non-draft `nli-approved-*`, проверяет SHA256 каталога и `.deb` по
GitHub asset digest и catalog, проверяет Package/Version/Architecture, ставит
`neiro-nli` через dpkg и сверяет `nli --version`. Object config он не создаёт
и сервисы WB не перезапускает. После первой установки дальнейшее обслуживание —
`nli self-update`. Initial adoption неизвестного объекта остаётся отдельной
reviewed процедурой.

## Обычный сценарий принятого объекта

```sh
nli status
nli self-update check
nli check hhm
nli update hhm
nli verify hhm
nli rollback hhm
nli firmware check
nli firmware update
```

Human CLI — русский, ANSI только для TTY (NO_COLOR/--no-color поддерживаются).
`--json` — чистый JSON; exit 0 = ok, 1 = failure/recovery, 3 = unavailable.
Check показывает установлено/доступно, точную release identity и результат preflight.
Обычный update автоматически разрешает approved target; вручную менять path/SHA не нужно.
Первичная регистрация неизвестных live bytes и reviewed unmanaged inventory остаётся
отдельной процедурой: [WB_SMOKE](WB_SMOKE.md), [pressure_makeup](PRESSURE_MAKEUP.md).

## Approved release discovery

Источник только `psv76/Neirolinks`, HTTPS GitHub API. Автоматический target берётся
из **published, non-draft, non-prerelease** GitHub Release с tag `nli-approved-*`
и единственным asset `nli-catalog.json`. Публикация такого release — явное действие
одобрения maintainer. Catalog schema=1, repository фиксирован, approved=true;
component entry также approved=true, совпадают component/object/role.
GitHub asset digest SHA256 обязателен. Manifest берётся по 40-char immutable commit
и path из каталога, сверяется SHA; внутри manifest обязательны immutable payload
commit, тот же repository и exact per-file SHA. Payload не берётся из mutable main.

Выбирается наибольшая числовая version (major/minor/patch); suffix/build metadata
не задают порядок. Новая публикация должна повышать числовую version. Конфликтующие
entries одной latest version блокируются. Draft #73 не становится auto target.
Нет approved новее установленного — no-op без restart. Обновление не понижает версию.
Required NLI из metadata выше установленного → понятная команда `nli self-update`.
Check не резервирует релиз и не пишет cache: update снова читает approved metadata,
показывает выбранную identity в audit и использует один зафиксированный manifest
на всю транзакцию. Если maintainer опубликовал новый release между check/update,
update выберет его; metadata/hash/payload/preflight проверяются заново.

Offline/transport error: check сообщает unavailable, update не останавливает сервисы.
Уже работающая автоматика и локальный status/verify не зависят от GitHub.
Пустой approved catalog означает отсутствие новых releases, а не автоматический
выбор draft или старого `components.*.target`. Для намеренного offline/pinned
maintenance можно явно задать top-level `release_source: "pinned"`; default старых
0.1.7 config без нового поля — `approved`. Legacy target pins остаются валидны для
этого явного режима и recovery; config не переписывается пакетом.
Approved discovery также игнорирует legacy `payload_dir`: payload загружается
по выбранному immutable commit. Offline bundles используются только в pinned режиме.

Release preparation: [RELEASES.md](RELEASES.md). Этот PR создаёт CI artifact, но не
публикует approved GitHub Release: maintainer делает это после review.

## Installed-state reconciliation 0.1.7 → 0.1.8

Status/check/verify сравнивают bytes с recorded release и package-reviewed known
manifests. Exact boiler HHM 3.1 из commit
`14354bcf1e0033c51f02f0b242bea8aa7fa29e4e` распознаётся локально по manifest SHA
`3c17f811f1580306c440143de958d723d26bb3ed7151f81991d4b957d0a2eb09` и всем file SHA.
Gazebo имеет отдельный manifest. Known manifests — **recognition-only**, не разрешение
автоматически устанавливать draft runtime. Partial/mixed bytes → unknown/drift.
Старый retained sensor_health_contract не читается и не доказывает версию.

Read-only reconciliation не пишет state и не меняет files/services. При следующем
update, после strict preflight и проверки payload, actual manifest сохраняется в
state; backup/rollback используют фактическую версию. При отсутствии нового release
эта синхронизация не вызывает restart. Pending никогда не обходится reconciliation.

## Installation-only verification

Проверяются exact managed paths/hash, manifest identity, ownership inventory,
required active services и однозначно атрибутированные managed syntax/load errors.
Journal boundary сохраняется от начала standalone наблюдения либо до service start
транзакции. SyntaxError/ReferenceError/TypeError, cannot find module/failed to load
или compile errors в managed source/dependencies fatal. Остальные, сторонние и
неатрибутированные сообщения сохраняются как diagnostics, не как доказательство
ошибки установки. Штатные состояния приложения не вызывают rollback.

HHM frames, runtime_status/circuit/diagnostics, M1W2/sensor-health attestation,
readiness, NORMAL/STARTUP и controls подпитки после запуска не являются gates.
Legacy verify metadata читается как данные, не исполняется как policy. Проверка
не обещает ПНР или отсутствие будущих runtime errors. Прежний readiness retry
удалён согласно #74 §1A; bounded installation_steps (files/services/inventory/journal)
в audit показывают технический blocking step. Функциональная диагностика — в HHM.

Preflight OFF `pressure_makeup/active=0`, `A04/K1=0`, identity, peer ownership/drift и
active serial сохранены. NLI не публикует команды outputs. Только wb-rules restart
для HHM/507. Общий restart штатно сбрасывает 507 counters/alarms; evaluate может
снова открыть клапан. NLI не требует постоянного OFF после restart.

## Self-update и storage

`nli self-update check` читает metadata, не скачивает deb и ничего не пишет.
`nli self-update` получает approved deb, сверяет SHA/Package/Version/Architecture,
запрещает maintainer hooks/triggers/conffiles/links и writes за пределы NLI runtime,
вызывает dpkg и сверяет installed package и новую CLI version. Сервисы объекта
не перезапускаются. Component config/state/pending/backups не перезаписываются.
Незавершённая установка пакета имеет отдельный `self-update.json`; повторная
`nli self-update` восстанавливает установку approved same/newer package.

После committed success cleanup сохраняет 20 успешных audit/transcripts и 3 recent
backup references на компонент, всегда защищает current rollback point. Ошибки,
partial/unverified evidence и recovery backups автоматически не удаляются. Pending
откладывает cleanup целиком. Failed history поэтому намеренно может расти; status
показывает cleanup warning, оператор архивирует evidence отдельно. Успешные старые
rollback generations могут истечь; восстановленный state не ссылается на удалённую
копию. Config, state и ручные pins/releases под /mnt/data/etc никогда не pruning.
Manifests/payload discovery живут только в памяти; временный deb удаляется на exit.
Cleanup failure не отменяет verified installation и не запускает rollback.

## Package / FIT / проверки

```sh
python3 -B -m unittest discover -s NLI/tests -v
python3 -B NLI/tests/sandbox.py
python3 -B NLI/tools/build_deb.py
sha256sum NLI/dist/neiro-nli_0.1.8_all.deb
```

Runtime в /usr/bin/nli, /usr/lib/neiro-nli и /usr/share/neiro-nli (WB nodoc compatible).
Config/pins /mnt/data/etc/neiro/nli; state/backups /mnt/data/var/lib/neiro/nli;
audit/transcripts /mnt/data/var/log/neiro/nli. После FIT runtime может исчезнуть:
установить проверенный deb заново и использовать прежние persistent данные.
Нет package conffiles/maintainer scripts. Canonical WB symlinks поддерживаются;
произвольные symlinks/junction/path traversal по-прежнему запрещены.

[SECURITY](SECURITY.md) · [FIRMWARE](FIRMWARE.md) · [RECOVERY](RECOVERY.md) ·
[TEST_RESULTS](TEST_RESULTS.md). Live WB этим PR не затрагивается.
