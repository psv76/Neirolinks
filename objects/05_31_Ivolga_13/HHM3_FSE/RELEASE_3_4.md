# HHM 3.4 — операторский журнал по общему стандарту #94

Основание: #69, #94, PR #95 и полевой журнал Иволги 29.09.2026.

## Причина выпуска

Approved HHM 3.3 корректно исправил полевую регрессию A05 TTL, но операторский журнал оставался слишком подробным:

- обычный шаг регулирования создавал `OUTPUT_TRANSITION`;
- в строке повторялись расчёт, write attempts, Level/Switch/pump readback и saved Level;
- каждый transition повторял «положение штока / вращение насоса / расход = Не измеряется»;
- штатные pending/output-handshake могли создавать краткие WARNING/INFO oscillation.

После принятия нового общего стандарта #94 / PR #95 это считается технической трассировкой, а не операторским событием.

## Изменение 3.4

- `OUTPUT_TRANSITION` и `VALVE_COMMAND_DROP` публикуются как machine-readable trace и не пишутся в operator journal;
- повторяющийся хвост «не измеряется» удалён;
- в operator journal остаются короткие изменения команды насосу и Switch горячего порта;
- штатные pending ON/OFF при сохранённом READY-пути уходят в trace;
- краткий source `REQUESTS_UNAVAILABLE` во время output handshake не создаёт operator oscillation; устойчивое состояние становится WARNING после `requestTtlMs`;
- timers, sensor LOST/RECOVERY, safety и реальные write/readback faults остаются operator events.

## Что не меняется

- алгоритм отопления;
- MAO4 contract;
- timeout/retry/fail-safe;
- postrun;
- Sensor Health;
- ownership outputs;
- source/OpenTherm policy;
- NLI 0.1.9 transaction engine.

## Предел доказанности

Readback электрического канала по-прежнему не является доказательством положения штока, вращения насоса или расхода. Эта граница закреплена в стандарте и diagnostic profile, но больше не повторяется в каждой строке operator journal.

## Проверка

До публикации approved 3.4 обязательны:
- HHM regression suite;
- logging regressions operator journal vs trace;
- release manifest reproduction;
- NLI compatibility;
- повторный boiler field check журнала без изменения прикладной логики.
