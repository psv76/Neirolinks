# NST 2.0: approved deployment

## Источник

`nst check/sync` выбирает последний published stable `nst-approved-platform-*` и assets `nst-controller-registry.json`, `nst-deployment-<SERIAL>.json`. Проверяются GitHub asset SHA256, hardware serial/fingerprint, lifecycle, object/node/role, immutable commits, profile и diagnostics profile hashes, component manifests и payload hashes.

Отсутствие serial в последнем platform release не разрешает откат к более старому registry. Unknown, planned, retired, fingerprint mismatch и несовпадающий локальный config блокируют mutation. Unconfigured чистая установка получает назначение из approved registry; hostname не заменяет hardware identity.

Package release и platform release — разные approvals. Установка Debian-пакета не одобряет объектовый payload. Установщик пакета не использует legacy NLI release как запасной вариант.

## Транзакция

Все component manifests проверяются встроенными plugin policies; object files допускаются только как `.js` в `/etc/wb-rules` и `/etc/wb-rules-modules`. Protected 507 и PersistentStorage не могут стать обычными object files. Компонент подпитки сохраняет отдельную policy.

Перед первым service action:

1. Проверить lifecycle, отсутствие pending/self-update, загрузить и проверить все payload bytes.
2. Проверить ownership, неизвестные writers, drift, interlocks и свободное место под payload/backup.
3. Сохранить прежние bytes/permissions и отсутствие новых файлов, config, component state, registry и platform state.
4. Записать durable pending intent; затем остановить требуемые services.

Все файлы заменяются атомарно; config и регистрация компонентов создаются из проверенных metadata. После старта проверяются files/services и технические ошибки загрузки управляемых JS. Только после успеха platform state получает `exact`, audit фиксируется, pending очищается.

Обычная ошибка вызывает rollback всей транзакции, включая удаление только новых файлов этой транзакции. Power loss/SIGKILL оставляет pending. `nst recover-deployment` восстанавливает snapshot; повреждённый backup блокирует восстановление. Остальные mutation-команды отказывают при pending.

При exact deployment повторный sync не перезапускает services. Исторические component rollback references после миграции сохраняются. Deployment backups хранятся отдельно и автоматически не удаляются.

## Ограничения

Удаление ранее управляемых компонентов/файлов требует отдельного reviewed decommissioning plan. Произвольные system config/object targets, hooks и shell expressions не поддерживаются.

Локальные unknown files не становятся approved только из-за нахождения на контроллере. Если новый approved target уже существует, допускаются только точные одобренные bytes либо подтверждённая предыдущая managed version.

Для ABF62SL approved pressure_makeup отсутствует в desired components: публикация полного platform deployment блокируется до решения этого пробела. Реальные hardware/MQTT interlocks должны быть доступны; CI использует fake backend и не доказывает ПНР на физическом WB.
