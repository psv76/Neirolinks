# Issue #286 / #216 — Integrate accepted Routes B into actual NLP 3.1

## Baseline and authorities
- Repo `psv76/Neirolinks`, `main/Systems/NLP` base SHA `f53f77089d9038a1098cb6a5da86c4b9b0e1d861`.
- This worktree ONLY: `D:\GitHub_NEW\_worktrees\nlp-286-routes-b\Neirolinks`, branch `work/nlp-286-routes-b-integration`.
- Accepted UX source is Issue #216 §4 plus doc-only PR #220 (`origin/docs/nlp-216-routes-b-accepted`) and existing `docs/product/14_WORKING_USER_INTERFACE.md`, §9 and proposed §9.1. User selected option B on 2026-10-20 without changes.
- Existing working code candidate: PR #221 (`origin/system/nlp/216-routes-b-production`), four files. **Its branch is ~432 commits behind main; do NOT merge wholesale**. Port/adapt after reviewing its diff and existing 3.1 Q07. PR #219 is *comparison spike*, never production.

## Required result / phase 1
1. Actual `RoutesWorkspace` in `ObjectWorkspace`, replacing temporary legacy `Открыть трассы и трубы` button as primary section; preserve legacy expert service navigation if the current architecture requires it.
2. One high-density full-width `QTableView` + `QAbstractTableModel` (no right pane) and flat expandable rows: real `Conduit`→physical `CableSegment`/`BusSegment` by **stable segment/conduit IDs**, plus standalone `Без трубы` for all relevant physical unassigned segments, tri-state need `Требуется / Не требуется / Не определено`; `Требует трубы` filter.
3. Project services only (`CableService.list_conduits(), line_cards(), topology()` and `BusService.journal_cards(), journal_topology()`); a needed read-only conduit_id on BusService may be added using real `bus_segment_conduit_assignment`. No second persisted route model, no DWG access/scan at tab open, no SQLite migration.
4. Correct source→target labels, ID, cable/line, conduit type/color, mount, status, lengths (segment pure G not rounded; conduit **actual persisted length with accurate explanation**; do not falsely claim full Q08 final formula if domain is legacy); physical BUS skip noncable TRACK associations.
5. Search, sort/filter, stable multi-select Ctrl/Shift, explicit hidden-selected count when filters/collapses hide selection, selections of parents do not implicitly select children, keyboard scrolling. Double click child segment navigates to exact Line; specification jumps to Conduit.
6. Lazy read loading/refresh after Project events; preserve existing Lines/Q07 editing/navigation and UI state. No silent write/mutation when viewing screen.
7. **Do not enable move/create/delete/assignment controls** before approved Q03 physical boundaries + atomic ordinary/BUS commands (#222/#224/#228/#229) are integrated and proven on current main. Disabled state must be explicit/understandable, not deceptive. Phase-1 is legitimately **read-only** and is only an initial integration for routes task; explain this in status.

## Allowed scope
- `Systems/NLP/docs/product/14_WORKING_USER_INTERFACE.md` (faithfully port accepted doc-only PR #220 §9.1 into current main; do not overwrite newer content)
- `Systems/NLP/src/nl_project_2/presentation/routes_workspace.py` new; `presentation/object_workspace.py` integration.
- `Systems/NLP/src/nl_project_2/buses/service.py` **read-model only**, if necessary.
- `Systems/NLP/tests/integration/test_routes_workspace.py` and narrow adjacent UI tests only.
- This scoped engineering task doc.
- If code+docs conflict with accepted UI or current 3.1, STOP and report concrete discrepancy; do not redesign.

## Strict safety
- No live production DB access: `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite`. No real CAD/AutoCAD COM, no DWG save/close; canonical checkout and installed program stay unchanged.
- Disposable tests only under `%TEMP%\NL_Project_3\issue-286-routes-b\`, worktree above.
- Do not touch Ethernet Apply, schema, electrical graph/domain, conduit formulas, specification quantities, migration/catalog.
- Do not push/merge/create PR/install; coordinator controls GitHub integration and user visual acceptance.
- Windows test with existing canonical `D:\GitHub_NEW\Neirolinks\Systems\NLP\.venv\Scripts\python.exe` as read-only interpreter. Do not modify canonical env.

## Required evidence
- Run test_routes_workspace, Q07 tests/integration, ObjectWorkspace, Lines/shell/specific navigation smoke + related BUS read-model regression; scoped Ruff check/format, `git diff --check`, syntax.
- On test fake and actual sqlite TEST FIXTURE assert no writes on view/refresh, exact IDs/lengths, independent conduit branches, unassigned tri-state, hidden multi-select, spec jump and keyboard.
- Provide file list, tests PASS/FAIL, limitations and risk note. Commit local after successful validation, do not push.
