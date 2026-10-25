# NLP-255-C7B-VALIDATOR — 2026-10-25

status: PASSED (C7B validator scope; full suite retains 11 confirmed baseline failures)
branch: feature/nlp-255-c7b-validator-integration
base_sha: c4c641a9bef9e62b1490d7ab13c1dc35d84a45fc (reviewed C7a)
start_sha: 7b9df4111d38ce31e9ff250c67b255c21e4b6600 (verified clean branch)
intermediate_sha: 6a936ac22b3f84e4099fec15621b158734eb2699
tested_sha: ff3fbf3cf86f8bac122742aff0ca0ded4fa5ae75
final_head_sha: recorded in Issue #255 after this checkpoint commit (avoids self-reference).

## Result and boundaries

- BOARD resolution uses catalog role-aware placement. Only BOARD_IN / BOARD_AV accepts valid 700_*; ordinary BOARD roles retain POWER and legacy BOARD placement.
- AV destination board retains physical BOARD payload, normalized attributes, ATTDEF/value checks and destination lookup. It bypasses AV outlet normalization, missing-field relaxation and AV cable facts. Its payload has no cable identity, cable source or cable link. AV CABLE_OUTLET free-text normalization and BOARD+CABLE_ID duplicate detection remain enforced.
- DALI_GROUP uses accepted C4 numeric 300_*/400_* predicate. Legacy DALI_GROUPS and malformed layers reject. D.YYY, uniqueness, dynamic metadata and logical-only payload behavior preserved.
- HVAC heating cable outlet / FAN / AIR_VALVE coverage and TRACK_DALI numeric 3YY/4YY plus legacy shared-layer and passive DALI graph coverage pass.
- No catalog, machine JSON/schema, helper C1-C6, COM, synchronization, DB, real DWG/SQLite or main changes. No production deployment, C7c, new issue or merge. No live CableLine persistence test is claimed: this stage verifies validator line facts and read payload only.

## Changed files (all relative to Systems/NLP)

- src/nl_project_2/cad_contract/validator.py
- tests/cad_contract/test_validator_numeric_layers.py: new parameterized runtime acceptance/negative tests.
- tests/cad_contract/test_dali_layer_rules.py: numeric placement in runtime fixtures; unchanged ID/dynamic assertions and machine inventory.
- tests/cad_contract/test_numeric_contract_mapping.py: staged runtime assertion replaced with conditional runtime acceptance; catalog checks retained.
- tests/cad_contract/test_validator_positive.py: DALI fixtures explicitly use 300_DALI. Generic BOARD_IN positive fixture explicitly selects BOARD_DISTRIBUTION for its 100_POWER layer; the shared factory otherwise selects BOARD_AV alphabetically. Dedicated negative tests continue to reject BOARD_AV on 100_*.
- tests/cad_contract/test_issue237_track_dali_integration.py: added numeric 300/400 feeder cases reusing the existing complete passive DALI graph fixture. Existing legacy tests retained.
- docs/engineering/checkpoints/NLP_255_C7B.md

## Verification

Environment: Windows, existing .venv Python 3.14.3 / pytest 9.1.1 / Ruff 0.15.22. PYTHONPATH=src;. and TEMP/TMP point to ignored .venv/tmp. No locked Python 3.13 CI or live AutoCAD certification claimed.

Commands run from Systems/NLP with .venv/Scripts/python.exe:

1. `-m pytest -q --tb=short tests/cad_contract/test_validator_numeric_layers.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_numeric_contract_mapping.py tests/cad_contract/test_validator_av.py tests/cad_contract/test_issue237_track_dali_integration.py`: **208 passed, 0 failed**, exit 0.
2. `-m pytest -q --tb=short tests/cad_contract`: **711 passed, 11 failed**, exit 1; zero new failures and no skipped/xfail suppression.
3. Identical full command in an unchanged `git archive` of start_sha, extracted under ignored `.venv/tmp/c7b-baseline-7b9df41`: **634 passed, 11 failed**, exit 1. Same 11 failure node IDs and causes. Working tree was not reset or replaced.
4. `-m compileall -q src/nl_project_2/cad_contract`: exit 0.
5. `-m ruff check` and `-m ruff format --check` for validator.py and all five changed test files: exit 0, all checks passed / 6 files already formatted.
6. `git diff 7b9df4111d38ce31e9ff250c67b255c21e4b6600 --check`: exit 0.

The first full implementation run had 710 passed / 12 failed. The only additional failure was the generic BOARD_IN fixture selecting BOARD_AV on 100_POWER; the explicit ordinary role correction above resolved it. No validator rule was relaxed. An initial new HVAC test used device-type names as block names; corrected to actual canonical FAN/AIR_VALVE/CABLE_OUTLET with CABLE_HEAT. No production code change was needed for these test setup errors.

## Eleven baseline failures, not hidden

All under tests/cad_contract:

1. test_catalog.py::test_machine_contract_has_exact_approved_shape — expects version 3.0.0, actual 3.2.0.
2. test_repair08_contract.py::test_exact_71_names_and_attdef_fixture — stale names, CABLE_OUTLET_BUS added.
3. test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash[EL_BOX_OUT_100x100]
4. test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash[TRACK_230V]
5. test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash[TRACK_48V]
6. test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash[TRACK_DALI]
7. test_repair08_contract.py::test_project_only_tags_are_not_attdefs[BUS_ID]
8. test_issue134_box_chains.py::test_base_only_box_chain_has_distinct_graph_nodes — obsolete BUS_POINT_ID/passive bus fixture.
9. test_validator_positive.py::test_every_approved_name_has_a_valid_metadata_observation[EL_BOX_OUT_100x100] — BUS_ID_REQUIRED.
10. test_validator_positive.py::test_every_approved_name_has_a_valid_metadata_observation[TRACK_DALI] — BUS_ID_REQUIRED.
11. test_validator_positive.py::test_representative_of_each_non_key_physical_family_is_valid[TRACK_DALI] — BUS_ID_REQUIRED.

## Exact next operation

Publish this checkpoint commit and preceding implementation commits to origin/feature/nlp-255-c7b-validator-integration; record final_head_sha and results in existing Issue #255. Then independent review of `start_sha..final_head_sha` against NLP_255_C7B_TASK.md, especially AV BOARD line exclusion and DALI protections. C7c may be considered only after acceptance and a separate explicit task; do not start it in this session.
