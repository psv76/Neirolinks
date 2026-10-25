# NL Project 3.1 — D18: activation-readiness / accepted Project source fingerprint

## Status and current source of truth

D17 [Draft PR #256] verifies D16 whole-line prepared quantity readback
against accepted Project facts. It does **not** establish that real external
DWG geometry, BOX coordinates, or physical cable termination classes have
been re-scanned since approval. The D17 result `VERIFIED_READBACK_ONLY`
is not proof for a canonical publication.

D18 is intentionally a **read-only, fail-closed** readiness gate on top of D17
(#235/#237). No publication or activation code exists in this stage.
`main`, actual Windows DWG/AutoCAD, catalog, working SQLite and releases
are not touched.

## New API

`cables/transit_activation_readiness.py` exports
`TransitActivationRequest`, `TransitLineActivationReadiness`,
`TransitActivationPlan` and
`plan_transit_activation(engine, requests, selected_line_ids, confirmed)`.
`CableService.transit_activation_readiness()` exposes this through a
lazy import to prevent the established `cad_contract/cad_sync/cables`
startup cycle.

Selection is exact, unique and within one Project. Calls never mutate SQL.
For each line the gate rechecks:

1. D17's exact D16 batch SHA, current electrical CableLine/Segment,
   `cable_length_fact` manual/extra and accepted D13/D14/D15 facts.
2. A deterministic `project_source_sha256` over *accepted Project*
   topological endpoint owners and their logical identity, point location,
   revision and DWG observation ID, plus all mapped active field devices,
   active transit BOX normalized data/row_version, binding IDs/signatures
   and the physical BOX identity inventory. The source digest changes when
   these accepted facts change, even if the D17 arithmetic happens to remain
   equal. Unrelated Project devices are not included in a line fingerprint.
3. Missing/ambiguous BOX ownership, incomplete canonical endpoint references,
   missing or multiple accepted DWG document bindings are explicit blockers.
4. The final `plan_sha256` binds the exact selected set, D16 batch IDs,
   the new Project fingerprint, confirmation flag and unresolved blockers.

`project_source_sha256` **is not an external DWG fingerprint**. It proves
only what accepted Project SQLite currently holds; a previous binding
signature, observation ID or scan record cannot establish that a user's
DWG file has not subsequently changed outside NL Project.

## Explicit blockers

All D18 plans return `status=BLOCKED`, `can_publish=False` and
`authoritative_cable_m=None`/`authoritative_conduit_m=None`. These
are intentional open implementation and acceptance gates, not user data errors:

- `D18_CAD_LIVE_SCAN_AND_ROUNDTRIP_NOT_VERIFIED`: no approved current live
  AutoCAD scan/roundtrip evidence tied to the D16 quantity and exact DWG
  source geometry.
- `D18_TERMINATION_SOURCE_FRESHNESS_NOT_VERIFIED`: D15's physical
  board/endpoint end classification is reviewed evidence, not a live
  synchronized physical termination contract.
- `D18_CANONICAL_RECALCULATION_SOURCE_SWITCH_NOT_IMPLEMENTED`: existing
  `cables/recalculation.py` still recalculates the electrical segments and
  may overwrite `cable_length_fact`.
- `D18_ALL_QUANTITY_CONSUMERS_NOT_REVISION_AWARE`: current cable cards,
  effective length, specifications and AV selections do not share a
  revisioned activation/revocation state. D18 exports an explicit audit
  inventory of those consumers.
- `D18_CONDUIT_ORDINARY_BUS_SHARED_OWNER_NOT_VERIFIED`: Q03/Q06 shared
  physical ownership of Conduit across ordinary cable/BUS is not proven.
- `D18_LIVE_ACCEPTANCE_AND_RESTORE_NOT_PERFORMED`: full locked tests,
  Qt/WebView crash, real working SQLite backup→official migration/catalog
  successor→startup smoke/restore and Windows/real DWG acceptance are open.

D17 stale owner / BOX / manual / D16 breakdown errors propagate as REVIEW
reasons into the D18 BLOCKED decision. Passing D17 only removes that class of
blocker, **not** the D18 release blockers.

## Open next gate

A future implementation must provide verified current source witness with
actual DWG checksum/scan and accepted per-side geometry, independently
approved board/end classification, a single revision-aware canonical quantity
source and safe activation/revocation for every consumer, including
specifications, AV and reruns of legacy recalculation. It must prove no
regression on manual overrides or legacy Conduit, handle branched lines and
shared ordinary/BUS Conduit correctly, and pass full locked/Windows acceptance.

No schema migration or catalog release is made in D18 (stacked D16 Draft
schema 17 remains uninstalled). `main`, actual SQLite, DWG and AutoCAD
remain unchanged. Issues #235/#237 and PR remain open.
