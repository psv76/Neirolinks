# Issue #142 / PR #143 — software validation record

Date: 2026-10-03. Repository: `psv76/Neirolinks`. Scope: `Systems/NLP` only.

> Historical evidence from PR #143. The accepted user interaction was subsequently
> changed by PR #144. Current normative behavior is defined by
> [14_WORKING_USER_INTERFACE.md](../product/14_WORKING_USER_INTERFACE.md),
> [25_DWG_SYNCHRONIZATION.md](../product/25_DWG_SYNCHRONIZATION.md) and
> [WORKING_UI_WORKFLOWS_AND_TARGET.md](WORKING_UI_WORKFLOWS_AND_TARGET.md).
> PR #144 merge gates are tracked in PR #144 / Issue #142; performance and final
> real-object acceptance are separate NL Project 3.0 stages #148 and #149 under
> global router #145.

## Baseline and integration

- Continued existing branch `fix/nlp-142-working-cable-journal` at
  `4064838fb9b600975bbcce60c69a30ce33cba984` in a separate checkout.
- Integrated current main `eb940bca5b379cbf6e19037ee919ae940bedb7a5`
  (merged #141) with merge commit `c8322f2`; no merge conflicts.
- Existing Draft already implemented the segment chain, initial route editor,
  per-line breakdown and BOARD-root geometry/reserve. It was not a finished repair:
  segment assignment/number and object breakdown were missing; edited conduit facts
  could disagree with assignments; missing-geometry diagnostics were overbroad;
  recalculation did not cover downstream source dependencies or restored room links.
- Baseline targeted run: 79 passed / 3 failed. Two stale UI text expectations and
  one Qt enum conversion in the draft were corrected.

## Final behavior and evidence

| Requirement | Implementation / regression evidence |
|---|---|
| Branched topology in Lines | Stable source-first traversal of unique edges; human BOX/point/port/resource labels; synthetic BOARD → BOX.021 → BOX.022 → 111.05 with branch to 111.06 |
| Exact segment editing | All five methods; type/color/number or existing-conduit selection; exact segment ID retained after refresh; neighboring segment and point rows unchanged |
| Conduit assignment consistency | Same designation requires compatible type/color; incompatible shared edit rolls back atomically; moving one segment leaves other assignments/facts intact |
| Lengths | Synthetic physical total 6 m; segment cable total 6.5 m; board reserve 1.5 m; line total 8 m; additional 2 m gives 10 m; manual full 30 m overrides line only |
| DWG/room updates | Accepted source or BOARD geometry recalculates dependent edges; room-only canonicalization uses accepted facts and does not consume pending DWG coordinates/routes |
| Missing data | Specific source/target room, base mark, ceiling height, mount height or X/Y; contradictory shared-point facts remain incomplete; numerically equal forms compare equally |
| Per-line and object breakdown | Separate physical/cable sums by method; object summary reachable from Lines; partial counts explicit; line-only reserves/manual overrides not allocated among methods |
| Pipe / cable / product | Separate columns; conduit → segment → cable-line hierarchy with actual line ID; cable display mark does not prove exact catalog selection |
| Persistence | Reopen, repeat preview, integrity_check=ok and empty foreign_key_check on temporary synthetic databases |

New tests are in `tests/cad_sync/test_issue142_working_journal.py` and
`tests/cables/test_issue142_diagnostics.py`; retained and extended regressions include
`test_p0004_segment_recalculation.py` and `test_lines_workspace.py`.

Three full-suite assertions needed an additive `label` field in their expected
FIELD_PORT read model. The reference remained `902.003/K1`; identity, cross-line
ownership, selective import and foreign-key assertions were retained.
The panel-state test now supplies the same representative 1440×1000 window size
before saving and reopening; its keyboard, selection, column and splitter assertions
remain in place. The two-row segment editor had exposed minimum-size clamping in
the old unspecified-size fixture.

The #140 resolver rules were not rewritten. The only additions in cad_sync/service
are derived-length recalculation hooks within the existing transaction, using
accepted Project data and preserving conduit assignments. The room-only regression
also proves that unselected DWG geometry is not imported.

## Runtime and checks

Windows, CPython 3.13.14 x64. Isolated `.venv` uses the previously provisioned
official locked Python runtime. Dependencies were copied from the verified isolated
acceptance environment with an identical lockfile, then all 31 installed distribution
versions were compared with `requirements.lock`. Installed package files were not
rehashed during this task; this is not a fresh hash-verified wheel installation.

Lockfile SHA-256:
`bfd1ac286f85720da500fdbb2125eee1dc79054c1ba9595b61b20bbc5d6dad2d`.

Commands (from `Systems/NLP`):

```powershell
& .\tools\format-check.ps1
& .\tools\check.ps1
& .\tools\test.ps1
& .\tools\catalog-check.ps1
& .\tools\autocad-contract-check.ps1
```

`check.ps1` includes compileall and Ruff lint. `test.ps1` uses the existing marker
expression `not live_cad and not manual_acceptance` on Windows. STA bridge/client,
persistence and Qt UI suites run against fixtures; they do not constitute live CAD
acceptance. Qt functional tests and a rendered synthetic Lines screen were inspected.

Final results:

- format-check: PASS, 248 files already formatted.
- check: PASS (compileall and Ruff).
- targeted cables/topology/conduit/UI/#134/#140/#142: **130 passed**, 63.53 s.
- full standard non-live/non-manual test.ps1: **707 passed**, 1 warning, 226.30 s;
  no skipped tests reported. This includes all 16 #140 room regressions.
- additional UI rerun: **17 passed**, 8.10 s.
- catalog-check: PASSED; 18 passports, 31 products, normative identity/facts equal;
  payload SHA-256 `f8d27710485e1d1f8b23070e6ffa693ddd304c05150996a3c7eeae455c4af4c5`.
- autocad-contract-check: OK, contract 3.0.0, 71 names, 10 groups, geometry_files=0.
- git diff --check: PASS; changes confined to Systems/NLP.

Targeted command:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/cables tests/cad_sync/test_issue142_working_journal.py tests/cad_sync/test_issue140_room_canonicalization.py tests/cad_sync/test_issue134_box_identity.py tests/cad_sync/test_p0003_reconciliation.py tests/integration/test_lines_workspace.py -q
```

Software criteria are green and the candidate is ready for review. The real-object
smoke below remains outstanding. No Release, live acceptance PASS or merge is implied.

Known warning: SQLAlchemy/sqlite3 default datetime adapter deprecation in the
existing topology migration test (Python 3.12+). No schema/migration, catalog release,
AutoCAD block contract, NL Project 1.0, working SQLite or DWG edits were made.

## Historical PR #143 real-object smoke plan — 05 44 Богданович

This was the outstanding real-object plan recorded for PR #143. It is retained as
historical evidence and must not be treated as the current PR #144 merge gate.
Any real-object execution now follows the active task router #145 and the dedicated
3.0 acceptance/performance stages.

1. Identify the exact current Project DB and target DWG by absolute path and object
   identity. Record DWG hash/size/mtime. Create a verified SQLite backup using the
   SQLite backup API; check integrity/FKs, then create a separate writable test copy.
   Launch the PR against that copy and visibly verify its path. Do not open live DB
   through the PR, save the DWG, apply Project-to-DWG writes or attach to arbitrary
   active CAD documents.
2. Read/preview the named real DWG. Select a real branched line with at least two
   EL_BOX nodes; record its actual line ID, handles, sources and BOX/point labels.
   Do not substitute the synthetic test line 111. If this topology is absent in the
   object, record that limitation and choose a user-confirmed representative case.
3. In `Линии`, compare every displayed source→target edge against the DWG facts.
   Verify no duplicate physical edges or UUID primary labels, and visible type,
   color, number, physical meters, cable meters and exact incomplete reasons.
4. On the test DB only, change one selected segment's route/type/color/pipe number.
   Exercise an existing compatible pipe and a separate pipe; incompatible shared
   editing must be rejected atomically. Verify neighboring segment facts and
   assignments are unchanged. A subsequent DWG preview must show the selected
   Project edit, not silently overwrite it or unrelated facts.
5. Compare hand calculations from accepted endpoint coordinates, room base/height
   and mounting heights with segment meters. Verify +0.5 m cable per timber segment,
   no cable reserves in conduit length, unique-edge sum, applicable board reserve,
   additional/manual length semantics and line/object method breakdowns.
6. Recheck lines 102/103: existing Дом_2/Постирочная room relation and labels remain
   correct. If room_id is already canonical, no repeat canonicalization is expected.
   Where an actual DWG geometry/room update exists, preview and select only that
   update on the test copy; verify affected lengths and unselected changes.
   Do not fabricate DWG changes for the smoke test.
7. Reopen the test Project, compare lengths/assignments and run integrity_check and
   foreign_key_check. Confirm original DB facts and DWG hash are unchanged. Record
   screenshots and results in the existing Issue #142; keep the test copy isolated.

Stop and report any unexpected live-data access, requirement to save/modify working
DWG/SQLite, inconsistent topology, unresolved product decision or failed integrity.
For the historical PR #143 state, software green permitted review but did not prove
release/live acceptance. Current closure and cutover decisions are governed by the
active #145 task queue rather than this historical smoke plan.
