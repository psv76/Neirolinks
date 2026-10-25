# NLP-255-C7C-SCAN-INTEGRATION — 2026-10-25

status: PARTIAL
branch: feature/nlp-255-c7c-scan-integration
base_sha: 18babcb8861adecf74854e6dafdf89450856681a (accepted C7b)
start_sha: ee1d1e2766b7d3b966b6c85b95a373608b7444c5 (verified exact, clean checkout)
intermediate_sha: e88eb1c63c826549c6de6ad9b1792d7496dfae11
tested_sha: 3d8f93312d70d67e4293e536e991583a44626ee8
final_head_sha: reported in Issue #255 after this documentation-only checkpoint commit.

## Implemented versus disabled

Implemented: pure, side-effect-free census/observation assessment in `src/nl_project_2/cad_sync/scan_layer_safety.py:79`. Frozen evidence DTOs describe complete unfiltered INSERT handle/layer census before and after a heavy read, document identity, fresh read ID, revision and explicit individual absence proof. These are declared evidence, not independently verified live attestations. No current scanner constructs them.

The helper uses the exact C1 parser. Heavy-read plan includes every numeric-layer insertion and every surviving tracked insertion, regardless of its current layer. It does not infer contract ownership from layer or block name. Legacy eligibility is separate; tracked legacy inserts cannot disappear merely because numeric selection excludes them. A tracked handle present on ARCH/legacy/malformed layer is present-excluded and requires heavy observation when absent from the payload; it is never classified as missing from DWG. Missing handles remain unknown without an explicit successful unfiltered absence check bound to the same document/read/revision. Lookup failure is not absence proof.

Duplicate/noncanonical handles, stale reads, incomplete/filtered census, scan errors, revision drift, handle/layer mismatch and contradictory/duplicate absence proofs produce REQUIRES_ATTENTION. Complete synthetic evidence returns STAGED_ONLY, not permission to synchronize. The helper does not merge cached observations, create a CadObservationBatch, change source metadata, emit MISSING_DWG_INSERTION or bypass C6. Preview and apply continue rejecting the unchanged partial metadata, verified before any DB access.

Implemented scan speedup: **none in C7C**. No time-saving claim. Existing C5 mocked call-count tests still verify excluded entities read only ObjectName/Layer and no heavy properties/definitions, in one ModelSpace traversal; that opt-in remains internal and disabled in the protocol. It is not evidence of normal-path acceleration.

Still disabled: new filtered fingerprint/COM mode, runtime census production, authority promotion, filtered Update, new reconciliation wiring. Existing production default and #148 remain unchanged.

## Source-backed integration limitation

- `src/nl_project_2/cad_sync/bridge.py:183` read_observations first uses fingerprint; cold read can deserialize its heavy signatures; cache hit reuses complete observations. Changed handles use scan_handles at line 227 and verify fingerprint again. COM scan remains fallback.
- `tools/autocad_sta_bridge.py:240` _fingerprint_lisp selects every model INSERT (line 267), then reads EffectiveName (line 275), InsertionPoint, dynamic state, attributes and definition. It has no lightweight complete census/evidence envelope or C1 filter protocol.
- `_scan` at line 166 retains internal C5 predicate, partial flags and full default. `scan_handles` is unfiltered. Neither path produces the new read/revision/absence witnesses.
- C6 requires an authoritative full batch. The staged DTO's matching revision strings are not proof of freshness in AutoCAD; DBMOD is explicitly not accepted as a revision guarantee. Merely setting complete=true or clearing partial flags would be unsafe.

Therefore this bounded increment stops before scanner wiring. No hand-written LISP numeric parser, skipped-count authority heuristic, fabricated completeness flag or user-selectable gate bypass was introduced.

## Changed paths

Only these four allowed paths, relative to Systems/NLP:

