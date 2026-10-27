# Issue #293 — WBE2-I-RS485-ISO additive catalog release (2026-10-27)

**Source of truth:** `psv76/Neirolinks:main/Systems/NLP`.
**Release status:** **INSTALLED on the live SQLite (PASS on 2026-10-27); GUI launch and end-to-end operator acceptance not yet verified**.
**Issue status:** **IN PROGRESS**; full legacy WB passport coverage is not complete.

## Release content

- Predecessor: `nlp3.equipment.2026-10-05.wb-mge-v3`.
- Successor: `nlp3.equipment.2026-10-27.wbe2-rs485-iso`.
- Additive delta: one passport `module.wirenboard.wbe2_i_rs485_iso` and one Product `product.wirenboard.wbe2_i_rs485_iso`; 19/32 → 20/33.
- New WBE2 module has one physical `HOST_SLOT_ATTACHMENT` and one separate isolated `RS485_INTERFACE`. WB8.5 `MOD1…MOD4` installer and bus-root guards are implemented and tested.
- Existing catalogue entries are unchanged, schema remains `000000000017`; no new migration revision is required.
- Canonical `resources/catalogs/` and normative `docs/product/catalogs/` use identical payload JSON.
- Manufacturer sources: [module hardware](https://wiki.wirenboard.com/wiki/WBE2-I-RS485-ISO_RS485_Extension_Module) and [WB8.5 slot compatibility](https://wiki.wirenboard.com/wiki/Wbincludes%3AWBE2-I-RS485-ISO). Dimensions and power figures are left unknown where not verified.

## Verified offline evidence

On authorized Windows desktop:

- Live DB: `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite`; schema `000000000017`, predecessor release active.
- Backup via `create_verified_backup`: `D:\NLP_3_BACKUPS\issue293_release_validation_20261027T181226\verified-backup\nl_project_3.000000000017.backup.sqlite`; SHA-256 `b9e35c27c9a97b6d46874952a538d0efcdad4d9fe5d0e9d955e108fa5c70bd4c`.
- Official `CatalogInstaller.install` successor on `nl_project_3_REHEARSAL.sqlite`: **PASS**, idempotent on repeat; expected release code/content hash and all original identities matched.
- Unchanged Project identity counts: 1 project, 25 ProjectInstances, 296 InstanceResources, 27 buses, 0 functional relations.
- SQLite `integrity_check=ok`, `foreign_key_check=0`. Original live DB not modified.
- Independent restore rehearsal: `nl_project_3_ROLLBACK_REHEARSAL.sqlite` restored from verified backup; predecessor 19/32, `integrity_check=ok`, `foreign_key_check=0`: **PASS**.
- Qt Constructor field selection, new Product selection, module creation, typed MOD relation, Bus `903` root gate and reopen: PASS on isolated test DB.
- Expanded regression: `pytest -q tests/catalog tests/constructor tests/buses tests/recovery tests/cables` → **171 passed**.
- Guarded installer `tools/apply_additive_catalog_successor.py` blocked itself while two `pythonw.exe -m nl_project_2` processes were running (PID 32524, 29952). This confirms live mutation guard. Do not terminate either without user's authorization.
- Startup auto-successor hazard fixed: `ApplicationRuntime.open()` installs a catalog only for a **new** database. An existing database on a declared predecessor remains on its release until an explicit offline successor. Tests `test_issue293_runtime_catalog_guard.py` prove both paths (existing 19/32 remains unchanged; new DB receives 20/33).
- Real-database startup smoke on two isolated backup clones (old and successor) returned PASS; same 1 project, 25 instances, 27 buses, unchanged release code in both.
- Separate integration suite `tests/objects tests/integration`: **85 passed, 1 failed**. The failing `test_p1007_ui_stabilization.py::test_lines_default_and_persisted_layout_header_and_tree` expects three rows after expanding a cable-line tree but sees two. The same failure was reproduced independently on untouched baseline `d39b2e4`; unrelated to Issue #293.

## Live installation completed — 2026-10-27 19:05 +05

- All `python.exe` / `pythonw.exe` application processes were absent immediately before installation; the installer repeated its own process guard.
- Live working database: `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite`.
- Exact pre-install database SHA-256: `5371f3bf7634351f9a2782fae83195caf06627faf53dfb273d39ef43b33364c6`.
- Official `tools/apply_additive_catalog_successor.py`: **PASS**, predecessor `nlp3.equipment.2026-10-05.wb-mge-v3` to successor `nlp3.equipment.2026-10-27.wbe2-rs485-iso`, schema unchanged at `000000000017`.
- Verified backup: `D:\NLP_3_BACKUPS\issue293_wbe2_successor_20261027T190546\nl_project_3.000000000017.backup.sqlite`. Backup SHA-256: `3f098dd665f60bf99a7e9048e7a0258fd00732ec3e06f92e017dd5b5a9e1fbbd`.
- Receipt: `D:\NLP_3_BACKUPS\issue293_wbe2_successor_20261027T190546\release_receipt.json` (`status: PASS`; identity parity true).
- Independent read-only SQLite readback confirms active new release hash `4e3f7a0b96ffc36919de9d1b49f25a93361f526ee6402cb92977930b4a8f60d5`, 20 passports, 33 products, 1 project, 25 ProjectInstances, 296 InstanceResources, 27 buses, `integrity_check=ok` and zero FK violations.
- The first preflight used upper-case hex from PowerShell and was correctly rejected by the byte-for-byte **case-sensitive string** comparison (database unchanged); the subsequent lower-case SHA invocation succeeded. Installer now normalizes expected hexadecimal SHA case.
- No DWG changes or changes to the existing project topology. No WBE2 module was installed into the live Bogdanovich object.

## Remaining acceptance

- Operator UI runtime launch and selection of the released WBE2-I-RS485-ISO passport/Product in the intended working installation still require confirmation. An older separate code snapshot exists in `D:\NLP 3.1\Neirolinks\Systems\NLP`; avoid running it against the updated database, use the canonical updated `D:\GitHub_NEW\Neirolinks\Systems\NLP` source.
- Do not create new WBE2 instances/buses in live Bogdanovich: perform any installation/RS485-903/reopen acceptance on a separate project/database copy.
- The complete #293 hardware catalog coverage across all known legacy Wiren Board devices, UI acceptance, and cross-issue compass synchronization are not yet complete; do not mark #293 PASSED or close it.

This increment does not close #293: review/normalize every legacy WB device, physical resources, model revisions and product mapping, and perform full acceptance on a copy of the Bogdanovich object.
