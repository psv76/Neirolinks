# Reference baseline — Sprut Configurator v0.2.2

Этот каталог фиксирует **версию и подтверждённое поведение** standalone Sprut Configurator v0.2.2 как reference baseline общей разработки.

Исходный архив документации, переработанный в Issue #21, не содержал исходник приложения. Поэтому здесь не размещается неполный или восстановленный по памяти source package.

## Что считается зафиксированным

```text
DISCOVER
→ YAML validation
→ DRY RUN
→ fresh preflight
→ APPLY
→ fresh DISCOVER
→ VERIFY
```

Также зафиксированы:

- matching Accessory по `serial`;
- room-by-name;
- Service-by-type;
- запрет APPLY при validation errors;
- локальное явное подтверждение `APPLY`;
- session credentials только в RAM;
- round-trip validation имён Sprut.

Подробный contract:

```text
SprutConfigurator/docs/CONFIGURATOR_V0_2_2.md
SprutConfigurator/docs/YAML_CONTRACT_V1.md
```

## Object-specific fixture

План и acceptance snapshot первого reference объекта сознательно вынесены из общей разработки:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/
```

Это frozen regression reference, а не источник текущей физической карты объекта.

## Source package

Если standalone source будет отдельно версионироваться в GitHub, его следует добавить явной самостоятельной задачей или в рамках очередной доработки Configurator, сохранив эту границу:

```text
generic source / contracts → SprutConfigurator/
object fixtures            → objects/<object>/
```

Не восстанавливать код из документации приблизительно и не объявлять такой восстановленный вариант reference implementation.
