# Sprut Configurator v0.3.0-dev — Issue #22

Статус: **рабочая ветка**, не production.

## Что реализовано

Поверх frozen reference `v0.2.2` добавлен development launcher:

```text
SprutConfigurator/sprut_configurator_dev.py
```

Новый presentation core:

```text
SprutConfigurator/src/presentation_core.py
```

Он реализует read-side для YAML `format_version: 2`:

```text
validation
→ DISCOVER matching
→ diff
→ DRY RUN
→ VERIFY
```

Поддерживаемые desired-state свойства:

```text
services[].visible
services[].status.<CharacteristicType>
bridge.alice
```

### `Service.visible`

Текущее значение читается из `Service.visible` в DISCOVER.

### `Characteristic.statusVisible`

Characteristic выбирается по устойчивому типу. Read parser допускает фактически встречающиеся формы:

```text
Characteristic.type
```

или:

```text
Characteristic.control.type
```

Текущее значение берётся только из фактического `Characteristic.statusVisible`.

Если нужного поля нет, DRY RUN получает `ERROR`; значение не угадывается.

### Alice

Контракт и diff-механизм готовы через отдельный adapter `alice_state_getter`.

Путь хранения текущего состояния Alice в runtime Sprut пока не подтверждён. Поэтому при наличии `bridge.alice` и отсутствии подтверждённого adapter система работает **fail-closed**:

```text
bridge.alice → ERROR
```

а не считает состояние известным.

## Почему APPLY пока заблокирован

Issue #22 прямо запрещает придумывать write RPC.

Точные исходящие Sprut WebUI frames для:

```text
Service.visible
Characteristic.statusVisible
Alice bridge policy
```

ещё не сняты на реальном Sprut.hub.

Поэтому v0.3.0-dev имеет две защиты:

1. presentation policy уже участвует в DRY RUN / VERIFY;
2. если plan содержит presentation actions, кнопка APPLY остаётся disabled;
3. дополнительный fail-closed guard блокирует presentation APPLY до любой записи, если вызов всё же будет инициирован программно.

Это исключает опасный сценарий частичного APPLY: старые name/room изменения записались, а новые presentation actions упали позже.

## Offline tests

Файл:

```text
SprutConfigurator/tests/test_presentation_core.py
```

Проверяет:

- строгую validation boolean-полей;
- поиск Characteristic type;
- diff `Service.visible`;
- diff `Characteristic.statusVisible`;
- Alice diff через тестовый adapter;
- fail-closed Alice без adapter;
- ошибку при отсутствии `statusVisible` в DISCOVER;
- presentation VERIFY.

Локальный прогон при разработке 2026-09-10:

```text
PASS test_alice_without_adapter_is_fail_closed
PASS test_characteristic_type
PASS test_diff_with_confirmed_alice_adapter
PASS test_missing_status_visible_is_error
PASS test_validation
PASS test_verify
```

## Следующий шаг

Нужны реальные outgoing WebSocket frames из Sprut WebUI для трёх операций:

1. включить/выключить `Service.visible`;
2. включить/выключить `Characteristic.statusVisible`;
3. включить/выключить мост в Алису для Accessory.

После подтверждения frames нужно:

```text
добавить write adapter
→ добавить action metadata cId
→ включить APPLY
→ fresh DISCOVER
→ VERIFY
```

Секретные `token`, `cid`, session `serial` в документацию и тесты не сохранять.
