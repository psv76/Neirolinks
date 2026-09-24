# pressure_makeup 1.0 — отдельный компонент NLI 0.1.2

Решение: [PR #71, последний follow-up](https://github.com/psv76/Neirolinks/pull/71#issuecomment-5809381674).
Компонент `pressure_makeup`, plugin с тем же именем, object `05_31_Ivolga_13`,
role `boiler`. Единственный managed target: `/etc/wb-rules/507_Pressure_makeup.js`.
Единственный software owner A04/K1 — этот JS. NLI не публикует физические команды;
HHM не владеет ни выходом, ни файлом. Газебо этот компонент не получает.

## Baseline и release

Версия **1.0** задаётся внешним manifest, без вставки заголовка в legacy JS.
Автор PR подтвердил: live 507 совпадает с Git PR #65, кроме отсутствующего
последнего LF. В `NLI/releases/pressure_makeup/1.0/` сохранены эти точные bytes,
восстановленные из immutable blob `d75710dad93906af8869dcce48d26e14673b63fb`
удалением ровно одного terminal LF. Исходный файл объекта/логика не менялись;
live WB для этой работы не читался. Provenance указан рядом с artifact.

- Source commit: `728f5c4aa708c5040da2dce39b01adf68a1bfdc1`.
- JS SHA256: `767739a1358381297605fb598c38dfd6925e976121dfcfef2d9a77ea9ec4dafd`.
- Manifest: `pressure-makeup-boiler-1.0.json`.
- Manifest SHA256: `4a606a8b4e52f76576e08c54266e240b18144ca2cc4bce7a2ef3b10c169aae6e`.

Пакет содержит manifest и exact payload под `/usr/share/neiro-nli/`; WB nodoc
их не удаляет. Boiler example регистрирует hhm + pressure_makeup, baseline=target
1.0. Offline `payload_dir=/usr/share/neiro-nli/payload` у pressure_makeup позволяет
проверить текущий baseline без скачивания. Для нового релиза выпустить отдельный
immutable manifest/version/SHA, настроить соответствующий offline bundle либо
убрать payload_dir для загрузки точного Git source. При несовпадении bytes —
ошибка, без нормализации LF/CRLF или auto-adoption текущего файла.

## Контракт операций

`check`, `update`, `verify`, `rollback` работают через общий NLI transaction
engine. Preflight: hostname/object/role, exact live hashes, ownership inventory,
wb-rules >=2.42, active wb-mqtt-serial/wb-rules, `pressure_makeup/active=0` и
`A04/K1=0`. Давление, enabled/auto, pulse_count и alarm flags не добавлены как
новые gates. Перед записью interlocks перепроверяются. Recovery может допускать
остановленный wb-rules и частично отсутствующий свой файл, но не drift peer.

Backup/update/rollback pressure_makeup затрагивают только 507. HHM backup/update/
rollback не включают 507. Общий `wb-rules` при мутации перезапускает оба runtime.
Inventory проверяет installed manifest или baseline **каждого** зарегистрированного
peer и его exact bytes, не доверяет одному component id. Managed path в
unmanaged allowlist — конфликт, который нужно явно устранить при миграции.
Другие unmanaged JS по-прежнему требуют reviewed hash allowlist. Список может
находиться в hhm или pressure_makeup; противоречивые hashes блокируются.

Verify: exact installed bytes, active wb-rules, marker обычного запуска 507
в журнале после service start (ожидание до 15 секунд для штатного +3 s init),
наличие корректных virtual booleans, неотрицательного pulse_count, last_event и
отсутствие runtime errors. Legacy JS не публикует runtime version; NLI честно
проверяет release по SHA файла, а не выдуманному version control. Это проверка
загрузки/интерфейса, не доказательство давления, протока или положения клапана.

Restart штатно сбрасывает pulseCount и alarm flags. PersistentStorage для них
не добавляется, backup их не захватывает, rollback не восстанавливает counters.
Обычная init/evaluate может вновь выставить alarms или открыть A04/K1 при
enabled/auto и соответствующем давлении. Postverify **не требует** сохранения
старых flags/count или OFF после restart. Специального запрета HHM update из-за
этого поведения нет. Существующий OFF preflight остаётся; если после неуспешного
update цикл активен, rollback тоже обязан пройти interlocks, иначе pending
остаётся для отдельного разбора инженером.

## Следующий read-only smoke на boiler

Это инструкция оператору отдельного полевого окна. Агент не выполнял её на WB.
Взять `neiro-nli_0.1.2_all.deb` и `.sha256` из **конкретного зелёного artifact
`neiro-nli-0.1.2-deb`**, указанного с SHA256 в PR; сверить hash с PR. От root:

```sh
set -e
sha256sum -c neiro-nli_0.1.2_all.deb.sha256
test "$(hostname)" = wirenboard-ABF62SL
test "$(readlink /etc/wb-rules)" = /mnt/data/etc/wb-rules
test "$(readlink /etc/wb-rules-modules)" = /mnt/data/etc/wb-rules-modules
findmnt /mnt/data
systemctl show wb-rules wb-mqtt-serial -p Id -p ActiveEnterTimestampMonotonic
apt install ./neiro-nli_0.1.2_all.deb
nli --version
nli --json status
```

На boiler уже есть persistent config 0.1.1 с reviewed unmanaged allowlist.
**Не заменять его целиком новым example.** Следующий helper проверяет identity,
отсутствие pending/уже зарегистрированного pressure_makeup, hashes manifest и
текущего 507, сохраняет прежний config отдельной копией, добавляет только новый
pin/component и удаляет только 507 из прежнего unmanaged allowlist. Остальные
reviewed entries, HHM pins и настройки сохраняются. Он не меняет JS, state/log,
MQTT или services. При отличающемся 507 либо конфликте прекращает работу.

```sh
python3 -B /usr/share/neiro-nli/register_pressure_makeup.py
nli --json check hhm
nli --json check pressure_makeup
systemctl show wb-rules wb-mqtt-serial -p Id -p ActiveEnterTimestampMonotonic
```

Если pressure_makeup уже зарегистрирован, helper не запускать повторно:
проверить config/pins и выполнить только два check. Для нового незаполненного
контроллера пример boiler содержит оба компонента; первоначальная ПНР и
подготовка baseline выполняются отдельно, NLI не устанавливает их на пустой WB.

Ожидание обоих check: `final_status=ok`, `preflight=ok`, exit 0. У pressure_makeup
from/to = `1.0`. Timestamps сервисов не меняются; если state/log каталоги
отсутствовали, после read-only checks они остаются отсутствующими. История
уже существующих транзакций также не меняется. HHM check по-прежнему требует
сеть для своего immutable payload; pressure baseline использует packaged bytes.
Сохранить результаты. Не выполнять update/rollback/firmware/restart в этом smoke.

Все durable пути и FIT reinstall policy 0.1.1 сохраняются. Reinstall 0.1.2
возвращает executable/runtime data, автоматически читая прежний persistent
config/state. Он не регистрирует pressure_makeup за оператора и не меняет allowlist.
