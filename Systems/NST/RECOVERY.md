# NST 2.0: восстановление

`nst status` показывает незавершённую операцию. До восстановления новый sync/update/firmware блокируется.

- Незавершённая миграция NLI: повторить `nst migrate-nli`; не удалять исходные данные и migration journal. При конфликте хранилищ требуется разбор inventory.
- Component pending: `nst rollback <component>` использует проверенную старую backup point; NLI 0.1.9 backup references сохраняются после миграции.
- Deployment pending: `nst recover-deployment` восстанавливает прежние managed/object files, config, component state, registry и platform state. Новые файлы транзакции удаляются; чужие файлы не затрагиваются.
- Package self-update pending: проверенный reinstall либо `nst self-update`; package marker отдельный и не уничтожает component/deployment pending.
- Firmware pending: `nst firmware recover` по правилам [FIRMWARE.md](FIRMWARE.md).

При ошибке rollback pending и backup сохраняются. Не очищать marker вручную для обхода interlock/identity/hash отказа. Повреждение backup требует внешней проверенной копии.

После FIT вернуть NST package в rootfs, сохранив `/mnt/data`. Runtime использует `/mnt/data/{etc,var/lib,var/log}/neirolinks/nst`. Исторические `/neiro/nli` остаются доказательством миграции, а не рабочим хранилищем.
