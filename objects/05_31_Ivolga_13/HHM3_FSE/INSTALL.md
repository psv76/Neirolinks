# HHM 3.1 — migration и rollback через NLI 0.1.7

**25.09.2026: BLOCKED. Не повторять update по существующим manifests.** Runtime `14354bcf1e0033c51f02f0b242bea8aa7fa29e4e` трижды не прошёл live readiness; NLI выполнил autorollback. Новый исправленный runtime не выпущен. План ниже остаётся историческим/будущим и не означает готовность к повторной попытке. Результаты расследования, недостающие доказательства и условия будущего smoke: [FIELD_STARTUP_2026-09-25.md](FIELD_STARTUP_2026-09-25.md).

Это план будущих действий оператора, не разрешение и не выполненный deploy. В рамках Issue #68 нет доступа к live WB, restart, OT или физическим командам.

## Исходное состояние и подготовка

База репозитория: merge PR #71 `1668c32d7187f0a59ccdea5d5b7da10f14f9660f`; HHM runtime базы — 3.0.0-FSE из `d75710dad93906af8869dcce48d26e14673b63fb`, установленный NLI 0.1.6. Для manifest HHM 3.1 с двухчастной версией требуется пакет NLI 0.1.7: обновить его перед сменой target. Установка пакета NLI сама по себе не перезапускает отопление. Не предполагать, что installed bytes совпадают с Git: перед согласованной операцией NLI должен проверить identity, inventory/drift, pending и установленный baseline каждого WB.

1. На машине подготовки проверить CI точного PR HEAD, пакет `neiro-nli_0.1.7_all.deb` с его `.sha256`, HHM manifest, NLI `releases/hhm-boiler-3.1.json` и `hhm-gazebo-3.1.json` с их `.sha256`. Role manifests закрепляют полный runtime commit и exact bytes payload; он может предшествовать финальному документационному коммиту PR.
2. Воспроизвести payload офлайн: `python -B NLI/tools/prepare_hhm31.py --commit <release.commit из manifest> --role boiler --output <каталог подготовки>`; повторить для gazebo. Сверить с reviewed manifests. Старый `prepare_hhm.py` специально продолжает отвергать 3.1.
3. Сохранить NLI config/pins/state/audit и PersistentStorage. Pending должен отсутствовать. Установить проверенный пакет NLI 0.1.7 на каждый WB до смены target, проверить `nli --version` и `nli status`. При drift/pending не редактировать hashes/state для обхода проверки; сначала отдельное восстановление по NLI/RECOVERY.md.
4. До начала согласованного окна проверить wb-rules с поддержкой `trackMqtt.retained` (API исследован на 2.46.5; прежний минимум транспорта 2.42.0 сохранён), активный wb-mqtt-serial, опрос обоих controls каждого используемого M1W2 и отсутствие #error. Пустые неиспользуемые входы с OK=0 не входят в required set. Config wb-mqtt-serial не менять ради искусственного heartbeat.
5. Startup ждёт live temperature и live OK каждого датчика. Если штатная публикация неизменных данных отключена, retained-only старт может оставаться неготовым до естественного обновления. Не обходить qualification подстановками, публикациями или увеличением TTL. Runtime contract attestation подтверждает загруженную реализацию; она не является health-сводкой всех 20 датчиков. Проверить фактические valid/state отдельно. Прежний 30-секундный NLI readiness budget не увеличивается.

## Состав и порядок будущей установки

Устанавливается полный role payload из NLI manifest: boiler — 500/620/600 и шесть модулей; gazebo — 624 и HHM3Config/HHM3Wire/HHM3Runtime. Не переносить один helper поверх старых consumers. 600 для 3.1 зависит от тех же модулей.

После отдельного разрешения оператора обновлять каждый WB отдельной транзакцией NLI. Предлагаемый порядок — gazebo, затем boiler. Wire schemas v2 (504) и v3 (house), TTL и session/seq не изменены, поэтому переходный смешанный выпуск не требует bridge/ACL edits; старый boiler до своего обновления сохраняет прежние ограничения локальных датчиков.

Оператор привязывает reviewed target manifest и offline payload через принятый NLI config/pin workflow, сохраняя installed baseline и независимый pressure_makeup. Далее `nli --json check hhm`, в разрешённое окно `nli --json update hhm`, затем `status` и `verify hhm`. Эти команды здесь не выполнялись. NLI обеспечивает backup, atomic install, postverify и autorollback; не заменять их старыми четырёхфайловыми installers PR #65.

Обычный restart wb-rules влияет и на независимый 507: сбрасывает его runtime counters/alarms и запускает штатный evaluate. Сохранён OFF preflight pressure_makeup/active=0 и A04/K1=0; постоянный OFF после restart не обещается. HHM payload/backup/rollback не содержит 507. wb-mqtt-serial не перезапускается.

## Приёмка после согласованной установки

- Проверить version 3.1 в HHM3Config и `sensor_health_contract=m1w2-health-v1` на HHM3_FSE (boiler) / NL_combo_thermostat_504 (gazebo); attestation controls входят в соответствующие NLI manifests.
- Проверить 18 пользовательских настроек дома и отдельный 505, compact diagnostics, отсутствие нового первичного ввода. `start_heating` повторно не нажимать.
- Дождаться startup qualification, наблюдать >120 с при стабильных температурах: локальные M1W2 valid, 504 не переключается в автономию из-за numeric silence. Проверить диагностику 411–420, включая 412. Отказ датчика не моделировать опасным нагревом.
- Действующие MSW, межконтроллерная связь, реальные ошибки датчиков и локальные защиты должны сохранять свои реакции. UI/гидравлическая приёмка остаётся отдельной #20, не выводить её из CI или software command accepted.
- Итог NLI: update_ok, pending=null, соответствующий immutable manifest, сохранённые state/bytes pressure_makeup и журнал проверки. При неожиданном поведении прекратить приёмку и следовать rollback.

## Откат

В согласованное окно выполнить `nli --json rollback hhm` отдельно на затронутом WB: восстановится предыдущий managed release с его manifest, всеми HHM bytes и проверкой. Вернуть target pin на прежний approved manifest, чтобы следующее update не повторило 3.1 автоматически. Если обновлялись оба WB, откатывать в обратном порядке: boiler, затем gazebo. Смешанные версии сохраняют формат frames.

Не удалять PersistentStorage, уставки, NLI backups/audit или pending. Если autorollback/rollback не прошёл verify, сохранить pending и следовать NLI/RECOVERY.md; не регистрировать baseline повторно. Проверить 507 и фактические насосы/клапаны после общего restart. Откат на 3.0 возвращает и прежнюю numeric TTL проблему M1W2 — это известное свойство исходного выпуска.
