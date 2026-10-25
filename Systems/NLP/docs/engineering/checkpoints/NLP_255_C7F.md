# NLP-255-C7F-PRAGMATIC-FILTERED-SYNC — 2026-10-26

status: PARTIAL — application opt-in, explicit full fallback and lightweight Apply checks implemented; applicable subset/fast projection not activated.
branch: feature/nlp-255-c7f-pragmatic-filtered-sync
base_sha: cd511d7d9b8ed588f17a1797aa1f4f189d37462f
start_sha: 916188e2b05eb7d10a08d05d87afdfc42105067f (exact, clean start verified)
intermediate_sha / tested_sha: 9227eb43ea9f2d5c4cc57d67f22ec90034d92100
final_head_sha: recorded in Issue #255 after this documentation-only commit.

## Approved simplification implemented

The previous demand for an atomic DWG/SQLite lease is NOT a C7F blocker. No AutoCAD edit lock, long-lived COM process/transaction, snapshot clone, cryptographic attestation or second heavyweight attribute read was introduced for freshness. A session-local preview ID only associates a full proposal with its project/binding/census context; it does not prove atomicity.

Accepted residual risk: attribute/coordinate-only edits after the initial scan are not detected by Handle+Layer; changes can occur between the last lightweight check and SQLite commit. The new test intentionally changes coordinates while keeping census identical and verifies that Apply uses the scanned facts without any heavy reread. This is the approved pragmatic behavior, not a claim that all DWG edits are detected.

## Actual application workflow

- ObjectWorkspace includes an explicit unchecked-by-default `dwgFilteredSyncOptIn` checkbox. Default full scan/#148 behavior remains available and unchanged.
- With opt-in, real scan_active calls the C7E project/binding-bound C7c candidate read; stored tracked handles are loaded from SQLite before any filtered read. Wrong/unconfirmed context or a failed candidate read requires explicit full retry.
- A layer-selected subset cannot currently certify excluded untracked INSERT ownership and projection completeness. scan_active raises FullScanRequired rather than passing it to preview or changing C6 flags. This remains true when zero objects were skipped: a zero count is not promoted into authority.
- UI presents a clear Yes/No full-scan retry question, default No. Cancel makes no writes. No silent retry applies different facts. Yes calls the ordinary full read, creates a full proposal and opens the real DwgSyncPreviewDialog with explicit direction/selection/Apply.
- The application remembers the project during identity/read and rechecks it before preview and after the modal Apply dialog. A switched project cannot receive the old proposal.
- Errors/stale census in the new Apply path offer a new full scan/preview, not silent continuation. After success the UI asks for a new scan before further changes.

Source entry points: bridge.py read_insert_census; service.py scan_active, _binding_state, _check_pragmatic_census; object_workspace.py _offer_full_scan, _review_pragmatic_proposal; autocad_sta_bridge.py insert_census operation. Tests exercise these UI methods and real dialogs, not only a standalone diagnostic API.

## Lightweight freshness and write boundary

New bridge command `insert_census` enumerates model INSERTs through the existing _insert_census: ObjectName, Handle, Layer only. No Name/EffectiveName, attributes, insertion coordinates, dynamic flags or block definitions. It verifies expected document identity and request read ID, completeness/unfiltered status and canonical handles/layer values. Its complete flag refers to the HANDLE/LAYER census, not a full heavy observation snapshot.

The explicit full fallback obtains one normal authoritative read, then verifies its entire Handle+Layer set against a fresh census and its project/binding state against the state before read. Session-local full-preview context is attached without changing the original full batch/cache or partial flags. Before Apply and explicit write-back, a new lightweight census must match. Missing/new/moved handles, read failure, stale/foreign context or expired preview reject with rescan instructions.

Immediately before DWG-to-Project writes, the existing SQLite UnitOfWork rechecks project revision and the whole captured binding row; C7E _ensure_binding still checks confirmed binding ID/project/document/path. Existing write-back target preconditions and project/binding checks remain in place. No heavy fingerprint/attribute comparison is used at Apply. Check failure happens before scan/device/topology persistence.

## Completeness and activation result

C6 is unchanged. Neither filtered completeness flags nor filtered provenance are removed/promoted. No new partial batch becomes applicable. A genuinely authoritative full view comes only from the existing unfiltered read after user consent.

Activation:

