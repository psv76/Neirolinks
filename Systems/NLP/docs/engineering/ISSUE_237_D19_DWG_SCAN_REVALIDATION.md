# NL Project 3.1 — D19 accepted DWG observation revalidation gate

## Intent / limits

After D18 #257, the accepted Project snapshot has a stable SHA but cannot
establish whether the user's DWG file has changed. D19 adds a **pure read-only
comparison** of caller-supplied current CAD observations with persisted
accepted DWG scan observations, verified Project owners and explicit D13
physical endpoints/BOX geometry. No AutoCAD session or real DWG is available
in this cloud-only stage, so test fixtures are synthetic.

An in-memory `CadObservationBatch` is **not authenticated as having originated
from a current open AutoCAD file**. A saved or replayed old scan can match.
D19 therefore never authorizes canonical quantity publication.

## New opt-in APIs

`cables/transit_dwg_scan_lineage.py`:
- `compare_current_dwg_observations(connection, approval, current_batch, confirmed)`
- `plan_dwg_transit_revalidation(engine, requests, selected_line_ids,
  supplied_batches, confirmed)`

`CableService.review_current_dwg_transit()` and
`CableService.plan_current_dwg_transit_revalidation()` use lazy imports to
preserve the existing CAD/cable startup import boundary.

### Strict comparison scope

For every D13 approved BOX waypoint and non-INTERNAL_SOURCE electrical
endpoint:

1. Resolve an unambiguous active, accepted Project `field_device` owner;
   for an endpoint, use the canonical `cable_topology_endpoint` →
   `cable_point` → `cable_point_field_device` mapping.
2. All required owners must have stable unique DWG `entity_handle` and one
   shared `dwg_document_binding`. Confirm its Project status and exact
   `document_signature` versus the supplied batch identity (not path guess).
3. Select the latest persisted **ACCEPTED** `dwg_scan` for that binding,
   and the corresponding stored `dwg_observation` by each owner handle.
   No accepted scan, missing owner in scan, or duplicates block the gate.
4. Exact block name, layer, all raw attributes and planar X/Y must match
   between persisted accepted observation and supplied current observation.
   Only selected owner handles enter the digest; other devices don't quietly
   establish or overwrite a route.
5. Physical BOX observation XY plus `MOUNT_HEIGHT` must match the D13
   `route.box_positions`, and the corresponding `BOX_ID` and
   `CABLE_TRANSIT` must match accepted Project fields.
6. For each non-internal-source endpoint, the current CAD XY and
   `MOUNT_HEIGHT` must match the independently approved D13
   `VerifiedLocation`. This catches accepted-scan/approved-geometry
   mismatches that D15 arithmetic alone cannot detect.
7. Return a deterministic SHA of the selected accepted vs supplied observed
   handles, their names, layers, coordinates and raw attributes. These are
   **subset scan fingerprints**. The persisted `dwg_scan.content_sha256`
   hashes the earlier full CAD batch, not the bytes of a current DWG file.

An exactly matching sample returns `HISTORICAL_LINEAGE_MATCH_ONLY` and no
comparison issues; missing/changed inputs return `REVIEW` with deterministic
codes. Both permanently return
`proves_live_dwg_freshness=False` and
`authorizes_quantity_publication=False`.

### Combined D18/D19 plan

`plan_dwg_transit_revalidation` requires an exact line-ID selection and
corresponding batch mapping; it runs D18 readback and adds D19 observation
lineage. The combined plan is always `BLOCKED` and `can_publish=False`.
It adds `D19_LIVE_CAD_BATCH_PROVENANCE_NOT_ATTESTED` and
`D19_ALL_QUANTITY_CONSUMERS_NOT_ACTIVATED` regardless of a matching
historic scan.

## Important proven counterexample

The isolated D13 fixture approves the target TRACK at X=1200 mm while its
persisted DWG observation is X=100 mm. D15 whole-line arithmetic accepts
the separately user-reviewed location, but D19 now detects
`D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG`, **rather than silently
treating an unrelated accepted scan as proof of physical route accuracy**.
A separate synthetic test changes the reviewed location to match the
original CAD observation and verifies successful *comparison only*, never
quantity publication.

## Still OPEN

1. Real Windows/AutoCAD fresh CAD read, proof of opened document identity,
   timestamped source fingerprint, no-save inspection, and repeatable
   readback tied to an immutable acceptance token; no inference from a
   user-supplied or cached batch.
2. Signed/immutable actual device-end inventory and physical span route
   reconciliation, including multi-edge and branches.
3. Revision-aware activation/revocation across *every* canonical consumer:
   legacy cable recalculation, length facts, line cards, specification,
   AV HDMI and speaker lengths and any cached demand.
4. Typed shared ordinary/BUS Conduit physical boundary ownership and Q03/Q06
   measurements, #218/#231 full line policy and rounding.
5. Full locked Qt/WebView acceptance and the previous `0x80000003` crash;
   separately approved working SQLite verified backup→official migrations
   (draft schema17 from D16)→catalog successor if needed→startup and restore
   drill and live Windows/real DWG acceptance.

No new issue. Issues #235/#237 remain OPEN. No merge, schema or catalog
change in D19, release, `main`, actual SQLite/DWG/AutoCAD or installed NLP
modification. PR remains Draft.
