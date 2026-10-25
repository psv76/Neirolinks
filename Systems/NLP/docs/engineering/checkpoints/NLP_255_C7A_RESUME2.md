# NLP-255-C7A-CONTRACT-MAPPING — resume2

## Intermediate persistence after usage-limit interruption

- status: **PARTIAL**
- start_sha: `040db57ee5ef22d1dcffbfacdc27dcd910a71eb8`
- branch: `feature/nlp-255-c7a-contract-integration`
- base_sha: `1b3d79de5e216e4254eea1ecc488a58802b8b6d2`
- This intermediate commit preserves the six surviving implementation/test/doc
  changes plus this checkpoint before further work. Final tested/head SHA and
  results will be appended after verification; no runtime acceptance claimed.

Inspected git status and every changed path. catalog.py and the new
test_numeric_contract_mapping.py survived. The rejected edit to
test_layer_groups.py did not execute: that file remains identical to HEAD.
No reset, clean, clone or removal performed.

Prior-run evidence (before this resumption): new targeted tests 57 passed;
existing selected suite 375 passed / 8 failed: seven known baseline failures
plus the old C2 inventory test referencing removed HEATING/VENTILATION groups.
No fresh verification yet. A narrow documentation line-ending cleanup is also
pending; unrelated physical DALI text must remain byte-identical to base.

next_action: Update the C2 inventory test for the approved HVAC migration,
preserving both former device sets, remove incidental documentation line-ending
changes, then run C7A tests and report staged-versus-runtime limitations.

No validator/COM/sync or real DB/DWG edits. C7b not started.

## Final C7A result after continuation

- task_id: `NLP-255-C7A-CONTRACT-MAPPING`
- status: **PARTIAL**, as required by the approved addendum when runtime
  cannot yet enforce role-conditional placement without C7b.
- start_sha: `040db57ee5ef22d1dcffbfacdc27dcd910a71eb8`
- intermediate_commit: `50747bd34a5034b75bf6634d5b4ec5b7fb2b2257`
- tested_commit_sha: `9c11b5cb8a4f031ffca05935cdc84864b2e666a2`
- final pushed head_sha: recorded in Issue #255 after this checkpoint commit.

### Implemented within scope

Machine contract now has exactly nine groups. HVAC=600 contains the exact union
of former ventilation/heating types; special FAN/AIR_VALVE profiles are unchanged.
AV retains null ordinary cable_prefix and free BOARD+CABLE_ID identity. Numeric
representative layer names are recorded in JSON; C1/C2-backed catalog resolution
accepts arbitrary valid suffixes, not just those representatives.

Explicit compatibility boundary: groups_for_layer defaults include_legacy=True
to retain exact aliases already listed in machine layers. Numeric-only consumers
can pass include_legacy=False. HEATING/VENTILATION legacy names resolve to HVAC;
old 7YY heating identifiers are NOT silently rewritten. Legacy TRACK_DALI layer
still has both lighting groups; numeric 300/400 layers resolve unambiguously.

Restored board_rules.av_role=BOARD_AV, av_block_name=BOARD_IN and staged
av_function_group=AV. BOARD_IN has its own family referencing load_types.BOARD;
other boards reference ORDINARY_BOARD, preserving their former six roles.
No generic BOARD allowed_groups gains AV. New catalog groups_for_board_layer
requires the exact BOARD_IN+BOARD_AV+valid numeric 700 combination. Tests reject
ordinary BOARD_IN roles on 700, BOARD_AV on 100/600/legacy/invalid layers and
BOARD_AV on other board-family names. Approved role/layer clarification added
only to BOARD_IN exact reference and a short product/20 paragraph.

Schema semantic comparison proves its ONLY change is minProperties 10 -> 9.
Full Draft202012Validator acceptance and fewer-than-nine rejection pass. Schema
was not expanded for new family properties: ORDINARY_BOARD uses the existing
load_type_group mechanism. All non-board block families, all attribute profiles,
ATTDEF, AV identity rules and logical DALI metadata match start_sha exactly.

The C2 inventory test was updated because its old lookup of two removed machine
groups is incompatible with the explicitly approved migration. It now pins both
former type sets, verifies their complete union equals actual HVAC, and rejects
the old group names. This change does not alter any of the seven baseline tests.

### Deliberate runtime limitation / C7b gate

