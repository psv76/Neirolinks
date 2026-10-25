# Issue #237 / #235 — D14: shadow reconciliation of D13 physical transit

## Source of truth
`docs/product/22_CABLE_LENGTHS_AND_CONDUITS.md` §§3.1, 5, 8–12 and existing D13 Draft #251.

## Boundary

D14 introduces `cables/transit_reconciliation.py` as an explicitly **read-only**
Project projection; integrates `CableService.transit_reconciliation()` and
additional `transit_reconciliation` / `staged_transit_review` fields in
topology, line cards and the project route breakdown.

Existing `cable_length_fact`, electrical `cable_segment`,
`conduit_segment_assignment`, `conduit`, canonical specification and
`effective_m` are **not updated or replaced** by D14.

## Checks

- Each approved route must still belong to the exact active Project CableLine
  and electrical edge. Both endpoint IDs and row_version must match D13 approval.
- Numbered physical spans must be contiguous, with distinct physical boundaries
  and stable keys. Every intermediate BOX must still have an accepted active
  `CABLE_TRANSIT` member for that exact cable base.
- Multiple electrical edges per line block line-level quantity adoption:
  D13 original preview totals include *per-edge* reserves, so blindly summing
  these would double-count board/end/BOX allowances and apply rounding several
  times. D14 exposes only `staged_geometry_m` and `staged_corrected_m` as
  **uncommitted** evidence; it keeps final `authoritative_cable_m=None`.
- Proposed GOFRA_IDs are grouped **once** by exact physical boundary + method,
  type, color and geometry. Different bounds sharing an ID return REVIEW, never
  a merged unique length.
- Any reuse of existing canonical Conduit designation or legacy BUS
  `bus_segment.gofra_id` returns REVIEW because physical boundary identity is
  not established by those older records. Neither automatic adoption nor
  cross-domain sharing can occur on designation alone.
- An otherwise valid proposed conduit is still only `CANDIDATE_ONLY`:
  `unique_geometry_m` is **not** Q03/Q06-rounded authoritative pipe quantity.
  Stale owner/box/route excludes all its proposed conduit metres.
- Independent staged lines are evaluated individually, but any shared physical
  conduit ambiguity is surfaced to all affected owners.

## Open gates

D14 is not a final physical topology integration and is not a replacement of
actual length calculation/specifications. Still needed: owner-aware selective
Project↔DWG per-side roundtrip, approved geometry/length contract merge with
#218/#231, one-line percent/allowance/rounding policy and zero transit-splice
allowance, Q03/Q06 canonical ordinary+BUS Conduit boundary ownership and
atomic reconciliation, full locked suite, approved migration/restore drill and
Windows/AutoCAD/real DWG acceptance. Schema stays revision 16; no migration,
catalog release, `main`, installed application or actual SQLite/DWG change.
