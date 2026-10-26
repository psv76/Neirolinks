# Issue #286 — контролируемый ремонт и пересборка базы Богдановича (2026-10-26)

## Scope of release

Источник истины — текущий сохранённый `House_2/working.dwg`; `CABLE_ID`
существующего смонтированного кабеля **не перенумеровывать по прежней SQLite**.
Пользователь поручил заменить базу, оставив **только** 23 Room (включая
отметки, высоты, цвета), 10 Project settings (включая длины и запасы),
идентичность здания/проекта и техническую схему/системный каталог.
WB/project_instances, BUS roots, кабельные линии, Conduits, все старые
общие трубы и их назначения не переносить. Новые WB и BUS roots будут
заданы после чистой пересборки.

Этот узкий релиз намеренно **НЕ ВКЛЮЧАЕТ** рабочий экран «Трассы» B из
непринятого полностью Draft PR #291. Включены только четыре проверенных
repair commit (Ethernet Apply diagnostics, BUS-conduit isolation,
GOFRA auto-id reuse, CAD 800_Ethernet BOARD_SCS/FRAME).

## Фактические данные, снимки и контроль

- Открытый DWG очищен **по прямому запросу пользователя** отдельным
  действием: 361 `GOFRA_ID`, все пустые, 195 исходных значений были
  очищены, остальные 7738 атрибутов имеют тот же контрольный хеш.
  **Дальнейшая перезапись DWG не входит** в этот шаг релиза.
- Свежий полный COM scan уже после очистки: **585 вставок**, 58
  Ethernet 8xx. По сравнению с ранним снимком добавлены две SOCKET_IN
  `118.01` и одна `FRAME_2`; изменение положений ещё 12 существующих
  вставок. Принят **актуальный** снимок, а не старый набор на 582.
  Snapshot SHA256 `92c73a6f64540813d368ca60dd24d7e70e5bac0902f53002a511f4a62d4f1bc3`.
- Проверенный pre-deployment backup рабочей SQLite:
  `D:\NLP_3_BACKUPS\issue-286-rebuild-20261026\before_rebuild_20261026T163117Z.sqlite`,
  SHA256 `b24b1588802949d8722349dc1c2dac3a2325651f70feea0ee65a89d4a6590216`,
  source before/after hash `7a3c45f75e5341df6069ef8b32b23606cde490c7b55f0c7b3265f8f105bba5ba`.
  Схема `000000000017`, целостность OK, FK=0.
- Отдельный пересобранный файл:
  `D:\NLP_3_BACKUPS\issue-286-rebuild-20261026\staged\nl_project_3_rebuilt_05_44_20261026.sqlite`,
  hash до startup smoke
  `5207e2534aad521c0cd15965b1a0fb7ea1fd33b9f936649869b5728c4cb7e90f`.
  **194** CableLines; **58** Ethernet; **4** Boards, включая SCS-20;
  **313** индивидуальных Conduits + 313 назначений, **0** общих;
  **23** Room, **10** settings, **0** WB instances/BUS roots;
  `PRAGMA integrity_check=ok`, `foreign_key_check=0`;
  повторный scan: **0** повторных NEW insertions, **0** GOFRA conflicts.
- 313 `GOFRA_ID:PROJECT_CHANGED` — будущая штатная операция
  Project→DWG записи назначенных номеров (отдельное разрешение).
- **23** `BUS_TYPE_REQUIRED` из-за намеренно отсутствующих новых
  WB root assignments пока допустимы при пересборке; не подавлять
  в CAD контракте. Все 25 прежних ошибок BOARD_SCS/FRAME на
  `800_Ethernet` исправлены.
- Narrow release Python checks: **164 PASS**, Ruff PASS.
  GUI offscreen `python -m nl_project_2 --auto-close-ms 1600`
  c отдельными root dirs и **копией** staged SQLite:
  exit code **0**. Не использовалась рабочая SQLite, AutoCAD не трогался.

## Переключение

1. Установить только эти repair commits в source-of-truth `main`.
2. Убедиться, что рабочая программа NL Project не запущена и текущий
   файл рабочей SQLite совпадает с pre-deployment SHA256.
3. Снять ещё одну проверенную копию при необходимости, выполнить
   rollback-capable file replacement из подготовленного файла.
4. Выполнить startup smoke на **рабочем** пути, подтвердить project,
   23 Room, 10 settings, 4 Boards, 194 Lines, 58 Ethernet, 313 труб,
   no shared Conduits, zero старых WB/BUS roots, целостность и FK OK.
5. AutoCAD оставить открытым. Не пытаться создавать BUS roots за пользователя
   и не писать GOFRA_ID обратно в DWG без отдельного согласования.

Backup и staged файлы сохранять; PR #291 остаётся Draft/unmerged.