- src/nl_project_2/cad_sync/scan_layer_safety.py (new pure helper).
- tests/cad_sync/test_scan_layer_safety.py (new, 60 tests).
- tests/cad_sync/test_bridge_client.py (13 new regressions; existing assertions retained).
- docs/engineering/checkpoints/NLP_255_C7C.md.

No changes to bridge runtime, STA scanner, validator, catalog, machine contract, C5/C6, service, schema/migrations or deployment. No actual AutoCAD connection, real DWG/SQLite mutation, new issue, main merge or C7d. Regression fixtures use temporary test databases only.

## Verification

Windows; existing .venv Python 3.14.3, pytest 9.1.1, Ruff 0.15.22. PYTHONPATH=src;. and TEMP/TMP=.venv/tmp. No locked Python 3.13 or live acceptance claim.

From Systems/NLP:

`python -m pytest -q --tb=short tests/cad_sync/test_scan_layer_safety.py tests/cad_sync/test_bridge_client.py tests/cad_sync/test_sta_layer_prefilter.py tests/cad_sync/test_sta_bridge.py tests/cad_sync/test_reconciliation_scan_completeness.py tests/cad_sync/test_sync_service.py tests/cad_sync/test_p0003_reconciliation.py`

Final result on tested_sha: **265 passed, 0 failed, 0 skipped**, exit 0 (43.35 s), with local execution outside sandbox for mocked named pipes. Includes explicit C5/C6 coverage, current sync service and p0003 regression tests. Both normal fingerprint and COM fallback retain unrelated blocks, numeric DALI_GROUP, legacy and malformed layers. A move from 100_Power to ARCH remains an insertion in the #148 DELTA result and uses scan_handles without an extra full scan. Existing cache-hit/change/stability tests remain passing.

Earlier sandbox run before 8 additional defensive tests: 256 passed / 1 failed; existing named-pipe progress timeout test did not reach pipe connection within its 0.4 s deadline. All 22 bridge-client tests passed unchanged outside sandbox (2.12 s), then the entire final set passed. No production workaround or assertion relaxation. Initial new helper test mistakenly called nonexistent service.apply; corrected to existing apply_dwg_to_project before the intermediate commit. No legacy test failures suppressed; full cad_contract not rerun because C7C does not modify its code or tests.

- `python -m compileall -q src/nl_project_2/cad_sync tools/autocad_sta_bridge.py`: PASS, exit 0.
- `python -m ruff check src/nl_project_2/cad_sync/scan_layer_safety.py tests/cad_sync/test_scan_layer_safety.py tests/cad_sync/test_bridge_client.py`: PASS, exit 0.
- `python -m ruff format --check` same three files: PASS, 3 already formatted, exit 0.
- `git diff ee1d1e2766b7d3b966b6c85b95a373608b7444c5 --check`: PASS, exit 0.

## Exact next operation

Push checkpoint and implementation commits to origin/feature/nlp-255-c7c-scan-integration; report final_head_sha and PARTIAL in existing Issue #255. Then review this staged increment and explicitly approve a continuation of C7C to define/implement a complete lightweight INSERT census and fresh document/revision/absence evidence producer for BOTH AutoLISP and COM. Before activation, prove C1 parity and LISP escaping/error handling, bind heavy payloads to the same stable read, read every existing tracked handle even on excluded layers, handle unknown absence as requires-attention, and verify full snapshot authority end-to-end without changing C6 semantics or #148 atomicity. Any necessary service.py change requires separately expanded scope. Keep production full/unfiltered until then. Do not begin C7d; Issue #255 stays OPEN.


## Resumed C7C after explicit request to finish

The prior PARTIAL describes the first saved increment. Work now adds a separate diagnostic read_layer_filtered_observations API and scan_working_layers transport, shared lightweight COM census, selected-only AutoLISP fingerprints and strict COM fallback. Default read_observations/Update remains unfiltered; no authority promotion. Both paths keep tracked insertions even on excluded layers. New synthetic call-count/error/transport tests pass; final combined checks pending. Final results below will supersede the first increment's no-speedup/no-producer statements.
