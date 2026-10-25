# NLP-255-C7C-SCAN-INTEGRATION — resumed completion, 2026-10-25

status: PARTIAL — both scan paths implemented as explicit diagnostic reads; filtered synchronization intentionally disabled.
branch: feature/nlp-255-c7c-scan-integration
base_sha: 18babcb8861adecf74854e6dafdf89450856681a
start_sha: ee1d1e2766b7d3b966b6c85b95a373608b7444c5
first_partial_final_sha: 089dfc938d6b8f0502b3bda3218f37a791de910a
intermediate_sha: e48221d9146729ad27748c902373bd58efea1213
tested_sha: e48221d9146729ad27748c902373bd58efea1213
final_head_sha: recorded in Issue #255 after this documentation-only commit.

This checkpoint supersedes the first pure-helper-only result. The user explicitly requested continuation; the resumed work implements the scanner producers and client path below.

## Implemented scan integration

`AutoCadBridgeClient.read_layer_filtered_observations(request, tracked_handles=...)` in bridge.py is a separate explicit diagnostic API, not called by normal read_observations or Update. It invokes the new `scan_working_layers` operation in autocad_sta_bridge.py.

`_scan_working_layers` performs:

1. Complete unfiltered lightweight COM census of model-space block references: ObjectName, Handle and Layer only, no names, coordinates, attributes, dynamic state or definitions. Canonical uppercase hex handles are checked and duplicates/errors rejected. Explicit document identity is checked around enumeration.
2. Selection in Python using the exact accepted C1 parser. Every surviving tracked handle is added regardless of layer, so moved-off-layer and legacy tracked insertions remain present. Numeric DALI_GROUP 300/400 participates without a special suffix whitelist. Unrelated blocks are not assumed to be contract-owned.
3. AutoLISP fingerprint of ONLY selected handles. Generated LISP resolves the canonical handle list, verifies model INSERT membership and expected document identity before heavy reads, escapes document/path strings and fails on selected definition errors. No independent LISP numeric parser exists. Default fingerprint still uses the full model INSERT ssget.
4. On LISP failure, discard that entire result and read the SAME selected handles through strict COM fallback. Strict definition/dynamic/attribute errors fail closed; default scan_handles behavior is unchanged.
5. Repeat the lightweight census and reject handle/layer/document drift. Return observations/signatures plus before/after census and explicit non-authoritative metadata. No full heavy scan is repeated just to enumerate excluded blocks.

Client checks request read ID, document identity, matching census maps, selected/tracked handle sets, heavy observation ownership/layer and partial flags. Duplicate, missing or stale/foreign transport evidence raises BridgeError. It returns a frozen LayerFilteredRead with present_excluded_handles and absent_unknown_handles. It never reads/writes the #148 cache, never promotes metadata, and has no UI switch to bypass C6.

## Safety boundary and remaining limitation

The shared census proves presence at its samples, not an atomic attribute revision or durable deletion. An absent tracked handle stays UNKNOWN, not MISSING_DWG_INSERTION. The result ALWAYS has layer_filter_applied=true and scan_is_complete_for_reconciliation=false, even if the excluded count is zero. Its actionable status is REQUIRES_ATTENTION: obtain a full unfiltered read before preview/apply. Tests verify both preview and apply reject before DB access.

The pure scan_layer_safety helper remains staged for evidence assessment: it requires fresh document/read/revision context and an explicit successful individual unfiltered absence proof before classifying synthetic true deletion. No scanner fabricates that proof, a revision witness, or a complete snapshot. DBMOD is not treated as a revision guarantee.

Production read_observations remains full/unfiltered. Source: bridge.py read_observations still starts with fingerprint, uses _batch_from_fingerprint for cold reads, cached full observations on cache hit, scan_handles for changes and full scan fallback. Existing #148 tests and moved 100_Power -> ARCH delta case pass. No filtered batch is wired to DwgSyncService.

