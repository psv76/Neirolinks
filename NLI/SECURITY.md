# NLI 0.1.8: trust и границы ответственности

Root CLI, не sandbox для недоверенного Python/JS. Доверяются reviewed object config,
NLI package и maintainer approved Releases в psv76/Neirolinks. Компрометация root,
GitHub maintainer или пакета вне этого threat model. Initial adoption не auto-trust:
неизвестные writers/bytes требуют отдельного review, автоматического allowlisting нет.

Discovery принимает stable published nli-approved-* с SHA256 metadata asset,
approved component/object/role/version, immutable 40-char manifest/payload commits
и SHA каждого файла. Нет payload mutable main, redirect в произвольный host,
непроверенного network cache. Transport имеет size/time/page/catalog bounds и
fail closed. Проверка metadata не заменяет review публикующего maintainer; HTTPS
и GitHub asset digests не являются независимой offline подписью. Public API должен
быть доступен контроллеру; rate-limit/offline/private repository access не обходятся.

Known HHM 3.1 package manifest разрешает только локальное распознавание exact bytes,
не auto deploy draft #73. Reconciliation не меняет files/services и не делает
unknown/mixed bytes approved. Read-only команды не создают state/cache/history/lock.
Файловая система может менять atime, системные демоны — вести собственный журнал.

Installation gate не оценивает business logic. Hash/identity/ownership/service и
managed technical syntax/load errors проверяются; unknown/foreign/application
messages диагностические. Journal ограничен текущей проверкой/исходным restart
boundary. Это конечное наблюдение, не мониторинг будущих ошибок и не ПНР.
Legacy runtime/health metadata не используется как runtime attestation. Retained
MQTT не определяет installed version. Interlocks подпитки сохранены как safety
preflight; retained OFF не является аппаратным доказательством закрытого клапана.

Mutation lock объединяет component/firmware/self-update; внешние root-editors,
WebUI/updaters lock не соблюдают. Оператор исключает такие параллельные изменения.
Peer files и unmanaged_rules проверяются exact SHA. Только две canonical ссылки
/etc/wb-rules -> /mnt/data/etc/wb-rules и /etc/wb-rules-modules ->
/mnt/data/etc/wb-rules-modules; nested symlinks/junctions/hardlinked targets запрещены.

Durable intent до service stop, atomic replacement, fsync, managed-only backup.
Power loss/SIGKILL сохраняет pending; Ctrl-C вызывает best-effort rollback и может
оставить partial_failure. Ошибка recovery не маскируется. Заполненный диск проверяется
до component mutation; fsync/space check не дают гарантии против отказа носителя или
параллельного потребления места. Неудачный backup/audit может требовать диагностики.

Self-update сохраняет отдельный durable marker, не затирая component pending.
Approved deb проверяется до dpkg: package identity, SHA, no maintainer hooks,
no persistent/system writes outside NLI runtime. Dpkg имеет собственный lock.
Нельзя запускать параллельный apt/root package editor. Не обещается автоматический
откат Debian package при power loss; repeat self-update либо documented reinstall.

Cleanup после committed success под тем же lock; failed/pending evidence защищены.
Delete только NLI backup/audit paths, все вложенные пути проверяются до удаления.
Сбой pruning — warning, не rollback. Failed history/unmanaged artifacts намеренно
не ограничиваются автоматически; их архивирует оператор, не удаляя recovery context.

Firmware compatibility policy встроена в NLI. Версия, reviewed executable Git blob,
package ownership и dpkg verification обязательны; object SHA pins больше не нужны.
Проверка не запускает upstream даже с --help. Реального read-only device inventory
нет: honest unavailable. Firmware mutation интерактивная, upstream prompts сохранены;
flasher не убивается по timeout. Подробнее FIRMWARE.md.