- UI opt-in candidate attempt: ON, default unchecked.
- Visible explicit full fallback with preview/Apply: ON.
- Lightweight check for that full fallback proposal: ON.
- Default legacy/full Update and #148: unchanged.
- Applicable filtered subset / accelerated production reconciliation: OFF.

Remaining C7F limitation: Handle+Layer alone cannot distinguish an unrelated excluded insertion from an excluded untracked contract claimant, or supply a proven complete projection for absence-sensitive cable/bus/conduit reconciliation. No such projection/ownership classifier was added here. This is separate from, and not an attempt to reinstate, the rejected atomic-lock requirement. Coordinator must review a complete-view/ownership design before enabling fast Apply.

Performance: the new Apply census demonstrably has zero expensive property reads. Existing C5/C7c selected AutoLISP/COM candidate tests still demonstrate reduced heavy reads on excluded blocks. However EVERY applicable proposal in this new UI path still uses the full fallback. Therefore **no production scan speedup is claimed**; opt-in currently adds candidate work before full retry. Do not advertise it as a completed optimization.

## Tests and checks

Windows, .venv Python 3.14.3 / pytest 9.1.1 / pytest-qt 4.5.0 / Ruff 0.15.22. PYTHONPATH=src;. and TEMP/TMP=.venv/tmp; QT_QPA_PLATFORM=offscreen. Named pipes mocked; no real AutoCAD connection. No locked Python 3.13/live acceptance claim.

1. `python -m pytest -q --tb=short tests/cad_sync/test_pragmatic_filtered_sync.py tests/objects/test_object_ui.py`: **31 passed, 0 failed**, exit 0, 34.23 s. Includes 17 new service/UI cases and 14 existing ObjectWorkspace regressions. Real widgets, modal preview, selection and Apply are used with synchronous test scheduling and mock CAD transport; writes go to disposable SQLite.
2. Single full `python -m pytest -q --tb=short tests/cad_sync`: **587 passed, 0 failed, 0 skipped**, exit 0, 261.65 s.
3. Targeted cad_contract command for test_validator_numeric_layers.py, test_dali_layer_rules.py, test_numeric_contract_mapping.py, test_validator_av.py, test_issue237_track_dali_integration.py: **208 passed, 0 failed**, exit 0, 0.57 s. Known 11 baseline failures in the unchanged full cad_contract suite are not claimed fixed; no tests weakened.
4. `python -m compileall -q src/nl_project_2/cad_sync src/nl_project_2/presentation/object_workspace.py tools/autocad_sta_bridge.py`: PASS, exit 0.
5. `python -m ruff check` and `python -m ruff format --check` for all eight changed Python files: PASS, exit 0, 8 already formatted.
6. `git diff 916188e2b05eb7d10a08d05d87afdfc42105067f --check`: PASS, exit 0.

Coverage includes actual UI opt-in/full retry/preview/apply, refusal of retry, project switch in modal review, census drift/deletion/addition/COM failure, DB revision/binding mutation after the last census but before UoW, allowed coordinate-only residual risk, unchanged default full path, moved-off-layer vs genuine missing through full fallback, stale write-back rejection, strict census transport and zero-heavy-read census assertion. C5/C6/C7c/C7e and #148 regressions are in the full suite. No skipped/xfail suppression. An initial UI test double lacked cancel(); fixing the double made all four Qt flow cases pass without production workaround.

## Changed allowed paths

Relative to Systems/NLP:

- src/nl_project_2/cad_sync/bridge.py
- src/nl_project_2/cad_sync/scan_layer_safety.py
- src/nl_project_2/cad_sync/service.py
- src/nl_project_2/presentation/object_workspace.py
- tools/autocad_sta_bridge.py
- tests/cad_sync/test_bridge_client.py
- tests/cad_sync/test_sta_layer_prefilter.py
- tests/cad_sync/test_pragmatic_filtered_sync.py (new; UI tests located here, no adjacent presentation test file added)
- docs/engineering/checkpoints/NLP_255_C7F.md

No C6 gate modification, CAD contract/catalog/validator/parser change, schema/migration, real DWG/SQLite edit, new Issue, main merge, C7d or release.

## Exact next_action

Push commits and report final SHA/results in Issue #255; coordinator independently reviews the working explicit fallback + lightweight UI Apply and decides the complete excluded-ownership/reconciliation-view design needed for actual fast Apply under the already accepted pragmatic residual risk. Until then keep subset Apply OFF and make no production acceleration claim.
