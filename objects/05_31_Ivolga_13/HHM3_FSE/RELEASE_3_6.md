# HHM 3.6 — выбег насосов 501–504 и завершение operator logging

Основание: #69, #81 и live-проверка HHM 3.5 на Иволге 29.09.2026.

## Подтверждённые полевые факты

- 502: выбег 120 с прошёл полевой тест.
- 504: live-журнал показал 120 с от начала выбега до команды OFF насосу.
- 501: live-журнал показал выключение без выбега; это соответствовало конфигу 3.5 `pumpPostrunMs=0`.
- пользователь отдельно подтвердил фактический переход котла `Ожидание → Зима ЦО + ГВС` после перезагрузки и изменения уставок термостатов; отсутствие этого фрагмента в конкретном WebUI export не считать отсутствием перехода.

## Выбег насосов

Для Иволги в 3.6 явно закреплено:

```text
501 = 120000 ms
502 = 120000 ms
503 = 120000 ms
504 = 120000 ms
505 = 0 ms
```

505 в решение 501–504 не включён и остаётся без выбега до отдельного согласования.

Для 501/502/503 зональные приводы имеют расчётное закрытие 180 с; 120-секундный выбег остаётся меньше полного времени закрытия при `collectorHasBypass=false`.

## Operator logging

Live 3.5 показал повтор `BOILER_SETPOINT_COMMAND=40` примерно через 30 с без изменения требуемой уставки. Причина соответствует техническому reassert output после истечения write cache и не должна выглядеть новым операторским событием.

3.6:
- сохраняет последнее operator-значение setpoint в `PersistentStorage hhm3_operator_log`;
- повторная запись того же значения в том же heating session не журналируется;
- restart сам по себе не превращает неизменную уставку в новое operator event; если после restart подтверждён новый переход в Winter, одна запись setpoint допустима как начало новой heating session;
- подтверждённый переход `Ожидание → Зима ЦО + ГВС` заново разрешает ровно одно setpoint event, даже если значение совпадает с предыдущей сессией;
- дальнейшие неизменные reassert снова подавляются.

Mode command и mode readback остаются отдельными operator events.

## TIMER_ZONE_OPEN_FINISHED

В live WebUI export 3.5 были видны `TIMER_ZONE_OPEN_STARTED`, но отсутствовали строки окончания. Код и Node regression генерируют FINISHED/CANCELLED. Поскольку сам export повторяет блоки и содержит управляющие байты, 3.6 не меняет эту логику вслепую. Требуется отдельно отличать raw event от дефекта WebUI export.

## Что не меняется

- Current Boiler Mode contract 0/1;
- порядок Winter readback → Heating Setpoint;
- WB-MAO4 OFF contract;
- Sensor Health;
- thermal protection;
- output ownership;
- 505 postrun;
- NLI transaction semantics.

## Acceptance

- 501/502/503/504: `pumpPostrunMs=120000`;
- 505: `pumpPostrunMs=0`;
- 501 и 503 model regression подтверждает 120 с от снятия последнего зонального запроса до pump OFF;
- периодический 30-секундный reassert неизменной Heating Setpoint не создаёт новое operator event;
- после restart прежний setpoint допускается только после нового подтверждённого Winter session;
- Standby→Winter создаёт одну mode command, один mode readback и затем одно setpoint event;
- полный HHM3 CI и NLI CI зелёные.
