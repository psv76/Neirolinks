# Sprut plan YAML contract — format_version 1

## 1. Назначение

YAML — декларативный desired state, который передаётся Configurator.

Он отделяет вопрос:

```text
каким Sprut должен быть
```

от вопроса:

```text
как безопасно привести текущий Sprut к этому состоянию
```

## 2. Минимальная схема

```yaml
format_version: 1
object: optional human-readable context

accessories:
  - serial: "<stable serial>"
    name: "<Accessory display name>"
    room: "<existing Sprut room name>"
    services:
      - type: "<Sprut Service type>"
        name: "<Service display name>"
```

Поле `object` информационное и не участвует в matching.

## 3. Обязательные поля

Accessory:

```text
serial
name
room
```

Service:

```text
type
name
```

## 4. Matching

### Accessory

Только по:

```text
serial
```

Если в Sprut нет такого SERIAL — `ERROR`.

Если найдено несколько Accessory с одинаковым SERIAL — `ERROR`.

### Room

По точному имени комнаты.

Если комнаты нет — `ERROR`.

Если имя комнаты неоднозначно — `ERROR`.

### Service

По `type` внутри найденного Accessory.

Если Service такого типа нет — `ERROR`.

Если внутри Accessory несколько Service одного типа — выбор только по `type` считается неоднозначным, DRY RUN должен остановиться с `ERROR`.

## 5. Что YAML v1 намеренно не хранит

```text
accessoryId
sId
roomId
Sprut token
cid
Sprut session serial
```

Runtime ID каждый раз читаются через свежий DISCOVER.

## 6. Validation baseline v0.2.2

Проверяются:

- `format_version == 1`;
- уникальность SERIAL в plan;
- обязательные поля;
- наличие target Accessory в DISCOVER;
- duplicate SERIAL в Sprut;
- существование комнаты;
- однозначность room name;
- существование Service type;
- однозначность Service type;
- round-trip ограничения display name.

## 7. Display-name constraints

Полевым тестом подтверждены ограничения текущего Sprut.hub:

### Максимум 32 символа

Имя длиннее 32 символов нормализуется/обрезается Sprut. Configurator v0.2.2 считает такой plan ошибочным до APPLY.

### Ведущий цифровой префикс с точкой

Наблюдалось преобразование вида:

```text
5. Свет ...
→
5 Свет ...
```

Поэтому pattern:

```text
^\d+\.\s
```

в v0.2.2 запрещён как не обеспечивающий точный round-trip VERIFY.

## 8. Свойства, которых ещё нет в format_version 1 baseline

На момент фиксации v0.2.2 YAML не описывает:

```text
Service.visible
Characteristic.statusVisible
bridge / Alice policy
read-only presentation policy
порядок отображения
```

Если эти свойства добавляются следующими задачами, contract должен быть расширен явно, с обновлением validation, diff, APPLY и VERIFY.
