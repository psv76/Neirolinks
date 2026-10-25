# NLP #255 — C7b: runtime CAD validator adoption of numeric groups

TASK_ID: NLP-255-C7B-VALIDATOR
ISSUE: psv76/Neirolinks#255
BASE_SHA: c4c641a9bef9e62b1490d7ab13c1dc35d84a45fc (independently reviewed C7a machine/catalog)
BRANCH: feature/nlp-255-c7b-validator-integration
STATUS: READY — implementation not started.

## Preflight findings from exact source (do not repeat lengthy historical research)

In `src/nl_project_2/cad_contract/validator.py`:
- `_validate_logical` lines ~538-597 compares logical DALI_GROUP placement to legacy `rule.logical_layer` literal; ID `D.YYY`, duplicate, dynamic metadata checks live in the same method.
- `_function_group` lines ~599-655 uses `catalog.groups_for_layer(observation.layer) & rule.allowed_groups`; legacy TRACK_DALI group ambiguity is decided by actual 3YY/4YY ordinary CABLE_ID, not BUS_ID. New 300/400 numeric layers resolve unambiguously.
- `_validate_one` lines ~253 onward computes function group, then any AV group triggers AV CABLE_ID normalization, AV line required attributes, nonblocking incompleteness, etc.
- `_collect_line_facts` lines ~1090 onward treats **every** `function_group == "AV"` as AV cable outlet, raising `AV_BLOCK_NAME` for `BOARD_IN`. Role-specific AV BOARD must bypass AV cable-line-only behavior, WITHOUT relaxing AV outlet rules.
- `_collect_board_fact` lines ~1216 tracks BOARD_ID → LOAD_TYPE, and batch AV target check lines ~1345 compares with `catalog.board_rules["av_role"]`.
- `_collect_line_facts` ordinary CABLE_ID validation uses `_STANDARD_CABLE_ID` plus expected prefix from group, and AV uses free BOARD+CABLE_ID identity.

C7a staged catalog: `groups_for_board_layer(block_name, load_type, layer)` requires exact `BOARD_IN` + `LOAD_TYPE=BOARD_AV` + valid `700_*` only; ordinary BOARD_IN roles remain on normal POWER group, and BOARD_AV at `100_*` must fail. `is_valid_dali_group_layer` from accepted C4 handles only valid `300_*`/`400_*`. Numeric nine-group mapper already exists. C7a explicitly retained legacy named aliases for old projects by default, with `groups_for_layer(...,include_legacy=False)` for numeric-only consumers.

## Scope and required runtime behavior

1. Adopt C7a role-conditional BOARD resolution in validator `_function_group`: BOARD observations must use `groups_for_board_layer` on relevant numeric layers, and ensure ordinary roles cannot take AV group and BOARD_AV cannot take POWER or other numeric/legacy layer. **Do not grant generic BOARD AV permissions.** Maintain legacy BOARD roles and legacy layer compatibility for non-AV existing projects. For invalid BOARD role/group use a blocking diagnostic compatible with existing `LAYER_FUNCTION_GROUP_MISMATCH` semantics.
2. Handle AV destination `BOARD_IN/BOARD_AV` as a **logical destination board represented by a physical BOARD block**, not AV `CABLE_OUTLET`: do not apply AV outlet `av_rules.required`, free-form CABLE_ID normalization, AV incompleteness or `AV_BLOCK_NAME` diagnosis to BOARD. It must still collect BOARD_ID/role and participate in AV outlet destination lookup. Preserve BOARD_IN ATTDEF requirements, BOARD validation and project read payload; do not create a cable line for AV BOARD. Other AV observations remain restricted to valid CABLE_OUTLET.
3. DALI_GROUP logical placement must now use `is_valid_dali_group_layer` on **all valid 300_* and 400_* layers**, not exact `DALI_GROUPS`. Preserve `D.YYY` format, batch uniqueness, dynamic-flag rejection and logical-only/nonphysical behavior. Invalid 300/400 suffix, legacy DALI_GROUPS and other numeric groups reject. Existing C4 tests intentionally assert legacy validator still rejects staged numeric layers: updating those exact tests to the new runtime expectation is in scope, but DO NOT change logical ID/dynamic expectations.
4. Preserve TRACK_DALI physical power group compatibility (3YY/4YY) including legacy shared TRACK_DALI layer, BUS_ID/passive DALI rules, ordinary non-AV prefix consistency, AV free-text BOARD+CABLE_ID and duplicate checks, HVAC 600 combined device types and special FAN/AIR_VALVE rules, unrelated physical source/bus/conduit checks.
5. Numeric group suffixes are unrestricted but parser-valid; reject 350_X, empty/malformed suffix, trailing/leading whitespace. Preserve C7a explicit legacy aliases for other existing blocks; do not renumber existing identities.
6. Beware C7a machine allowed_groups: BOARD_IN is not globally permitted AV. The approved exception is conditional on role. Ensure BOARD_AV on 700 accepted and other BOARD roles on 700 blocked **even if** catalog.groups_for_layer returns AV, and BOARD_AV on 100 blocked.
7. Update tests only for actual approved new behavior, with negative and regression cases. Do not mask baseline suite failures.

