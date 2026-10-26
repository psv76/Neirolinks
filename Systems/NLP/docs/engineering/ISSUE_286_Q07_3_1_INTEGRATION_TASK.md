# Issue #286 — NLP 3.1 Q07 physical tree integration task

## Base and scope
- Repository: psv76/Neirolinks, main/Systems/NLP; baseline SHA `34bd74de1f6ed1ebf2c1531eea03a6c4ad59f810`.
- Execute **only** in existing branch `work/nlp-286-q07-3.1-integration` and existing controlled worktree.
- Target: accepted UI behavior Q07 in Issue #216 and accepted candidate PR #217, branch `origin/fix/nlp-216-lines-physical-tree`; reference candidate is old and MUST NOT be merged wholesale.
- Accepted production contract: `docs/product/14_WORKING_USER_INTERFACE.md` §9, current code/tests for Lines, and the Q07 acceptance in Issue #216 (relevant section only). No new product decisions.
- Goal: adapt reviewed implementation from six changed files in PR #217 to current NLP 3.1 main. This is a narrow UI-only repair of physical tree rendering.

## Required result
1. For ordinary CableLine and BUS topology, draw physical order by actual stable source/target endpoint identities; never infer adjacency using display labels or arbitrary ornamental depth.
2. Multiple independent physical root branches from one BOARD output remain separate; genuine EL_BOX forks get tree connectors from real graph. Ambiguous/missing graph parts remain visible with issue evidence rather than invented links.
3. Every child row carries its own correct incoming `segment_id`, and mounting/conduit/length/status/navigation/issue actions refer to that exact physical edge.
4. Compact mode MUST preserve physical roots, branching nodes, EL_BOX, problematic rows and necessary ancestors; provide explicit expansion to all segments.
5. Preserve current release 3.1 LinesWorkspace: normal/AV/BUS records, columns, room chips, inline markers, filters, selection, navigation, editing, double click; do not regress the working UI.
6. Only add read-only endpoint identity to CableService/BusService read-model when necessary. No topology or persistence writes in this task.

## Allowed code/test paths
- `Systems/NLP/src/nl_project_2/presentation/physical_tree.py` (new if needed)
- `Systems/NLP/src/nl_project_2/presentation/lines_workspace.py`
- `Systems/NLP/src/nl_project_2/cables/service.py` (read-only metadata only)
- `Systems/NLP/src/nl_project_2/buses/service.py` (read-only metadata only)
- `Systems/NLP/tests/unit/test_physical_tree.py` and `Systems/NLP/tests/integration/test_lines_workspace.py`.
- Additional narrow test files ONLY if essential; explain in report.

## Prohibitions
- No SQLite schema/catalog migration, topology semantics or formula changes, AutoCAD contract changes, new route UI, Ethernet Apply changes, Q01–Q06/Q08–Q11 changes.
- Do not access, update, copy, migrate or open real `D:\NL_Project_3_Data\Projects\nl_project_3.sqlite` or any client DWG. Do not connect to live AutoCAD COM, and do not Save/Close AutoCAD.
- Do not change canonical checkout `D:\GitHub_NEW\Neirolinks` or any other worktree, do not install/release, do not merge/push, do not create Issues or PRs.
- Only work in the specified worktree. Build/test scratch must remain within worktree or `%TEMP%\NL_Project_3\nlp-286-q07`.
- If accepted behaviors conflict with current code, explain exact conflict and STOP rather than invent a new design.

## Checks
- Run focused tests `tests/unit/test_physical_tree.py` and `tests/integration/test_lines_workspace.py`, plus existing related tests when touched.
- Run appropriate syntax/ruff checks and `git diff --check`. Report exact commands, pass/fail and environment. Never claim Windows AutoCAD/live acceptance.
- Include regression tests: independent BOARD roots, true EL_BOX forks, same labels/different IDs, swapped edges, BUS graph, compact/full, issue-preserving rows and exact segment mapping.
- Check final diff and keep code changes limited to approved scope.
- Do not commit unless tests run and are passing; if a tool limitation prevents tests, leave uncommitted changes with a clear report for coordinator.
- Conclude with a concise evidence report: files changed, tests, remaining gaps and exact branch HEAD; coordinator will push/open PR after review.
