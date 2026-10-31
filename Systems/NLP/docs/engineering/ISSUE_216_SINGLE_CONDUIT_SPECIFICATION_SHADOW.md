# #216 — one physical Conduit, one proposed Specification source (shadow only)

Status: **2026-10-31, NON-PUBLISHABLE / DB READ-ONLY**.
Dependent stack: PR #301 (Routes B) -> PR #303 (Q03 owner audit) -> PR #313 (BUS Q08 read-only) -> this PR.
Not approved to change canonical Specification.build, export, procurement or user overrides.

## Engineering result on Bogdanovich SQLite copy

Project: `e2213b89-8cc3-424f-a4ec-d2028061a483`, revision 48.
Verified source: `D:\NLP_work\issue216_stale_lengths_20261031.sqlite`.
Read with `PRAGMA query_only=ON`; no writes to working DWG/SQLite.

Current specification has 332 `CONDUIT` ordinary + 80 `BUS_SEGMENT_CONDUIT`
sources (412 total); BUS physical tubes are omitted and represented by
segment-owned quantities, without physical tube Q08 route reserves/rounding.

The shadow returns exactly 417 `SpecificationSource` entries, **all**
`source_kind=CONDUIT` and each with a distinct `source_id=Conduit.id`:
- 279 `KNOWN_SINGLE`: one canonical physical ordinary member, persisted tube
  length carried forward without recalc or arbitrary replacement.
- 80 `CANDIDATE_BUS`: one physical BUS cable member per tube, canonical pair
  Q03 match, confirmed BUS G, matching material and color; project-specific
  Q08 2%+5% and q=1m gives **1,031 m** (G sum 924.12936m).
- 49 `BLOCKED_UNRESOLVED`: Q03 canonical owners are unproven or different,
  including shared `146.PP20` lines 204/205. These are **not** zero-metre tubes.
- 9 `BLOCKED_EMPTY`: five orphan AUTO_BUS 364–368 with no G and four
  ordinary 107,109,130,131 with **114m** of stored length but no member.
  Their current budget quantities remain untouched until intent is proven.

All `blocked` shadow quantities are **None**, not zero and not reused from
legacy BUS segment data. The grouped shadow can therefore show unknown totals
rather than a misleading purchase amount.

## Contract and release restrictions

`SpecificationService.preview_single_conduit_specification` reads and
constructs a new **separate** source stream, retaining pricing, product keys,
supply scope, explicit overrides and source navigation keys `Conduit.id`.
It never calls `build()` as a write, never replaces the existing export/source
stream, never writes `Conduit.length_m_decimal`, never changes Q03 assignments.

The returned object has `preview_only=True, can_publish=False`. For each
Conduit the result has a decision status, reason(s), and quantity; any unknown
G, ambiguous physical owner, mixed physical tube, missing BUS candidate,
duplicate identity, bad input or empty tube **blocks publication**. The
ordinary base-source and BUS legacy-source rows are retained side-by-side
solely for before/after trace and comparison. **Do not** publish a numeric
delta across legacy and shadow totals with blocked unknown sources.

## Remaining acceptance

1. Operator-approved Q03 physical proximity rule for switches sharing one
   physical installation box, with explicitly confirmed exception handling.
   Do not equate coordinates alone with canonical owner identity.
2. Proof that confirmed BUS segment geometry G is coextensive with each
   specific physical Conduit geometry; Q06 material/mixed-class compatibility.
3. Resolve empty tube provenance and four existing ordinary tubes in
   live purchasing Specification without deleting or assuming reserve intent.
4. Full DB-copy and Windows Qt/API acceptance of unified Specification rows,
   technical origin, overrides, aggregation, navigation and grouped unknowns.
5. Only then introduce separately reviewed **production cutover** from
   BUS_SEGMENT_CONDUIT to one Conduit-owned source stream and decide if
   any persisted lengths/migrations are required. No schema/catalog release
   is changed by this shadow.
