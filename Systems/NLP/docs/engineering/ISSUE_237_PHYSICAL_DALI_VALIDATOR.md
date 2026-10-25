# #237 physical DALI validator checkpoint

Scope: draft #239 on #236, not runtime readiness. Main baseline remains
`8f566f7a1eddb2c7eb4242dd275cdd775ca79a89`; previous #239 head was
`932eb80d2549bc9c3ed2ea0e589c72e1c54f2296` (CI 39999582519 successful).
The CAD authoring contract remains 3.2.0 / 72 definitions; production runtime
contract remains 3.0.0. Future NLP 3.1 is not a release created by this change.

## Implemented boundary

The full `CadContractValidator.validate` now resolves explicit DALI parents by
BOX_ID, TRACK_ID, or addressable BUS_POINT_ID. It checks source existence,
same-bus membership, protocol, duplicate endpoint identities, incompatible
parents, missing parent, cycles and root reachability. Duplicate endpoints are
never collapsed into a selected winner. Iterative traversal handles long graphs.
No edges, lengths, short addresses, persistence plans or automatic migrations
are produced. Legacy passive BUS_POINT_ID is blocking and is never exposed as
an addressable typed payload; raw observation data remains available for review.

Project roots cannot be discovered from DWG: `project_bus_roots` is an explicit
read-only caller snapshot of existing root endpoint IDs. A physical BOX/TRACK
DALI component without this snapshot reports BUS_ROOT_UNVERIFIED; an explicit
snapshot without the requested root reports BUS_ROOT_NOT_FOUND. Downstream
unreachable nodes are blocking. Loading that snapshot in reconciliation/workflow
is still gated work. For backward compatibility, **numeric-only legacy DALI
batches without a snapshot retain the existing .000 root convention**; they do
not prove Project root existence. Passing a snapshot validates numeric roots too.

`project_bus_kinds` follows the constructor convention already present in #227.
CABLE_OUTLET_BUS remains addressable and requires an explicit Project type;
BUS_SOURCE presence cannot imply DALI, RS485 or KNX. The new physical graph
validates DALI only. RS485 ordering and KNX Project topology are not replaced;
full #227 catalog/service/UI integration and KNX topology checks remain that
separate dependency. The small boundary here prevents the previous draft's
incorrect universal-outlet DALI inference.

## Actual verification

- Isolated Windows Python 3.14.3 environment, not locked runtime Python:
  **123 pytest cases passed**: 45 new full-validator graph cases, 77 existing
  rules/physical-topology/AV cases, and the universal-outlet positive case.
- Existing 11-case typed membership smoke passed with explicit Project type/root
  fixture input. These 11 cases remain field checks, not graph acceptance.
- New cases include 2 BOX + 2 TRACK + 10 addressable lights, mixed/self cycles,
  missing/cross-bus/untyped/duplicate parents, conflicting parent attributes,
  Project root absence, legacy passive IDs, and a 1997-node chain.
- The full BOX + addressable example is acceptable. The larger TRACK example
  checks the bus graph and explicitly retains #238's layer/group blocker. It is
  **not** full TRACK runtime acceptance or a physical-length calculation.
- Ruff lint, format and diff checks passed for the changed Python files.
- Broader cad_contract run excluding `test_repair08_contract.py`: **212 passed,
  5 failed**. All five failures reproduced on the original #239 SHA (167 passed,
  5 failed): old 3.0.0 catalog assertion, old BOX BUS_POINT_ID fixture, and three
  BOX/TRACK positive fixtures with BUS_SOURCE but no BUS_ID. No test was marked
  xfail or rewritten to hide these inherited contract-integration failures.
- `test_repair08_contract.py` could not collect in the isolated environment:
  PySide6 is absent through its reconciliation import path.
- Required `format-check.ps1`, `check.ps1`, `test.ps1` were invoked; all stopped
  at the missing locked environment before running their checks. **Not PASS.**
- CI executes the 123 selected pytest cases, 11-case smoke, syntax and Ruff.
  Exact pushed SHA and actual CI outcome are recorded in PR #239 / #235 / #237.

## Remaining gates and retained work

No #238 merge/cherry-pick: head `b2d1027e2fd702337992b1da7da202934ac9d056`
and CI 39938256663 success were rechecked. Integrate as a separate dependency.
Owner-aware sync, explicit legacy inventory/mapping/preview/backup/approval/
rollback, typed persisted endpoints, CABLE_TRANSIT, general cross-type TRACK
identity management, ordinary/internal TRACK links and lengths remain gated.
Full locked runtime, #227 integration, five inherited fixture failures and
Windows/AutoCAD acceptance remain open. #231 and other #216 work are untouched.

Reused local checkout (not installed program):
`C:\Users\psv76\.codex\.chatgpt-projects\g-p-6a09aaee6a448191abb66fc50ae2abde\gate235-review`.
Existing `.audit-venv` and `.audit-tmp` were reused. `.audit-tmp/pr239-baseline`
and its zip retain the original SHA for the baseline comparison. These scratch
items may be removed after review; keep the checkout until all work is pushed
and review is complete. They are not source artifacts or production backups.
No real SQLite, DWG, AutoCAD, installed program, TechDocs, contract, migrations,
release/tag or main changes.
