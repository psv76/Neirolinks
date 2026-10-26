# Issue #286 / #149 — Ethernet DWG preview/Apply failure diagnostics and safe repair

## Base and scope
- `psv76/Neirolinks`, `main/Systems/NLP`, base SHA `f53f77089d9038a1098cb6a5da86c4b9b0e1d861`.
- This worktree ONLY `D:\GitHub_NEW\_worktrees\nlp-286-ethernet\Neirolinks`, branch `work/nlp-286-ethernet-apply-diagnostics`.
- Source facts from Issue #286 C and #149; previous PR #190 `origin/fix/nlp-149-sync-apply-diagnostics` is an OLD reference (~483 commits behind current main), do NOT merge wholesale.
- Current DWG observation (READ-ONLY evidence): House_2 working.dwg 13 CONTROL_PANEL_4 ID801–813 and 45 SOCKET_ETHERNET ID830–874 on 800_Ethernet; 58 unique legal IDs; active DB 40 lines 801–813 / 830–856, **new 857–874 (18) missing**.
- Two visible blocker signals `BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION:906:906.001` and `CONDUIT_COLOR_INCONSISTENT` (GOFRA_COLOR). Shared UnitOfWork currently may roll back valid Ethernet insertions due to unrelated errors. This causality is **HYPOTHESIS until reproduced**; no assertion that it is proven in production.
- Also reported FRAME_1 / FRAME_2 on 800_Ethernet classified as MOUNTING, possible layer-classification contract gap.

## Work order — prove before changing behavior
1. Inspect current `cad_sync/service.py`, `cad_contract/validator.py`, `presentation/object_workspace.py`, plan/preview candidate generation and errors. Analyze current HEAD status of previous PR #190 concepts.
2. Construct fully synthetic fixture matching valid new Ethernet 857–874 alongside an independently inconsistent BUS 906 and conduit GOFRA color conflict, without accessing the real DWG or working DB. Capture original expected preview, apply/rollback or blocker behavior; distinguish validation / preview vs write transaction and prove exact failure path. Tests must explicitly assert 18 candidate records, existing 40 untouched, idempotent replay when valid, correct project binding.
3. Implement narrowly scoped **informative preview** UI or read-model so users see `NEW_DWG_INSERTION` valid candidates (count+IDs) distinct from conflicts, and exact global blockers / aborted-transaction reason, with no false success and no silent rollback. Preserve current GUI navigation, user resolution and no write during preview.
4. Implement SAFE fixes only when the fixture proves the defect and domain ownership: duplicate BUS_POINT_ID must remain blocking for that BUS and must NOT arbitrarily renumber or replace existing BUS segments; `CONDUIT_COLOR_INCONSISTENT` cannot be suppressed or normalized silently. The code may safely preserve previous BUS state and import unrelated valid Ethernet IF atomicity of all correlated records is proven; otherwise retain global fail-closed and show a precise actionable message. Never remove validation globally or split UnitOfWork naively.
5. Audit whether FRAME_1/FRAME_2 on 800_Ethernet are auxiliary frames of Ethernet endpoint and can be classified consistently with accepted numeric layer contract. Only change validator if the actual machine contract/spec and synthetic test support; otherwise report separate gate and leave validation. Do not require live DWG bulk edits to hide the defect.
6. Reconcile diagnostics/logging for any Apply failure with no false committed status. Maintain unique IDs, stable source/target, no silent DWG changes. Never save/close AutoCAD.

## Allowed files
- Narrow relevant parts of `Systems/NLP/src/nl_project_2/cad_sync/`, `cad_contract/validator.py`, `presentation/object_workspace.py`; related focused tests in `tests/cad_sync`, `tests/cad_contract`, `tests/integration`. No unrelated broad fixes.
- This task doc. Prefer pure fixture/tests and UI preflight over invasive changes.

