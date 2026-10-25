# NL Project 3.1 — D21 reversible in-request quantity source (shadow only)

Existing Issues #235/#237; stacked after D20 Draft PR #259. All
implementation and test work is GitHub-only; no real DWG, AutoCAD or
working SQLite is available or authorized for production changes.

## Scope

D20 provides a forced full stable open AutoCAD bridge read *in memory* but
not a durable disk-file attestation or immutable source-lifetime contract.
D16/D17 hold approved candidate whole-line lengths for a restricted,
single-electric-edge physical transit chain. Legacy
`cables/recalculation.py::_recalculate_line_fact` still writes
`cable_length_fact` from electric segments, preserving an existing manual
full-length field. `CableService.effective_length` is the ordinary source
for real line cards and specifications. Silently persisting a PREPARED
candidate in its place risks ghost quantities, overriding recalculation
and source double counts.

**D21 introduces a request-scoped source selector for isolated preview
only**. It does NOT implement production ACTIVE/REVOKED persistence or
promote D16 receipt to canonical acceptance.

## New pure selector

`cables/transit_source_selection.py`:
- `selection_sha256(requests, selected_line_ids, mode)` binds exact unique
  line selection, D16 approval batch identifiers, one Project and
  `PREPARED_SHADOW` or `LEGACY_ONLY` intent.
- `make_shadow_selection` requires explicit confirmation and the same SHA.
  PREPARED_SHADOW requires freshly revalidated D17 status
  `VERIFIED_READBACK_ONLY` for *every* selected line and a non-null D16
  `prepared_final_m`. If any line is stale, **none** of the selected
  lines switches to the shadow source.
- The mode `LEGACY_ONLY` is a deterministic request-scoped revocation
  and resolves the original canonical length without modifying storage.
- Result shows canonical effective length, D16 candidate and preview
  effective length as separate values. Both mode results explicitly have
  `can_publish=False` and line-level `authorizes_publication=False`.

`CableService.preview_transit_quantity_sources` obtains the true
legacy effective length using existing `effective_length`; a missing
legacy calculation appears as unknown, not fabricated zero.
For PREPARED_SHADOW, it recomputes D17 against current D13–D16 data,
including changed cable edge, manual+additional quantities, BOX and
ordinary/BUS Conduit owner guards. No source is cached or installed on
the service. Standard cable cards, AV selection and effective_length
remain unchanged.

## Specification shadow using the same selector

`SpecificationService.preview_transit_source_specification` reuses the
CableService selector and the standard `_all_sources` pipeline. It creates
**copies** of CABLE_LINE sources whose unit is metres; it does not adjust
HDMI piece counts, BUS, Conduit, LED or any unrelated equipment sources.
A selected candidate changes only the in-memory projected quantity and
trace; pre-existing explicit `quantity_correction_decimal` overrides
are preserved. The result is visibly
`preview_only=True, can_publish=False` with both baseline and simulated
source rows and separately grouped preview cost. Default
`SpecificationService.build`, procurement, export and pricing stay on
the legacy source.

Revoking with the same approved selection in `LEGACY_ONLY` yields the
original baseline sources and quantities. No `cable_length_fact`,
`CableSegment`, Conduit, D16 receipt, specification override, working DB
or AutoCAD writes.

## Why production activation is still OPEN

D21 is not a persistent revisioned ACTIVE/REVOKED lifecycle and no report
or purchase may treat its results as authoritative. Remaining gates:

- Actual Windows AutoCAD live acceptance and independent current disk
  DWG provenance plus tamper-resistant time-limited source witness.
- Owner-approved physical terminations and per-side route geometry, full
  branch/multi-edge coverage; Q03/Q06 ordinary+BUS physical Conduit identity.
- Atomic ACTIVE/REVOKED canonical quantity source with optimistic revision
  fencing, recalculation-aware protection and consistent updates to all
  specification/AV/report/export consumers and caches. A rollback must
  restore the original legacy data without manual edits.
- #218/#231 calculation policy, full locked tests and existing Qt/WebView
  `0x80000003` Windows failure.
- Separately authorized real working SQLite verified backup, official
  migration to stacked D16 schema17, permitted catalog successor if needed,
  startup smoke, restore exercise, real DWG/AutoCAD acceptance.

No new Issue, merge to main, release, catalog or schema migration in D21.
Issues #235/#237 stay OPEN, PR Draft. Actual DB/DWG and installed app untouched.

## D22 follow-up

The [D22 integrity correction](ISSUE_237_D22_SHADOW_INTEGRITY.md) explicitly
binds Project identity in the V2 selection token and rejects mismatched or
invalid D17 readbacks. V1 ephemeral tokens must be previewed and confirmed
again; persisted D16 receipts and production quantities are unchanged.
