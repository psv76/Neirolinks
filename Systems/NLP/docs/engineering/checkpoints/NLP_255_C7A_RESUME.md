# NLP-255-C7A-CONTRACT-MAPPING — resumption checkpoint

- task_id: `NLP-255-C7A-CONTRACT-MAPPING`
- branch: `feature/nlp-255-c7a-contract-integration`
- base_sha: `1b3d79de5e216e4254eea1ecc488a58802b8b6d2` (accepted C6)
- start_sha / tested_sha: `939e006a9fb8a5b1ec16d0a79abf55fe553ce682`
- prior_checkpoint_sha: `2bc4ca6275c5119b609e9a5cab12510558a2e371`
- status: **BLOCKED** by an additional schema scope requirement, not BOARD_AV.
- final head_sha: recorded in Issue #255 after checkpoint commit/push.
- changed_paths: only this new checkpoint. Historical checkpoint preserved.

## Approved decision retained; new stop condition

Read the full updated task, including “Approved C7A resumption decision —
2026-10-25”, and the previous checkpoint. The approved BOARD_IN / BOARD_AV /
700_* exception resolves the old blocker and is not being reconsidered.

Before editing, found `resources/autocad/block_contract.schema.json:127-132`:
functional_groups requires `minProperties: 10`. Replacing HEATING and VENTILATION
with HVAC produces the approved nine groups. Keeping a tenth legacy or dummy
group would violate the approved mapping. The schema file is absent from both
the original and updated allow-lists (the addendum adds only two normative docs).

The still-applicable task instruction is explicit:
“If strict machine schema/parity test requires another file, stop and document
exact additional scope before changing it.”

`tools/check_issue235_target_contract.py:113-124` actually validates the full
candidate using Draft202012Validator before parity checks. Thus this is an
enforced machine-schema conflict, not a hypothetical future requirement.

## Reproduction: no tracked files modified

Using jsonschema 4.26.0 / Draft202012Validator in local .venv:

1. Load current block_contract.json and block_contract.schema.json;
   check_schema succeeds; baseline iter_errors returns **0 errors**.
2. Deep-copy data in memory, remove HEATING and VENTILATION, insert HVAC with
   cable_prefix='6', layers=['600_HVAC'] and the union of both device_type sets.
3. Validate the copy against the unchanged schema. Exactly **1 error**:
   validator `minProperties`, instance path `['functional_groups']`, schema
   path `['properties', 'functional_groups', 'minProperties']`, required `10`.
4. Actual candidate group count is 9: AV, BUS, HVAC, LIGHTING_230V, LIGHTING_LED,
   NETWORK, POWER, SENSORS, SWITCHES.

The diagnostic script asserted that this precise error exists and exited 0.
No candidate was written to disk. No implementation or altered expectations
were committed. Existing catalog still uses its previous mapping.

## Verification on unchanged start SHA

Directory `D:\NLP 3.1\Neirolinks\Systems\NLP`; existing
`.venv/Scripts/python.exe` as `python`; PYTHONPATH=src;. on Windows.
Final test run used TEMP/TMP pointing to ignored `.venv/tmp`.
Environment: CPython 3.14.3, pytest 9.1.1, Ruff 0.15.22, jsonschema 4.26.0.
jsonschema and its dependencies were installed only in the ignored local venv.

Command:

```text
python -m pytest -q --tb=no tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py tests/cad_contract/test_av_layer_identity.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_catalog.py tests/cad_contract/test_repair08_contract.py tests/cad_contract/test_validator_av.py tests/cad_contract/test_issue237_track_dali_integration.py
```

Final result: **7 failed, 376 passed in 0.60s**, pytest exit 1. An initial run
before setting workspace TEMP/TMP had 7 failed, 374 passed, 2 fixture errors;
after setting those environment variables the same complete selection had no
fixture errors. No tests were removed, skipped or changed.

The seven failures remain exactly the previously recorded baseline failures:

- `test_catalog.py::test_machine_contract_has_exact_approved_shape`
- `test_repair08_contract.py::test_exact_71_names_and_attdef_fixture`
- `test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash`
  for EL_BOX_OUT_100x100, TRACK_230V, TRACK_48V and TRACK_DALI
- `test_repair08_contract.py::test_project_only_tags_are_not_attdefs[BUS_ID]`

`python -m compileall -q src/nl_project_2/cad_contract`: PASS.
`python -m ruff check src/nl_project_2/cad_contract/catalog.py`: All checks passed.
No new implementation/regression PASS is claimed; these are baseline checks.

## Exact additional scope and next operation

Required additional allowed file:
`Systems/NLP/resources/autocad/block_contract.schema.json`.
At minimum, its functional_groups cardinality constraint must permit the nine
approved groups instead of requiring ten. Any new numeric-mapping properties
introduced by resumed implementation must also respect that object's existing
additionalProperties=false restriction. No schema changes made without scope.

next_action: Coordinator explicitly authorizes the narrowly necessary C7A
machine-schema update in the task allow-list, then resumes C7A with the already
approved BOARD_AV decision intact. C7b is not started.

No catalog, machine JSON/schema, validator, COM, synchronization, DWG/SQLite,
runtime, main or D23 changes; no new Issues. No locked 3.13/full CI/live claims.
Issue #255 remains OPEN, release BLOCKED. Checkout retained for review/resume.
