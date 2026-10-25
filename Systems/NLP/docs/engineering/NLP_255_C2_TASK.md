# NLP-255-C2 — group mapping and HVAC candidate, executable task

TASK_ID: `NLP-255-C2-GROUP-MAPPING`
ISSUE: `psv76/Neirolinks#255`
BASE C1 HEAD: `a8d9f6d775b4345893b6b581fbb665de38d9fbef`
WORK_BRANCH: `feature/nlp-255-c2-group-mapping`

## Current contract and boundaries

The C1 parser `cad_contract/layer_names.py::parse_working_layer_name` is completed and has 49 passing unit cases; its returned values are `100,200,...,900` or `None`. Existing `catalog.py::groups_for_layer` still uses exact legacy named layers. The current machine contract `resources/autocad/block_contract.json` is 3.2.0/72 with separate `HEATING` and `VENTILATION`, and old-layer `AV`. Issue #255 defines unified `HVAC=600` and independent `AV=700`. These runtime changes are **not** part of C2.

## Required result — pure staged group resolver

Implement `cad_contract/layer_groups.py` with a standalone, deterministic API `function_group_for_working_layer(layer: object) -> str | None` that calls C1's parser. Map strictly:

| Prefix | Group |
| --- | --- |
| 100 | POWER |
| 200 | SWITCHES |
| 300 | LIGHTING_230V |
| 400 | LIGHTING_LED |
| 500 | SENSORS |
| 600 | HVAC |
| 700 | AV |
| 800 | NETWORK |
| 900 | BUS |

Use the exact Issue #255 names. Do not interpret the free layer suffix, convert numeric/nonstring inputs, or silently admit old exact names. Return `None` for any layer rejected by C1. Keep this resolver **unwired**: no existing production callsite may change in this task.

Also implement a pure helper `hvac_allowed_device_types(ventilation: Collection[str], heating: Collection[str]) -> frozenset[str]` computing the union of both existing device-type sets **without dropping either family**; no changes to actual block allowed groups, catalog file, or device types. Test the helper using the actual two group sets loaded read-only from the existing machine contract, and explicit subset/union assertions. Do not alter the contract.

## Allowed code and tests

- `Systems/NLP/src/nl_project_2/cad_contract/layer_groups.py` (new)
- `Systems/NLP/tests/cad_contract/test_layer_groups.py` (new)
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C2.md` (new checkpoint)
- This task brief is immutable input and must not be rewritten except to correct a proven contradiction, with explanation.

## Explicitly out of scope

Do **not** edit `catalog.py`, `validator.py`, `layer_names.py`, `block_contract.json`, COM bridge, scan, reconciliation, SQLite, DWG, CAD blocks, AV identity, DALI, migrations, product docs, any existing test, or installed program. Do not change `main` or either D23 Draft PR. Do not start C3 or connect the resolver to runtime. The later integration stage will adopt HVAC and remap allowed_groups only after full dependency checks.

## Tests and acceptance

From `Systems/NLP` (use the existing environment):

```bash
PYTHONPATH=src python -m pytest -q tests/cad_contract/test_layer_names.py tests/cad_contract/test_layer_groups.py
python -m compileall -q src/nl_project_2/cad_contract
python -m ruff check src/nl_project_2/cad_contract/layer_groups.py tests/cad_contract/test_layer_groups.py
python -m ruff format --check src/nl_project_2/cad_contract/layer_groups.py tests/cad_contract/test_layer_groups.py
```

Tests must cover all nine mappings; arbitrary differing valid suffixes per group, Cyrillic, extra underscores, invalid prefixes/whitespace, nonstring values, HVAC device union, no accidental `HEATING`/`VENTILATION` returned and no `7YY` interpretation of AV `CABLE_ID`. The last is a separation invariant: C2 reads **layer names only** and does not read a cable ID.

Accept C2 only with implementation + tests PASS, runtime untouched, exactly allowed paths changed, commit pushed to work branch, and checkpoint giving tested implementation SHA and final pushed head SHA (self-reference limitation may put final SHA in #255 comment).

## Checkpoint protocol

Follow `CODEX_SESSION_STANDARD.md` in Draft PR #264. Save `task_id, base_sha, branch, tested_commit_sha, head_sha, status PASSED/PARTIAL/BLOCKED, exact tests, scope, next_action`; also leave brief #255 comment. For interrupted sessions, commit safe partial work and record one next operation. Do not spend context window researching history or rebuilding C1.

**NEXT ACTION AFTER C2:** Independent coordinator code/test review. C3 only after separate assignment.
