# Reference baseline — Sprut Configurator v0.2.2

Этот каталог фиксирует **оригинальный рабочий standalone source package Sprut Configurator v0.2.2** и его подтверждённое поведение как reference baseline общей разработки.

## Состав

```text
sprut_configurator.py
selftest.py
requirements.txt
setup.bat
run.bat
README.md
```

Файлы `sprut_configurator.py`, `selftest.py`, `requirements.txt`, `setup.bat` и `run.bat` взяты из реального рабочего пакета `Sprut_Configurator_v0.2.2`, а не восстановлены по документации или памяти.

Контроль оригинального `sprut_configurator.py`:

```text
Git blob SHA-1: 8cacfb101f979ed51bb94a5eb86dba634e670e03
SHA-256:        2cf996de6df1d6c3a1353faef4a2de66713d658155ec2f2ae45988dcc6e85781
size:           51433 bytes
```

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

## Проверка selftest

Оригинальный `selftest.py` проверен на исходном рабочем наборе fixtures:

```text
targets: 51
changes: 167
errors: 0
PASS: YAML parsed; 51 targets resolved; no DRY RUN errors; pre-APPLY differences detected.
```

`selftest.py` исходно ожидает рядом два объектовых fixture-файла:

```text
05_31_Ivolga_sprut_plan_v3.yaml
Ivolga_home_sprut_2.json
```

В общей папке Configurator они намеренно не дублируются, потому что относятся к конкретному объекту.

Reference YAML/acceptance snapshot хранится в:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/v0.2.2/
```

Большой DISCOVER JSON Иволги не переносится в generic source tree. Это runtime snapshot конкретного объекта, а не общий механизм Configurator.

## Граница generic / object

```text
generic source / contracts → SprutConfigurator/
object fixtures            → objects/<object>/
```

Физические каналы, комнаты и object-specific aliases никогда не должны считаться частью generic reference implementation.
