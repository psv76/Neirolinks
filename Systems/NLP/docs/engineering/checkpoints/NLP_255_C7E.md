# NLP-255-C7E-FILTERED-SYNC-AUTHORITY — intermediate

status: PARTIAL (production filtered sync disabled)
start_sha: 93d69513b3103dad6525559ca6739f14f21e4def
base_sha: cbf557cc57c7824622e8b5ae9e5b94f24fdb3e22
branch: feature/nlp-255-c7e-filtered-sync-authority

Implemented canonical project/binding-bound diagnostic review, tracked handles from active field devices plus logical observations in accepted baseline scans, project/binding/owner recheck after CAD read, explicit full-confirmation requirement. Added point-of-write confirmed binding identity/project validation in _ensure_binding. C6 now also rejects diagnostic FILTERED_* provenance if flags are removed/flipped.

New integration tests exercise real preview/apply with disposable SQLite: 16 passed. No device/topology writes from partial data, no false deletion on moved-off-layer, genuine missing only from independent full fixture, no automatic removal, tampered flags and wrong/stale project/binding blocked. Full regression/static checks pending.

Architecture limitation: service preview computes MISSING_DWG_INSERTION and topology absence; _repair_stale_topology_endpoints and _prune_stale_snapshot_points can remove projections. Bridge commands are short-lived, and no DWG transaction lease spans preview/read -> SQLite apply. Two equal census maps/DBMOD cannot close that race. Existing full read remains supported; no diagnostic flags promoted and no filtered mode enabled in scan_active/UI.

next_action: complete full cad_sync regression plus C7b targets, static checks, final checkpoint/commit/push and Issue #255 report. Need separately approved stable DWG read/commit boundary before filtered sync activation. No release/main merge/real DWG or SQLite changes.
