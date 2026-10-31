# Issue #216 — BUS Conduit quantity preview (read-only, Q03/Q06/Q08)

Status: **candidate only; NOT approved for Specification, purchase, migration or write**, 2026-10-31. Source of truth remains Issue #216 / product contract. This branch builds on read-only physical audit PR #303 (itself stacked on Routes B PR #301). It must not be deployed alone or silently rebased without those dependencies.

## Verified Windows evidence: Bogdanovich House 2, project revision 48

All SQL was performed against `D:\NLP_work\issue216_stale_lengths_20261031.sqlite` (SQLite backup copy, `PRAGMA query_only=ON`), with SHA-256 unchanged before/after. Live SQLite and DWG were untouched.

- 417 active physical `Conduit`, among them 86 with `length_m_decimal IS NULL`.
- **80** auto-generated BUS conduits: each has exactly **one** confirmed, physical (`connection_kind=CABLE`) BUS segment, no ordinary CableSegment assignment, and Q03 `PHYSICAL_MATCH` canonical owner pair. The 27 BUS root segments with `source_endpoint_id=NULL` are resolved through persisted `bus.root_resource_id`; no guessed coordinate or physical owner.
- All 80 BUS segment geometry `G` are numeric, nonnegative and their `gofra_type`/`gofra_color` match the corresponding Conduit. MOUNT_WAY is 79 floor + 1 ceiling.
- **Five** more auto-generated conduits **364.PP20–368.PP20** are physically `EMPTY`: no current BUS/ordinary member. They are **BLOCKED**, not counted as 0 m, not automatically deleted.
- The additional shared ordinary `146.PP20` (204/205) is `BOUNDARY_CONFLICT`, `INCOMPLETE_SHARED`, out of scope for BUS preview and still lacks known physical shared length.

## Current product discrepancy

`SpecificationService._conduit_sources()` **skips** `path_json.origin=AUTO_BUS_SEGMENT`; `_bus_conduit_sources()` emits one `BUS_SEGMENT_CONDUIT` source per BUS segment with its raw `bus_segment.length_m_decimal`, **not** one measured `Conduit.id` quantity using Q08. For the current 80, this exposes **924.12936 m** of BUS segment G as tube demand rather than applying route factors and rounding per physical tube.

The project's saved settings are **2% nonlinearity + 5% bypass, q=1 m**. Pure `calculate_conduit_quantity(G, policy)` yields a **non-publishable preview** of **1,031 m** total across 80 single-member tubes, delta **+106.87064 m** compared with raw BUS geometry. This is **not a purchase recommendation or accepted Conduit length**, and does not imply changing legacy specification data now.

Examples:

| Conduit | Source BUS geometry G, m | Q08 preview, m |
| --- | ---: | ---: |
| 322.PP20 | 7.02656 | 8 |
| 323.PP20 | 2.00919 | 3 |
| 324.PP20 | 5.81341 | 7 |
| 327.PP20 | 10.51821 | 12 |

## Implementation boundary

`cables/bus_conduit_preview.py` has a pure, strict candidate planner and read-only SQLAlchemy loader. It requires canonical Q03 physical `PHYSICAL_MATCH`, one BUS cable only, confirmed BUS geometry, recognized protected MOUNT_WAY, matching type and color, no existing Conduit length; every missing input fails closed. It returns `CANDIDATE` or `BLOCKED`, with **`can_publish=False` always**. No new schema, catalog, mutable commands, Conduit overwrite or Specification change.

Remaining gates before quantities can be published or installed:
1. Prove the Conduit path really follows the corresponding BUS physical geometry and supplier length calculation, not just owner-pair identity; preserve Q03 and class compatibility.
2. Resolve five orphan auto-BUS conduits 364–368 without deleting real design assignments.
3. Design and test one quantity per **physical `Conduit.id`** including mixed BUS + ordinary, overrides, zero/unknown, and source navigation; remove separate per-BUS segment tubing source **only after** accepted full replacement, not in a narrow partial release.
4. Validate technical fill, conductor class, material, route and cable-channel exclusions. Do not infer mixed-network compatibility from `PHYSICAL_MATCH`.
5. Backed-up DB-copy integration and actual Windows acceptance, then a separately approved publication/migration gate. Never fill `146.PP20` automatically.

This document is evidence, not a competing source of accepted design rules.
