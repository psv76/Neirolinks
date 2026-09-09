# Архитектура Sprut Configurator

## 1. Слои системы

```text
NL Project / проектные данные
        ↓
Project-owned identity / MQTT contracts
        ↓
Wiren Board
        ↓
Sprut custom templates
        ↓
Sprut.hub actual state
        ↕
Sprut Configurator
        ↑
YAML desired state
```

## 2. Ответственность слоёв

### NL Project / Project model

Владеет проектным смыслом:

- project ID;
- помещение;
- назначение устройства;
- функциональный профиль;
- назначение relay channel;
- пользовательское имя;
- решение о пользовательском представлении;
- desired state Sprut.

Project не должен хранить Sprut runtime ID как бизнес-идентичность.

### Wiren Board

Владеет runtime-инженерией:

- физические датчики;
- исполнительные команды;
- отопительная и климатическая логика;
- гистерезисы;
- degraded modes;
- защиты;
- таймеры;
- синхронизация;
- инженерные журналы.

Sprut не должен быть обязательным условием автономной работы инженерных систем.

### MQTT contract

Даёт стабильную границу идентичности между Project/WB и внешними системами.

MQTT alias должен быть:

- устойчивым;
- детерминированным;
- машинно-читаемым;
- не зависеть от пользовательского display name;
- по возможности выводиться из Project model.

### Sprut template

Определяет форму сущности в Sprut:

- model recognition;
- состав Accessory;
- Service type;
- связи Characteristics с MQTT;
- options;
- read/write link, если он предусмотрен контрактом устройства.

Template не должен содержать объектовые комнаты или инженерную логику.

### Sprut Configurator

Выполняет reconciliation:

```text
desired state (YAML)
vs
actual state (DISCOVER)
```

Контракт baseline v0.2.2 позволяет изменять:

- Accessory name;
- room;
- Service name.

Расширение этого контракта выполняется отдельными конечными задачами после полевой проверки.

### Sprut.hub

Хранит runtime state:

- Accessory ID;
- Service ID;
- roomId;
- фактическую UI-конфигурацию;
- связи с внешними мостами/экосистемами.

Runtime ID считаются ephemeral и не должны попадать в declarative plan.

## 3. Ownership matrix

| Данные | Project | WB | Template | Configurator | Sprut |
|---|---:|---:|---:|---:|---:|
| project ID | OWNER | consume | — | consume | — |
| MQTT alias | define | publish | match | use as identity | see |
| room | OWNER | — | — | apply | store |
| display name | OWNER | optional UI | base only | apply | store |
| sensor/device profile | OWNER | publish controls | match | validate | render |
| thermostat logic | model intent | OWNER runtime | UI link | — | UI |
| physical actuator command | — | OWNER | — | — | — |
| Service type | intent | — | OWNER mapping | validate | instantiate |
| Accessory/Service/room ID | — | — | — | runtime read | OWNER |
| YAML desired state | generate/author | — | — | consume | — |
| VERIFY | expected state | — | — | OWNER | source actual |

## 4. Ключевые архитектурные правила

### Stable identity ≠ display name

Переименование пользовательского устройства не должно менять его SERIAL.

### Project identity ≠ Sprut runtime ID

Нельзя сохранять в Project как постоянные ключи:

```text
accessoryId
sId
roomId
```

### Device capabilities ≠ Sprut presentation

Физическое устройство может иметь больше данных и каналов, чем реально нужно показывать пользователю.

Это принцип модели, а не утверждение, что baseline v0.2.2 уже умеет управлять всей presentation policy. В v0.2.2 Configurator применяет только name/room/service name. Более тонкая видимость и bridges относятся к следующим итерациям.

### Один параметр — один runtime owner

Если два слоя одновременно считаются владельцами физической команды, архитектура требует пересмотра.

## 5. Общая и объектная документация

Общая разработка содержит только переносимые контракты и механизм.

Конкретные:

- физические каналы;
- MQTT-алиасы объекта;
- помещения;
- whitelist;
- объектовые plan;
- field mapping;

должны находиться в `objects/<object>/`.
