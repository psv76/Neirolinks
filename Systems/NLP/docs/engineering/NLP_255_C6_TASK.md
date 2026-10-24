# NLP #255 — C6: защита от неполного DWG snapshot

**TASK_ID:** NLP-255-C6-RECONCILIATION-GATE
**Repo:** psv76/Neirolinks
**Base SHA (accepted C5):** `2ecb36f7dddb9aab3609e748d2ca21d381bcb75a`
**Work branch:** `feature/nlp-255-c6-reconciliation-gate`
**State:** READY / NOT IMPLEMENTED

## Existing state (verified)

- `Systems/NLP/tools/autocad_sta_bridge.py::_scan` provides optional `include_layer`, but it is NOT enabled by protocol/Update. Opt-in returns `source_metadata.layer_filter_applied=true`, `skipped_block_references=N`, `scan_is_complete_for_reconciliation=false`, even if N=0.
- `Systems/NLP/src/nl_project_2/cad_sync/service.py::preview` validates a batch, builds the canonical snapshot and computes `ChangeClass.MISSING_DWG_INSERTION` by comparing stored handles with `valid_by_handle`. There is also topology-stale repair derived from absences. `apply_dwg_to_project` accepts selected changes and writes persistent changes. `_persist_scan` persists `batch.source_metadata`.
- Current default/full scan must stay untouched. C6 is a **fail-closed safety gate**, NOT activation of fast scanning or a migration of layers. Future integration must include full negative regression before filtered Update is enabled.

## Required outcome: enforce non-authoritative scan boundary

Provide a small, pure check in `cad_sync` (e.g., `reconciliation_safety.py`) that classifies `source_metadata` as authoritative for *absence-dependent reconciliation* ONLY if neither `layer_filter_applied=true` nor `scan_is_complete_for_reconciliation=false` is present. The check must fail closed on contradictory/invalid metadata; unknown or malformed completeness values must never grant absence authority. Legacy metadata without these keys is authoritative for **existing unfiltered scan paths only**, retaining backwards compatibility. The helper is **not** proof of actual DWG completeness; it enforces the trust boundary declared by the adapter.

Wire this check into the entry points in `cad_sync/service.py` so that a filtered/partial batch cannot produce an authoritative comparison or be applied as an ordinary full scan:
1. At `preview(..., batch=...)`, **reject partial/non-authoritative source metadata explicitly with a clear `DwgSyncError`**, before constructing a misleading missing-insertion/topology-removal proposal. A complete historical scan continues unchanged.
2. At `apply_dwg_to_project(proposal, ...)`, **recheck the proposal's source metadata** before any DB writes, even if a caller supplied a crafted/stale proposal bypassing preview. Do not trust `selected_paths`/GUI or `skipped_block_references=0`.
3. Preserve scan metadata as evidence in existing normal persistence. Do not reinterpret skipped rows as absent DWG entities. Existing MISSING_DWG_INSERTION and topology-stale behavior for legitimate *unfiltered* scans must remain unchanged.

Safety regressions should include metadata variants:
- `{ }` and representative normal full-scan metadata ⇒ legacy allowed;
- `layer_filter_applied=true` and `scan_is_complete_for_reconciliation=false` ⇒ blocked;
- filtered but zero excluded (`skipped_block_references=0`) ⇒ still blocked;
- contradictory `layer_filter_applied=true, scan_is_complete_for_reconciliation=true` ⇒ blocked;
- false completeness marker even without filter ⇒ blocked;
- malformed flags `"false"`, `"true"`, 0/1, null etc. ⇒ no unverified completeness assertion and **fail closed** where supplied.
- No actual production writes (use in-memory/fake DB or existing test fixtures). Assert preview fails *before* MISSING_DWG_INSERTION classification, and apply fails before writes for forged proposals. Test same DWG repeated ordinary preview/update remains behaviorally unchanged when authorized.

**Be careful:** source_metadata may contain unrelated fields; do not reject those. Error messages should identify scan incompleteness, not claim objects deleted. Existing D23/Stage C/BUS/transit/AV identities and #148 incremental scan must not regress.

## Allowed edits

- `Systems/NLP/src/nl_project_2/cad_sync/reconciliation_safety.py` (new, if suitable)
- `Systems/NLP/src/nl_project_2/cad_sync/service.py` (minimal guard at preview/apply)
- New focused tests in `Systems/NLP/tests/cad_sync/test_reconciliation_scan_completeness.py` (or nearest existing tests, with documented necessity)
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C6.md` (new)

**Do not modify:** scanner COM/protocol, C1–C5 helpers, block contract JSON, catalog, validator, schemas/migrations, actual DB/DWG, runtime scan activation, git main, D23 branches or release. No new Issue. No C7.

## Verification

From `Systems/NLP` run focused new + existing relevant `cad_sync` tests; select them based on actual existing test filenames. Also:
```
PYTHONPATH=src:. python -m pytest -q tests/cad_sync/test_reconciliation_scan_completeness.py
python -m compileall -q src/nl_project_2/cad_sync
python -m ruff check src/nl_project_2/cad_sync/reconciliation_safety.py src/nl_project_2/cad_sync/service.py tests/cad_sync/test_reconciliation_scan_completeness.py
git diff --check
```
If a named file/path differs, adapt commands to actual created paths; don't silently skip tests. Include unchanged full-scan/repeated Update and #148 regression evidence if runnable. State precisely what was not tested. No claim of locked Python 3.13/full CI/live tests unless actually run.

## Checkpoint / interruption

First verify this task file and current HEAD **in the work branch**. If mismatch, stop. Run only C6. Commit smallest safe unit and tests, push to the work branch, save checkpoint with base/start/tested/final SHA (final in Issue #255 if self-referential), changed paths, exact tests, limits, one `next_action`. If time/limit runs low, save partial state immediately.

**C6 DONE means safety guard only:** real filtered scan remains disabled until C7 integration, normative docs, locked/Windows/live acceptance. Release #255 stays BLOCKED.
