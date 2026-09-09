# Sprut Configurator v0.3.0-dev — Issue #22

Статус: **рабочая ветка, не production**.

## Реализовано

Development launcher:

```text
SprutConfigurator/sprut_configurator_dev.py
```

Presentation core:

```text
SprutConfigurator/src/presentation_core.py
```

Field-confirmed RPC builders:

```text
SprutConfigurator/src/rpc_contract.py
```

Поддержан read/diff/DRY RUN/VERIFY для YAML `format_version: 2`:

```text
services[].visible
services[].status.<CharacteristicType>
services[].bridge.alice
```

`bridge.alice` теперь Service-scoped, потому что реальная команда Sprut адресует `aId + sId`.

## Field-confirmed RPC 2026-09-10

### Service.visible

Снято с реального Sprut WebUI:

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

В v0.3.0-dev этот action уже разрешён в APPLY после успешного свежего DRY RUN.

### Characteristic.statusVisible

Снято с реального Sprut WebUI:

```json
{"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}}
```

В v0.3.0-dev этот action уже разрешён в APPLY. `cId` всегда берётся из свежего DISCOVER по Characteristic type.

### Alice/Yandex disable

Снято с реального Sprut WebUI:

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

Команда сохранена как field-confirmed contract, но **generic APPLY для `bridge.alice` пока заблокирован**.

Причина: для полноценного desired-state цикла всё ещё нужны:

1. read-path текущего состава `Yandex_1` для DRY RUN/VERIFY;
2. exact enable/create RPC.

Одностороннее `delete` без возможности надёжно прочитать состояние и вернуть `true` не считается законченной bridge policy.

## APPLY safety

Для `visible` и `statusVisible` теперь действует полный существующий механизм:

```text
fresh DISCOVER
→ DRY RUN
→ APPLY confirmation
→ write CHANGE actions
→ fresh DISCOVER
→ VERIFY
```

Если plan содержит `bridge.alice`, DRY RUN остаётся fail-closed и APPLY не активируется. Это предотвращает частичную запись остальных изменений перед ошибкой Alice.

## Offline tests

`SprutConfigurator/tests/test_presentation_core.py` проверяет:

- strict boolean validation;
- Service-scoped bridge contract;
- Characteristic type matching;
- `Service.visible` diff;
- `Characteristic.statusVisible` diff;
- Alice fail-closed без read adapter;
- VERIFY;
- точное соответствие builders трём реально снятым `params`.

Локальный прогон после получения реальных frames:

```text
PASS test_alice_without_adapter_is_fail_closed
PASS test_characteristic_type
PASS test_diff_with_confirmed_alice_adapter
PASS test_field_confirmed_rpc_params
PASS test_missing_status_visible_is_error
PASS test_validation
PASS test_verify
```

Все изменённые Python-файлы также прошли `py_compile`.

## Следующий блокирующий capture

Для завершения Alice нужны два факта из WebUI:

```text
A. включить обратно тот же Service в Алису → outgoing frame
B. запрос/ответ, из которого WebUI узнаёт текущий состав Yandex_1
```

После этого можно реализовать bridge read adapter, enable/delete APPLY и VERIFY без догадок.
