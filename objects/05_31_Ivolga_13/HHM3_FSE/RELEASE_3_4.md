# HHM 3.4 — операторский журнал и техническая трассировка

Основание: #69, новый общий стандарт #94 / PR #95 и полевые журналы Иволги 29.09.2026.

HHM 3.4 не меняет алгоритмы отопления, гидравлические ограничения, ownership выходов,
Sensor Health Contract, postrun, A05 readback contract или OpenTherm policy относительно 3.3.
Изменяется только наблюдаемость и представление событий.

## Причина выпуска

HHM 3.3 сделал журнал существенно понятнее, но обычное регулирование по-прежнему
создавало избыточный операторский поток:

- каждый `OUTPUT_TRANSITION` писал полный snapshot расчёта, write attempts и readback;
- повторялся хвост `положение_штока=Не измеряется; вращение_насоса=Не измеряется; расход=Не измеряется`;
- штатный partial-ready мог давать WARNING/INFO oscillation;
- короткие `REQUESTS_UNAVAILABLE ↔ ACTIVE` источника могли появляться из-за обычной
  фазы подтверждения нового output command.

По новому стандарту операторский журнал и глубокая техническая диагностика разделены.

## Изменение 3.4

### Operator journal

Остаются значимые события:

- изменение команды насосу;
- значимая команда закрыть горячий порт и подтверждение readback;
- таймеры открытия зоны и выбега — только start/finish/cancel/interruption;
- safety/overheat;
- output write/readback faults;
- sensor health LOST/RECOVERY;
- существенные состояния источника;
- восстановление после ошибок.

Обычный regulator handshake не журналируется как INFO на каждом шаге.

### Technical trace

Подробные данные перенесены в отдельный MQTT topic:

```text
/neiro/ivolga/hhm3/trace
```

Trace содержит machine-readable переходы, включая расчёт клапана, write attempts,
readback Level/Switch/pump, saved Level, readiness и внутренние transient states.

Trace не пишет строки в `journalctl -u wb-rules` и не влияет на управление.

### Sensor Health

Подробные phase/reason/cause/value/Sensor OK/error уходят в trace.
Operator journal пишет короткое событие при реальной непригодности и короткое recovery.
Ожидаемая startup qualification не объявляется операторской ошибкой.

### Source

Короткий `REQUESTS_UNAVAILABLE`, исчезнувший раньше `sourceJournalDelayMs`, остаётся
только в trace. Устойчивое состояние после задержки журналируется.
Текущее поле источника в VD показывает русский текст состояния.

## Границы доказательства

Команда, readback и физический результат остаются различными сущностями.
Switch readback не доказывает ход штока, команда насосу — вращение или расход.
Эти ограничения не повторяются механически в каждой строке operator journal.

## Release policy

Approved HHM 3.3 остаётся неизменяемой историей.
3.4 публикуется только новым immutable runtime commit, новыми role manifests и новым
approved tag после green CI/review. Никакие assets 3.3 не переписываются.

Live deploy, restart контроллеров и физические команды этой веткой не выполняются.
