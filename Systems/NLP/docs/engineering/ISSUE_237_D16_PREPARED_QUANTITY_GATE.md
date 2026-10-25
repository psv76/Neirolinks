# NL Project 3.1 — #237/#235 D16: approved selected quantity PREPARE gate

## Gate outcome and non-goals

D15 #253 provides a complete, explicitly reviewed **single-edge whole-line**
quantity preview. D14 #252 rejects stale owners/BOX and unproven shared
ordinary/BUS Conduit. D13 #251 stores approved physical spans separately from
canonical electrical `CableSegment`.

D16 records only an **immutable prepared quantity commit**, not a released or
authoritative line quantity. The legacy `cables/recalculation.py` can still
recalculate the old electrical segment graph and overwrite
`cable_length_fact`; blindly storing the D15 preview in that table would be
unsafe (and would risk manual override, double counts and inconsistent
specifications). D16 explicitly refuses this automatic canonical mutation.

## Additive draft schema head 000000000017

`cable_transit_line_commit` links one prepared total to the existing Project
CableLine, approved D13 transit route and electrical segment and persists:
approval SHA bound to exact selected-line set and immutable input evidence,
current row versions of `cable_line`, `cable_segment` and
`cable_length_fact`, automatic/final quantities and an auditable breakdown.
Its state is `PREPARED_APPROVED`, never `PUBLISHED`.
No legacy backfill. Historical revision 7 recovery explicitly excludes the
rev17 table. A downgrade crossing rev17 with nonempty prepared records is
refused **before** SQLite DDL to avoid partial schema rollback.

## Explicit API and transaction

`cables/transit_quantity_prepare.py`:
`prepared_transit_batch_sha256(intents, selected_line_ids)` and
`prepare_approved_transit_quantities(engine, intents, selected_line_ids,
approved_batch_sha256, confirmed=True)`.

- All selected line IDs must correspond exactly to a unique supplied intent,
  within a single Project. Empty, foreign, unknown or repeated selection:
  no write.
- SHA binds all D15 approval evidence, end/geometry inputs, current expected
  Project row versions, manual/additional length and full selection. Explicit
  confirmation and independent acceptance note are required.
- The API checks active CableLine, the original electrical segment and both
  endpoint IDs, the source segment row version, and the current canonical
  `cable_length_fact` identity and row version. The approved additional
  length and manual replacement must match the existing persisted values
  **numerically**; neither is overwritten.
- D15 must again yield `APPROVED_PREVIEW_ONLY`, including D13 owner, BOX
  acceptance, per-side measurement and all D14 ordinary/BUS Conduit conflicts.
  A manual total alone cannot bypass missing physical evidence.
- Selected records insert atomically in one transaction. A failing member
  rolls the batch back; identical replay is idempotent; conflicting SHA or
  already prepared line rejects changes (no silent overwrite).
- `read_prepared_transit_quantities` reads the approved-but-unpublished
  snapshots; it does not change `CableService.effective_length` or
  specification quantities, and never assigns Conduit / writes DWG.

## Validation / separate real database gate

Synthetic, temporary SQLite CI covers schema16→17 verified backup, empty
downgrade, occupied downgrade veto, selection exactness, SHA tampering,
optimistic version and manual conflicts, canonical Conduit collision, error
rollback, idempotent replay, canonical rows unchanged and D15–D10 regression.
The selected test suite is **not** the full locked suite. In particular, the
existing local Qt/WebView `0x80000003` crash remains unresolved.

Before enabling actual canonical length publication or Project↔DWG automatic
apply: complete multi-edge/branched physical coverage, user-reviewed physical
end and geometry freshness, explicit per-side CAD roundtrip, Q03/Q06 typed
shared ordinary/BUS Conduit, #218/#231 runtime calculations and revision-safe
authoritative quantity integration. Actual working database schema migration
requires **separate authorization** and verified backup, official migration
API to head17, authorized catalog successor if needed, startup smoke on real
SQLite, restore drill and Windows/AutoCAD/real-DWG acceptance. No release,
merge, live SQLite/DWG/AutoCAD writes or TechDocs changes in this gate.
