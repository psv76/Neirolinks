# Issue #293 — WBE2-I-RS485-ISO additive catalog release (2026-10-27)

**Source of truth:** `psv76/Neirolinks:main/Systems/NLP`.
**Release status:** **source ready, clone verified; NOT YET INSTALLED on live SQLite**.
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

- Live DB: `D:\\NL_Project_3_Data\\Projects\\nl_project_3.sqlite`; schema `000000000017`, predecessor release active.
- Backup via `create_verified_backup`: `D:\\NLP_3_BACKUPS\\issue293_release_validation_20261027T181226\\verified-backup\\nl_project_3.000000000017.backup.sqlite`; SHA-256 `b9e35c27c9a97b6d46874952a538d0efcdad4d9fe5d0e9d955e108fa5c70bd4c`.
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

## Remaining live installation procedure

**Only after all NL Project 3.1 instances have been closed and unsaved work preserved:**

1. Verify Git `main` source and payload, read the actual active release and schema head. Compute the live database SHA-256 **at this time**; do not reuse a stale checksum.
2. Run `tools/apply_additive_catalog_successor.py` with `--database D:\\NL_Project_3_Data\\Projects\\nl_project_3.sqlite --backup-root D:\\NLP_3_BACKUPS --expected-database-sha256 <CURRENT_SHA256> --confirm-project-closed`. The script rejects open processes, missing predecessor, schema mismatch, unverified backup, hash mismatch and broken post-install parity. Do not apply any manual SQL patches.
3. Confirm `release_receipt.json` PASS, `20/33` on working SQLite, same original ProjectInstance/InstanceResource/Bus IDs and `integrity_check=ok`.
4. Restart NLP 3.1; select WBE2 passport and product in Constructor, test addition and MOD installation on a **separate test project/copy**, then bus root and reopen. Do not create WBE2 instances/buses in the live Bogdanovich project without separate approval.
5. If a live installation fails, leave the verified backup intact, stop and evaluate recovery using the approved backup, not blind file overwrite while NLP is running.

This increment does not close #293: review/normalize every legacy WB device, physical resources, model revisions and product mapping, and perform full acceptance on a copy of the Bogdanovich object.
