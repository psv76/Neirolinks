# NLP #255 — C7c: AutoCAD scan integration, completeness-safe

task_id: NLP-255-C7C-SCAN-INTEGRATION
base_sha: 18babcb8861adecf74854e6dafdf89450856681a (accepted C7b)
branch: feature/nlp-255-c7c-scan-integration
status: READY / NOT STARTED

## Actual scan architecture — coordinator preflight

**This is important: the normal first scan does not necessarily use COM `_scan`.** In `src/nl_project_2/cad_sync/bridge.py` `read_observations` first tries AutoLISP `fingerprint` and `_batch_from_fingerprint`; cache hits reuse full cached observations and delta uses `scan_handles`; COM `scan` is a fallback. In `tools/autocad_sta_bridge.py` `_fingerprint_lisp` uses `ssget _X INSERT model` and for EACH insertion reads EffectiveName, InsertionPoint, DynamicBlock, attributes, definition — the expensive reads targeted by Issue #255. Thus simply exposing the C5 predicate in COM `scan` does NOT implement early prefilter in the dominant fingerprint path.

C5 `_scan(...,include_layer=...)` is intentionally opt-in and marks results `layer_filter_applied=true,scan_is_complete_for_reconciliation=false`. C6 `cad_sync/reconciliation_safety.py` rejects such results in `preview` and `apply`; this is deliberate. Never set this marker to true merely to bypass C6. `scan_handles` and #148 incremental caching must be preserved.

## Deliverable and safe approach

Implement one **functional, testable C7c increment** addressing scan-path integration and its safety, not a pretend production switch.

1. **Authoritative census vs heavy observation separation:** design an explicit complete physical INSERT handle/layer census, before expensive per-insertion metadata. Any new layer-filtered heavy payload remains **non-authoritative for absence**. A full authoritative `CadObservationBatch` sent to existing `preview/apply` must include all previously contract-owned tracked insertions or prove individually, with immutable handle/document identity evidence, that missing handles were truly deleted rather than simply moved to a non-work layer. If proof cannot be established, return a blocking, actionable **requires attention** status (or C6 error); NEVER fabricate deletion. Prefer a staged pure merge/reconciliation helper operating on synthetic census+batch to minimize integration risk.
2. **Early filter applies on both paths if enabled:** normal AutoLISP fingerprint and fallback COM `scan` must share the exact C1 numeric layer semantics, including DALI_GROUP 300/400 and rule that legacy layer support is separate. If modifying LISP to filter, read only handle+layer before expensive Name/coordinates/attributes/definition; implement explicit failures/complete census and escaping/case semantics, not a hand-coded invalid numeric parser. Avoid claiming that a C5 COM-only opt-in improves normal scan. If this cannot be safely implemented within the C7c scope/time budget, keep normal path unfiltered and deliver/test pure census safety and measured coverage first, status PARTIAL, without activating.
3. **No unsafe production activation:** the existing `read_observations -> DwgSyncService.preview/apply` path remains full-authoritative by default. Do not activate filtered snapshots in protocol or Update until completeness evidence can be verified end-to-end; never introduce a user-selectable bypass of C6. A moved block that still exists but is now on excluded layer must be **not classified as `MISSING_DWG_INSERTION`**. If the current data contract cannot express this safely, stop short of runtime wiring and preserve working default.
4. Maintain #148 fingerprint cache-hit / delta / changed-handle flow, document identity and update atomicity. Avoid multiplying full DWG scans. Fail closed on COM/LISP errors, duplicate handles, stale census, drift between fingerprint and heavy observations. Ensure generic unrelated CAD blocks, legitimate `DALI_GROUP`, invalid malformed layers are covered.
5. Do not change CAD validator/C7a machine JSON/catalog, C5/C6 meaning, database migrations, installation or live DWG. Provide a source-backed checkpoint explicitly distinguishing **implemented scan speedup**, **staged safety**, and **still-disabled modes**.

## Suggested bounded coding sequence (one Codex session; checkpoint early)

- Read the two real paths `src/nl_project_2/cad_sync/bridge.py` and `tools/autocad_sta_bridge.py`, and tests `tests/cad_sync/test_bridge_client.py`, `test_sta_layer_prefilter.py`, `test_sta_bridge.py`. Do not resurvey all project history.
- Build pure, side-effect-free census/observation matching helper as needed; retain absent-handle reason as `unknown` without an explicit unfiltered deletion proof. Test moved-off-layer, true deletion, foreign block, duplicate handles, stale fingerprint. Ensure C6 still blocks partials.
- Only wire early filtering into an actual scanner path if these tests establish the authority boundary without relying on skipped-count alone. Otherwise mark PARTIAL and leave production path unchanged. **A safe PARTIAL with meaningful tested code is better than fabricated PASSED.**

## Allowed paths

- `Systems/NLP/src/nl_project_2/cad_sync/bridge.py`
- `Systems/NLP/tools/autocad_sta_bridge.py`
- `Systems/NLP/src/nl_project_2/cad_sync/scan_layer_safety.py` (new pure helper, only if needed)
- `Systems/NLP/tests/cad_sync/test_bridge_client.py`, `test_sta_layer_prefilter.py`, `test_sta_bridge.py`
- `Systems/NLP/tests/cad_sync/test_scan_layer_safety.py` (new)
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C7C.md` (new)
If an indispensable production change requires `service.py` or C6 safety gate changes, do NOT quietly add them: stop at a staged, safe implementation and detail separate integration acceptance. Other files forbidden. C7d not begun.

## Checks

Run modified/focused tests and current sync regression tests including `test_sync_service.py`, `test_p0003_reconciliation.py` where available; C5/C6 tests explicitly included. Windows named-pipe mocked bridge tests may require unsandboxed local execution. Compileall, Ruff check + format, git diff --check. For performance claims, present real call-count assertions (no heavy properties on excluded layers), not invented time savings. Distinguish legacy baseline failures from introduced failures. No real AutoCAD/DB changes, no locked Python 3.13 or live acceptance claims.

## Checkpoint and stop criteria

Start only on exact brief-head SHA posted to #255. Commit intermediate work early; on exhaustion persist code/tests/checkpoint rather than lose it. Record start/tested/final SHA, changed files, exact PASS/FAIL, skipped paths, assertion about moved-off-layer and true deletion, integration gaps, next_action. Issue #255 only; no new Issue, no main merge, no C7d or release. #255 remains OPEN.
