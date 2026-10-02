# NST — NEIROLINKS Service Tool

NST 2.0 — сервисный инструмент для установки approved desired state и обслуживания контроллеров Wiren Board.

Нормативный источник: [стандарт именования и версий](../../EIM/Standards/Software_naming_and_versioning_standard.md).

## Версия и состав

Выбрана **2.0**: чистая установка по registry/deployment, транзакция компонентов вместе с object files и перенос persistent storage меняют архитектуру и существенно расширяют функциональность. Это изменение X; начальная ревизия Y равна 0.

Пакет `nst`, артефакт `nst_2.0_all.deb`, CLI `/usr/bin/nst`, Python package `nst` в `/usr/lib/nst`, данные `/usr/share/nst`, документация `/usr/share/doc/nst`.

Persistent config/state/logs: `/mnt/data/etc/neirolinks/nst`, `/mnt/data/var/lib/neirolinks/nst`, `/mnt/data/var/log/neirolinks/nst`.

## Чистая установка

Установить reviewed пакет `nst_2.0_all.deb` с зависимостями обычным пакетным менеджером. Установка пакета не запускает сервисы инженерной автоматики и не пишет persistent config. Предварительная установка NLI не нужна; `/usr/bin/nli` не поставляется.

1. `nst status` — локальные identity и состояние; первоначальный профиль unconfigured.
2. `nst check` — получить последний approved platform release, проверить hardware serial/fingerprint, registry/profile, deployment и показать план без записи данных.
3. `nst sync` — явно выполнить bootstrap и транзакцию. Config, registry и state создаются из проверенного deployment; локальная регистрация компонентов заранее не нужна.
4. `nst status` и `nst check` — подтвердить exact desired state.

`nst sync` не заменяет ПНР: контроллер должен иметь исправные WB services и подтверждённые аппаратные interlocks. Неизвестные writers, drift, неполные профили и отсутствующие approvals блокируют применение.

## Миграция

После замены NLI 0.1.9 пакетом NST выполнить `nst migrate-nli`. Это явная операция копирования с проверкой, журналом возобновления и сохранением исторических оригиналов. При наличии старого хранилища остальные команды до миграции отказывают, а не создают новое пустое состояние.

Порядок и восстановление: [NST_MIGRATION.md](NST_MIGRATION.md), [RECOVERY.md](RECOVERY.md).

## Deployment и публикация

[DEPLOYMENT.md](DEPLOYMENT.md) описывает транзакцию и ограничения; [RELEASES.md](RELEASES.md) — подготовку package/component/platform assets.

Исторические approved component releases и `neiro-nst 1.0.0` сохраняют исходные имена, номера и байты. Они не являются новыми пакетами NST и не выбираются установщиком NST 2.0.

## Что остаётся отдельной работой

- Для ABF62SL опубликован и включён в desired state approved компонент `pressure_makeup 1.0`. Полный platform Release и полевой pilot публикуются/выполняются отдельно; merge сам по себе не обновляет контроллер.
- Публикация NST package release и полного platform release выполняется отдельно после merge; один package release не заменяет registry/deployment assets.
- Удаление ранее управляемых файлов/компонентов требует отдельного decommissioning plan и сейчас блокируется.
- Реальная установка, firmware и ПНР на WB в этой задаче не выполняются. Результаты проверок: [TEST_RESULTS.md](TEST_RESULTS.md).

Merge меняет исходники и CI в main. Он не публикует Release и не обновляет контроллеры.
