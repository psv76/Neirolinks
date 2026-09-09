# Sprut Configurator tests

For Issue #22, run:

```bash
python SprutConfigurator/tests/test_presentation_core.py
```

Current offline coverage:

- YAML v2 presentation validation;
- Service-scoped Alice policy;
- Service.visible diff;
- Characteristic.statusVisible diff;
- Characteristic type matching;
- fail-closed Alice without a confirmed read adapter;
- presentation VERIFY;
- exact `params` builders for the three real WebUI frames captured on 2026-09-10.

The tests are offline and never contain Sprut token/cid/session serial.
