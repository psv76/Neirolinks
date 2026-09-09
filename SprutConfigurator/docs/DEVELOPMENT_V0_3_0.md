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

`bridge.alice` Service-scoped, потому что реальные команды Sprut адресуют `aId + sId`.

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

### Alice/Yandex enable

Снято с реального Sprut WebUI:

```json
{"params":{"bridgeService":{"create":{"bridgeIndex":"Yandex_1","aId":118,"sId":13,"write":true}}}}
```

Обе write-операции Alice теперь field-confirmed и зафиксированы в `rpc_contract.py`.

При этом generic APPLY для `bridge.alice` **пока остаётся заблокирован**. Причина теперь только одна: не подтверждён read-path текущего состава `Yandex_1`, поэтому Configurator пока не может достоверно выполнить:

```text
DISCOVER → diff → DRY RUN → APPLY → fresh DISCOVER → VERIFY
```

Запускать `create/delete` без надёжного определения текущего состояния нельзя: desired-state механизм обязан понимать, когда действие не требуется, и обязан подтвердить результат после записи.

## APPLY safety

Для `visible` и `statusVisible` действует полный существующий механизм:

```text
fresh DISCOVER
→ DRY RUN
→ APPLY confirmation
→ write CHANGE actions
→ fresh DISCOVER
→ VERIFY
```

Если plan содержит `bridge.alice`, DRY RUN остаётся fail-closed и APPLY не активируется до подключения подтверждённого bridge read adapter. Это предотвращает частичную запись остальных изменений перед ошибкой Alice.

## Offline tests

`SprutConfigurator/tests/test_presentation_core.py` проверяет:

- strict boolean validation;
- Service-scoped bridge contract;
- Characteristic type matching;
- `Service.visible` diff;
- `Characteristic.statusVisible` diff;
- Alice fail-closed без read adapter;
- VERIFY;
- точное соответствие builders четырём реально снятым `params`:
  - Service.visible;
  - Characteristic.statusVisible;
  - Yandex delete;
  - Yandex create/write=true.

После добавления create RPC ожидаемый regression-набор остаётся тем же по числу test-функций; тест `test_field_confirmed_rpc_params` теперь проверяет четыре RPC shape.

## Следующий блокирующий capture

Остался один внешний факт из WebUI:

```text
запрос/ответ, из которого WebUI узнаёт текущий состав Yandex_1
```

После него можно реализовать bridge read adapter, включить `create/delete` в общий APPLY и завершить Alice через полноценный VERIFY без догадок.
