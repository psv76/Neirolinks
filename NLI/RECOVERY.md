# NLI 0.1.8: migration, recovery и read-only field smoke

Live действий агент не выполняет. Перед recovery оператор сохраняет копии
/mnt/data/etc/neiro/nli, /mnt/data/var/lib/neiro/nli и /mnt/data/var/log/neiro/nli.
Не удалять pending и не переписывать hashes/state ради прохождения проверки.

## Upgrade 0.1.7 → 0.1.8 и smoke без live mutation

Пакет 0.1.8 из green CI устанавливается отдельным решением оператора после сверки
SHA256. Пакет не содержит maintainer scripts и не перезапускает сервисы.
Существующий config читается без переписывания; default release_source=approved.
Повторная регистрация HHM/507 не нужна. Known HHM 3.1 manifest установлен в
/usr/share/neiro-nli/known независимо от WB nodoc policy.

Затем только read-only:

```sh
nli --json --version
nli --json status
nli self-update check
nli check hhm
nli verify hhm
nli firmware check
```

Зафиксировать timestamps wb-rules/wb-mqtt-serial и hashes config/state/JS до/после:
они не должны измениться. Exact HHM 3.1 disk bytes при stale state 3.0 должны
показать installed 3.1 и reconciliation_required; unknown/mixed → unknown/drift.
No network не мешает status/verify и распознаванию, но check может быть unavailable.
Sensor-health retained control не читается. Нет approved новее — update_available=false.
Firmware check с supported updater: compatibility=supported, updates=unavailable,
exit 3 — отсутствие безопасного inventory API, не отсутствие device updates.
Никаких update/rollback/firmware mutation в этот smoke plan не входит.

## Component pending

Status показывает фактический pending component, backup reference и последний audit.
Если pending есть, check/verify/update заблокированы: не удалять его ради check.
После отдельного решения оператора о maintenance window проверить active services,
OFF interlocks и целостность указанного backup; выполнить `nli rollback <component>`.
Это stop/start wb-rules для hhm/pressure_makeup. Только verified success очищает
pending. Технические file/load/service ошибки остаются fatal; business states HHM
не являются причиной rollback 0.1.8. После успеха сохранить audit, проверить status,
installed hashes и serial timestamp. При failure остановиться и сохранить evidence.
Команда должна соответствовать component в текущем pending, а не старому ID из PR.

## Package interruption / FIT

Self-update не меняет component pending. /mnt/data/var/lib/neiro/nli/self-update.json
сохраняет отдельный interrupted package intent; он блокирует component/firmware
mutation. Повторная `nli self-update` проверяет approved same/newer package и
повторяет установку. Если CLI утрачен после FIT/повреждения rootfs, установить
проверенный approved deb внешним package manager, сохранив /mnt/data; затем
завершить self-update marker штатной командой. Не создавать пустой config поверх
persisted данных. При unavailable release/network сохранить intent до восстановления
доступа, не выдавать проблему package manager за успешное обновление.

## Firmware recovery / cleanup

Firmware partial/unverified/interrupt сохраняет pending; `nli firmware recover`
допускается только оператором, после проверки отсутствия running updater. Нельзя
восстановить firmware старым component backup. Upstream bootloader может меняться.
Cleanup warning после success не означает failure установки. Текущий rollback point,
pending и failed evidence сохраняются; архивировать failures вручную после разбора.
Ручные config/pins/unmanaged inventory не относятся к автоматически удаляемым данным.
