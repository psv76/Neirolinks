# NST approved deployment

Scope: GitHub Issue #87.

## Layers

```text
engineering source commit S
  controller profile
  object payload declarations
  approved-components snapshot
  resolver/schema
        |
        v
deterministic deployment manifest
        |
        v
future NST check/sync
```

The deployment manifest is generated **from an immutable source commit S** and is committed afterwards. This avoids a self-referential commit identity: rebuilding from the same S must produce byte-identical JSON.

## Component resolution

A controller profile requests a track, currently only `stable`. CI resolves the newest compatible entry from `Systems/NST/deployment/approved-components.json`.

The committed snapshot is not trusted merely because it is in Git. CI also verifies each entry against the published stable GitHub Release:

1. release is published, non-draft and non-prerelease;
2. tag resolves to the recorded immutable commit;
3. the single `nli-catalog.json` asset has the recorded GitHub SHA256;
4. the approved catalog contains the exact component/object/role/version;
5. the catalog's manifest commit/path/SHA256 equals the snapshot.

The deployment then embeds the exact component version, immutable manifest reference, immutable payload commit, target file set/SHA256 and required service actions.

## Object files

Object-specific files are declared in the controller profile as source/target pairs. Their SHA256 is calculated from source commit S. Mutable `main` is never an install source.

The pilot #87 profile deliberately has an empty `object_files` list: #87 proves the format/resolver. Completing the full ABF62SL object payload belongs to the field pilot #93.

## Offline verification

`nli.deployment.verify_offline()` accepts a local byte reader `(commit, path) -> bytes` and verifies:

- controller profile and diagnostics profile bytes from S;
- exact object file bytes from S;
- every component manifest against its pinned SHA256;
- component identity/version/object/role;
- immutable component payload commit;
- every payload SHA256.

No network lookup is required for this verification once the referenced Git objects are locally available.

## Future signatures

Schema v1 contains `signatures[]`. It is empty today. A future NEIROLINKS signing layer can add key ID, algorithm and signature records without changing the deployment's core identity fields or introducing a breaking schema migration.

## Safety boundary

#87 does not install anything, does not change live WB state, and does not make application-runtime health a deployment gate. Actual status/check/sync integration is #89.
