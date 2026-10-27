# Issue #293 — WBE2 RS-485 module installation and bus-root gate

**Status:** implemented at the Constructor/BusService code layer; catalog candidate only, **not an approved runtime catalog release**.

## Contract

1. `MODULE_INSTALLATION` is a typed Constructor relation: controller `INTERNAL_EXPANSION_SLOT` (source) → expansion module `INTERNAL_EXPANSION_MODULE_ATTACHMENT` (target).
2. Current explicitly supported host is `controller.wiren_board_8_5`, `INTERNAL_MODULE_SLOT` ordinal `0…3` (`MOD1…MOD4`). Targets are explicitly approved WBE2 passports (`module.wirenboard.wbe2_i_knx` or staged `module.wirenboard.wbe2_i_rs485_iso`). A generic port cannot impersonate a MOD slot.
3. Exclusivity rejects double use of a slot/attachment. Relations are persisted Project entities and must survive reopen.
4. `module.wirenboard.wbe2_i_rs485_iso` provides a separate `RS485_INTERFACE` resource. Its port is not eligible as a new RS485 bus root unless there is exactly one valid active module installation connecting it to a compatible WB8.5 MOD slot.
5. The RS485 source candidate selector exposes uninstalled module ports as `source_available = false`. `create_rs485_bus` independently enforces the same condition at transaction time.
6. Deleting `MODULE_INSTALLATION` is forbidden if an active physical bus roots at a resource belonging to that module instance. Remove the active bus first; a removed module ceases to be an eligible source.
7. Native WB8.5 RS485-1/RS485-2 remain independent of internal modules. No placeholder RS485 resource is created on an empty MOD slot.

## Evidence

- `tests/constructor/test_issue293_mod_persistence.py`: actual WB8.5 MOD slot and currently published WBE2-I-KNX attachment, exclusive relation + persisted reopen.
- `tests/buses/test_issue293_wbe2_root.py`: **test-database-only** materialization of candidate WBE2-I-RS485-ISO passport (not production), unavailable root before installation, installation, bus `903` creation, reopen, uninstall blocked while bus active, successful uninstall after removal.
- 2026-10-27: `pytest -q tests/constructor tests/buses` → **62 passed**.

## Release gates still open

The WBE2-I-RS485-ISO passport/Product exist only under `docs/legacy/issue293/candidates/`. No runtime catalog manifest or successor has been updated. Do not claim the feature available in the working GUI yet. Requires approved catalog successor, installation/selector UI test with installed release, schema/release compatibility, verified working SQLite backup and startup smoke, and coverage of all remaining legacy WB models. No live SQLite/DWG mutations were performed in this increment.
