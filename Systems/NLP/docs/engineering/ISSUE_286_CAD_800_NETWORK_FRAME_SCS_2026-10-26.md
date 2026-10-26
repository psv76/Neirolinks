# NL Project 3.1 — CAD-контракт 800 для рамок и щита СКС (Issue #286)

## Принятое правило

Слой `800_*` — функциональная группа `NETWORK` (Ethernet).

- Монтажные блоки `FRAME_1`, `FRAME_2` для интернет-розеток разрешены
  на `800_*`. Точно такое же разрешение по группе распространяется на
  прочие монтажные рамки `FRAME_*`: это графические элементы, а не
  самостоятельные кабельные линии или BUS-узлы.
- На `800_*` разрешено **ровно** сочетание функционального блока
  `BOARD_OUT` с `LOAD_TYPE=BOARD_SCS`; пример — щит `SCS-20`.
- Другие роли щитов (`BOARD_DISTRIBUTION`, `BOARD_IN`,
  `BOARD_AV` и т. п.) и другие блоки щитов (`BOARD_IN`,
  `BOARD_PANEL`, `BOARD_OUT_IP*`) **не получают** автоматического
  разрешения на `800_*`.
- Существующее размещение обычных щитов в `100_*` / POWER и
  специальное исключение `BOARD_IN+BOARD_AV` на `700_*`
  сохраняются без изменений.
- `BOARD_ID` щита СКС и `CABLE_ID` Ethernet-линий имеют разное
  назначение; `SCS-20` не должен требовать `CABLE_ID`, если
  самостоятельная кабельная линия к нему не назначена.

Реализация: `resources/autocad/block_contract.json` (FRAME в NETWORK),
`src/nl_project_2/cad_contract/catalog.py` (узкая role-aware
вставка для `BOARD_OUT+BOARD_SCS`). Действующий формат каталога
CAD-контракта не меняется, миграции SQLite нет.

## Доказательство на Богдановиче (только копия, без AutoCAD-записи)

Входные доказательства:
- сохранённый read-only снимок `House_2/working.dwg` после исправления
  линии 118: 582 вставки;
- сохранённая чистая тестовая SQLite с перенесёнными только
  23 Room и 10 project_setting;
- `GOFRA_ID` и `BUS_GOFRA_ID` очищены **только виртуально в памяти**.
  Действительный DWG не менялся.

После изменения CAD-контракта:
- все 25 прежних `LAYER_FUNCTION_GROUP_MISMATCH` исчезли
  (13 `FRAME_1`, 11 `FRAME_2`, 1 `BOARD_OUT` на `800_Ethernet`);
- осталось 23 `BUS_TYPE_REQUIRED` для будущих 900-шин без корневых
  WB-ресурсов — вне scope исправления слоёв, валидатор не выключен;
- в новом copy-only `DwgSyncService.apply_dwg_to_project`
  импортированы **194 CableLine, 58 Ethernet 8xx, 4 Board (включая
  SCS-20), 313 индивидуальных Conduit и 313 segment assignments**;
- ни одного ошибочно общего Conduit, старых экземпляров WB,
  BUS-узлов или root assignments;
- 23 Room и 10 project_setting сохранены; SQLite integrity=ok,
  foreign_key_check=0, повторный Preview не предлагает новые
  физические вставки;
- ожидаемые 313 `GOFRA_ID:PROJECT_CHANGED` означают
  **Project→DWG writeback**, а не ошибку импорта. Физическая запись
  в DWG — отдельный разрешаемый шаг, в этом задании не выполнялась.

Артефакты тестовой копии на авторизованном ПК:
`%TEMP%\NL_Project_3\issue-286-ethernet-live-diagnosis\cad_800_full_snapshot_review.json`,
`rebuild_with_800_contract_trial_report.json`,
`rebuild_with_800_contract_TRIAL.sqlite`.

## Граница готовности

Код в отдельном Draft PR до контролируемой установки. Нельзя
объявлять live SQLite обновлённой по факту зелёных тестов:
текущая рабочая база и DWG оставлены без изменений.

Следующий этап — проверенная резервная копия, контролируемое
переключение Project DB и install проверенной версии CAD-контракта;
пользователь создаст новые WB и BUS roots после сброса объекта.