Therefore overall C7C remains PARTIAL for full production reconciliation integration, as required by the task's safety stop condition. Enabling filtered preview/apply would require separately approved authority semantics, actual fresh/atomic evidence and potentially service.py/C6 scope expansion; those files are explicitly forbidden in this task. No false completeness flag was used to force completion.

## Performance evidence and limits

Implemented: early reduction of heavy reads on BOTH opt-in paths. In mocked selected-LISP and actual mocked COM fallback tests, excluded blocks receive exactly [ObjectName, Handle, Layer] twice (two lightweight census passes), with zero EffectiveName/InsertionPoint/GetAttributes/definition reads. Selected numeric plus tracked-excluded blocks receive one heavy read; definition lookup is cached. Generated LISP source selects handles before its heavy loop and contains no full ssget in selected mode. Default LISP still has full ssget. These are call-count/source/transport tests, NOT live AutoLISP execution or elapsed-time speedup measurements. No claim of faster production Update, locked Python 3.13 or live AutoCAD acceptance.

## Changed allowed paths

Relative to Systems/NLP:

- src/nl_project_2/cad_sync/bridge.py
- src/nl_project_2/cad_sync/scan_layer_safety.py
- tools/autocad_sta_bridge.py
- tests/cad_sync/test_bridge_client.py
- tests/cad_sync/test_sta_layer_prefilter.py
- tests/cad_sync/test_scan_layer_safety.py
- docs/engineering/checkpoints/NLP_255_C7C.md

No validator/catalog/machine JSON, C1-C6 implementation, service.py, migrations, deployment, main or actual DWG/SQLite changes. No new Issue, merge or C7d. Test databases are temporary fixtures only.

## Final verification on tested_sha

Windows, .venv Python 3.14.3 / pytest 9.1.1 / Ruff 0.15.22. PYTHONPATH=src;. and TEMP/TMP=.venv/tmp. Named-pipe tests executed outside sandbox, with no AutoCAD connection.

`python -m pytest -q --tb=short tests/cad_sync/test_scan_layer_safety.py tests/cad_sync/test_bridge_client.py tests/cad_sync/test_sta_layer_prefilter.py tests/cad_sync/test_sta_bridge.py tests/cad_sync/test_reconciliation_scan_completeness.py tests/cad_sync/test_sync_service.py tests/cad_sync/test_p0003_reconciliation.py`

**287 passed, 0 failed, 0 skipped**, exit 0 (41.52 s).

Includes new census/transport tests, C5 call counts, C6 preview/apply gate, sync service and p0003 reconciliation. Checks both paths, tracked off-layer retention, true deletion remaining unknown without explicit proof, legitimate numeric DALI, generic foreign blocks, malformed layers, duplicate handles, stale read IDs, census/layer/document drift, COM/LISP error fallback, strict metadata failure, LISP escaping and unchanged cache/delta behavior.

- `python -m compileall -q src/nl_project_2/cad_sync tools/autocad_sta_bridge.py`: PASS, exit 0.
- `python -m ruff check` for all six changed Python files: PASS, exit 0.
- `python -m ruff format --check` same files: PASS, 6 already formatted, exit 0.
- `git diff ee1d1e2766b7d3b966b6c85b95a373608b7444c5 --check`: PASS, exit 0.

Prior first-increment final set: 265 passed. Its initial sandbox run had 256 passed / 1 existing named-pipe startup timeout; unchanged tests passed outside sandbox. No skip/xfail or relaxed assertions. Full cad_contract is unchanged and not rerun; its known 11 baseline failures are not claimed fixed.

## Exact next operation

Push the resumed implementation and checkpoint commits; update existing Issue #255 with final_head_sha, 287/0 results and PARTIAL limitation. Then independent review of start_sha..final_head_sha, especially the new diagnostic protocol and proof that partial flags cannot be lost. For full activation, separately approve a C7C continuation defining verified stable read/deletion evidence and its integration with reconciliation authority; expand allowed scope only if service.py/C6 changes are necessary. Until acceptance, keep filtered Update disabled and use the existing full unfiltered path. Do not start C7d; #255 remains OPEN.
