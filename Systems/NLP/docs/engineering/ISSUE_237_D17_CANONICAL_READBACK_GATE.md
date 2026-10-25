# NL Project 3.1 — Issues #235/#237 D17: canonical readback safety gate

## Scope and evidence

D16 [Draft #254] stores an immutable prepared line-level D15 quantity in
`cable_transit_line_commit` (draft schema17). The existing production length
service `cables/recalculation.py` continues to calculate from ordinary
electrical `CableSegment`, storing results in `cable_length_fact`.
It can legitimately recompute that record on edits, so copying a prepared
total there and treating it as stable is **not safe**.

D17 is a deliberately narrow **readback integration**. It uses no schema
migration and does not change the existing calculation source, quantities,
catalog or Conduit assignments.

## New explicit API

`cables/transit_canonical_readback.py::review_prepared_transit_for_canonical`
and `CableService.review_prepared_transit_line(...)`.

Requires the full D15 approval inputs again, the **actual D16 batch SHA**
and explicit `confirmed=True`. Read-only transactionally consistent
checks against current Project state:

1. D16 receipt exists, is `PREPARED_APPROVED`, has matching complete batch
   SHA and matching D15 single-line approval SHA (real ends, geometry,
   route policy, line additions, manual replacement).
2. Active CableLine and unchanged `row_version`; original electrical
   `CableSegment` source/target IDs and row version still match.
3. D13 approved route exists and SHA matches the supplied physical evidence.
4. Current canonical `cable_length_fact` row identity and version are
   identical to those at D16 approval (including when no fact existed).
   Manual/extra values match *numerically*; invalid legacy Decimal is REVIEW.
5. D15 preview is rerun: D14 still checks all accepted BOX transit members,
   unbranched single-edge route, physical segment evidence and ordinary/BUS
   `GOFRA_ID` collisions.
6. The **complete stored D16 quantity breakdown** must match the freshly
   recomputed, approved whole-line D15 result (geometry, route factor,
   board/box/endpoint ends, additional, raw, automatic, final and source),
   rather than trusting an unvalidated persisted number.

Result is either `VERIFIED_READBACK_ONLY` with prepared and existing values
**separated**, or `REVIEW` with deterministic issue codes. Both leave
`authoritative_m=None` and `conduit_quantity_m=None`.

## Not a release / why no canonical publication yet

The rev17 receipt stores a SHA but **not sufficient independent proof**
that real DWG geometry, termination kinds and per-side mounting have remained
unchanged since user approval. D15/D14 currently check accepted BOX
`CABLE_TRANSIT` membership but no live AutoCAD scan, accepted endpoint
geometry refresh or approved per-side CAD writeback. Numeric parity cannot
replace source freshness evidence or publication revocation semantics.

Furthermore legacy recalculation and specification paths are not revision
aware. Publishing a value into `cable_length_fact` without resolving these
paths can create a ghost source and double-count reserves. For these reasons
D17 does **not** activate `VERIFIED_READBACK_ONLY` candidates as
specification lengths. This remains an OPEN production gate.

Remaining work: prove live/accepted source freshness and exact endpoints,
implement revision-aware canonical quantity source and selective activation/
revocation across all consumers, ordinary+BUS shared Conduit physical
identity (Q03/Q06), multi-edge branched coverage, #218/#231 runtime policy
adoption, DWG↔Project per-side route sync, full locked regression and
Qt/WebView failure, authorized real DB verified backup/migration/startup smoke
and Windows AutoCAD acceptance. No merge to main, actual SQLite/DWG change,
release, catalog or schema revision in D17.
