# 05 31 Иволга 13 — Sprut Configurator v0.2.2 acceptance snapshot

Это **замороженный reference snapshot** первого успешного end-to-end применения Sprut Configurator.

Он нужен как доказательство baseline и regression reference, но **не является источником актуальной физической карты объекта**.

Для текущих физических каналов, устройств и отопительных связей использовать актуальные материалы объекта:

```text
objects/05_31_Ivolga_13/README.md
objects/05_31_Ivolga_13/PHYSICAL_CHANNEL_MAP.md
objects/05_31_Ivolga_13/HEATING_CHANNEL_MAP.md
objects/05_31_Ivolga_13/THERMOSTAT_MAP.md
objects/05_31_Ivolga_13/etc/
objects/05_31_Ivolga_13/Templates/
```

## Baseline acceptance

Зафиксированный состав plan на момент проверки:

```text
51 target Accessory
17 sensor/leak/motion entities
19 relay Lightbulb entities
15 thermostat entities
```

Контрольный массовый прогон:

```text
167 RPC changes
VERIFY PASSED = 51
VERIFY FAILED = 0
```

Этим подтверждены:

- stable SERIAL matching;
- room-by-name;
- Service-by-type;
- DRY RUN;
- fresh preflight;
- APPLY;
- independent VERIFY;
- field-name constraints, добавленные в v0.2.2.

## Reference YAML

`05_31_Ivolga_sprut_plan_v3.yaml` — тот plan, который использовался для baseline acceptance.

Он сохраняется здесь как **fixture истории реализации**, а не как автоматически актуальный desired state объекта после последующих изменений.

Новая работа по Иволге выполняется в GitHub Issue #22 и должна опираться на текущие объектовые данные, а не на этот frozen plan.

## Object-specific template

Object whitelist relay Lightbulb хранится отдельно:

```text
objects/05_31_Ivolga_13/Templates/Sprut/05_31_Ivolga_Relay_Lightbulb.json
```

Он не является generic relay template для всех объектов.
