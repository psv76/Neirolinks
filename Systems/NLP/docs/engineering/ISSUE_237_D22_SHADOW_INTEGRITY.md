# NL Project 3.1 — D22 shadow selection identity and readback integrity

## Recovery boundary

Accepted source remains main `8f566f7a1eddb2c7eb4242dd275cdd775ca79a89`,
canonical path `Systems/NLP`. D21 is the open stacked Draft PR #260,
head `ea66d8628f68bf1b3887c010aa98eaef2ec28a4a`, with successful
D21 CI run 40080663698. No D22 branch or PR existed at recovery.
D22 continues #235/#237 as a bounded fix on D21, not a production activation
stage. The dependency stack and all outstanding acceptance gates remain.

## Defects and bounded correction

D21 checked that all requests belonged to one Project but omitted that
Project from the selection hash. Identical line IDs, batch strings and mode
therefore produced the same token after changing only the request Project.
D17 independently checks persisted evidence for PREPARED_SHADOW, so this
finding is not evidence of a production write or an exploitable DB bypass.
LEGACY_ONLY does not run D17; its explicit selection approval must also bind
the intended Project.

The selection payload now includes `project_id` and uses domain marker
`NLP_D21_REQUEST_SCOPED_SOURCE_V2`. Existing ephemeral V1 tokens intentionally
require a new preview/confirmation. D16 persisted batch receipts are unchanged;
there is no migration or catalog/product version change.

The pure selector previously accepted a VERIFIED_READBACK_ONLY label plus
any non-null amount. It now checks the readback's own cable_line_id against
the selected owner, requires a finite nonnegative Decimal, and treats any
reported issue as blocking even with a success label. These are defensive
checks on internal D17 results, not acceptance of user-supplied evidence.
CableService still recomputes D17 itself.

Any invalid member leaves the entire selection on LEGACY, with the offending
reason recorded. Unknown legacy length remains None; zero candidate length
is valid. LEGACY_ONLY remains independent of candidate readback validity.

## Validation

The existing D21 workflow includes the extended
`test_issue237_d21_quantity_shadow.py`, so no duplicate CI workflow is added.
New regression cases cover both modes' cross-Project token replay,
permutation invariance, mode/batch binding, mixed Projects, wrong/missing
readback owner, None/string/negative/NaN/sNaN/infinite candidates, contradictory
success with issues, all-or-nothing fallback and zero length.
Existing service/specification tests retain canonical non-write, stale-owner,
manual length and preview/revoke checks.

Exact-head CI outcome is recorded in the D22 PR and existing Issues.
Selected Linux tests are not the full locked Windows/Qt suite. The prescribed
PowerShell checks are not run locally in this GitHub-only task; the existing
Windows Qt/WebView 0x80000003 gate remains unresolved.

## Unchanged gates and limits

No persistent ACTIVE/REVOKED source, procurement/export authorization,
canonical cable/Conduit quantity write, schema or CAD contract change.
Independent current disk-DWG identity and witness lifetime, all-consumer
revision-safe activation/revocation, real terminations, multi-edge coverage,
Q03/Q06 ordinary+BUS shared Conduit, #218/#231 integration, #255 layers,
full locked tests, separately authorized backup/migration/catalog/startup/
restore and Windows/AutoCAD/live DWG acceptance remain OPEN.

No local checkout or test-data directory is created. No new Issue, main merge,
real SQLite/DWG/AutoCAD access, installed application, TechDocs or release/tag
change. #235/#237 remain OPEN and this work remains Draft.
