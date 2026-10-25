# D23 — CAD contract compatibility and #255 release gate

## Proven observations (2026-10-24)

- Machine contract in `main`: `3.0.0`, 71 approved block names.
- Machine contract in this D23 integrated candidate: `3.2.0`, 72 approved block names. Added `CABLE_OUTLET_BUS` and the `BUS_OUTLET` profile; the old block-name set remains.
- Expanded synthetic CI [run 40093488631](https://github.com/psv76/Neirolinks/actions/runs/40093488631) passed every selected shard, including 298 CAD-sync tests. This does not prove legacy DWG compatibility or Windows COM behaviour.
- The candidate machine contract still has `VENTILATION` and `HEATING` as independent functional groups, fixed explicit layer allow-lists and `AV` on its legacy named layer.
- `cad_contract/catalog.py::groups_for_layer` performs exact membership in `rule.layers`, rather than parsing the `GGG_<suffix>` layer grammar accepted in Issue #255.

## Outstanding mandatory conditions

Issue #255 is a **separate task/PR**. Its target rules are not incorporated by this D23 integration candidate. Before a 3.1 release:

1. Implement numeric group prefix parsing (100–900), arbitrary valid suffixes including Cyrillic and interior spaces, strict rejection of missing/whitespace-padded suffixes.
2. Combine `HEATING` and `VENTILATION` into `HVAC=600`; make `AV=700` while keeping free-text AV `CABLE_ID`, `BOARD_AV`, existing AV identity.
3. Allow logical `DALI_GROUP` on `300_*` or `400_*`, no required `DALI_GROUPS`; preserve DALI and physical-track contracts.
4. Filter by work-layer name **before expensive COM reads**; retain incremental scan and fail closed against silent destructive reconciliation when previously seen inserts leave the selected set after layer changes.
5. Test against fixtures including existing DWG layer identities, unknown/old rooms, existing manually confirmed quantities and BUS/conduit assignments; do not rewrite live DWG or force a legacy migration.
6. Execute locked Windows/AutoCAD COM/Qt checks and authorized backup + migration/catalog startup/restore acceptance if required.

## Release decision

**BLOCKED** for release; no claim of #255 completion or Windows/live acceptance. The additive 71→72 contract check establishes only inventory preservation, not semantic compatibility. Do not merge this D23 stack or activate new canonical quantities based solely on Linux green CI.
