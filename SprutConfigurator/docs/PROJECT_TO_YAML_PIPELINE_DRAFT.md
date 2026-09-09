# Project → Sprut Plan YAML pipeline — Issue #22 draft

## Purpose

Issue #22 needs a real Project → YAML path for Ivolga without coupling the future NL Project 2.0 implementation to the legacy NL Project 1.0 SQLite schema.

The accepted boundary is:

```text
Project source
→ adapter
→ normalized Project source model
→ Sprut export policy
→ reusable Sprut Plan generator
→ YAML format_version 2
→ standalone Sprut Configurator
```

The active Sprut.hub is selected by the operator in WebUI/session context. The YAML contains no `target_hub`, hub serial, token, `aId`, `sId`, `cId` or other runtime/session identity.

## Legacy NL Project 1.0 path

For the Ivolga gazebo, the only Project data currently available are in NL Project 1.0.

Implemented:

```text
SprutConfigurator/src/nl_project_v1_adapter.py
SprutConfigurator/src/sprut_plan_generator.py
SprutConfigurator/tools/nl_project_v1_to_sprut_yaml.py
```

The adapter:

- opens only the explicitly supplied SQLite file in `mode=ro`;
- does not initialize or migrate the database;
- repeats the legacy application's own normalized-line merge rule;
- strips legacy database IDs from the normalized output;
- does not invent modern MQTT aliases or Sprut runtime identity.

The generator is independent of SQLite and consumes only the normalized source model plus a presentation policy.

## Why a separate policy exists

Project owns physical/project facts such as:

```text
line id
room
purpose
connection point
module/device metadata
```

But Project facts alone do not answer every Sprut presentation question:

```text
should this capability be exposed to the user?
which Sprut Service type should represent it?
visible?
statusVisible?
Alice bridge membership?
```

Therefore Issue #22 keeps these choices in an explicit Sprut export policy. The generator reads physical fields from Project and presentation fields from policy.

This prevents copying physical bindings into a second handwritten YAML.

## Ivolga gazebo proof

Source: read-only copy from user-provided `NLP56.zip`.

Object-specific policy:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/issue22/besedka_sprut_export_policy.yaml
```

Regression source subset:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/issue22/nl_project1_besedka_source_fixture.json
```

Generated draft:

```text
objects/05_31_Ivolga_13/Doc/SprutConfigurator/issue22/sprut_plan_besedka_generated_draft.yaml
```

The first implemented policy block generates 18 lighting/dimming Accessory targets directly from current Project line facts:

```text
301..311
320
351..356
```

Examples:

```text
Project line 301
room             Фасад
purpose          Свет фасад беседки
connection_point A41/K1

→ YAML
serial A41/K1
name   301 Свет фасад беседки
room   Фасад
Service Lightbulb
```

```text
Project line 351
room             Гостиная
purpose          Подсветка балки
connection_point A47/Channel 1

→ YAML
serial A47/Channel 1
name   351 Подсветка балки
room   Гостиная
Service Lightbulb
```

No physical room/purpose/connection-point value for these targets is duplicated in the policy.

## Fail-closed rules

The reusable generator currently rejects at least:

- missing or ambiguous `source_line`;
- empty identity;
- a non-direct connection point when `require_direct_output: true`;
- duplicate generated SERIAL;
- empty room/name;
- names over Sprut's 32-character limit;
- missing/duplicate Service types.

This is intentional. If Project does not contain enough information for stable Sprut identity, the generator must report the unresolved target rather than guess.

## Intentionally unresolved gazebo entities

The first generated draft does not yet include:

```text
441, 442     WB-MWAC leak sensors
470, 471     M1W2 contact sensors
501          exhaust fan
921.09       WB-MSW T+RH+Motion
921.10       WB-M1W2
922.01       separate motion sensor
923.01/.02   curtains
924.01       climate device
```

Reasons differ by item: missing current MQTT/SERIAL identity, missing W1/W2 role data, or an unconfirmed final Sprut Service/template contract.

These omissions are explicit in the object policy and are not silent data loss.

## Local integration result

Using the read-only SQLite copy extracted from `NLP56.zip`:

```text
python tools/nl_project_v1_to_sprut_yaml.py <copy-of-nl_project.sqlite> \
  --object "05 31 Иволга" \
  --policy besedka_sprut_export_policy.yaml \
  --output sprut_plan_besedka_generated.yaml
```

Result during Issue #22 development:

```text
PASS: generated 18 accessories
```

The generated YAML matched the checked-in regression draft byte-for-byte apart from the explanatory header added to the repository copy.

## Future NL Project 2.0

NL Project 2.0 should not copy the legacy SQLite adapter.

It should provide the same normalized Project source model from its own current model/repository layer:

```text
NL Project 2.0 model
→ adapter/export view 2.0
→ same normalized source model
→ same sprut_plan_generator
→ YAML v2
```

This is the reusable result of exercising the pipeline on NL Project 1.0.
