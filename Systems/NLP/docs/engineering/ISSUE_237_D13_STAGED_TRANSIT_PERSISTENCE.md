# Issue #237 / #235 — D13: approved physical transit staging (not live deployment)

## Canonical scope

D13 is stacked on D12 #250 and the approved §§3.1, 5, 8–12 of
`docs/product/22_CABLE_LENGTHS_AND_CONDUITS.md`.

D13 introduces a deliberately **separate**, additive physical evidence store
(`cable_transit_route` and `cable_transit_span`) in draft schema revision
`000000000016`. This is not an electrical `cable_segment` and is **not**
a replacement for the accepted legacy topology, existing Conduits, cable
length facts or the specification.

## Explicit acceptance API

`ApprovedTransitEvidence` holds confirmed physical waypoints from D12,
an existing Project `cable_line` and its exact electrical `cable_segment`,
the expected electrical endpoint IDs and row version, confirmed geometry,
the per-hop `MOUNT_WAY/GOFRA_*` choices, approved calculation policy
and a nonempty approval record.

`approved_transit_sha256()` hashes these exact typed fields under a D13
versioned canonical contract.

`persist_approved_transit(engine, evidence, approved_sha256=..., confirmed=True)`:

- requires exact SHA, nonempty approval note and an unambiguous continuous
  chain; never treats a transit BOX as an electrical splice;
- recomputes the D12 result and accepts only fully MEASURED routes, no guessed
  geometry, missing data or unapproved individual segment route;
- verifies an active Project CableLine, exact source/target identities,
  row-version of its existing electrical CableSegment and the accepted
  active `EL_BOX_OUT_100x100` owner with the matching transit token;
- stores the physical chain and per-span approved properties atomically in an
  independent transaction; an injected failure during the second INSERT
  rolls back the complete chain;
- exact reapply is idempotent; an edited approved SHA requires separate
  conflict review rather than replacing accepted records;
- records a `proposed_gofra_id` per span, **not** an actual
  `conduit_segment_assignment` or canonical `Conduit` relationship;
- rejects reuse of an existing canonical `Conduit` designation whose boundary
  cannot be proven by this stage and rejects conflicting boundaries for a
  previously staged designation.

## Schema/migration

Revision 16 is an additive, zero-backfill migration on top of revision 15:
no existing `cable_segment`, `cable_point`, `conduit`, `field_device`,
historical wire topology, catalog or technical decision is rewritten.
Use **only** the normal `upgrade_database` API after independently
verified backup. A populated D13 table blocks downgrade, preserving accepted
physical evidence; an empty store can downgrade with verified backup.

**Note:** In this GitHub/cloud stage, migrations and backup/downgrade tests run
**only** on disposable, synthetic SQLite. There is no permission to migrate
the actual working database or call this PASSED on real data.

## Open gates (no overclaim)

D13 is an explicitly invoked *staged approved record* API; it is **not**
called automatically by ordinary DWG scan/apply and not used in live length
or Conduit quantities. No production UI, automatic per-side CAD roundtrip,
physical endpoint type at the main CableSegment layer, Q03/Q06
ordinary+BUS shared Conduit merge, #218/#231 formula integration or actual
Windows/AutoCAD/DWG acceptance is implemented here.

Before enabling live mutation/reporting: full locked regression, approved
restore drill, per-project catalog successor if necessary, verified-backup
to schema head 16 through the official migration API, startup smoke on the
actual working SQLite, selective Project↔DWG replay/rollback and explicit
owner approval must all pass. `main`, installed NL Project, user data, DWG,
AutoCAD, release/tag and TechDocs must remain untouched until then.
