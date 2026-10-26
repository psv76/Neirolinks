# Issue #286 / PR #287 — Q07 second visual preview

## Scope and execution
- Source: `psv76/Neirolinks`, accepted `main/Systems/NLP` UI contract §9 plus Q07 code-only PR #287.
- Current isolated worktree: `D:\GitHub_NEW\_worktrees\nlp-286-q07-v2\Neirolinks`, branch `work/nlp-286-q07-v2-preview`, base `57e5713e6a9b23bd02664209877eaf8829252a4f`.
- This is a **second test GUI / visual candidate**, not release acceptance or permission to change `main` or live.
- Review the source and current tests first. Implement the accepted presentation direction with **real Project physical topology** (no fake points/labels or inferred links).

## Target UI — actual LinesWorkspace
1. Retain full-width current nine-column working table and columns, inline room chips, search/filters/editing/navigation and expandable base line rows. No major UI shell rewrite.
2. In **every physical child segment row**, show the **actual immediate source** in the existing `Источник` column: prefer the stored endpoint's human label `edge.source.label` and stable identity. Do NOT duplicate root BOARD into all rows or invent a link. Missing/ambiguous source should remain explicitly unknown, with existing actionable diagnostics.
3. `ID` shows readable physical target identities `BOX.NNN`, `XYY.ZZ`, etc., and actual graph indentation. Parent/child comes from stable source/target IDs. Preserve `segment_id` and exact row routing/edit/issue behavior, compact/full tree and all root/fork/issue rows.
4. For missing segment length, replace bare warning triangle + em dash with a compact explicit text such as `⚠ нет длины` in the length cell; retain exact failure reason via tooltip and click on the **same segment** (never turn missing into 0 or invent missing height/room). For valid lengths show existing values.
5. **Remove all ADDITIONAL length pseudo-rows** (e.g. `+ подключение в щите`, `+ коммутация в распредкоробках`, `+ выводы из подрозетников`, manual length/unrounded/rounded) from the *expanded physical tree in the base Lines table*. The base line still shows its correct unchanged final length.
6. **Keep all those existing length components**, with their exact values/semantics, in a **separate existing line-details dialog** (opened by double-clicking a base line). Add a readable section `Состав длины` under its physical segments, with all nonzero components that the current topology actually supplies, the complete manual/rounded values if present, and description that they are non-physical line-length components and must not be added a second time. Do not alter formula, totals, or data ownership.
7. In line-details physical segment table show a clear **Источник** column as well as existing room, ID, mount, conduit, length; uses actual source label, no guessed root.

## Tests and acceptance
- Add precise focused Qt test(s): child source equals `edge.source.label` on BOX roots and socket children, displayed missing length and interactive exact issue context; no `ADJUSTMENT` rows while expanded; line details still show every available length component, including 4/1.4/1.2 case without double counting; compact/full and identity regressions remain.
- Run existing `tests/unit/test_physical_tree.py` and `tests/integration/test_lines_workspace.py`, related Cable/BUS service tests; scoped Ruff and syntax, `git diff --check`. Use existing compatible CPython in `D:\GitHub_NEW\Neirolinks\Systems\NLP\.venv\Scripts\python.exe` **only to execute** in this isolated worktree; do not modify that environment or canonical repo.
- If an existing test insists on the obsolete adjustment pseudo-rows, **replace with explicit new contractual assertions** rather than silently dropping tests. If actual source label missing, render `Источник не определён` with explanation, not a guess.

## Boundaries
- Only modify `Systems/NLP/src/nl_project_2/presentation/lines_workspace.py` and affected focused integration tests, plus this task document; physical_tree graph/data contracts should remain unchanged unless a demonstrable read-only deficiency requires a narrowly justified change.
- No DB/schema/catalog/domain/cable formula changes, no AutoCAD COM operations, no live GUI installer, no real DWG, no production DB access/copy, no `main` checkout changes.
- Do not push, merge, create PR, or install. Complete in separate branch for coordinator to inspect/push. Do not commit if tests fail.
- Working test scratch belongs only to `%TEMP%\NL_Project_3\issue-286-q07-v2\`; avoid untracked files in source.
- Report exactly files changed, tests, failures and residual UX caveats. End execution after code/test report; coordinator will run a distinct test GUI with a copied production database and DWG sync disabled.


## Execution report — 2026-10-26

Implemented on `work/nlp-286-q07-v2-preview`, based on
`57e5713e6a9b23bd02664209877eaf8829252a4f`.

Files changed:
- `Systems/NLP/src/nl_project_2/presentation/lines_workspace.py`
- `Systems/NLP/tests/integration/test_lines_workspace.py`
- This task document (provided untracked at execution start; report appended).

Presentation changes:
- Physical child rows display the stored immediate source label; tooltips retain
  typed stable identity and graph diagnostics. Missing labels explicitly show
  `Источник не определён` with an exact-segment actionable issue.
- Existing graph-based target IDs, indentation, compact/full behavior, routing,
  nine working columns, base totals and service ownership remain in place.
- Missing child lengths display `⚠ нет длины`; tooltip and click retain the
  precise reason and segment. No missing values are converted to zero.
- Expanded trees contain only physical children and the existing show-more row,
  with no length-adjustment pseudo-rows.
- Existing details dialog has an immediate-source column and a separate
  `Состав длины` table beneath physical segments. All supplied nonzero reserves,
  additional length, manual length (including zero), unrounded and rounded totals
  are preserved. Component values retain supplied decimal precision. Explanation
  distinguishes components from geometry and totals, including manual override,
  and warns against adding them to the final length again.

Validation used only the existing canonical Python executable to run worktree
code: `D:\GitHub_NEW\Neirolinks\Systems\NLP\.venv\Scripts\python.exe`,
CPython 3.13.14 / PySide6 6.11.1. Bytecode writes were disabled; pytest cache was
 disabled and Ruff used `--no-cache`. Test scratch and disposable fixture
 databases were confined to `%TEMP%\NL_Project_3\issue-286-q07-v2\`.

Results:
- `tests/unit/test_physical_tree.py` and
  `tests/integration/test_lines_workspace.py`: **28 passed**.
- Complete `tests/cables` and `tests/buses`: **119 passed**.
- Scoped Ruff lint and format check: passed.
- In-memory syntax compilation of both changed Python files: passed.
- `git diff --check`: passed.
- No test failures. The focused tests cover stored BOX/socket labels versus
  stable IDs, exact mouse-click issue context, unknown source diagnostics,
  absence of ADJUSTMENT rows, unchanged base totals and the 4/1.4/1.2 components,
  manual/rounded values and precision beyond two decimals. Existing CABLE/AV/BUS
  identity, graph ordering and compact/full regressions continue to pass.

Residual UX / acceptance:
- Qt tests use offscreen widgets; no separate production-data GUI preview or
  visual acceptance was performed. The coordinator owns that distinct launch.
- Existing interactive column widths may require resizing for long source labels;
  component tables scroll when their content exceeds the dialog height.
- Physical-tree contracts, domain/formula code and canonical code/environment
  were not modified. No production DB access/copy, DWG/COM operation, install,
  push, merge or PR creation was performed. Disposable databases were created
  only by the existing service-test fixtures.
