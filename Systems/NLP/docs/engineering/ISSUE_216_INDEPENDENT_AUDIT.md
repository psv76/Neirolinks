# Issue #216: independent audit, 2026-10-21

This is candidate evidence, not release or live acceptance. Q01-Q11 and accepted
UI variant B are unchanged. Canonical accepted source remains main/Systems/NLP.

## Reviewed revisions

- main: `8f566f7a1eddb2c7eb4242dd275cdd775ca79a89`
- #221, UI B: `2f9427fce2802d77e64089f005c4bf5b478833c1`, draft against main
- #222: `bd2be7450315d82cda40d2444d53f63134e85594`, draft against main
- #224: `bcba8077e31ea3fb9dbd8d48326e0b1e2be0c431`, stacked on #222
- #228: `c1825a741a0392d48be473c312080c1d6c7cbe1c`, stacked on #224

#222 advanced beyond #224's recorded base `70c1c6b`, but its physical identity,
repository, planner and audit source files are byte-identical to #228. The
additional commits are formatting changes already present in the descendant.
All four PRs were open drafts, not merged, at inspection.

## Reproduced defects and narrow repairs

Four new negative test cases failed on unmodified #228 (DID NOT RAISE):

1. A provider could supply a confirmed span and class name but no permitted-class
   set. A single-member target accepted the write. The command now requires
   positive class approval for affected tubes, including single-member tubes.
2. A changed ordinary segment's `gofra_color` could be absent or disagree with its
   assigned Conduit while the insertion still matched. The mirror silently
   overwrote the segment. It now checks the segment's previous type/color before
   replacement and rolls back on drift. Existing synthetic seeds were corrected
   to contain consistent initial assigned route facts.
3. BUS assignment to a FIELD_DEVICE target updated bus_segment but not insertion
   `BUS_GOFRA_*`. `cad_sync/reconciliation.py` classifies these as insertion facts;
   `_load_project_owner_values` reads the insertion projection. Thus updating only
   bus_segment is not a complete Project-to-DWG change. This unsupported write
   now fails closed. This is a safety gate, NOT implementation of a BUS mirror.
   Resource-target BUS synthetic transactions remain supported.

Additional FK-enabled tests exercise actual ordinary/BUS membership in the SAME
Conduit, mixed-network refusal/approval, and FIELD_PORT-to-device mirror success
and baseline-drift rollback. Existing mixed tests used separate target tubes and
therefore did not prove same-Conduit integration.

## Confirmed boundaries

- Canonical spans compare unordered typed owner UUIDs, not endpoint-local IDs,
  GOFRA text, coordinates or length. Shared EL_BOX uses cable_point UUID.
- The command takes the SQLite write lock via Project revision CAS before reads;
  assignment changes, mirror, invalidation and revision share one UnitOfWork.
  Existing tests cover injected rollback, stale selection/revision and no-op.
  This does not prove coordination with every legacy writer across UI refresh.
- Shared ordinary insertion conflicts and insertion baseline drift fail closed.
  FIELD_PORT tests prove the mirror boundary only, not a full CAD round trip.
- Automatic Conduit lengths are invalidated; USER_CONFIRMED length is preserved.
  Invalidation is not Q08 recalculation or specification parity.
- #221 has disabled write buttons, stable typed segment selection and a read-only
  Project service view. #221 and #228 are separate branches, not an integrated UI.
- No schema, migration, catalog or ATTDEF change is introduced by this repair.
  Existing migration 000000000014 is the shared-point FK contract.

## Remaining merge/production gates

Do not merge this stack as a completed #216 implementation or enable assignment
buttons based on focused green tests.

- No trusted production Project/catalog provider supplies confirmed Conduit
  spans, cable classes, allowed combinations, diameter/fill constraints and
  installation evidence. A typed callback alone does not establish these facts.
- Implement transactional BUS insertion projection with before/after conflict
  validation, then prove Project edit -> proposal -> exact write/readback -> no-op
  on synthetic CAD fixtures. Current existing sync suites do not invoke the new
  atomic assignment command in an end-to-end round trip.
- Q02 physical-only transit across successive tubes remains unrepresented. Do not
  fabricate commutation or a new RouteSection to work around it.
- Lengths are still legacy: cables/recalculation.py applies percentages to
  geometry PLUS outputs, retains timber_segment_reserve_m=0.5, and rounds with
  integer ceiling. buses/recalculation.py also retains timber reserve. Q04/Q05/Q08
  roots, actual terminations, common height zero and configurable Decimal-safe q
  are not established by this stack.
- specification/service.py adds `_conduit_sources` and `_bus_conduit_sources`.
  The latter emits one source per bus_segment without consulting assignment IDs;
  the former skips AUTO_BUS_SEGMENT origins. Shared ordinary/BUS tubes can be
  counted twice, and BUS-only shared tubes can be counted per segment. Manual
  Conduit length is not a general repair of this derivation. Q06/Q08 remain open.
- Canonical docs still contradict accepted decisions: product/22 retains timber
  reserve, percentages on outputs and old BOX rules; README claims schema 12,
  whereas schema head is 14. The physical-identity candidate also refers to
  NL_PROJECT_3_Q01_Q11_DECISIONS.md, absent from this stack. Integrate accepted
  decision docs and calculation/spec changes before completion; do not reopen B.
- The mirror validates all ordinary target owners and tubes in the Project;
  unrelated invalid legacy ownership can block a local batch. Scope this with
  care without omitting other users of an affected insertion.
- The legacy CableService/BusService write paths are unchanged and are not made
  safe merely by adding this separate gated command.

## Verification scope

Original #228 CI run 39540227796 was independently inspected: completed/success,
including lint, focused suite and existing sync/recalculation steps. That is
historical evidence for c1825a7, not proof of the repair commit.

Local tests use isolated synthetic SQLite and offscreen Qt on Windows, Python
3.14, SQLAlchemy 2.1.5, PySide6 6.12.0. This is NOT the locked deployment runtime
(CPython 3.13.14 and requirements.lock). Exact commands/counts and repair CI
results are recorded in Issue #216 after execution. Full locked release scripts
and live acceptance are not claimed. No live SQLite, DWG or AutoCAD was accessed.
