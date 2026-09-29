# Sprut Configurator v0.2.2

Статус: **field-proven standalone baseline**.

Оригинальный рабочий source package сохранён в:

```text
SprutConfigurator/reference/v0.2.2/
```

Файл `sprut_configurator.py` в repository точно совпадает с исходным рабочим ZIP:

```text
Git blob SHA-1: 8cacfb101f979ed51bb94a5eb86dba634e670e03
SHA-256:        2cf996de6df1d6c3a1353faef4a2de66713d658155ec2f2ae45988dcc6e85781
size:           51433 bytes
```

## 1. Рабочий цикл

```text
DISCOVER
→ load YAML
→ validation
→ DRY RUN
→ fresh preflight DISCOVER + DRY RUN
→ explicit APPLY confirmation
→ APPLY only CHANGE operations
→ fresh DISCOVER
→ VERIFY
```

## 2. WebSocket

Подтверждённый endpoint:

```text
wss://web.spruthub.ru/spruthub
```

Subprotocol:

```text
json-rpc
```

## 3. Сессия и secrets

Пользователь локально копирует одно исходящее сообщение из WebUI WebSocket и вставляет его в Configurator.

Из него извлекаются:

```text
cid
token
serial
```

Политика v0.2.2:

- только RAM;
- не писать в YAML;
- не писать в логи;
- не экспортировать в discover snapshot;
- не хранить в application config.

## 4. Подтверждённые RPC

Rooms:

```json
{"params":{"room":{"list":{}}}}
```

Accessories:

```json
{"params":{"accessory":{"list":{"expand":"services,characteristics"}}}}
```

Rename Accessory:

```json
{"params":{"accessory":{"update":{"id":145,"name":"..."}}}}
```

Assign room:

```json
{"params":{"accessory":{"update":{"id":144,"roomId":3}}}}
```

Rename Service:

```json
{"params":{"service":{"update":{"aId":145,"sId":13,"name":"..."}}}}
```

Числовые ID в примерах — только runtime placeholders. Они никогда не должны становиться постоянными ключами plan.

## 5. DISCOVER

Читаются:

- rooms;
- accessories;
- services;
- characteristics;
- serial;
- model;
- roomId;
- online/runtime properties, доступные в ответе.

На основе DISCOVER строятся runtime lookup tables.

## 6. DRY RUN

Read-only стадия.

Статусы действий:

```text
SAME
CHANGE
ERROR
```

Baseline kinds:

```text
accessory_name
room
service_name
validation
```

При наличии `ERROR` APPLY недоступен.

## 7. APPLY safety model

Перед записью обязательно выполняется свежий DISCOVER и повторный DRY RUN.

Если YAML изменился после ранее просмотренного DRY RUN, пользователь должен выполнить DRY RUN заново.

Для разрешения массовой записи пользователь локально вводит:

```text
APPLY
```

Выполняются только операции со статусом `CHANGE`.

## 8. VERIFY

После APPLY выполняется свежий DISCOVER и независимое повторное сравнение с plan.

Для каждого target проверяется baseline contract:

- Accessory name;
- room;
- Service name.

`RPC success` не считается достаточным доказательством конфигурационного успеха.

Именно полевая проверка выявила, что Sprut может принять RPC, но нормализовать display name. Поэтому VERIFY — обязательная часть архитектуры.

## 9. UI

Reference v0.2.2 использует Tkinter и ориентирован на Windows.

Это UI standalone-инструмента, а не обязательная часть engine contract.

## 10. Проверка исходного selftest

Оригинальный `selftest.py` из рабочего пакета проверен вместе с исходными fixtures:

```text
targets: 51
changes: 167
errors: 0
PASS: YAML parsed; 51 targets resolved; no DRY RUN errors; pre-APPLY differences detected.
```

Object-specific fixtures не дублируются в generic source tree; baseline YAML вынесен в `objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/`.

## 11. Что считается проверенным ядром

Не нужно переизобретать без причины:

- stable SERIAL matching;
- room-by-name;
- Service-by-type;
- session parsing;
- WebSocket transport;
- declarative diff;
- mandatory DRY RUN;
- fresh preflight;
- explicit APPLY confirmation;
- fresh VERIFY;
- token-in-memory policy;
- display-name round-trip validation.

## 12. Что не входит в v0.2.2 baseline

Configurator v0.2.2 ещё не изменяет:

```text
Service.visible
Characteristic.statusVisible
Alice/bridge policy
Service order
прочие presentation properties
```

Эти функции должны добавляться отдельными проверяемыми итерациями.
