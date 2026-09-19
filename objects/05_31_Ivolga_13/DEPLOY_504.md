# 504 — будущая установка из GitHub

**READY_FOR_REVIEW, не DEPLOYED и не READY_FOR_APPLY.** Каждый этап SSH/изменения
WB требует отдельного согласования Сергея. Здесь таких действий не выполнялось.
Блокеры: [HM2_504.md](HM2_504.md). Автоматического apply/restart-скрипта нет:
реальная схема brokers и live ownership неизвестны.

## 1. Подготовка без контроллеров

Взять полный 40-символьный SHA одобренного PR, сверить с GitHub и записать в протокол.
Пример POSIX-команд в новом checkout; доступ к private GitHub через credential helper:

```sh
git clone --no-checkout https://github.com/psv76/Neirolinks.git hm2-504-review
cd hm2-504-review
REVIEW_SHA='REPLACE_WITH_REVIEWED_40_HEX_COMMIT'
git fetch origin "$REVIEW_SHA"
git checkout --detach "$REVIEW_SHA"
test "$(git rev-parse HEAD)" = "$REVIEW_SHA"
git status --short
node objects/05_31_Ivolga_13/Tools/test_hm2_504.js
node objects/05_31_Ivolga_13/Tools/verify_hm2_504_manifest.js
git archive --format=tar --output=../hm2-504-reviewed.tar "$REVIEW_SHA" \
  objects/05_31_Ivolga_13/Besedka \
  objects/05_31_Ivolga_13/Wirenboard/wb-rules-modules/HM2504.js \
  objects/05_31_Ivolga_13/Wirenboard/wb-rules/504_gp_besedka_manager.js \
  objects/05_31_Ivolga_13/Wirenboard/wb-rules/HM2_arbiter_request.js \
  objects/05_31_Ivolga_13/Tools/hm2_504.sha256 \
  objects/05_31_Ivolga_13/HM2_504.md \
  objects/05_31_Ivolga_13/DEPLOY_504.md \
  objects/05_31_Ivolga_13/Sprut/Templates/NL_combo_thermostat.json \
  Templates/WB-rules/Heating/HM2/MixingController/MixingController.js
tar -tf ../hm2-504-reviewed.tar
sha256sum ../hm2-504-reviewed.tar
```

Manifest покрывает 8 code/config/reference файлов, не себя и не docs; commit SHA
фиксирует весь пакет. Git archive даёт canonical LF, manifest проверяет эти байты.
Сохранить SHA архива вместе с commit. Никаких credentials в URL или архиве.

## 2. Read-only audit — после разрешения SSH

На обоих WB снять версии wb-rules/Mosquitto, includes/listeners/TLS/ACL/bridges,
инвентарь scripts/modules/cron/systemd, MQTT clients, VD, Sprut/Fluxa сценарии.
Секреты хранить локально 0600, не печатать password-файлы в чат/GitHub.
Проверить пять sensor topics, ошибки и публикацию неизменного значения чаще 120 с,
время обоих WB, namespace frame и отсутствие VD collision. Зафиксировать, установлен
ли live 504, и всех writers A03/K4/A05 Channel 3. Снять актуальные копии 501/502/503,
620, source, arbiter/shared modules. Показать `diff -u` с reviewed SHA, особенно
Level/Switch в 501/502. Эти writers не входят в установку.

Проверить, допускает ли действующая схема dedicated bridge identity без перезапуска
котельной. Если нет — отдельное решение/окно, не анонимный broker и не широкие ACL.
Проверить старые обратные/широкие bridge: exact-topic нового моста не доказывает
отсутствие циклов в уже работающей схеме. Параметры `.example` пока не готовые к APPLY.

## 3. Backup и staging — по разрешению

На каждом WB отдельный каталог backup с timestamp и reviewed SHA, `umask 077`.
Сохранить `/etc/wb-rules`, `/etc/wb-rules-modules`, все фактически используемые
Mosquitto includes/ACL/credentials, modes/owners, hashes, список отсутствующих новых
файлов, существующие persistent данные 504 и журнал ошибок. Backup секретов не в GitHub.
Состояния gates/аварий не считать восстановленными только по файлам JS.

