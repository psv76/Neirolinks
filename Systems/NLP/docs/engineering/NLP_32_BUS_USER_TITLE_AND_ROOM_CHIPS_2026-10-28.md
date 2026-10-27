# NLP 3.2 — проектное имя шины и цветовая маркировка помещений

Дата: 28 октября 2026. Канонический путь: `Systems/NLP`, ветка `main`.

## Контракт: два независимых уровня имени

- **`bus.display_name`**: необязательное пользовательское название *целой физической шины*, хранится в рабочей SQLite Project; сохраняется после перезапуска. Не изменяет `bus.designation`, `BUS_ID`, ресурс-источник, порядок `9YY.ZZZ`, кабель, трубу, длины, маршруты, параметры контроллера и оригинальные DWG-атрибуты.
- **`field_device.normalized_fields_json.LOAD_NAME`**: инженерное имя *отдельного* подключённого устройства/кабельного вывода, продолжает приходить из AutoCAD; его не редактирует команда изменения общего имени.
- При пустом пользовательском названии родительская строка возвращается к построенному из полевых `LOAD_NAME` краткому перечислению. Для самостоятельного назначения сохранённое имя показывается вместо перечисления, а полный список `9YY.ZZZ: LOAD_NAME` сохраняется в подсказке.
- В NLP 3.2: вкладка **Линии** → найти родительскую `9YY` → **двойной щелчок по «Назначение»** → изменить общее название. Пустая строка сбрасывает ручное имя и включает автоматический список.
- Защита Project: изменение применяется по паре `(project_id, bus_id)`; не создаёт и не изменяет шину другого Project; более 160 знаков запрещено, многострочное значение запрещено.

## Откуда метки помещений

Для каждой физически включённой `bus_endpoint → field_device` читается каноническое `field_device.room_id → room.id/name/display_json.marking_color`. Маркеры собираются без дубликатов по `room.id` и передаются в существующий `ROOM_MARKERS_ROLE`/ `RoomChipDelegate`, точно как у других кабельных линий. В исходном объекте Богданович **80/80** полевых точек шин уже имеют ненулевую каноническую связь с Room; создавать новые помещения не требуется. Неразрешённые связи продолжают показываться предупреждением, цвета и комнаты не выдумываются по сырым `ROOM` из DWG.

Пример на **копии реальной базы**: `921` → **Детская 2** (цвет `#F8D7E8`), **Будуар 2** (`#EADCF8`), **Ванная Детская 2** (`#FADFC8`). Пять `LOAD_NAME` отдельных электрокарнизов остаются доступными в раскрытии после установки общего имени.

## Схема, бэкапы, проверка

Добавлена строго аддитивная Alembic revision `000000000018` поверх `000000000017`: nullable `bus.display_name TEXT`, без backfill и изменения иных данных. Guard downgrade запрещает потерю непустых авторских названий. Обычный runtime требует head 18 и не выполняет миграции автоматически, даже если поле `display_name` в старой тестовой схеме уже случайно создано bootstrap metadata.

Репетиция на реальном DB-copy: `D:\NLP_3_BACKUPS\nlp32_bus_title_schema18_trial.sqlite`; исходная копия версии 17; официальное `upgrade_database` создало verified backup `D:\NLP_3_BACKUPS\nlp32_bus_title_schema18_trial_verified_backup\`. Переход 17→18 PASS, изменения и сброс имени 921 PASS, чтение канонических маркеров PASS. 1 Project, 5 Board, 27 Bus, 80 BusEndpoint, 80 BusSegment, 608 FieldDevice, 207 CableLine, 418 Conduit, 26 ProjectInstance сохранены. `PRAGMA integrity_check=ok`, `foreign_key_check=0`.

**Рабочая база обновлена PASS (28.10.2026 03:40, Екатеринбург).** Перед применением проверено отсутствие GUI/Python NLP процессов; исходный SHA-256 SQLite: `d3f0593ab72599e750b97d2b33bfc80b99a906fcb077e6f918714bbd562485e6`. Штатный guarded installer `tools/apply_nlp32_bus_display_name.py` подтвердил этот SHA, создал verified backup `D:\NLP_3_BACKUPS\nlp32_bus_title_schema18_20261028T034056053923\nl_project_3.000000000017.backup.sqlite` с SHA-256 `a4b398fca4c5c15ae8803cdde3cb0530e3451beb3c4e6c55137d22c74af7eeee`, затем выполнил `upgrade_database` 17→18. `DatabaseManager.open_existing` + `BusService.journal_cards` для всех 27 BUS: PASS. Все 1 Project, 5 Board, 1 Building, 23 Room, 27 Bus, 80 BusEndpoint, 80 BusSegment, 608 FieldDevice, 207 CableLine, 329 CableSegment, 418 Conduit, 329 assignments, 26 ProjectInstance, 298 InstanceResource, 1 FunctionalRelation сохранены. `integrity_check=ok`, `foreign_key_check=0`. Receipt: `D:\NLP_3_BACKUPS\nlp32_bus_title_schema18_20261028T034056053923\migration_receipt.json`. Рабочая SQLite имеет head18; объектовый DWG и инженерные данные не менялись. Результаты полного тестового набора: **280 PASSED**, одно предупреждение Python/sqlite3 о datetime-адаптере.

## Тесты

- `tests/persistence/test_nlp32_bus_display_name_migration.py`: полноценный переход 17→18 с verified backup, проверка новых/старых схем, startup acceptance.
- `tests/buses/test_nlp32_bus900_journal.py`: хранение имени Project, reset, независимость от DWG, запрет чужого Project, запрет >160 символов, canonical room marker colors.
- `tests/integration/test_nlp32_lines_readability.py`: Qt `ROOM_MARKERS_ROLE`, вызов редактора родительской строки BUS по двойному щелчку (не редактирование CHILD точки).
- Regression tests for previous migration adapted to check explicit revision 17 instead of asserting there can never be later schema revisions.
