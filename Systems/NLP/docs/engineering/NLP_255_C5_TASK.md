# NLP-255-C5 — AutoCAD COM early layer prefilter (opt-in, non-destructive)

TASK_ID: NLP-255-C5-COM-PREFILTER
ISSUE: psv76/Neirolinks#255
BASE_SHA: 441678248d05a7c255a215c87f2d94a715a605d7 (accepted C4)
WORK_BRANCH: feature/nlp-255-c5-com-prefilter
STATUS: READY / NOT IMPLEMENTED

## Observed baseline — do not rediscover

Actual AutoCAD STA source: `Systems/NLP/tools/autocad_sta_bridge.py`.
- `_scan(document, identity, definition_names=None, progress=None)` enumerates `document.ModelSpace`, tests `entity.ObjectName == "AcDbBlockReference"`, then always calls `_observation_payload`. The latter performs `EffectiveName/Name`, `Blocks.Item`, `IsDynamicBlock`, `InsertionPoint`, `Layer`, `HasAttributes/GetAttributes`, `Handle`.
- `_scan_handles` does incremental per-handle updates by `HandleToObject`; **leave untouched**.
- Protocol operation `"scan"` currently invokes `_scan` with positional arguments; **preserve protocol, return schema and existing call defaults**.
- Existing tests: `Systems/NLP/tests/cad_sync/test_sta_bridge.py`, including legacy POWER-layer fixtures.
- C1 `cad_contract/layer_names.py::parse_working_layer_name` and C2 `cad_contract/layer_groups.py::function_group_for_working_layer` already exist, but are not wired.
- Issue #255: on normal DWG scan check layer **before costly per-block COM properties**. A filtered-out insertion MUST NOT be silently treated as physically removed by reconciliation. #148 incremental path must not regress.

## Deliverable — safe staged COM prefilter

Implement a **backward-compatible, opt-in** early layer filter in `_scan` or an adjacent helper in `tools/autocad_sta_bridge.py`:

1. Add an optional **keyword-only** predicate argument (e.g. `include_layer: Callable[[str], bool] | None = None`) after current arguments. `None` preserves 100% legacy scan output and calls. No new CLI/request flag, no automatic activation. If task requires changing the signature, ensure old positional calls work.
2. For confirmed `AcDbBlockReference` entities under opt-in, read **only `entity.Layer`** before requesting `EffectiveName`, `Name`, `Handle`, `InsertionPoint`, `IsDynamicBlock`, `HasAttributes/GetAttributes`, or `Blocks.Item`. If predicate rejects layer, do not call `_observation_payload`. If predicate accepts, produce the same observation payload shape and data as legacy.
3. Add a convenient pure predicate using existing C1 parser `parse_working_layer_name` (e.g. `is_working_layer_for_scan`) to recognize valid 100_* ... 900_*, including 300/400 DALI_GROUP positions. Do not duplicate rules. Since `tools/` and `src/` are separate imports in the existing test/runtime setup, verify import works under existing test bootstrap and do not add heavyweight app imports or an unconditional import that breaks bridge startup.
4. Return **explicit non-authoritative exclusion evidence** when opt-in is on, suitable for later safe integration: number of skipped block references and a machine-readable flag such as `scan_is_complete_for_reconciliation: false` / `layer_filter_applied: true`. Consider whether the current response envelope permits additive keys and verify contract/tests. If not possible safely, keep the optimized helper internal and clearly document why it cannot yet be used by sync. Never mark a filtered subset as a complete authoritative DWG snapshot.
5. Do **not** introduce a new full enumeration pass, bulk COM attributes on all design layers, DWG changes or expensive block-name prechecks. Preserve progress callbacks and document identity/source_metadata behavior.
6. **Fail closed**: predicate exceptions and failures reading Layer must be propagated/diagnosed, never silently skip an insertion. Never modify `_scan_handles`, client synchronization, deletion logic, or activate opt-in in actual Update. C6 will handle reconciliation semantics. Default normal scan must still deliver old authoritative/full content.

## Tests and acceptance

Add targeted spy/mock tests in `Systems/NLP/tests/cad_sync/test_sta_bridge.py` or new `tests/cad_sync/test_sta_layer_prefilter.py`:
- Mixed modelspace: non-blocks, valid 100_* 300_* 400_* 600_* 700_* 900_* blocks, invalid layers (300, 300_, ARCH_WALLS, 350_X), legacy POWER. Legacy default mode returns all inserted blocks unchanged.
- Under explicit opt-in predicate, excluded blocks get **zero reads** of EffectiveName/Name, attributes/Handle/geometry/dynamic metadata/definition, while Layer read is allowed; accepted block fully serialized.
- A DALI_GROUP reference on 300_* or 400_* survives filtering without needing old DALI_GROUPS.
- Strict invalid layer handling; predicate exceptions cause scan failure, not a partial success.
- In opt-in mode exclusion evidence indicates a **non-authoritative** partial scan, never zero-deletions permission. Default scan remains complete.
- `_scan_handles` and existing incremental/fingerprint behavior unchanged; run existing bridge tests.
- Verify no unexpected expensive full COM traversal beyond existing ModelSpace enumeration.

Run from `Systems/NLP`:
```bash
PYTHONPATH=src:. python -m pytest -q tests/cad_sync/test_sta_bridge.py tests/cad_sync/test_sta_layer_prefilter.py
python -m compileall -q tools/autocad_sta_bridge.py
python -m ruff check tools/autocad_sta_bridge.py tests/cad_sync/test_sta_layer_prefilter.py
python -m ruff format --check tools/autocad_sta_bridge.py tests/cad_sync/test_sta_layer_prefilter.py
git diff --check
```
If tests are placed in existing `test_sta_bridge.py`, adjust the test command accordingly. Existing Windows-only mocked win32com/pythoncom test dependencies must be handled as pre-existing environment constraints, not by weakening tests. Do not claim locked Python 3.13 or live AutoCAD acceptance unless actually executed.

## Allowed changes

- `Systems/NLP/tools/autocad_sta_bridge.py`
- `Systems/NLP/tests/cad_sync/test_sta_layer_prefilter.py` (new), and existing `test_sta_bridge.py` only where strictly necessary for compatibility tests
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C5.md` (new)

No edits to CAD contract machine JSON, catalog, validator, C1-C4 implementations/tests, client sync, reconciliation, actual SQLite/DWG, installed app, version/release, main or D23 PRs. No new Issues. Do not start C6.

## Stop conditions and checkpoint

If safe opt-in + explicit non-authoritative signal cannot be provided without changing scan consumers, stop and document BLOCKED/PARTIAL instead of introducing destructive semantics. If the existing test bootstrap cannot import the C1 parser into the bridge, document and use minimal safe import that does not break existing Windows startup; do not silently copy the parser. If HEAD differs from verified start, stop without resetting other's work.

One task, commit tests and implementation, persist a checkpoint `task_id/base_sha/start_sha/tested_sha/head_sha/status/changed_paths/exact_test_results/next_action`, post final SHA to existing #255. Coordinator will independently review C5; no C6 or runtime enablement without separate permission.
