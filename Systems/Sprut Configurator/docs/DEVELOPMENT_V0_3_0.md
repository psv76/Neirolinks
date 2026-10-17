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

Field-confirmed RPC/read contract:

```text
SprutConfigurator/src/rpc_contract.py
```

YAML `format_version: 2` поддерживает:

```text
services[].visible
services[].status.<CharacteristicType>
services[].bridge.alice
```

`bridge.alice` Service-scoped, потому что реальные команды Sprut адресуют `aId + sId`.

## Field-confirmed Sprut WebUI contract 2026-09-10

### Service.visible

```json
{"params":{"service":{"update":{"aId":118,"sId":13,"visible":false}}}}
```

### Characteristic.statusVisible

```json
{"params":{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}}
```

### Alice/Yandex disable

```json
{"params":{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}}
```

### Alice/Yandex enable

```json
{"params":{"bridgeService":{"create":{"bridgeIndex":"Yandex_1","aId":118,"sId":13,"write":true}}}}
```

### Alice/Yandex read

Запрос:

```json
{"params":{"bridgeService":{"list":{"bridgeIndex":"Yandex_1"}}}}
```

Подтверждённая форма ответа:

```json
{
  "result": {
    "bridgeService": {
      "list": {
        "services": [
          {
            "aId": 118,
            "sId": 13,
            "write": true,
            "key": "Bridge:Yandex_1",
            "bridgeIndex": "Yandex_1"
          }
        ]
      }
    }
  }
}
```

Текущее состояние Alice определяется по точному совпадению пары:

```text
(aId, sId)
```

в `result.bridgeService.list.services` для `bridgeIndex = Yandex_1`.

Отсутствие пары означает `alice: false`; наличие пары — `alice: true`.

## Полный presentation lifecycle

После подтверждения read-path все три presentation policy включены в один desired-state цикл:

```text
DISCOVER
→ accessory.list + bridgeService.list(Yandex_1)
→ diff
→ DRY RUN
→ APPLY confirmation
→ write только CHANGE
→ fresh DISCOVER
→ VERIFY
```

Для `bridge.alice`:

```text
false → true  : bridgeService.create(..., write=true)
true  → false : bridgeService.delete(...)
```

Runtime `aId`, `sId`, `cId` не сохраняются в YAML и каждый раз берутся из свежего DISCOVER.

Если DISCOVER JSON старого формата не содержит блока `bridges.Yandex_1`, а YAML требует `bridge.alice`, DRY RUN остаётся fail-closed: состояние не угадывается.

## Offline tests

`SprutConfigurator/tests/test_presentation_core.py` проверяет:

- strict boolean validation;
- Service-scoped bridge contract;
- Characteristic type matching;
- `Service.visible` diff;
- `Characteristic.statusVisible` diff;
- fail-closed Alice без read adapter;
- VERIFY;
- точные field-confirmed RPC для visible/statusVisible/Yandex list/create/delete;
- parser `result.bridgeService.list.services`;
- membership по паре `aId+sId`;
- отказ parser при неизвестной форме ответа.

Python-файлы, изменённые при добавлении read-path, прошли `py_compile` локально перед commit.

## Что ещё не подтверждено реальным APPLY

Кодовый контракт presentation policy теперь полный, но Issue #22 требует отдельного полевого acceptance:

```text
реальный YAML Иволги
→ clean DRY RUN
→ APPLY
→ fresh DISCOVER
→ VERIFY FAILED=0
```

До этого v0.3.0-dev остаётся development build.
