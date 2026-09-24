# Завершение существующего recovery_required (NLI 0.1.4)

Это инструкция оператору, не автоматический deploy. Команды ниже агент на live
WB не выполнял. Для случая PR #71 контроллер — `wirenboard-ABF62SL`, компонент
`pressure_makeup`, pending/backup ID `a41ddaee893d4c2b95cc0fbeb64be60c`.
Состояние из комментария устаревает: перед действием нужно проверить его заново.

1. Сохранить копию `/mnt/data/etc/neiro/nli`, `/mnt/data/var/lib/neiro/nli` и
   `/mnt/data/var/log/neiro/nli` вне этих каталогов, включая pending, backup и audit.
   Не удалять pending, не редактировать state/manifest/hash и не запускать повторную
   регистрацию компонента. Остановить другие NLI/config editing сессии.
2. Скачать `.deb` и `.sha256` из конкретного green artifact `neiro-nli-0.1.4-deb`
   по ссылке в PR. Сверить SHA256 с опубликованным в PR, затем от root:

   ```sh
   sha256sum -c neiro-nli_0.1.4_all.deb.sha256
   apt install ./neiro-nli_0.1.4_all.deb
   nli --version
   nli --json status
   ```

   Выполнять последовательно, прекращая при неожиданной ошибке. Ожидаемая версия
   `0.1.4`. У `status` сейчас ожидается exit 1 с `final_status: recovery_required`,
   поэтому не запускать весь блок под `set -e`. Установка пакета сама не выполняет
   restart, не устанавливает 507 и не очищает pending.
3. Проверить в JSON pending компонент, ID и backup reference. Для указанного случая
   они должны соответствовать ID выше. Проверить, что сохранённый backup относится
   к baseline 1.0 и его manifest/metadata/payload не изменены. NLI повторно проверит
   их pinned hashes при rollback. При другом pending или отсутствии backup —
   остановиться и разобрать фактическую транзакцию, не подменять reference.
   Проверить active `wb-rules` и `wb-mqtt-serial`, актуальные read-only MQTT значения
   `pressure_makeup/active=0` и `A04/K1=0` (проверяет также preflight). На полевом
   случае уже восстановленный файл проверяется командой:

   ```sh
   sha256sum /etc/wb-rules/507_Pressure_makeup.js
   ```

   Ожидаемый SHA256 baseline 1.0:
   `767739a1358381297605fb598c38dfd6925e976121dfcfef2d9a77ea9ec4dafd`.
   При расхождении с этим полевым сценарием остановиться для диагностики.
   Не исправлять hash и не посылать команды клапану ради прохождения interlock.
4. В согласованное оператором окно обслуживания выполнить **один явный rollback**:

   ```sh
   nli --json rollback pressure_makeup
   ```

   Это мутация: она использует существующий pending backup и выполняет stop/start
   **wb-rules**; `wb-mqtt-serial` не перезапускается. Проверяются exact hashes,
   services, controls, startup marker 507 и журнал от границы перед start.
   Однозначно атрибутированные ошибки другого проверенного неизменённого скрипта
   сохраняются в `verification_attempts[].journal` как `shared_runtime`, `fatal=false`.
   Собственные и неатрибутированные ошибки остаются fatal. Только успешный rollback
   с `final_status: ok` (exit 0) очищает pending. При failure прекратить действия,
   сохранить новый audit и pending; не повторять вслепую и не чистить вручную.
5. Выполнить `nli --json status`: ожидаются exit 0, `final_status: ok`, `pending: null`,
   установленный pressure_makeup 1.0 и `last_result: rollback_ok`. Сохранить ID нового
   rollback и его audit `/mnt/data/var/log/neiro/nli/<id>.json`; старый failure audit
   и backup сохраняются. Проверить SHA файла, active services и неизменность
   `ActiveEnterTimestampMonotonic` у wb-mqtt-serial относительно значения до операции.

Restart штатно сбрасывает pulseCount/alarm flags 507 и запускает init/evaluate:
при enabled/auto клапан может открыться по текущему давлению. NLI не обещает OFF
после restart, не сохраняет эти counters и не заменяет физическую приёмку.

Отдельный `nli --json verify pressure_makeup` после recovery — read-only проверка
текущего окна наблюдения: старые ошибки не учитываются, но новая сторонняя ERROR
внутри этого окна по прежней политике standalone остаётся failure. Это само по себе
не создаёт pending и не отменяет успешно завершённый rollback. Причину сторонних
ошибок нужно исправлять отдельно; `shared_runtime` в audit не означает их устранения.
