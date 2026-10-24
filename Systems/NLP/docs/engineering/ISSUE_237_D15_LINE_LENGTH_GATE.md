# D15 — explicitly approved line-level quantity preview

Stacked Draft on D14 #252 (`7d167e1458ce067e7eff332eb720bfa3d4d8ad0a`).
Existing Issues #235/#237 remain OPEN. This is the bounded intermediate step
allowed by the task, not an applied production recalculation.

## Normative and dependency evidence

- Product `22_CABLE_LENGTHS_AND_CONDUITS.md` §§3.1, 4, 5, 8–12:
  pure physical geometry; zero termination reserve at uninterrupted transit;
  additive percentages only on geometry; actual physical ends; additional length
  once; rounding once per CableLine; full manual replacement.
- D12 #250 provides explicitly approved per-side route/geometry measurement.
  D13 #251 stores separate staged spans (draft revision 16); D14 #252 checks
  current electrical owner/version, BOX acceptance and Conduit collisions.
- #218 introduces `cables/length_policy.py`. D15 imports that existing module
  and its 23 unit tests from #231 commit
  `ec7689c9827001d218d0e35bb9b81e56c79945e0`: module unchanged, test formatting only. No parallel arithmetic
  implementation or blanket merge of the Stage C runtime changes.
- #231 fixes CEILING to `R*1000`, removes TIMBER +0.5 and introduces revision-aware
  recalculation. D12 already measures these formulas in its isolated preview.
  Legacy `cables/recalculation.py` and BUS runtime integration remain separate.
- Q03/Q06: ordinary/BUS sharing needs proven canonical unordered physical
  boundaries and compatible assignments. D15 reuses D14 refusal for collisions
  with legacy canonical or BUS designations. It creates no Conduit or assignment,
  and produces no authoritative pipe quantity, even if labels match.

## New explicit read-only API

`cables/transit_line_preview.py::preview_transit_line(connection, approval,
approved_sha256=..., confirmed=True)` requires:

1. Exactly one staged route for a fully covered, single-electrical-edge line.
   Multi-edge/branched lines remain REVIEW; no inferred path or partial total.
2. Original D13 evidence matching the persisted approval SHA and current D14
   reconciliation. Remeasure geometry and compare every ordered stored span's
   key, boundaries, geometry and per-side mounting/pipe properties.
3. Two individually evidenced real terminations attached to the exact source
   and target endpoint IDs, with distinct physical-end identities and optional
   individual overrides. A transit boundary cannot be added as a third end.
4. Explicit whole-line policy, additional/manual length and approval note,
   all bound with the complete transit evidence in a separate versioned SHA.
   A boolean without the matching SHA is insufficient.

The caller must independently verify end classification and current physical
geometry. A SHA proves which inputs were approved, not their real-world truth.
There is no automatic physical-end discovery, approval UI, or automatic refresh
of approved room/BOX geometry in this stage. Do not call the API a live freshness
proof or enable it as a normal reporting source.

Only pure remeasured span geometry goes into the reused quantity kernel.
Stored D13 per-edge totals and corrected spans are never summed. Electrical
edge geometry is not added on top of its replacement physical-span geometry.
Each verified end, line addition and line rounding is applied once. A manual
total does not bypass missing-evidence gates.

Result: `APPROVED_PREVIEW_ONLY` with an auditable `CableQuantity` breakdown,
or `REVIEW` with no quantity. `authoritative_cable_m` and
`authoritative_conduit_m` are always `None`. This explicit API is not wired to
normal CableService, specification, journal, CAD sync or persistence writers.
No new schema, catalog, ATTDEF, electrical endpoint or release version.

## Validation and remaining gates

Synthetic tests cover the line formula, fractional rounding, manual/per-end
overrides, zero transit splice, repeat reads and unchanged canonical/staged
rows, missing/duplicate/foreign ends, approval tampering, stored span tampering,
stale edge, partial line coverage and ordinary/BUS Conduit collisions.
The imported #218/#231 tests include exact-multiple rounding, duplicate physical
segment/end identities, multiple real roots, three box ends and independent
Conduit arithmetic. D14–D10 and existing cable service regression remain selected
CI checks, not the full locked suite or actual AutoCAD acceptance.

Open before production application:

- canonical owner-aware per-side persistence and selective Project↔DWG replay;
- independently verified physical ends, current geometry, complete multi-edge
  coverage and explicit branch ownership without guessed routes;
- #218/#231 integration into ordinary/BUS recalculation with legacy revision
  safety and retained manual overrides;
- Q03/Q06 typed shared Conduit ownership, compatibility and one physical quantity;
- full locked regression and separate Windows/AutoCAD/real-DWG acceptance;
- separately authorized actual-base verified backup → migration/catalog successor
  if required → startup smoke and restore verification.

No merge, live database access, live migration, DWG/AutoCAD operation or release
is performed or authorized by this preview gate.
