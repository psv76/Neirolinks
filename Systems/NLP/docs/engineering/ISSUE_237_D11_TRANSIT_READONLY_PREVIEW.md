# Issue #237 — D11: read-only CABLE_TRANSIT inventory

## Scope

D11 exposes a deterministic read-only transit audit on the existing DWG scan
proposal. It reads the approved CAD 3.2.0 field CABLE_TRANSIT on
EL_BOX_OUT_100x100 and the already-normalized ordinary electrical SegmentPlan.
It does **not** create physical subsegments or permit an automatic apply.

The existing source-of-truth rules remain in product document
22_CABLE_LENGTHS_AND_CONDUITS.md and CURRENT_TOPOLOGY_ARCHITECTURE.md §6.

## Evidence and conservative classifications

- Empty CABLE_TRANSIT is valid and contributes no waypoints.
- The documented semicolon grammar recognizes ordinary XYY or XYY-N where
  X is 1..8, YY is two digits and N is a positive ordinal; @ is invalid.
- A physical BOX_ID and the real INSERT handle, coordinates and
  MOUNT_HEIGHT are retained as read-only waypoint evidence.
- Repeated boxes, duplicate or discontinuous ordinals, mixed unnumbered and
  numbered multi-box routes, malformed values, or unresolved line/source
  produce explicit typed REVIEW evidence.
- Only a single electrical SegmentPlan and an unambiguous sequence of
  transit boxes can produce CANDIDATE. Multiple ordinary segments, including
  line branches, are **not** assigned a path merely by BOX positions.
- Independent bases remain independent: one 302 ambiguity does not prevent
  the evidence for an unambiguous 301 from being inspected.

CANDIDATE does **not** mean topology, cable length or Conduit approval.
No route geometry, segment allocation, physical boundary reconciliation or
roundtrip is inferred from the CABLE_TRANSIT string.

## Runtime boundary

D11 is a preview-only typed field on ScanProposal, derived from validated CAD
observations. Neither normalize nor preview mutates Project SQLite, existing
CableSegments, Conduits, cable/box allowance, DALI topology, DWG or AutoCAD.
The existing ordinary synchronization and selection/apply behavior is
unchanged in this stage; D11 issues do not silently remove accepted topology
or replace accepted assignments.

## Still OPEN

1. Resolve and persist actual split physical segments and per-side route facts
   only when path ownership is known; otherwise localized Requires Attention.
2. Safely synchronize individual MOUNT_WAY/GOFRA properties with owner-aware
   three-way roundtrip, retaining approved historical segments and Conduits.
3. Preserve zero extra splice allowance at uninterrupted transit boxes.
4. Integrate already-approved Q03/Q06 Conduit sharing and unique-boundary
   length accounting without interpreting same GOFRA_ID as sufficient proof.
5. Integrate Q04/Q05/Q08 geometry from the dependent #218/#231 stack.
6. Full locked suite, controlled actual database migration and approved
   Windows/AutoCAD/DWG acceptance remain separate gates.

No merge to main, release/tag, catalog/schema version change or live migration
is authorized by this D11 draft checkpoint.
