# NL Project 3.1 — D20 forced full AutoCAD bridge scan / live readiness contract

Existing Issues **#235 / #237**; stacked after D19 Draft #258.
Source of truth: `main` plus Draft stack; no `main` merge.

## Verified design boundary

D19 compares a *supplied* `CadObservationBatch` with accepted DWG
observations/approved BOX and endpoint geometry. A caller can replay an old
batch; it cannot be treated as a verified current AutoCAD source.
D20 connects that readback to an existing concrete
`cad_sync.bridge.AutoCadBridgeClient` and requires a **forced, non-incremental**
full read. The existing ordinary, cached/incremental scan remains unchanged.

`AutoCadBridgeClient.read_fresh_observations_with_witness(CadReadRequest)`:
- requires explicit exact document identity and positive deadline;
- discards any existing observation cache;
- reads STA bridge's active document identity/state BEFORE and AFTER,
  refusing unsaved or dirty (`DBMOD != 0`) documents;
- obtains the complete source fingerprint/handle order before and after;
- always issues the real `operation=scan` command (not CACHE_HIT, DELTA or
  fingerprint-only shortcut);
- fails if document state, binding, fingerprint, handle set/order or item
  count changes during scan;
- independently parses source fingerprints and compares every returned
  handle's name, layer, coordinates and raw attributes against the actual
  full scan output; fails if one side disagrees;
- returns `FreshCadReadWitness` with SHA-256 over the in-memory COM scan
  identity and signature inventory, and explicit
  `proves_durable_file_identity=False`.

`cables/transit_live_bridge_gate.py::review_transit_from_active_bridge`
and the lazy `CableService.review_live_transit_from_bridge`:
- require a concrete bridge client, exact selected line set,
  explicit document identity and confirmation;
- use all current CAD contract block definitions via `load_contract()`;
- calculate D18 canonical source snapshot before and after the bridge read;
  if Project changes concurrently, add a blocker;
- feed the forced full bridge batch directly into D19 + D18; no call path
  accepts an arbitrary old batch as trusted;
- remain `status=BLOCKED`, `can_publish=False`,
  `proves_disk_dwg_freshness=False` even after consistent in-memory COM
  data. This gate **never** writes DWG, `cable_length_fact`, `Conduit`,
  electrical `CableSegment`, reports or specifications.

## Why activation remains blocked

The STA bridge snapshot proves a stable *open-document in-memory read
sequence*, not an independent byte-for-byte hash of the underlying disk DWG
nor its continued validity after verification. No transaction spans external
AutoCAD memory, Project SQLite, and all quantity consumers. Production
activation/revocation still requires approved source-token lifetime rules,
subsequent live Windows/real-DWG acceptance, explicit physical termination
freshness, branch/multi-edge support, Q03/Q06 ordinary+BUS shared physical
Conduit ownership, and revision-aware source selection across
`recalculation`, `effective_length`, line cards, specifications and AV.

Tests execute mocked bridge IPC responses with synthetic CAD fixtures,
including dirty/unsaved document, changed pre/post fingerprints, mismatch
between fingerprint and full scan, a stale incremental cache, and Project
changes during the scan. **They are not Windows/AutoCAD live acceptance.**
No schema/catalog changes in D20; stacked D16 draft schema17 still needs
separately authorized actual working SQLite verified backup→official
migration/catalog successor→startup smoke/restore. The Qt/WebView
`0x80000003` blocker and full locked tests remain OPEN.

No new issue, no release/tag/merge, no live SQLite/DWG/AutoCAD or installed
NL Project changes. PR must remain Draft and #235/#237 OPEN.