## Pre-verified dependency map / allowed paths

- `Systems/NLP/src/nl_project_2/cad_contract/validator.py`
- `Systems/NLP/tests/cad_contract/test_validator_numeric_layers.py` (new, focused)
- `Systems/NLP/tests/cad_contract/test_dali_layer_rules.py` (adjust existing legacy-runtime expectation to C7b final behavior only)
- `Systems/NLP/tests/cad_contract/test_numeric_contract_mapping.py` (adjust its explicitly staged-only runtime assertion to runtime new behavior; preserve C7a catalog assertions)
- Existing `tests/cad_contract/test_validator_av.py`, `test_issue237_track_dali_integration.py`, `test_validator_positive.py`, `test_validator_negative.py` only if proven necessary for approved behavior; document justification in checkpoint.
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C7B.md` (new)

**Out of scope**: catalog, C1/C2/C3/C4/C5/C6 implementations, machine JSON/schema, product/exact docs, COM/scan, reconciliation, DB schema/migrations, live DWG/SQLite, application deployment, main, C7c/C7d and release. If a necessary change lies outside this scope, save checkpoint PARTIAL/BLOCKED with exact evidence, do not guess/relax invariant.

## Acceptance tests

- BOARD_IN/BOARD_AV on valid 700_* accepted; two unrelated valid suffixes; AV CABLE_OUTLET on 700_* references BOARD_AV and is accepted; AV free-form IDs and duplicates continue to behave as before.
- BOARD_IN/BOARD_DISTRIBUTION on 700_* rejected; BOARD_AV on 100_*, 600_* and legacy BOARD layer rejected; ordinary BOARD_IN/BOARD_DISTRIBUTION on 100_* and legacy BOARD preserved.
- BOARD_AV must not produce AV_BLOCK_NAME, AV outlet missing-field diagnostics, free CABLE_ID line or physical AV CableLine.
- DALI_GROUP 300_*/400_* with valid D.YYY accepted; legacy DALI_GROUPS/invalid layers blocked; duplicate/dynamic/ID errors still reported; no physical read payload.
- HVAC 600_* permits former heating and ventilation devices, invalid 600 suffix rejected. 300/400 TRACK_DALI correct prefix constraints incl. 3YY/4YY; legacy TRACK_DALI overlap preserved.
- Full/targeted tests, including DALI C4 and staged C7a tests, updated precisely to runtime behavior. Use no skipped tests. Report known 11 pre-existing cad_contract failures separately, and compare against unchanged baseline if new failures appear.

Commands from `Systems/NLP` (Windows PYTHONPATH=src;.):
```
python -m pytest -q tests/cad_contract/test_validator_numeric_layers.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_numeric_contract_mapping.py tests/cad_contract/test_validator_av.py tests/cad_contract/test_issue237_track_dali_integration.py
python -m pytest -q --tb=short tests/cad_contract
python -m compileall -q src/nl_project_2/cad_contract
python -m ruff check src/nl_project_2/cad_contract/validator.py tests/cad_contract/test_validator_numeric_layers.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_numeric_contract_mapping.py
python -m ruff format --check src/nl_project_2/cad_contract/validator.py tests/cad_contract/test_validator_numeric_layers.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_numeric_contract_mapping.py
git diff --check
```

First verify current branch HEAD matches the issued task's start SHA in Issue #255. If not, stop without reset. Make a checkpoint commit EARLY if time/limit risks interruption. Final checkpoint: base_sha/start_sha/tested_sha/final_head_sha (in issue if self-referential), changed files, exact test results, known baseline failures and C7c next_action. Full locked 3.13/Windows live not claimed. No C7c start, new issue, main merge or release.
