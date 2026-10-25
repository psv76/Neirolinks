# #235 / #227: совместимость кандидатов, 23.10.2026

Это schema-only подготовка draft #236, не merge/production/runtime acceptance.

## Проверенные ревизии

- main `8f566f7a1eddb2c7eb4242dd275cdd775ca79a89`.
- [#236](https://github.com/psv76/Neirolinks/pull/236) до изменения: `337fcb41c334204d008c98043e7a5dfc3130ce3f`, draft, 71 definition.
- [#227](https://github.com/psv76/Neirolinks/pull/227): `2c7dcebabbd37b4ac821d256978642b9cacef1f0`, open **не draft**, 72 definitions. Состояние #227 этой работой не меняется.

Оба JSON объявляют `contract_version=3.1.0`, но содержат разные exact profiles.
Версия сама по себе не определяет совместимость: до согласованной интеграции
фиксировать repository/commit SHA и содержимое JSON/schema. Номер новой версии
или публикация Release этим аудитом не утверждаются.

## Доказанные коллизии и безопасное исправление

1. #227 добавляет BUS_OUTLET/CABLE_OUTLET_BUS, family `bus_kind` и `allowed_groups`.
   Схема #236 запрещала два последних ключа через additionalProperties=false.
   В этой работе они добавлены как **необязательные**: bus_kind строго
   RS485/DALI/KNX; allowed_groups — непустой уникальный список существующих
   десяти групп. Неизвестные ключи по-прежнему запрещены.
2. Actual JSON #236 остаётся на 71 definitions: CABLE_OUTLET_BUS туда не добавлен,
   passive BUS_ID, TRACK.NNN, CABLE_TRANSIT и dual 3YY/4YY сохранены. Это подготовка
   schema к метаданным существующего PR, не заявление поддержки #227 runtime.
3. Замена JSON целиком на #227 откатит target BOX/TRACK profiles; замена на #236
   потеряет BUS_OUTLET и protocol metadata #227. Требуется объединение по смыслу
   отдельных profiles/families, а не выбор одного файла целиком.
4. #227 `catalog.py` читает allowed_groups и bus_kind; его validator определяет
   протокол по Project Bus, запрещает неизвестный тип и проверяет specialized
   block conflict. Нельзя вернуть эвристику DALI по наличию BUS_SOURCE или RS485
   fallback. Это не отменяет текущие ограничения RS485/KNX.
5. #227 DALI/KNX BUS_SOURCE по-прежнему требует `9YY.ZZZ`; #235 принимает физические
   BOX/TRACK для DALI. Совместная реализация должна расширить именно DALI typed
   source resolution и passive identity/owners, сохранив ограничения KNX/RS485.
   Наличие schema-valid JSON не доказывает эту поддержку.

## Воспроизводимая проверка

`tools/probe_issue235_bus_outlet_schema.py` читает pinned Git objects #227 и
предыдущего #236. В памяти сохраняет все target profiles #236, добавляет ровно
BUS_OUTLET/CABLE_OUTLET_BUS и metadata #227. Файлы контрактов не записывает.

Фактически проверено: старая schema отвергает metadata; обновлённая принимает
71-definition candidate и экспериментальную композицию 72 definitions;
четыре отрицательные мутации (неизвестный bus_kind, неизвестная группа,
пустой список и дубли групп) отвергаются. Passive BOX/TRACK остаются с BUS_ID,
BUS_OUTLET сохраняет BUS_POINT_ID без BUS_ID. Probe не загружает application,
не открывает DB/DWG и не выполняет миграций.

Существующий `check_issue235_target_contract.py` дополнен schema fixtures этих
полей (positive + четыре negative), поэтому текущий CI проверяет расширение.
Полная композиция #227 проверена локальным probe, не существующим CI workflow.

## До интеграции

- Зафиксировать единый reviewed JSON/schema revision, проверить 72 exact profiles
  и human parity, сохранив четыре target profiles #235 и 14 тегов BUS_OUTLET.
- Прогнать #227 protocol/no-fallback/graph/sync regression вместе с #237 passive
  BOX/TRACK, TRACK_DALI voltage и transit tests. Старые результаты #227 не
  переносить на объединённый стек автоматически.
- Проверить owner-aware selective apply, no-op/rollback, старые BUS_POINT_ID
  mappings и сохранение Conduit assignments/manual overrides.
- Сохранить принятые Q01–Q11 с уточнением высот от чистого пола; исправление
  формулы #231 остаётся отдельным техническим gate.
- Locked full-suite, Windows и отдельно разрешённая AutoCAD/live приёмка ещё
  необходимы. Никаких новых Issues, main merge, production-кода или live данных
  эта работа не меняет. Gate 1 остаётся открыт.
