# 05_31 Ivolga — HHM 3.1 controlled retry plan

Temporary operator workspace. Not a product release.

## Deployment policy

Decision 26.09.2026:

**NLI is the standard installer/updater on every managed NEIROLINKS WB.**

Manual replacement of managed HHM files is removed from the normal workflow. A controller that does not yet have NLI must first be adopted into NLI; all later managed updates/rollback go through NLI.

For Ivolga:

- boiler already has NLI 0.1.9;
- gazebo does not yet have NLI and is the next controller to adopt;
- gazebo HHM 3.1 will be installed only after NLI adoption.

## Fixed identities

- reviewed PR #73 source head before field-doc commits: `5efce9783886a991d9d1b9008860f9309b1d5559`
- HHM 3.1 immutable runtime: `20af0c29ed37130a5d4ff051ff1fb5984a5f8193`
- gazebo 3.1 manifest SHA256: `c3de99685ba6995ed2b51fcd74d1bc20c3c416e293691c9b42689cc857547261`
- boiler 3.1 manifest SHA256: `b8c45743c4d290949e42f0b459804b1e545087a788383fb0cb816edc0379d444`
- approved NLI: `0.1.9`
- NLI release tag: `nli-approved-0.1.9`
- approved package SHA256: `5042800dc01507742904b039d6d6539038255067aeec5b88603508bba5e718d5`
- bootstrap SHA256: `fb46edd0071dbe7c1c410f65dce97af66d1e96a23465a9da6895d189fc0e634c`

Do not merge PR #73 before live acceptance.

## Canonical filesystem

Persistent configuration on live WB is under:

`/mnt/data/etc`

Use these paths for field inventory and persistent NLI configuration:

- `/mnt/data/etc/wb-rules/`
- `/mnt/data/etc/wb-rules-modules/`
- `/mnt/data/etc/wb-mqtt-serial.conf`
- `/mnt/data/etc/wb-mqtt-db.conf`
- `/mnt/data/etc/neiro/nli/`

NLI manifests intentionally use logical `/etc/...` targets. Do not confuse those logical deployment targets with the persistent field inventory root.

## Gazebo live baseline already established

Current gazebo WB:

- hostname: `wirenboard-A52LY4MY`
- wb-rules: `2.46.5`
- wb-mqtt-serial: `2.268.0`
- role: 504 combo thermostat / MQTT frame sender; no physical heating outputs
- NLI: not installed before adoption

The four managed live files were hashed from `/mnt/data/etc` and match repository commit exactly:

`837b2c6da31275cdb8964373f73b070fbbd31d6a`

Exact reviewed adoption baseline manifest is stored in this workspace:

`hhm-gazebo-live-837b2c6.json`

Manifest SHA256:

`36aa0f6446043677a726bbd539b3f6664706ffcdf177277f89e95970eb26b932`

This is the real installed baseline. Do not substitute the later example `hhm-gazebo-3.0.json`, whose HHM3Runtime byte hash differs from live.

## Live evidence already collected — do not repeat

Gazebo history and hardware preflight are complete.

Observed old-runtime defect:

- 504 frame: `valid=false`, `reason=FLOOR_SENSOR_INVALID`, `floor=null`
- air healthy
- no new direct MQTT publication for 921.10 / OK in the short observation window
- direct read-only `port/Load`:
  - FC04 temperature = 22.8125 °C
  - FC02 Sensor OK = healthy
  - RTT ≈ 102 ms for each read

Conclusion: real serial hardware is healthy and installed wb-mqtt-serial supports the post-start read required by the fix. The old runtime false-invalid is reproduced live.

Gazebo post-fix soak remains 600 s.

## Phase G1 — install NLI package on gazebo

Use helper command:

`python3 field_retry.py bootstrap-nli --execute-install`

This step:

- downloads the fixed published 0.1.9 bootstrap;
- verifies bootstrap SHA before executing it;
- installs the approved NLI package;
- verifies NLI version;
- checks that wb-rules and wb-mqtt-serial service start timestamps did not change;
- does **not** create object config;
- does **not** restart WB services;
- does **not** change HHM files.

Package installation is now an approved architecture step.

## Phase G2 — reviewed initial adoption inventory

Immediately after package installation:

`python3 field_retry.py adoption-inventory --role gazebo`

The helper scans all JS under the real persistent directories, records logical `/etc/...` path + SHA256, marks the four known managed HHM files, and saves the full JSON report.

No unmanaged rule is trusted automatically.

The inventory report is reviewed before config activation. This is the only remaining discovery step for gazebo adoption.

## Phase G3 — activate gazebo NLI baseline

After inventory review, update this helper with an exact reviewed unmanaged allowlist and an atomic adoption command.

That adoption command must:

1. require NLI 0.1.9;
2. require hostname `wirenboard-A52LY4MY`;
3. require the four current live files to match the exact 837b2c6 baseline;
4. create only persistent NLI config/releases under `/mnt/data/etc/neiro/nli/`;
5. use `release_source=pinned` during adoption;
6. set baseline=target to the exact live baseline manifest;
7. include only reviewed unmanaged JS path/hash entries;
8. run read-only `nli status`, `nli check hhm`, `nli verify hhm`;
9. not stop/restart wb-rules and not alter HHM bytes.

No manual editing of managed HHM files is allowed.

## Phase G4 — gazebo 3.1 through NLI

After adoption PASS:

`python3 field_retry.py retry --role gazebo --skip-history --stability-seconds 600 --execute-update`

The helper must require configured NLI 0.1.9, stage the exact reviewed draft 3.1 manifest, then call `nli update hhm`.

NLI owns:

- backup;
- atomic managed-file install;
- wb-rules stop/start required by the manifest;
- installation verification;
- pending/audit;
- rollback mechanics.

Functional field smoke remains separate and runs for 600 s.

PASS requires no false `FLOOR_SENSOR_INVALID`, valid/fresh 504 frames and healthy sensor contract.

If gazebo fails, do not update boiler.

## Phase B — boiler after gazebo PASS

Run one boiler preflight with history:

`python3 field_retry.py preflight --role boiler --hours 24 --require-nli`

Review `recommended_stability_s` (120 or 180 s).

Then:

`python3 field_retry.py retry --role boiler --skip-history --stability-seconds <120|180> --execute-update`

Boiler current-state checks still repeat immediately before mutation; only history is reused.

## Safety

- no firmware update/recover in this workflow;
- no manual HHM file replacement;
- no direct wb-mqtt-serial restart;
- no artificial heartbeat/numeric republish;
- no deliberate sensor fault injection;
- no modification of 507;
- no business-state rollback gate inside NLI;
- preserve pending/audit on NLI failure;
- rollback through NLI only.

## Evidence

Complete reports are saved under:

`/mnt/data/var/log/neiro/hhm31-field-retry/`

Terminal output stays compact and prints the exact full-report path.