## Prohibitions
- Never access/copy/open/migrate or connect production `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite` OR live `House_2/working.dwg`. No AutoCAD COM, no operation on opened AutoCAD; do not Save/Close the drawing. Synthetic/fixture SQLite only under `%TEMP%\NL_Project_3\issue-286-ethernet\`.
- No SQLite schema head changes, catalog releases, electrical topology redefinition, Q07/Q10 Routes, filtered partial scan C7c-f (3.2).
- Do not commit unsafe workaround; STOP and report if safety proof is not possible. Do not push/merge/create PR/install. Never modify canonical checkout or its .venv. Existing canonical Python interpreter only for tests.

## Target tests
- 18 new valid Ethernet insertion candidates appear in preflight/preview, even when other blockers exist; existing 40 untouched; no premature claims of Apply.
- Duplicated BUS ID and GOFRA_COLOR conflict diagnosed distinctly with source evidence; no renumber/rewrite of BUS; rollback leaves DB unchanged on fail-closed.
- If safe independent commit implemented, show complete correlated-group atomicity, replay no-op, no duplicated shared conduits; else explicit block with reason and correct candidate counts.
- FRAME auxiliary contract if formally supported; stale/old layers and other invalid blocks are separate diagnostics.
- Run focused tests + existing CAD sync/contract regression, Ruff, format, syntax, `git diff --check`. Provide exact expected/apply behavior, evidence, limitations and required acceptance. Only local commit after tests pass.

## Execution evidence (2026-10-26)

- Base/branch verified exactly as above. Old commits `80e59d0` and `58a23b0`
  were read as references only. Their automatic error logging, duplicate BUS
  validation and duplicate-plan skip already exist in current HEAD; nothing
  was cherry-picked or merged.
- Before changing runtime code, three synthetic tests passed against current
  HEAD. The fixture first accepts 13 CONTROL_PANEL_4 (801–813), 27
  SOCKET_ETHERNET (830–856), and a separate DALI BUS 906 endpoint. The next
  snapshot adds SOCKET_ETHERNET 857–874: exactly 18 NEW_DWG_INSERTION records.
- Valid Apply creates 58 Ethernet lines, preserves the existing 40 and their
  field devices, and binds all records to the fixture project/document.
  Repeated preview produces no import paths and changes no database rows.
- Duplicate 906.001 plus two unrelated power lines sharing GOFRA_ID with
  different colors produces distinct DUPLICATE_BUS_POINT_ID and
  CONDUIT_COLOR_INCONSISTENT diagnostics with handles. These issues do **not**
  reproduce Ethernet rollback on current HEAD: the selected 18 import.
- A deliberately inconsistent accepted fixture (bus_endpoint address 906.002,
  accepted field-device/DWG identity 906.001), alongside the color conflict,
  reproduces BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION:906:906.001. SQL capture
  proves cable_line INSERTs occur before the BUS ownership guard raises.
  Comparing every metadata table proves complete rollback, including scans,
  operations, baselines, revision and correlated topology. This is a proven
  synthetic mechanism, **not evidence that the production DB has this state**.
- Keep the shared UnitOfWork and BUS ownership checks unchanged. Independent
  commit safety for inconsistent accepted BUS state has not been proven.
  No repair, automatic renumbering, conduit normalization or validator bypass
  was introduced.
- Added a pure diagnostics read-model and a read-only evidence pane in the
  existing resolution dialog: original candidate count/IDs/handles, validation
  scope and source messages are separate from Apply outcome. Automatic and
  decision Apply failures now retain full reason, project/document/binding,
  selected paths and selected candidate count in sync-apply.jsonl. Error text
  distinguishes validation-before-write from transactional cancellation and
  asks for correction and rescan; candidates never imply committed success.
- FRAME_1/FRAME_2 remain a separate contract gate. The machine family is
  MOUNTING/FRAME without cable/bus links, matching
  docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md. Synthetic 800_Ethernet
  placement produces LAYER_FUNCTION_GROUP_MISMATCH. There is no established
  endpoint ownership rule justifying a classification override here.
- All SQLite fixtures and test basetemps are under
  `%TEMP%/NL_Project_3/issue-286-ethernet/`. Tests use only the existing canonical
  `.venv/Scripts/python.exe`, with worktree PYTHONPATH and bytecode disabled or
  redirected to that TEMP subtree. No live SQLite/DWG/COM was accessed.

### Verification and acceptance gate

- Initial reproduction: **3 passed** before runtime edits.
- Diagnostic/UI/FRAME focused checks: **5 passed**; full-reason structured-log
  and global validation scope test: **1 passed**.
- Syntax compilation passed; changed-file Ruff and format checks passed;
  `git diff --check` passed.
- Full CAD sync/contract/integration collection is blocked by missing
  `jsonschema` in the permitted existing interpreter. No package installed.
  Remaining regression is run with only test_numeric_contract_mapping.py
  explicitly excluded; this is not equivalent to a complete green suite.
- Repository-wide Ruff reports pre-existing E501 in
  tools/d23_apply_stagec_service_for_ci.py. Format check reports six unchanged
  files: that script, d23_contract_delta_guard.py, d23_dependency_preflight.py,
  d23_layer_gate_inventory.py, d23_test_ast_parity.py and
  tests/cad_sync/test_p0003_reconciliation.py. These are outside the narrow fix.
- **No commit while required checks are not all green.** Acceptance requires
  the complete regression in a provisioned approved environment, resolution of
  baseline check failures, and separate authorized validation of the real
  failure cause. FRAME contract changes and live data repair remain separate.
