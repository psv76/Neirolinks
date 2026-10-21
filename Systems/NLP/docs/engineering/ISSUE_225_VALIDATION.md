# Issue #225 — CABLE_OUTLET_BUS: implementation and validation

Date: 2026-10-21. Scope: #225; development router: #145.

## Candidate and boundaries

- Base: origin/main `8f566f7a1eddb2c7eb4242dd275cdd775ca79a89`.
- Branch: `system/nlp/225-cable-outlet-bus`.
- Product line remains NL Project 3.0. Independent AutoCAD machine contract: 3.1.0, 72 definitions, 10 groups.
- No schema migration, schema-head change, equipment catalog release, deployment or release.
- No connection to AutoCAD, no live SQLite/DWG reads or writes, no AutoCAD save/close.
- This is automated implementation evidence, not live/user acceptance.

## Implementation

The universal outlet has the exact 14 ATTDEF tags defined by #225, BUS layer/group,
CABLE_OUTLET physical identity and a bus cable link only. Existing outlet groups
and all 71 predecessor ATTDEF sets remain unchanged.

Project Bus determines RS485/DALI/KNX for validation, normalized payload, import
and Project-to-DWG planned-state validation. Specialized legacy blocks declare
their protocol explicitly in machine metadata; ATTDEF presence no longer infers
DALI. The universal outlet cannot fall back to RS485. Missing Project bus/type
requires explicit selection/creation with a physical source. The UI offers all
three protocols and filters source resources by protocol and availability.

RS485 follows numeric point suffix order and requires empty BUS_SOURCE. DALI and
KNX use the same explicit physical-tree validation, retaining their separate
protocol identities and existing protocol-specific rules. Duplicate point,
multiple parent, cross-bus, missing parent, cycle and unreachable diagnostics
are scoped to affected points/buses.

BUS_SOURCE and route Project values are read from canonical Bus/BusSegment and
conduit assignments, while established insertion projection paths preserve sync
baseline compatibility. Selective apply uses accepted fields, preserves other
segments and reconnects an RS485 successor when necessary. Generated conduit IDs
are written back and converge to no-op. LOAD_NAME remains editable on bus-only
points. Canonical values are scoped to the selected DWG binding.

## Acceptance evidence

| Requirement | Automated evidence |
| --- | --- |
| Exact new tags, canonical name, BUS-only group, no ordinary link | `tests/cad_contract/test_issue225_bus_outlet.py`; human-reference parity test |
| Existing 71 exact definitions unchanged | immutable Repair08 hash fixture and `test_repair08_contract.py` |
| Project RS485/DALI/KNX identity; unknown kind; specialized conflict | `test_project_kind_and_no_ordinary_cable`, `test_no_protocol_guess`, `test_rs485_source_and_specialized_conflict` |
| Line/star/tree; missing/cross-bus parent, cycles, unreachable points | parametrized `test_tree_rules` for DALI and KNX |
| Reserved root, malformed point, duplicate identity/double parent, foreign definition tags | `test_invalid_facts`, `test_duplicate_parent_and_exact_definition` and predecessor exact-definition tests |
| FTP 5e, floor route, PP20 blue conduit, initially empty ID | `test_project_kind_and_no_ordinary_cable`, three-protocol integration and existing conduit regression |
| Numeric RS485 order; one BusSegment per edge; no ordinary CableLine or fictitious ProjectInstance | `test_import_edges_noop_writeback_conflict_and_missing` for all three protocols |
| Generated pipe number, exact write/read-back, no-save and repeat no-op | same integration test, using isolated SQLite and CAD test double |
| True two-sided route conflict, selective apply, preservation of other point | `test_segment_owner_conflict_selective_apply_and_writeback` |
| Canonical BUS_SOURCE write-back and rejection of Project-side ring | `test_bus_source_project_owner_and_invalid_write_cycle` |
| Explicit DALI/KNX source selection; existing RS485 UI compatibility | `test_explicit_bus_kind_creation_ui`, `tests/buses/test_ui.py` |
| Bus-only LOAD_NAME changes | `test_bus_only_load_name_remains_editable_without_line` |
| Cable length once, no invented motor commodity, unique specification sources | `test_lengths_and_specification_have_one_physical_segment`: 3.1 + 1.6 + 1.6 m raw physical lengths |
| Disappearance/reopen | missing DWG insertion is diagnosed; returning insertion retains identity and no-op; existing missing-insertion resolution policy is unchanged |
| Legacy RS485/DALI/KNX, cable, migration, UI, specification regressions | complete default-marker test suite |

## Executed checks

CPython 3.13.14 x64, locked dependencies, Windows; isolated worktree.

- `tools/format-check.ps1`: PASS, 261 files already formatted.
- `tools/check.ps1`: PASS (compileall and Ruff).
- `tools/test.ps1`: **792 passed, 0 failed, 0 skipped**, 433.10 seconds.
- Default marker expression: `not live_cad and not manual_acceptance`.
- One existing SQLAlchemy/SQLite datetime-adapter DeprecationWarning in
  `test_previous_head_upgrade_reopen_integrity_and_safe_downgrade`.
- Full-run scratch: `%TEMP%\NL_Project_3\issue-225\full-3`.
- `git -c core.whitespace=cr-at-eol diff --check`: PASS; existing per-file line endings retained.

Initial development runs exposed test-fixture setup/temporary-path issues and
implementation gaps; the results above are from the corrected implementation.
No live smoke was executed. A real AutoCAD smoke requires a separately named
DWG, permission and document identity check. It must verify real bridge behavior
and leave the document unsaved/open under the established contract.

## Worktree retention

`D:\GitHub_NEW\_worktrees\issue-225\Neirolinks` is the isolated candidate,
recorded in #225 before creation. Retain for PR review; after merge/abandonment,
remove through Git worktree management only after verifying no unique unpushed
work. `%TEMP%\NL_Project_3\issue-225` holds disposable test databases/logs and
may be removed after review. The canonical runtime checkout was not changed.


## Post-review repairs (2026-10-21; verification pending)

Independent review found three synchronization risks, addressed in follow-up
commits on the same PR branch. The original `792 passed` run listed above
**predates these commits** and must not be represented as their validation.

- RS-485 source reconstruction uses the **complete set of accepted Project
  BusEndpoint addresses**, including a temporarily missing DWG insertion.
  Adding a new intermediate point reconnects only the appropriate successor;
  route and conduit ownership remain unchanged.
- Existing `BUS_POINT_ID` changes are **explicit structural collisions**.
  Renumber/exchange is not yet a supported generic DWG Update operation.
  Even if structural apply is forced, the materializer checks endpoint/device
  ownership transactionally and rejects it before any committed changes.
- A consistently changed `BUS_CABLE_TYPE` can update the whole Bus in one
  transaction. An incomplete scanned set of accepted endpoints is rejected
  rather than changing the Bus owner based on a subset.

Added regression scenarios in `tests/buses/test_issue225_sync.py`:
missing middle RS-485 point + selective change, inserting an intermediate point,
free-address renumber and swap for all bus kinds, whole-bus cable type change
for RS485/DALI/KNX, and rejection of changes from incomplete DWG snapshots.

**Pending:** rerun `tools/format-check.ps1`, `tools/check.ps1` and
`tools/test.ps1` on the updated PR head; verify precise test counts and log
actual results here and in PR. At the time of this follow-up, the previously
available remote Windows device was offline. No live DWG/SQLite, AutoCAD
connection, or workstation main runtime was touched.