groups_for_board_layer is not called by the runtime validator. Tests explicitly
record that runtime still rejects BOARD_IN/BOARD_AV on 700 with
LAYER_FUNCTION_GROUP_MISMATCH and does not enforce its exclusion from 100.
These observations are not runtime acceptance. Runtime adoption and ordinary
group/role validation remain C7b work; no production activation or C7b edits.

### Final verification

From Systems/NLP, existing `.venv/Scripts/python.exe` as python,
PYTHONPATH=src;., TEMP/TMP=.venv/tmp. Windows CPython 3.14.3, pytest 9.1.1,
Ruff 0.15.22, jsonschema 4.26.0. Commands:

1. `python -m pytest -q tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py tests/cad_contract/test_av_layer_identity.py tests/cad_contract/test_dali_layer_rules.py tests/cad_contract/test_numeric_contract_mapping.py`
   — **308 passed in 0.38s**, exit 0 (57 new mapping cases).
2. `python -m pytest -q --tb=no tests/cad_contract/test_catalog.py tests/cad_contract/test_repair08_contract.py tests/cad_contract/test_validator_av.py tests/cad_contract/test_issue237_track_dali_integration.py`
   — **7 failed, 125 passed in 0.36s**, exit 1. Same seven baseline failures,
   no expectation changes/skips: old contract version, 71-name fixture,
   EL_BOX_OUT_100x100/TRACK_230V/TRACK_48V/TRACK_DALI ATTDEF hashes, blanket BUS_ID.
3. `python -m pytest -q --tb=no tests/cad_contract`
   — **11 failed, 634 passed in 1.46s**, exit 1. Includes the above seven and:
   - test_issue134_box_chains.py::test_base_only_box_chain_has_distinct_graph_nodes
   - test_validator_positive.py::test_every_approved_name_has_a_valid_metadata_observation[EL_BOX_OUT_100x100]
   - test_validator_positive.py::test_every_approved_name_has_a_valid_metadata_observation[TRACK_DALI]
   - test_validator_positive.py::test_representative_of_each_non_key_physical_family_is_valid[TRACK_DALI]
4. The two files containing those four additional failures were run unchanged
   from a git-archive snapshot of start_sha: **4 failed, 85 passed in 0.19s**.
   Current implementation on the same selection: **4 failed, 85 passed in 0.35s**.
   They predate C7A (old BUS_POINT_ID fixture / missing passive BUS_ID), not new
   regressions. Working tree was never reset or swapped for this comparison.
5. `python -m compileall -q src/nl_project_2/cad_contract` — PASS.
6. `python -m ruff check src/nl_project_2/cad_contract/catalog.py tests/cad_contract/test_numeric_contract_mapping.py tests/cad_contract/test_layer_groups.py` — PASS.
7. `python -m ruff format --check src/nl_project_2/cad_contract/catalog.py tests/cad_contract/test_numeric_contract_mapping.py tests/cad_contract/test_layer_groups.py` — 3 files already formatted.
8. `git diff --check 040db57ee5ef22d1dcffbfacdc27dcd910a71eb8` — PASS after
   correcting incidental line-ending changes. Intermediate commit intentionally
   preserved those pending edits first; final physical DALI documentation is
   byte-identical to baseline outside the approved BOARD_IN insertion.

Counts above overlap and must not be added together. No new failing tests in
the final runs beyond the eleven demonstrated baseline failures. No locked
CPython 3.13, full CI, complete application suite or live acceptance claimed.

### Final changed paths / persistence

Under Systems/NLP: resources/autocad/block_contract.json,
resources/autocad/block_contract.schema.json, src/nl_project_2/cad_contract/catalog.py,
tests/cad_contract/test_numeric_contract_mapping.py,
tests/cad_contract/test_layer_groups.py,
docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md,
docs/product/20_AUTOCAD_BLOCK_CONTRACT.md, this checkpoint (8 paths).
Previous checkpoints and task brief preserved. Validator/COM/sync/main and real
DWG/SQLite untouched. No new Issues or merge. Release remains BLOCKED.

Ignored baseline evidence snapshot retained at
`D:\NLP 3.1\Neirolinks\Systems\NLP\.venv\tmp\c7a-baseline-040db57` for this review;
it is disposable after coordinator review, not a working clone or installed app.

next_action: Coordinator reviews tested commit
`9c11b5cb8a4f031ffca05935cdc84864b2e666a2` for staged C7A acceptance and the
documented runtime gate. C7b requires a separate assignment and was not started.
