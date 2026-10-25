# NLP #255 — C7f: pragmatic filtered sync activation

Task ID: NLP-255-C7F-PRAGMATIC-FILTERED-SYNC
Branch: feature/nlp-255-c7f-pragmatic-filtered-sync
Base: cd511d7d9b8ed588f17a1797aa1f4f189d37462f (reviewed C7e PARTIAL)
Status: READY — not implemented.

## Approved product decision (2026-10-25)

The synchronization design is intentionally **pragmatic, single-engineer oriented**, not a cross-process AutoCAD/SQLite atomic transaction. Do not implement CAD edit locks, long-lived COM leases, snapshot cloning, cryptographic proof, or an exhaustive heavyweight second scan just to remove a millisecond-scale race.

Normal interaction: engineer edits DWG → scans → reviews preview → clicks Apply → continues drawing.

**Accepted residual risk, disclose accurately:** DWG attributes/coordinates may change after initial scan without a handle/layer change, and a change can occur between the last lightweight verification and SQLite commit. Do not describe the check as detecting all DWG modifications or as a strict atomic consistency guarantee.

**Mandatory safety still applies:** never infer deletion merely because filtering omitted an INSERT, never apply a proposal to the wrong project/DWG/binding, never turn `scan_is_complete_for_reconciliation` true by assertion alone, and preserve an unfiltered authoritative fallback for ambiguous cases.

## Current starting architecture

- C7c diagnostic `AutoCadBridgeClient.read_layer_filtered_observations(request, tracked_handles=...)` returns LayerFilteredRead; lightweight complete Handle/Layer census before/after, selected AutoLISP heavy read or strict COM fallback; tracks off-layer INSERTs; explicitly incomplete source metadata; no #148 cache poisoning.
- C7e `DwgSyncService.review_filtered_sync` loads DB tracked handles constrained by confirmed project/DWG binding and rechecks context; no applicable proposal. `_ensure_binding` rechecks binding during SQLite UnitOfWork. `reconciliation_safety.py` C6 rejects filtered batches and provenance.
- Normal `scan_active/read_observations` remains full, authoritative with #148 cache/delta; service preview and apply expect complete authoritative observation batches.
- Existing missing-insertion, pruning and endpoint cleanup can cause real changes. Never use a subset as a complete batch.

## Required implementation

1. Add a **deliberate, explicit** opt-in fast sync workflow accessible from the actual application scan/review/apply path (not only tests or a diagnostic method). Ensure selected project, canonical DWG binding and tracked handles are obtained from project SQLite before any filtered scan. Default full path must remain available as a selectable/reliable fallback.
2. Use C7c filtered heavy observation for candidate work. Before an applicable preview/proposal is created, obtain a complete reconciliation view that cannot misclassify tracked off-layer inserts, untracked contract-owned inserts, DALI logical blocks, AV board/lines, or missing/deleted blocks. A subset is never simply passed to full preview/apply. When presence, removal, ownership or projection completeness is ambiguous, **fallback to the existing full unfiltered authoritative scan and normal preview/apply**. This may cost speed in some cases; correctness takes priority. No automatic deletion from a filtered subset.
3. On user Apply, do a fresh **lightweight handle/layer census** of the active DWG and compare to the census associated with the preview; if changed, reject as stale with an actionable message and require re-scan. Also recheck project revision, DWG identity and binding inside the existing SQLite write transaction. No extra full heavy scan merely to compare fingerprints. Explicitly document that attributes/coordinates are not revalidated by this lightweight recheck.
4. Existing C6 fail-closed logic stays in place: do not set false partial completeness marker to true, strip filtered provenance, or make C6 accept a partial read. Any applicable proposal must be built via a **genuinely authoritative full view** or a separately designed complete projection whose authority is demonstrated in tests. If that cannot be realized without broader changes, deliver safe staged code + a working explicit full fallback, status PARTIAL; do not activate unsafe fast Apply.
5. Do not claim performance without tests showing fewer heavy property reads in successful fast cases. If all applicable paths need a full heavyweight read, report no production speedup rather than pretending success. Preserve C1-C7b numeric layers/AV BOARD/DALI/HVAC and #148 incremental behavior.
6. Test the real UI/application workflow path (not only service unit tests). When filtered preview/apply is impossible or stale, user sees a clear actionable option to retry using full scan. Prevent accidental project switching or write to another confirmed DWG. No silent retries that apply unexpected changes.

## Allowed scope

- Systems/NLP/src/nl_project_2/cad_sync/bridge.py
- Systems/NLP/src/nl_project_2/cad_sync/scan_layer_safety.py
- Systems/NLP/src/nl_project_2/cad_sync/reconciliation_safety.py
- Systems/NLP/src/nl_project_2/cad_sync/service.py
- Systems/NLP/src/nl_project_2/presentation/object_workspace.py
- Systems/NLP/tools/autocad_sta_bridge.py
- Systems/NLP/tests/cad_sync/test_filtered_sync_authority.py
- Systems/NLP/tests/cad_sync/test_sync_service.py
- Systems/NLP/tests/cad_sync/test_bridge_client.py
- Systems/NLP/tests/cad_sync/test_scan_layer_safety.py
- Systems/NLP/tests/cad_sync/test_reconciliation_scan_completeness.py
- Systems/NLP/tests/cad_sync/test_sta_layer_prefilter.py
- Systems/NLP/tests/cad_sync/test_pragmatic_filtered_sync.py (new)
- Systems/NLP/docs/engineering/checkpoints/NLP_255_C7F.md (new)

A narrow adjacent presentation test file may be added only when its exact existing path and necessity are explained in checkpoint. Do not change other production modules without coordinator scope approval. No migrations, schema, catalog, main merge or live data edits.

## Acceptance matrix

- Normal: full scan preview/apply unchanged.
- Fast: common unchanged/present case uses fewer expensive reads than full scan, if fast applicable; otherwise visible full fallback with no false acceleration claim.
- Previously tracked INSERT moved to ARCH: retained in authoritative view or full fallback, reported as layer mismatch/not missing, no false removal/pruning.
- Genuine deletion: discovered only from full authoritative path or verified complete reconciliation, never from omission in filtered batch.
- Untracked new INSERT on valid 100..900 layer included; excluded unrelated blocks not read heavily.
- DALI_GROUP 300/400, BOARD_IN/BOARD_AV 700 and AV CABLE_OUTLET identity accepted with existing validator.
- Changes in handle/layer census between preview and Apply: refuse and request fresh scan; changed binding/project: refuse inside transaction.
- Changed attributes without handle/layer change: explicitly acknowledged residual risk, not asserted detected.
- Preview/apply interrupted or COM fails: no partial SQLite writes, fallback/retry safe.
- C6 incomplete/provenance flag adversarial tests remain rejecting.
- Run tests/cad_sync (single full run if environment permits), targeted cad_contract, compileall, Ruff check/format and diff-check. Compare any failures to recorded baseline. No real AutoCAD acceptance claim without live test.

## Execution and reporting

Verify branch HEAD equals the coordinator's issued SHA. Read this task and relevant current code, but avoid broad repo archaeology. Save an early intermediate implementation commit if limit risk arises. Report tested SHA, final pushed SHA, pass/fail counts, evidence of fast success vs fallback, exact residual risk and whether activation is ON/OFF. Checkpoint `NLP_255_C7F.md`; comment only on existing Issue #255. No C7d, no new Issue, no main merge/release. A safe PARTIAL is acceptable.
