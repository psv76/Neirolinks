# #216 — read-only Q03 audit of physical Conduit boundaries

Status: **cloud code/test candidate only** (2026-10-30). This document is engineering evidence, not a replacement for accepted Q01–Q11 in Issue #216.

## Source and dependency

- Target base: `work/nlp-286-integration-20261029` / PR #301. The production `main` does not yet contain Routes B / atomic `route_commands.py`.
- Exact read-only physical identity / pure planner modules and regression test candidates reused from PR #222, `system/nlp/216-physical-bounds-plan`.
- A separate CI run must prove compatibility with the 2026-10-29 schema, catalog and PR #301; historical PR #222 test evidence alone is insufficient.

## Canonical rule

Q03 compares the unordered canonical pair `{A,B}` of typed Project physical-owner UUIDs. A line-local `cable_topology_endpoint.id`, visible `BOX_ID`, GOFRA designation, coordinates, route-length equality and even an explicit operator click do **not** replace identity evidence. Two consecutive physical sections can share a Conduit only where Q02 transit and permitted splitting are represented; do not fabricate an intermediate electrical junction.

The read-only loader inspects persisted ordinary `conduit_segment_assignment` and `bus_segment_conduit_assignment`, resolves actual same-project owners and reports `EMPTY`, `PHYSICAL_MATCH`, `UNRESOLVED` or `BOUNDARY_CONFLICT`. `PHYSICAL_MATCH` is **not** a technical approval for cable classes, fill, interference separation, diameter or final length.

## Critical gap in current PR #301

`cables/route_commands.py` validates same-project references, segment states, mount method, tube type/color/diameter, and receives the operator's `confirmed_same_physical_run`, but does **not** resolve the canonical Project physical span for each moved member. Existing tests' green results cannot certify Q03 across multiple different target points. The ordinary field-device and BUS DWG projection also need a complete atomic mirror/round-trip gate as documented in #229. In the read-only integration stage this candidate **does not enable, disable or change** any write operation.

The previously accepted operator merge of `146.PP20` and `147.PP20` (lines 204 and 205) demonstrates persistence, not canonical span equality. Do not retroactively modify this active Project from this audit. After Windows returns online, run the read-only audit against a verified backup/copy before any additional mass merges.

## Next gated work

1. Prove audit against current Qt/services + one SQLite copy of Bogdanovich; inspect unresolved and boundary-conflicting tubes with representative actual IDs (Q11).
2. Wire the audited physical span and approved compatibility provider to preview **and** atomic apply under the same SQLite transaction (not an untrusted preflight snapshot).
3. Require explicit positive class/mixed-network approval, validate all remaining members, provide transactional DWG-facing ordinary and BUS mirrors and fail-closed unknown owners. Add negative regression of different endpoints, same coordinates, partial overlap, shared BOX and BUS TRACK.
4. Prove preserved `segment_id`, Project/DWG reconciliation no-op, conduit final length and specification quantity once per `Conduit.id`.
5. Only then update/enable the production write commands as a separate reviewed implementation step with verified backup and user acceptance.

No migration, catalog change, working SQLite/DWG mutation or AutoCAD COM operation is authorized by this read-only candidate.
