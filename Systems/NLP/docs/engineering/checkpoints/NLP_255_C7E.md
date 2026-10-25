# NLP-255-C7E-FILTERED-SYNC-AUTHORITY — 2026-10-25

status: PARTIAL — safe project-bound review and write-time binding checks implemented; production filtered synchronization remains disabled.
branch: feature/nlp-255-c7e-filtered-sync-authority
base_sha: cbf557cc57c7824622e8b5ae9e5b94f24fdb3e22
start_sha: 93d69513b3103dad6525559ca6739f14f21e4def (verified exact and clean)
intermediate_sha: 2f32abfb556691a8b46e2da1b4b0b04b85b38125
tested_sha: 1da2d41f6c13f612187944244192f207bf12863b
final_head_sha: reported in Issue #255 after this documentation-only checkpoint commit.

## Implemented result

- service.py `_filtered_sync_context` loads the requested project's revision and confirmed DWG binding. Tracked handles come from canonical active field_device rows scoped by project AND binding, supplemented by logical observations from scans referenced by this binding's accepted baselines. It never infers stored owners from the filtered batch or treats historical foreign furniture observations as owners.
- `review_filtered_sync` invokes C7c's real diagnostic adapter with those DB-derived handles and explicit document identity, then rereads project/binding/owner context. Changes during the read fail closed. Wrong document or attempted authority promotion by the adapter is rejected. The result is a frozen FilteredSyncReview, not an applicable ScanProposal; status always REQUIRES_ATTENTION.
- C6 retains its original full/legacy acceptance rules and now additionally rejects known FILTERED_FINGERPRINT / FILTERED_COM_FALLBACK provenance even if completeness flags are removed or flipped. No false completeness flag is set. This is declared-metadata validation, not a cryptographic attestation against arbitrary fabricated legacy batches.
- `_ensure_binding` now revalidates confirmed binding ID, project, document UUID and normalized path inside the apply SQLite UnitOfWork before persisting a scan or projections. Revoked/rebound/cross-project bindings fail. A newly created binding after an unbound preview requires rescan instead of implicitly attaching the old proposal.
- New integration tests use real DwgSyncService preview/apply and disposable SQLite. They compare devices, cables, points/endpoints/segments, conduits, buses, AV profiles, scans and baselines before/after blocked operations. No partial batch reaches a projection update or generates an accepted missing proposal.

## Safety evidence and limitations

A tracked insertion moved to ARCH remains in the C7c read and in DB-derived ownership; partial preview/apply is rejected and existing topology is unchanged. Independent FULL fixture preview reports invalid placement, not MISSING_DWG_INSERTION. A truly absent tracked handle stays unknown in filtered review; only independent authoritative full-scan fixture yields MISSING_DWG_INSERTION. That missing change is not applicable as an automatic device deletion.

Wrong project/unbound document is rejected before CAD read. Project revision, binding metadata or owner-set changes during read reject the result. Apply rechecks binding in its write transaction. A diagnostic batch captured before subsequent DWG changes remains non-authoritative and cannot apply; it is not silently reconfirmed using stale census. Existing full snapshot behavior remains supported. Full numeric SOCKET/BOARD_IN-BOARD_AV/CABLE_OUTLET/DALI_GROUP preview and apply pass with a disposable DB; C7b validator coverage passes unchanged.

These checks DO NOT establish new live DWG transaction authority. No production filtered mode was enabled in scan_active or UI. Full confirmation is not automatically reused as a permanent receipt, and no new authoritative filtered proposal is exposed. The existing full-scan freshness model is not represented as newly atomic by this work.

## Precise architectural gap / source evidence

- service.py preview calculates MISSING_DWG_INSERTION as well as absence-dependent projection changes. `_repair_stale_topology_endpoints` and `_prune_stale_snapshot_points` can delete points, endpoints and segments from an accepted snapshot. Presence of all known handles alone is not enough to certify all projection inputs.
- bridge.py `_call` starts a short-lived STA process per command. C7c census samples establish handle/layer presence before and after selected reads, not a stable attribute revision held through a later SQLite commit. There is no document read transaction/lease or commit fence surviving preview -> apply.
- DBMOD, equal census maps, zero skipped, request read_id or an extra full confirmation sample cannot by themselves prevent the DWG changing after that sample and before write. A new full reread would detect some stale previews but not close this race; it is not implemented as a fake guarantee.
- presentation/object_workspace.py calls scan_active in a background worker and later apply_dwg_to_project; it carries a proposal, not a live CAD transaction token. UI/workflow changes are outside the C7E allowed paths unless separately approved. Production default therefore remains full AutoLISP fingerprint / #148 cache+delta / COM fallback.

