# Issue #237 — D10: internal 4YY power membership of DALI rail lights

Status: **stacked Draft / synthetic SQLite acceptance**. Source of truth production is still `main`; do not migrate or merge without review. Existing CAD authoring JSON 3.2.0 (72 definitions) is unchanged.

## Current bounded behavior

For accepted `TRACK_DALI` whose Project field evidence includes `TRACK_ID=TRACK.NNN`, `BUS_ID=9YY`, and an assigned ordinary external power feeder `CABLE_ID=4YY`, a `LIGHT_TRACK_DALI_48V` may reference:

- `CABLE_ID=4YY` — same 4YY cable family/feeder as the rail owner;
- `CABLE_SOURCE=TRACK.NNN` — an **internal, unmeasured membership** on the physical track;
- `BUS_POINT_ID=9YY.ZZZ` and `BUS_SOURCE=TRACK.NNN` — *separate* addressable physical DALI control connectivity.

The original CAD contract's optional fields are used unchanged. `TRACK.NNN` is permitted as a `CABLE_SOURCE` only for the `LIGHT_TRACK_DALI_48V` family. Other cable-source grammars are not broadened.

The new `TrackInternalPowerLink` is a typed **derived Project projection** (accepted `field_device.id` owners, track ID, 4YY base, DALI bus). It is not a physical cable run and has **no calculated length, `GOFRA_ID`, conduit or PSU value**. The existing accepted `field_device.normalized_fields_json.CABLE_SOURCE` supplies Project→DWG readback. There is deliberately **no new rail-power table or schema revision** in D10.

## Physical source separation

- One ordinary `cable_line` 4YY may connect the board/PSU feed to the physical track (its actual external termination).
- A track and its rail light never collapse into the same `cable_point` just because both use a bare `CABLE_ID=4YY`: the track uses its **existing TRACK_ID**, the DALI light uses its **existing BUS_POINT_ID** for unique point identity.
- The selected light gets **no extra `cable_segment`**, generated metre value or conduit from `CABLE_SOURCE=TRACK.NNN`; existing DALI `bus_physical_link` controls its BUS_SOURCE.
- Any previously accepted external cable segment to the same lamp refuses with `TRACK_POWER_LEGACY_SEGMENT_REQUIRES_REVIEW`. Any previously accepted collapsed 4YY track point (e.g. logical identity `401` rather than `TRACK.023`) refuses with `TRACK_POWER_LEGACY_POINT_REQUIRES_REVIEW`, rather than silently renaming/pruning accepted topology.
- Selecting only a lamp or scanning an incomplete DWG does not authorize finding/creating its source. A unique existing ACTIVE Project `TRACK_DALI` owner must exist with matching 4YY cable base, BUS_ID and explicit BUS_SOURCE. Cross-bus or missing/ambiguous owner refuses transactionally.

## Operational gate remains OPEN

D10 is an incremental integration test on new synthetic SQLite, **not full electrical track design**. It cannot infer PSU location, track internal feeder conductor lengths, load allocation across track segments, resistance/voltage drop, conduit, CABLE_TRANSIT, or approve legacy renumbering/graph repair. Confirm user-approved migration mapping in D8/D9, verified backup and normal schema migration API/catalog successor/startup smoke on the actual working database before live deployment. Full locked tests and Windows/AutoCAD real-DWG acceptance remain separate.

No changes to `main`, production application, TechDocs, CAD contract JSON, package/catalog schema head, real SQLite/DWG, AutoCAD, tag or NLP 3.1 release.
