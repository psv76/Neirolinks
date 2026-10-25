# NLP #237 — D9 controlled legacy DALI mapping and recovery gate

Status: **Draft implementation; synthetic SQLite acceptance only**. Depends on stacked Drafts #246 (D8 read-only audit) and #245 (D7 physical DALI schema rev 15). Source of truth for production remains `main`; this document does **not** authorize merge or migration.

## Intended use

D8 creates read-only accepted-Project evidence, records a stable fingerprint and classifies rows as:

- **ALREADY_MAPPED** — canonical physical target/source already agrees with accepted data;
- **CANDIDATE** — physical mapping could be reviewed for explicit approval;
- **REVIEW** — unresolved source, ownership, bus, root, cycle or legacy collision.

**Neither CANDIDATE nor this document is automatic approval.** Only selected accepted `field_device.id` records whose whole chain is already mapped or jointly selected can produce a D9 plan. Any REVIEW row remains blocked.

## Exact two-step authorization API

`nl_project_2.cad_sync.approved_dali_mapping.preview_legacy_dali_mapping(engine, *, project_id, selected_field_device_ids)`:

- A read-only Project-scoped plan that includes full D8 SHA-256 fingerprint; immutable accepted `field_device`, DWG binding+handle, typed BUS identity and source; ordered proposed insert-only actions and an exact `plan_sha256` approval token.
- The caller must show the human reviewer the Project, all selected rows, sources, operations and `plan_sha256` before any attempt to apply. A `NOOP` denotes already mapped accepted evidence and never edits the existing link.
- An unselected/unmapped upstream physical BOX/TRACK, mixed addressed/physical cycle, duplicate owner or unverified root refuses planning.

`apply_approved_legacy_dali_mapping(engine, plan, *, approved_plan_sha256, confirmed, backup_directory)`:

1. Requires `confirmed=True`, an independently supplied approval SHA-256 matching the immutable plan, and managed SQLite revision **15**.
2. Re-runs the full selected D8 audit/plan read-only and refuses drift.
3. Creates a **new, verified SQLite online backup** via the established `create_verified_backup`: integrity-check, managed revision and backup SHA-256. Existing backup path cannot be overwritten.
4. Within **one transaction**, re-reads D8 evidence and verifies the same plan, then creates only missing `bus_physical_node` and typed `bus_physical_link`. Resolves source and owner from accepted Project rows; makes no changes to `field_device`, BusPoint address, `bus_segment`, conduit or lengths.
5. Raises on ambiguity/conflict or database failure, with atomic rollback; verified backup is retained. Returns inserted-node/link counts and `BackupReceipt` on success.

**This is an opt-in backend gate, not a deployed UI or general-purpose migration command.** It does not infer unknown source, override REVIEW, delete/replace accepted edges, renumber BUS_POINT_ID or repair old cable topology.

## Recovery contract

An accepted backup receipt supplies the SQLite backup path, SHA-256 and schema revision. The backup represents the state **before D9 application**. Restoration is **not automatic** and must never overwrite a user's live SQLite while NLP/AutoCAD or any writer is running.

For future Windows/real-DB acceptance, a separate approved recovery runbook must:

1. Stop all writers and retain both the current damaged database and the verified backup without overwriting either.
2. Verify source backup SHA-256 and `PRAGMA integrity_check`, `foreign_key_check`, schema revision and project identity.
3. Restore to **a new file/path**, not directly over the current working DB; verify startup and Project identity on the restored copy, then explicitly authorize any file switch.
4. If schema/catalog head changes, separately complete verified backup → standard migration API → permitted catalog successor → startup smoke **on the actual working database** before declaring full PASSED.

D9 presently tests only fresh temporary SQLite databases. It has **not** been authorized on a production/user database, and cannot satisfy this real-DB restore gate without explicit permission.

## Evidence and remaining release blockers

D9 CI: [GitHub Actions #40030130383](https://github.com/psv76/Neirolinks/actions/runs/40030130383), **34 selected pytest PASS** including D8/D7 regression, strict Ruff lint and format. Tests cover preview byte invariance, full/partial/no-op mapping, exact approval, stale owner, project isolation, real backup receipt, SQL trigger failure rollback, physical/addressable mixed loop; overlap earlier regression scopes.

Unclosed Issue #237: catalog release/successor and runtime schema compatibility with `main`, historical full inventory and approved ambiguous-row mapping, production verified backup and on-device migration, owner-aware UI, internal TRACK power/3YY-4YY cabling, CABLE_TRANSIT/conduit/length semantics, full locked suite/historical CAD fixture failures and Windows/AutoCAD/live DWG acceptance. No production `main` merge, installed NLP, real DWG/SQLite, TechDocs, tag or release NLP 3.1.