Передать архив в staging вне `/etc/wb-rules`, сверить SHA с рабочей станцией и
`tar -tf`, проверить точный allowlist путей. Распаковать; из корня staging:

```sh
sha256sum -c objects/05_31_Ivolga_13/Tools/hm2_504.sha256
```

Показать diff каждого назначения, add/replace и backup path. MixingController —
reference для сравнения, **не разрешение заменить общий live-модуль**. Несовместимая
или неизвестная зависимость останавливает установку; не менять 501/502 ради 504.

## 4. Термостат и мост — отдельное окно

1. Только на WB беседки добавить `HM2504.js` в `/etc/wb-rules-modules`, затем
   `624_combo_besedka.js` в `/etc/wb-rules`; до этого collision audit. Добавление rule
   вызывает reload; нельзя обещать отсутствие влияния даже без общего restart.
2. Проверить logs, один VD, русские controls, startup OFF, freshness/error/stale.
   Persistence/reload сначала на изолированном стенде; live reload согласуется.
   До привязки Sprut проверить `init:true` опций и сохранение уставок. Fluxa не writer.
3. Заполнить `.example` подтверждёнными listener/TLS/identity; секреты только локально.
   Parser и две Mosquitto инстанции проверить изолированно, без подключения .101/.104:
   exact mapping, ACL deny чужого publisher и `/devices/.../on`, отсутствие inbound,
   retained/reconnect. Запуск `mosquitto -c` с live address не является офлайн-проверкой.
4. Согласовать механизм применения broker config. Никакого автоматического restart
   или reload Mosquitto на обоих WB; без решения этап blocked. Broker котельной
   по возможности вообще не менять. Проверить только frame и отсутствие чужих
   устройств в Sprut/Fluxa; происхождение подтвердить ACL, не строкой source.

## 5. Shadow manager, отдельно arbiter

На котельной после проверки зависимости добавить только HM2504 module и
504 manager. Никаких mass copy директорий. Проверить UNKNOWN, valid/demand/path=0,
gates=0, request_json, свежесть 411/418/419, NORMAL/DEGRADED/INTERLOCK, отсутствие
новых физических writes (включая OFF) по логам/истории. Чужие outputs не переключать.

Arbiter устанавливать отдельным действием после diff live, проверки source whitelist
и разрешения. ENABLE_504_SELECTION=false. Проверить прежние selection/grants/counters
501–503, grant_504 REJECTED. Source gates не менять. Обновление arbiter временно
делает результат UNKNOWN: заранее согласовать последствия для активного отопления.

## 6. ПНР — не часть этого пакета

Production writer/автономный нагрев ещё отсутствуют. Получить решения из HM2_504.md,
подготовить отдельный код и тесты, провести review. Затем отдельно передавать
владение и safe outputs: насос OFF → Level 0 → Switch OFF; открытие Level перед
Switch ON без гейтинга старым readback. Проверить реальный ход, циркуляцию, 418/419.
Нет автоматического restart wb-rules/Mosquitto/OpenTherm, git pull main в рабочие
каталоги, curl | sh, переключения gates или merge.

## 7. Откат

Зафиксировать состояния 504 и соседних контуров. По согласованному плану убрать новые
rules из активного каталога или вернуть их прежние версии атомарной заменой;
для ранее отсутствующих файлов вернуть отсутствие. Удаление rule тоже reload.
Модуль HM2504 удалять после снятия его consumers. Общий MixingController, 501–503,
source и 620 не заменять. Arbiter вернуть из проверенного live backup, не main.
Mosquitto/ACL/credentials восстановить с исходными правами и отдельно согласованным
способом применения. Persistent fault не очищать; уставки/gates/outputs не считать
автоматически восстановленными. Проверить logs и прежний выбор источника.
Rollback файлов не гарантирует бесшовность сервисов и не отменяет live ownership.
