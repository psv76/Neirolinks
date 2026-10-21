# NL Project 3.0 — арифметика длин, Stage C (Issue #216)

**Статус:** draft implementation на основе изолированного PR #218. Решения Q04/Q05/Q08 приняты, но полная интеграция физических окончаний, транзита и старых MOUNT_HEIGHT не завершена. Это не live acceptance и не разрешение менять рабочую SQLite.

## Реализовано

- Сохраняется чистое `G` у `CableSegment` и `BusSegment` для всех MOUNT_WAY. Специальная добавка «В брусе» `0,5 м` исключена из расчётного ядра, проектных настроек и отображаемой расшифровки. Требование защитной трубы для бруса не отменено.
- `G × (1 + P_nonlinearity + P_bypass)` используется в ordinary/BUS расчёте. К выводам и абсолютной дополнительной длине проценты не применяются; проценты не умножаются друг на друга.
- `RoundUp(L,q)` использует Decimal-safe политику из PR #218; q положителен, объектовый default `1 м`, допускается, например, `0,5` и `0,1`. Длина всей CableLine округляется единожды; не округляются отдельные сегменты.
- Для одного отдельного авто-Conduit с подтверждённым G физической длиной служит `RoundUp(G × factor,q)` без кабельных выводов. Для нескольких сегментов с неподтверждённой общей физической геометрией длина остаётся неизвестной, а не суммой/максимумом. Подтверждённая `USER_CONFIRMED` длина сохраняется.
- При вычислении `По потолку` C = B + высота помещения × 1000; MOUNT_HEIGHT использует тот же строительный ноль, что и B. Плоская стяжка/стена/брус и вертикали потолка выполняют отдельные согласованные формулы.
- Настройка «Нелинейность трассы» использует прежний persisted key `cable_meander_percent` и не обнуляет пользовательский процент. Добавлен отдельный key `cable_rounding_step_m`, старое хранилище `cable_timber_segment_reserve_m` больше не участвует в расчёте (без разрушительной миграции).
- `CALCULATION_REVISION=2` отделяет старую сохранённую геометрию, включая TIMBER +0.5, от новой. Старый сегмент `calculation_revision=1` не может подтверждать новую автоматическую длину трубы: вместо этого результат помечается неполным. Ручной override не теряется.

## Каноническая математика

```text
G_line = Σ G(unique CableSegment)
R_line = Σ G(segment) × (1 + P_nonlinearity + P_bypass)
Cable_raw = R_line + confirmed BoardEnds + confirmed BoxEnds + confirmed DeviceEnds + L_additional
Cable_auto = RoundUp(Cable_raw, q)
Cable_final = manual_full (if confirmed) else Cable_auto
Conduit_auto = RoundUp(G_conduit × (1 + P_nonlinearity + P_bypass), q)
Conduit_final = manual_confirmed (if present) else Conduit_auto
```

## НЕ реализовано / gates

1. **Q04 physical ends.** Текущие legacy `board_reserve_for_line`, `_distribution_box_line_count`, `_endpoint_mechanism_count` ещё используют упрощения (логическая линия, степень EL_BOX, три вида подрозеточных устройств). Их нельзя объявить нормой реальных физических концов. Production-real `ActualCableEnd` должен получать уникальные физические ID и факт коммутации. Выделенный pure policy PR #218 поддерживает explicit per-end overrides, но legacy адаптер их пока не создаёт.
2. **Q05 старые MOUNT_HEIGHT.** Историческая документация предполагала высоту от чистого пола. Необходимо исследование реальных уже сохранённых DWG/Project отметок и разрешённый migration/normalization plan. Этот PR не переписывает DWG и не утверждает корректность прежней базы.
3. **Q02 continuous physical-only EL_BOX.** Транзит одного кабеля через последовательные Conduit ещё не полностью представлен в persistence, и нельзя считать отдельные графовые рёбра самостоятельными коммутациями.
4. **Q03/Q06 shared Conduit.** Для общей трубы геометрия должна быть известна у самой физической Conduit по подтверждённым границам. Автоматическое вычисление из одной произвольно выбранной CableSegment/BusSegment запрещено. Production compatible assignments и BUS mirror ещё в draft PR #222/#224/#228/#229.
5. **Ранее сохранённые длины.** Смена `CALCULATION_REVISION` не является автоматической миграцией рабочей базы. Требуется approved verified backup → разрешённый расчёт/миграция данных → smoke + точечная DWG проверка. До этого не объявлять production PASSED.

## Приёмочные тесты

Ветка содержит независимые `tests/unit/test_length_policy.py` из PR #218 и новые/адаптированные тесты `tests/cables/test_length_domain.py`, `tests/cables/test_p0004_segment_recalculation.py`, `tests/buses/test_recalculation.py`. Запуски и результаты приводятся в PR и Issue #216 только после фактического выполнения.

Этот этап не создаёт новый Issue, не меняет schema head/catalog, не связывает запись с UI «Трассы» B и не выполняет live acceptance.