Missing mechanism: an independently verified stable DWG read/commit boundary, bound to document identity and project/binding/revision, with point-of-write validation, explicit absence confirmation, and failure/rollback semantics across CAD and SQLite. Coordinator approval and tests for this mechanism are required before filtered activation. C6 must not be weakened to compensate for its absence.

## Performance

C7c's existing reduced-heavy-read path is reused unchanged. C5/C7c tests verify shared C1 selection for selected AutoLISP and COM fallback, two lightweight census passes, zero heavy property reads on unrelated excluded blocks and inclusion of tracked off-layer inserts. New service test ensures unrelated F1 is not submitted as a DB tracked handle. No timing improvement is claimed, and production Update is not claimed accelerated. No live AutoLISP/COM or real DWG/SQLite operations were performed.

## Changed allowed files

Relative to Systems/NLP:

- src/nl_project_2/cad_sync/service.py
- src/nl_project_2/cad_sync/scan_layer_safety.py
- src/nl_project_2/cad_sync/reconciliation_safety.py
- tests/cad_sync/test_filtered_sync_authority.py (new, 19 tests)
- docs/engineering/checkpoints/NLP_255_C7E.md

No changes to catalog/validator/machine contract/parsers, schema/migrations, UI, bridge scanner, main, deployment or real project data. No new Issues, C7d, merge or release.

## Exact verification

Windows, existing .venv Python 3.14.3 / pytest 9.1.1 / Ruff 0.15.22; PYTHONPATH=src;. and TEMP/TMP=.venv/tmp. Mocked named-pipe tests outside sandbox; Qt tests offscreen. Installed the repository-pinned pytest-qt==4.5.0 into ignored .venv to supply qtbot (and bootstrapped local pip). No tracked dependency files changed. No locked Python 3.13/live acceptance claim.

1. `python -m pytest -q --tb=short tests/cad_sync` at intermediate_sha: **555 passed, 0 failed, 4 setup errors**, exit 1, 263.58 s. All four errors were missing qtbot, not assertion/regression failures.
2. After installing pinned pytest-qt, reran exactly the four errored node IDs with QT_QPA_PLATFORM=offscreen: **4 passed, 0 failed**, exit 0, 4.73 s:
   - test_issue140_room_canonicalization.py::test_preview_presents_canonicalization_as_explicit_selectable_room_link
   - test_issue142_working_journal.py::test_real_lines_widget_edits_exact_segment_and_preserves_selection
   - test_issue142_working_journal.py::test_object_breakdown_is_available_from_lines
   - test_issue142_working_journal.py::test_conduit_tree_exposes_exact_segment_then_line_and_product_columns
3. Final focused command at tested_sha:
   `python -m pytest -q --tb=short tests/cad_sync/test_filtered_sync_authority.py tests/cad_sync/test_reconciliation_scan_completeness.py tests/cad_sync/test_scan_layer_safety.py tests/cad_sync/test_sta_layer_prefilter.py tests/cad_sync/test_bridge_client.py`
   **259 passed, 0 failed**, exit 0, 31.65 s. Includes final 19 C7E tests. The final commit added three tests and corrected a comment after full-suite collection; no production behavior changed after that full-suite run. Thus all **562 current cad_sync cases** have passing coverage across these runs, not a claimed single 562-pass invocation. No skipped/xfail suppression.
4. C7b target command (test_validator_numeric_layers.py, test_dali_layer_rules.py, test_numeric_contract_mapping.py, test_validator_av.py, test_issue237_track_dali_integration.py under tests/cad_contract): **208 passed, 0 failed**, exit 0. Known eleven failures of the full cad_contract suite are not claimed fixed; that unchanged full suite was not repeated.
5. `python -m compileall -q src/nl_project_2/cad_sync tools/autocad_sta_bridge.py`: PASS, exit 0.
6. `python -m ruff check` and `python -m ruff format --check` for all four changed Python files: PASS, exit 0; 4 already formatted.
7. `git diff 93d69513b3103dad6525559ca6739f14f21e4def --check`: PASS, exit 0.

During development the new AV/full fixture initially lacked a valid MOUNT_WAY; corrected fixture to the existing valid ceiling route, without relaxing product validation. Final numeric full preview/apply passes.

## One next_action

After pushing commits and reporting final_head_sha in existing Issue #255, coordinator reviews this PARTIAL and approves a concrete stable-DWG read/commit authority design (including any required UI/workflow scope) before any production filtered-sync activation. Until then retain the existing full path, C6 blocking and #148 behavior; do not start release or merge main.
