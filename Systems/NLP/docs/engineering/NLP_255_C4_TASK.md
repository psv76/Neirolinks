# NLP-255-C4 — staged DALI_GROUP placement rule

TASK_ID: `NLP-255-C4-DALI-LAYER`
ISSUE: `psv76/Neirolinks#255`
BASE_SHA: `9027de64ee3d23c831b9d4db106ab54c3b351ca1` (accepted C3)
WORK_BRANCH: `feature/nlp-255-c4-dali-layer`
STATUS: READY / NOT IMPLEMENTED

## Verified existing system

- The staged C1 parser `cad_contract/layer_names.py` accepts valid working layers `100_*`…`900_*`. Staged C2 resolver `cad_contract/layer_groups.py` maps `300_*` → `LIGHTING_230V`, `400_*` → `LIGHTING_LED`.
- Current machine contract `resources/autocad/block_contract.json` v3.2.0 still has `logical_blocks.DALI_GROUP.layer = "DALI_GROUPS"`, `required = ["DALI_GROUP_ID"]`, `dynamic_if_metadata_available = true`. It is **read-only for C4**.
- Current `cad_contract/validator.py::_validate_logical` checks equality with the legacy logical layer and validates DALI identifier format `D.YYY`, uniqueness and dynamic metadata. These existing checks must not be removed or bypassed.
- Source: #255 specifies `DALI_GROUP` may be on **any valid 300_* or 400_*** and must not require the dedicated `DALI_GROUPS` layer. DALI_GROUP is logical and must not create an ordinary physical cable line.

## One bounded result

Create a **pure, staged eligibility helper**, separate from runtime:

`src/nl_project_2/cad_contract/dali_layer_rules.py` with the API:

`is_valid_dali_group_layer(layer: object) -> bool`

It must delegate to the already accepted C2 `function_group_for_working_layer`; return true iff the group is `LIGHTING_230V` or `LIGHTING_LED`. Arbitrary valid Cyrillic/Latin/free suffixes are accepted, including multiple distinct 300_* and 400_* layers. Reject legacy `DALI_GROUPS`, malformed/empty/space-bound suffixes, nonstring inputs and other prefixes. No magic whitelist/specific suffix required.

Include a **pure optional identifier validator** only if genuinely necessary for proving preserved logical safety; prefer tests inventorying the existing `_DALI_GROUP_ID` and `logical_blocks.DALI_GROUP` contract without copying / changing its semantics. Do not implement a second competing DALI ID parser.

Create parameterized `tests/cad_contract/test_dali_layer_rules.py` demonstrating:
1. Valid `300_Освещение`, `300_Light 230V floor`, `300_Свет__этаж`, `400_LED карнизы`, `400_DALI` and different suffixes on both prefixes.
2. Invalid `DALI_GROUPS`, `300`, `300_`, `300_ Свет`, `400_Свет `, `350_Свет`, `500_Датчики`, `700_HDMI`, nonstring values.
3. Independent read-only machine-contract inventory: `logical_blocks.DALI_GROUP.required = ["DALI_GROUP_ID"]`, dynamic metadata requirement remains true and ignored-project-data false; legacy layer is currently `DALI_GROUPS` and **not yet migrated**. Test does not declare it a valid new working layer.
4. `DALI_GROUP` identifier syntax/uniqueness and dynamic checks remain requirements for future runtime adoption; assert they are still present in the existing validator via appropriate targeted tests of its current code/API if readily available, otherwise document a follow-up integration gate; do not modify existing validator.
5. No cable-line creation, DALI physical topology, quantities or runtime changes.

The narrow scope is intentional: acceptance of C4 means staged placement contract + tests, **not** migrated runtime DALI_GROUP handling.

## Allowed changes

Only new files under `Systems/NLP/`:
- `src/nl_project_2/cad_contract/dali_layer_rules.py`
- `tests/cad_contract/test_dali_layer_rules.py`
- `docs/engineering/checkpoints/NLP_255_C4.md`

The task brief is already committed and must not be edited by executor.

## Out of scope

No edits to existing files. No `validator.py`, `catalog.py`, `layer_names.py`, `layer_groups.py`, `dali_graph.py`, `block_contract.json`, scan/COM, reconciliation, database, migration, DWG, product documentation, D23 branch/PR, C5 or main. Do not activate the new placement in production.

## Tests

From `Systems/NLP`:

```bash
PYTHONPATH=src python -m pytest -q tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py tests/cad_contract/test_av_layer_identity.py tests/cad_contract/test_dali_layer_rules.py
python -m compileall -q src/nl_project_2/cad_contract
python -m ruff check src/nl_project_2/cad_contract/dali_layer_rules.py tests/cad_contract/test_dali_layer_rules.py
python -m ruff format --check src/nl_project_2/cad_contract/dali_layer_rules.py tests/cad_contract/test_dali_layer_rules.py
git diff --check
```

Check changed paths against the pre-implementation SHA. Report the exact results; do not claim CPython 3.13 locked suite or Windows/AutoCAD/live acceptance unless actually run.

## Checkpoint

One session → one stage, as [CODEX_SESSION_STANDARD.md](https://github.com/psv76/Neirolinks/blob/docs/nlp-codex-session-standard/Systems/NLP/docs/engineering/CODEX_SESSION_STANDARD.md). Save checkpoint with base/start/tested/head SHA, changed paths, results and one next action. Final SHA (including checkpoint commit) can be posted in #255 comment to avoid self-reference. If budget runs low, persist safe partial work first.

**NEXT ACTION:** independent coordinator review. C5 must be separately assigned. Issue #255 remains OPEN and release stays BLOCKED.
