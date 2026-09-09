# Шаблоны Sprut.hub

Папка содержит шаблоны устройств Sprut.hub для интеграции с физическими и виртуальными сущностями Wiren Board по MQTT.

## Связь с общей разработкой Sprut Configurator

Общие архитектурные правила, identity/MQTT contracts, YAML contract и Configurator reconciliation описаны здесь:

```text
SprutConfigurator/
```

Главный документ:

```text
SprutConfigurator/README.md
```

Эта папка `Templates/Sprut/` хранит сами reusable template JSON и документацию конкретных template families.

Object-specific template/whitelist должен храниться внутри:

```text
objects/<object>/Templates/Sprut/
```

и не считается generic template автоматически.

## Разделы

```text
Templates/Sprut/
├─ Heating/
├─ Ventilation/
└─ Gates/
```

## Назначение разделов

- `Heating/` — отопление, термостаты и климатические зоны.
- `Ventilation/` — шаблоны вентиляции по мере появления подтверждённых contracts.
- `Gates/` — шаблоны ворот, калиток и приводов по мере появления подтверждённых contracts.

## Правило размещения

Подробное описание конкретного шаблона должно лежать внутри папки соответствующей инженерной системы.

Например:

```text
Templates/Sprut/Heating/README.md
```

## Граница ответственности

Sprut.hub используется как пользовательский интерфейс:

```text
Sprut.hub = отображение, уставки, режимы, пользовательское управление
```

Критическая инженерная логика остаётся в Wiren Board:

```text
Wiren Board = логика, защита, исполнительные команды, журнал
```

Template определяет entity shape и MQTT links, но не должен подменять WB-логику, кодировать объектовые комнаты или зависеть от runtime Sprut ID.
