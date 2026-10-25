# NLP-255-C7A-CONTRACT-MAPPING — resume2

## Intermediate persistence after usage-limit interruption

- status: **PARTIAL**
- start_sha: `040db57ee5ef22d1dcffbfacdc27dcd910a71eb8`
- branch: `feature/nlp-255-c7a-contract-integration`
- base_sha: `1b3d79de5e216e4254eea1ecc488a58802b8b6d2`
- This intermediate commit preserves the six surviving implementation/test/doc
  changes plus this checkpoint before further work. Final tested/head SHA and
  results will be appended after verification; no runtime acceptance claimed.

Inspected git status and every changed path. catalog.py and the new
test_numeric_contract_mapping.py survived. The rejected edit to
test_layer_groups.py did not execute: that file remains identical to HEAD.
No reset, clean, clone or removal performed.

Prior-run evidence (before this resumption): new targeted tests 57 passed;
existing selected suite 375 passed / 8 failed: seven known baseline failures
plus the old C2 inventory test referencing removed HEATING/VENTILATION groups.
No fresh verification yet. A narrow documentation line-ending cleanup is also
pending; unrelated physical DALI text must remain byte-identical to base.

next_action: Update the C2 inventory test for the approved HVAC migration,
preserving both former device sets, remove incidental documentation line-ending
changes, then run C7A tests and report staged-versus-runtime limitations.

No validator/COM/sync or real DB/DWG edits. C7b not started.
