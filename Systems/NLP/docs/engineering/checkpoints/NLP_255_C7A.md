# NLP-255-C7A-CONTRACT-MAPPING checkpoint

- task_id: `NLP-255-C7A-CONTRACT-MAPPING`
- base_sha: `1b3d79de5e216e4254eea1ecc488a58802b8b6d2` (accepted C6)
- start_sha: `54452f5d45e340ef3b6fbf24f457f0fa9426e009`
- tested_sha: `54452f5d45e340ef3b6fbf24f457f0fa9426e009` (unchanged baseline)
- branch: `feature/nlp-255-c7a-contract-integration`
- status: **BLOCKED**; no contract/catalog implementation attempted.
- head_sha: final checkpoint-only commit SHA is recorded in Issue #255.
- changed_paths: only `Systems/NLP/docs/engineering/checkpoints/NLP_255_C7A.md`.

## Stop condition: unresolved BOARD_AV contract and placement

The entire C7A brief was read and branch start SHA verified. The explicit stop
condition applies: preserving AV/BOARD behavior cannot be resolved consistently
from the current normative and machine inputs without a new domain decision.
Issue #255 body and comments through C7a preparation comment 6393759517 were
checked; no approved resolution of the following conflict was found.

Evidence at start_sha (paths below relative to `Systems/NLP/`):

1. Issue #255 explicitly requires preserving BOARD_AV and prohibits restoring
   cancelled domain decisions. `docs/product/24_AV_CABLE_SYSTEM.md:26-29` requires
   BOARD_IN with LOAD_TYPE=BOARD_AV; lines 64-76 require identity/uniqueness and
   reference to that board role.
2. `resources/autocad/block_contract.json:1456-1462` permits only BOARD_METER,
   BOARD_IN, BOARD_IN_AVR, BOARD_DISTRIBUTION, BOARD_AVR and BOARD_SCS for boards;
   BOARD_AV is absent. Lines 1469-1473 set av_role and av_block_name to empty
   strings. `docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md:1853-1860` gives
   the same six-role list, without BOARD_AV.
3. Loaded BOARD_IN.allowed_groups is only {POWER}; BOARD is a device type only
   in POWER. AV.device_types is only {CABLE_OUTLET}. The new placement for the
   AV-designated board is not specified by #255. Choosing 100_* vs 700_* or
   allowing BOARD in AV (potentially all board-family names/roles) would be an
   unapproved policy change, not just numeric layer parsing.
4. `cad_contract/validator.py:1345` compares AV target role with
   catalog.board_rules['av_role'], currently empty. Leaving that empty while
   claiming BOARD_AV preservation would retain a broken role check. Restoring
   BOARD_AV and BOARD_IN values would conflict with the current exact reference
   unless the coordinator explicitly resolves the contract and scope.

Read-only synthetic reproduction using the existing catalog/validator, a
BOARD_IN observation with all required definition tags, BOARD_ID=AV.01,
LOAD_TYPE=BOARD_AV, ordinary fixture coordinates and document identity:

| Layer | Current validator issue codes |
| --- | --- |
| BOARD | LOAD_TYPE_NOT_ALLOWED |
| 700_AV board | LAYER_FUNCTION_GROUP_MISMATCH, LOAD_TYPE_NOT_ALLOWED |

The first row demonstrates the role conflict independently of numeric migration.
The second is baseline evidence, not a new C7b behavior expectation.

TRACK_DALI was not guessed or changed: existing loaded allowed_groups and legacy
TRACK_DALI layer resolution both include LIGHTING_230V and LIGHTING_LED.
Product contract 20 line 29 explicitly preserves 3YY/4YY voltage compatibility.
HVAC union was not applied while the stop condition is outstanding.

## Baseline checks (no implementation changes)

Directory: `D:\NLP 3.1\Neirolinks\Systems\NLP`; existing
`.venv/Scripts/python.exe` used as `python`; `PYTHONPATH=src;.`.
Windows / CPython 3.14.3 / pytest 9.1.1 / Ruff 0.15.22.

| Command | Result |
| --- | --- |
| `python -m pytest -q tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py tests/cad_contract/test_av_layer_identity.py tests/cad_contract/test_dali_layer_rules.py` | 251 passed in 0.28s, pytest exit 0 |
| `python -m pytest -q --tb=no tests/cad_contract/test_catalog.py tests/cad_contract/test_repair08_contract.py tests/cad_contract/test_validator_av.py tests/cad_contract/test_issue237_track_dali_integration.py` | 7 failed, 125 passed in 0.52s, pytest exit 1 |
| `python -m pytest -q --tb=short --lf tests/cad_contract/test_catalog.py tests/cad_contract/test_repair08_contract.py` | 7 failed, 109 deselected in 0.72s, pytest exit 1; failure-detail capture |
| `python -m compileall -q src/nl_project_2/cad_contract` | PASS |
| `python -m ruff check src/nl_project_2/cad_contract/catalog.py` | All checks passed |

Exact baseline failures, all before any source/test edits:

- `test_catalog.py::test_machine_contract_has_exact_approved_shape`: expects
  contract_version 3.0.0, actual 3.2.0.
- `test_repair08_contract.py::test_exact_71_names_and_attdef_fixture`: actual
  definitions additionally contain CABLE_OUTLET_BUS.
- `test_repair08_contract.py::test_each_canonical_block_has_exact_attdef_hash`
  for EL_BOX_OUT_100x100, TRACK_230V, TRACK_48V and TRACK_DALI: hash mismatch
  against existing fixture (four failures).
- `test_repair08_contract.py::test_project_only_tags_are_not_attdefs[BUS_ID]`:
  blanket assertion conflicts with the candidate's passive DALI BUS_ID ATTDEF.

No fixture expectations were changed or failures hidden. Existing AV and
TRACK_DALI test files in this selection had no failures, but do not establish
the missing BOARD_AV positive contract. These are baseline/parity issues, not
regressions introduced by a C7A implementation. There is no C7A mapping PASS.

## Persistence, limits and next operation

Only this evidence checkpoint is committed. Machine JSON, catalog, validator,
tests, C1-C6, COM, reconciliation, schema, real DB/DWG and production unchanged.
C7b not started; no new Issues, main merge or release action. No locked 3.13,
full CI or Windows/live acceptance claimed. Issue #255 remains OPEN, release
BLOCKED. Checkout retained at `D:\NLP 3.1\Neirolinks` for review/resume.

next_action: Coordinator resolves and records in the C7A brief the authoritative
AV-board contract (BOARD_AV versus current six-role set, av_role/av_block_name
and permitted numeric layer/group), reconciling the exact reference and scope;
only then resume C7A from this checkpoint. Do not implement a guessed mapping.
