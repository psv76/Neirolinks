# Sprut Configurator tests

For Issue #22, run:

```bash
python SprutConfigurator/tests/test_presentation_core.py
python SprutConfigurator/tests/test_sprut_plan_generator.py
```

Current offline coverage includes:

- YAML v2 presentation validation;
- Service-scoped Alice policy;
- `Service.visible` diff/APPLY contract;
- `Characteristic.statusVisible` diff/APPLY contract;
- Characteristic type matching;
- Alice/Yandex membership parsing by `(aId, sId)`;
- exact field-confirmed `bridgeService.list/create/delete` params;
- presentation VERIFY;
- normalized Project source → Sprut Plan generation;
- direct-output identity guard;
- duplicate SERIAL rejection;
- Sprut 32-character name limit.

The tests are offline and never contain Sprut token/cid/session serial.

The Project-to-YAML regression fixture is a sanitized subset extracted from the user-provided NL Project 1.0 database copy. Workstation-local paths and internal SQLite IDs are intentionally omitted.
