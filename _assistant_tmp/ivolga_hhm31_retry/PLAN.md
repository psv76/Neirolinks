# 05_31 Ivolga — HHM 3.1 controlled retry plan

Temporary operator plan. This workspace is not a product release.

## Fixed identities

- PR #73 reviewed head: `5efce9783886a991d9d1b9008860f9309b1d5559`
- immutable HHM runtime: `20af0c29ed37130a5d4ff051ff1fb5984a5f8193`
- HHM version: `3.1`
- boiler manifest SHA256: `b8c45743c4d290949e42f0b459804b1e545087a788383fb0cb816edc0379d444`
- gazebo manifest SHA256: `c3de99685ba6995ed2b51fcd74d1bc20c3c416e293691c9b42689cc857547261`
- boiler NLI: `0.1.9`, installation-only

Do not merge PR #73 before live acceptance.

## Canonical live topology

Current live topology is asymmetric and MUST NOT be inferred from the two NLI manifests.

### Gazebo WB

- Runs `624_combo_besedka.js` plus shared `HHM3Config / HHM3Wire / HHM3Runtime` modules.
- This is the 504 combo thermostat / frame sender, not a full HHM controller.
- It reads local air/floor sensors, calculates demand and publishes non-retained `/neiro/ivolga/504/v2/frame`.
- It has no physical heating outputs / remote `/on` writes.
- The frame crosses the existing MQTT bridge and is consumed on the boiler WB.
- **NLI is not installed on the current gazebo WB baseline.**
- Missing `nli` on gazebo is expected and is NOT a preflight failure.
- `hhm-gazebo-3.1.json` is only a future delivery option. First-time NLI installation on gazebo requires a separate explicit operator decision.

### Boiler WB

- Runs the full HHM controller/consumers.
- NLI 0.1.9 is already installed and is the accepted installation/update mechanism.
- NLI verifies installation correctness only; HHM business/runtime health remains a separate field acceptance step.

## Canonical filesystem rule

Persistent `etc` on these WB controllers is:

`/mnt/data/etc`

All live inventory, checks, backups and helper-owned config paths use `/mnt/data/etc` directly.

Examples:

- rules: `/mnt/data/etc/wb-rules/`
- modules: `/mnt/data/etc/wb-rules-modules/`
- serial config: `/mnt/data/etc/wb-mqtt-serial.conf`
- mqtt-db config: `/mnt/data/etc/wb-mqtt-db.conf`
- NLI config on boiler: `/mnt/data/etc/neiro/nli/config.json`

Do not infer persistent state from `/etc`. Repository/NLI manifests may still contain `/etc/...` service targets; that is a deployment interface detail, not the path used by field inventory.

## What CI already proved — do not repeat live

Do not rerun HHM/NLI regression suites on the controller.

Already accepted offline:

- #75 regression: old runtime 4 PASS / 12 FAIL, fixed runtime 16 PASS.
- cold-start regression: 4 PASS / 3 FAIL -> 7 PASS.
- full HHM CI: SUCCESS.
- NLI CI: 172 tests + sandbox/package/FIT: SUCCESS.
- manifests pin exact runtime bytes.

Live work should only prove hardware/driver/environment facts that CI cannot prove.

## Historical evidence first

Use `wb-mqtt-db` through its MQTT-RPC history API; do not read SQLite directly and do not change database config.

Gazebo history is already collected and saved. It gives full channel coverage and confirms repeated historical `FLOOR_SENSOR_INVALID` episodes while the floor sensor was otherwise publishing. Therefore do not collect the same 24 h history again unless the saved evidence is lost.

Historical recurrence supports a 600 s post-fix gazebo soak. This is long enough to cross the old repeating failure cadence with margin.

For boiler, collect one compact 24 h history set before mutation. It is used only to determine required-sensor coverage and whether recent OK/error history justifies the short 120 s soak or the conservative 180 s soak.

## Gate A — gazebo read-only preflight

Gazebo is checked first because it contains the exact 921.10 / 504 path involved in #75 and has no physical heating outputs.

Run:

`python3 field_retry.py preflight --role gazebo --skip-history`

The helper checks:

1. hostname and installed package versions;
2. `wb-rules`, `wb-mqtt-serial`, `wb-mqtt-db` service state;
3. current gazebo runtime file inventory from **`/mnt/data/etc`** and SHA256;
4. current 921.10 temperature + `External Sensor 1 OK` + active errors;
5. air sensor state;
6. one bounded read-only `wb-mqtt-serial/port/Load` proof:
   - FC04 temperature;
   - FC02 Sensor OK;
   - JSON-RPC id correlation;
   - bus/local value agreement;
7. one live 504 frame observation from `/neiro/ivolga/504/v2/frame`.

Gazebo preflight deliberately does **not** require or verify NLI.

STOP if sensor health, required files, services, frame publication or `port/Load` proof fail.

## Gazebo deployment decision — separate stop point

After read-only gazebo preflight PASS, stop.

Do not automatically install NLI and do not run any NLI stage/update command on gazebo.

Choose the gazebo delivery mechanism separately and explicitly. Until that decision is approved, the helper exposes no gazebo NLI mutation path.

After the reviewed 4-file gazebo payload has been installed by the separately approved method, run only passive acceptance:

`python3 field_retry.py smoke --role gazebo --stability-seconds 600`

PASS requires:

- new 504 instance becomes valid after post-start proof;
- no artificial numeric republish is required;
- no false `FLOOR_SENSOR_INVALID` during the 600 s window;
- 504 frame stays fresh/valid;
- sensor health contract and runtime diagnostics are coherent.

If gazebo fails, do not touch boiler.

## Gate B — boiler only after gazebo PASS

1. Run one read-only boiler preflight **with** 24 h history:
   `python3 field_retry.py preflight --role boiler --hours 24`
2. Review its `recommended_stability_s` result (120 or 180 s).
3. Boiler preflight additionally requires:
   - NLI exactly 0.1.9;
   - `pending = null`;
   - `nli verify hhm` PASS;
   - `nli verify pressure_makeup` PASS;
   - all required runtime files present under `/mnt/data/etc`;
   - all required M1W2 current health PASS;
   - representative boiler `port/Load` proof PASS.
4. Only after explicit operator approval run retry while **reusing** the already-reviewed history:
   `python3 field_retry.py retry --role boiler --skip-history --stability-seconds <120|180> --execute-update`
5. Retry repeats all current sensor/service/NLI checks immediately before staging; only the history query is skipped.
6. NLI stages the exact reviewed boiler manifest, performs the update and keeps normal NLI backup/audit/pending semantics.
7. Field smoke is separate from installation verification. Use 120 s only when the reviewed preflight/history recommended 120; otherwise use 180 s.

There is no second 10-minute #75 soak on boiler. The long recurrence test belongs to gazebo; boiler acceptance focuses on all required sensors qualifying together and real serial-bus load/timing.

## Safety rules

- No firmware update/recover in this workflow.
- No direct restart of `wb-mqtt-serial`.
- No artificial heartbeat or numeric republish.
- No deliberate OK=0 / sensor disconnection / dangerous heating fault injection.
- No automatic rollback based on HHM business state.
- Once an NLI mutation has started, preserve pending/audit on failure and inspect before any second attempt.
- Do not modify 507.
- Do not merge PR #73 during the controlled retry.

## Evidence

Helper evidence is persistent:

`/mnt/data/var/log/neiro/hhm31-field-retry/`

Gazebo and boiler evidence directories are timestamped and independent.

Boiler-only NLI staging files:

- `/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry`
- one exact retry manifest under `/mnt/data/etc/neiro/nli/releases/`

`stage`, `retry`, and `unstage` are boiler-only in the helper.

## Time-saving strategy

Active operator time is minimized by:

- reusing saved gazebo history;
- one combined read-only gazebo preflight;
- one representative active serial read instead of repeated manual reads;
- one unattended 600 s gazebo smoke;
- one compact boiler history/preflight;
- one 120–180 s boiler smoke.

The workflow intentionally spends time only on live facts CI and previous history cannot prove.
