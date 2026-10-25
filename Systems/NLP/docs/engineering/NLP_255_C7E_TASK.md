# NLP #255 — C7e: safe production filtered synchronization authority

task_id: NLP-255-C7E-FILTERED-SYNC-AUTHORITY
base_sha: cbf557cc57c7824622e8b5ae9e5b94f24fdb3e22 (coordinator-reviewed C7c)
branch: feature/nlp-255-c7e-filtered-sync-authority
status: READY / NOT STARTED

## Outcome, not a declaration of completion

Convert the working C7c diagnostic early layer read into a genuinely safe, user-facing full synchronization pathway ONLY if all authority rules can be demonstrated by focused end-to-end tests. Otherwise preserve production full-scan behavior, commit a tested partial increment and report PARTIAL with concrete remaining proof, without bypassing C6.

## Verified current implementation

- `src/nl_project_2/cad_sync/bridge.py`: `read_layer_filtered_observations` returns `LayerFilteredRead`, brackets heavy reads with before/after complete lightweight handle/layer census, retains tracked off-layer handles, reports absent tracked as unknown. The normal `read_observations` uses full AutoLISP fingerprint, #148 cache/delta and fallback COM; it remains unfiltered.
- `tools/autocad_sta_bridge.py`: `scan_working_layers` performs selected-handle AutoLISP fingerprint and strict COM fallback. Marks `layer_filter_applied=true`, `scan_is_complete_for_reconciliation=false` categorically.
- `src/nl_project_2/cad_sync/reconciliation_safety.py`: C6 currently refuses non-authoritative batches. `src/nl_project_2/cad_sync/service.py` checks in BOTH `preview` and `apply_dwg_to_project`.
- `src/nl_project_2/cad_sync/scan_layer_safety.py`: pure evidence helper, but it does NOT by itself supply durable deletion proof; census sampling is not proof of atomic revision. DBMOD is not a revision token. Never turn a false completeness marker true merely because before/after census match.
- `src/nl_project_2/cad_contract/layer_names.py`: one canonical layer parser; keep this source of truth.

## Mandatory engineering invariants

1. An excluded/untracked layer may contain non-contract blocks. Tracked handles moved off working layers **must remain visible** and must NOT become `MISSING_DWG_INSERTION`.
2. Genuine removal of a tracked insertion may be reported as missing ONLY from an authoritative full scan or from a separately verified explicit absence witness with stable document identity and read transaction boundaries. HandleToObject failure, two equal census samples, zero skipped, or DBMOD alone do not prove durable deletion.
3. A filtered scan must not cause removal of cable endpoints, AV identities, conduit topology, bus connections or other absence-dependent projections while skipped/unproven insertions exist.
4. Full unfiltered scans remain supported and compatible with existing #148 fingerprint/delta cache behavior. No partial read may silently poison its cache.
5. End-to-end `preview -> apply` must revalidate authority at point of write. Do not merely test the pure helper. No user-facing unsafe override.
6. Performance must be demonstrated as reduced expensive property reads on unrelated excluded blocks, including both AutoLISP and COM paths, without multiple full heavyweight enumerations. Avoid invented timing claims.
7. Errors/races, changed layers, duplicate handles, stale document identity/read ID, inconsistent census, failed LISP+COM, and missing/deleted tracked handles fail closed. Preserve normal behavior on complete legacy/full scans.
8. Preserve C7b numeric 100..900 group validator, BOARD_IN/BOARD_AV on 700, DALI_GROUP on 300/400, ordinary cable and HVAC behavior.

## Execution strategy

Perform a short repository-specific dependency review FIRST, then implement only what is supported by current architecture. Compare the effective projection algorithm in `service.py` (MISSING_DWG_INSERTION and topology absence changes) with completeness gate and `LayerFilteredRead`. Do not call the diagnostic path production-ready without complete evidence.

Preferred **safe functional outcome**: maintain a complete authoritative observation set for all stored tracked handles, retain excluded tracked inserts, and establish independent trustworthy absence authority for tracked handles before marking missing. If durable absence authority cannot be guaranteed from live COM/census semantics, choose the safer design: use an authoritative unfiltered confirmation **only when tracked handle disappearance or other absence-dependent changes are suspected**, preserving the fast path for the normal unchanged/present case. The full confirmation must pass the existing unchanged C6 authority checks, and preview/apply must not rely on stale confirmation if the DWG has changed. If the existing application API cannot maintain transaction-safe evidence across preview/apply, do NOT claim production activation; report precise limitation.

Do not infer database tracked handles from layer-filtered batch; load them from canonical project/binding database context, preserving cross-project/document identity protections. Prevent switching to the wrong active project. Do not auto-delete devices. Do not change any client DWG or productive SQLite.

## Allowed code / tests / checkpoint paths

- `Systems/NLP/src/nl_project_2/cad_sync/bridge.py`
- `Systems/NLP/src/nl_project_2/cad_sync/scan_layer_safety.py`
- `Systems/NLP/src/nl_project_2/cad_sync/reconciliation_safety.py`
- `Systems/NLP/src/nl_project_2/cad_sync/service.py`
- `Systems/NLP/tools/autocad_sta_bridge.py`
- `Systems/NLP/tests/cad_sync/test_filtered_sync_authority.py` (new)
- `Systems/NLP/tests/cad_sync/test_scan_layer_safety.py`, `test_bridge_client.py`, `test_reconciliation_scan_completeness.py`, `test_sync_service.py`, `test_sta_layer_prefilter.py` (only where needed)
- `Systems/NLP/docs/engineering/checkpoints/NLP_255_C7E.md` (new)

No changes to machine CAD contract, C1-C4 parsers, catalog, validator, schema/migrations, application UI unless separately approved, deployment, main, real DWG/SQLite, other Issues. If production activation requires a file outside this list, stop with specific evidence and an additional scope request, rather than creating a bypass.

## Tests and acceptance

Run targeted new integration tests plus C5/C6/C7c, #148, full cad_sync fixture suites (as feasible), compileall, Ruff check/format and git diff --check. Tests must exercise real service preview+apply with disposable SQLite, not only pure helpers:
- present tracked insertion on excluded layer: still present, no false missing/topology removal;
- truly deleted tracked insertion: requires authoritative confirmation; no unconfirmed missing changes;
- previously untracked foreign block on excluded layer: no costly read, no accidental deletion;
- full working layer case: accepted numeric observations/AV/DALI without hidden regressions;
- tampered partial metadata/proposal: C6 refuses before DB writes;
- changed DWG or project binding after preview: apply must fail or safely reconfirm; no stale evidence;
- no regression of full scan and incremental cache paths.

Document exactly what tests were run and results. Existing 11 cad_contract baseline failures are known, not automatically fixed by this task; do not weaken tests. Claim no locked Python 3.13 or live AutoCAD acceptance unless actually executed.

## Commit and completion gate

Verify branch HEAD against SHA recorded by coordinator in Issue #255. Commit early to protect work from limit interruption, then checkpoint `NLP_255_C7E.md` with start/tested/final SHA, decisions, changed paths, precise tests, performance evidence, and one next_action. If proof is still lacking, **PARTIAL is correct**. DO NOT flip `scan_is_complete_for_reconciliation=false` to true without independent, verified authority. Do not open a new Issue, begin C7d, merge main, or release NLP 3.1.

Coordinator independent acceptance is mandatory. This is likely the last **feature implementation** stage if PASSED, but integration/regression/release review and real Windows/AutoCAD acceptance remain separate gates.
