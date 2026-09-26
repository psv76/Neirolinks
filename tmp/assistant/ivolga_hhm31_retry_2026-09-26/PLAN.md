# 05_31 Ivolga — HHM 3.1 controlled retry plan

Temporary engineering workspace. This plan is intentionally optimized for minimum operator time without replacing live evidence with CI evidence.

## Fixed release identity

- PR: #73
- PR HEAD: `5efce9783886a991d9d1b9008860f9309b1d5559`
- HHM runtime commit: `20af0c29ed37130a5d4ff051ff1fb5984a5f8193`
- HHM version: `3.1`
- NLI: `0.1.9`, installation-only
- boiler manifest SHA256: `b8c45743c4d290949e42f0b459804b1e545087a788383fb0cb816edc0379d444`
- gazebo manifest SHA256: `c3de99685ba6995ed2b51fcd74d1bc20c3c416e293691c9b42689cc857547261`

Do not merge PR #73 before live acceptance. Do not publish this draft component as a normal approved release before controlled retry.

## What is already proven and must NOT be repeated on live WB

Do not rerun HHM/NLI regression suites on the controller. CI already proves exact source/package behavior:

- #75 baseline: 4 PASS / 12 FAIL; fixed runtime: 16 PASS.
- cold-start baseline: 4 PASS / 3 FAIL; fixed runtime: 7 PASS.
- HHM CI 36212573411: SUCCESS.
- NLI CI 36212573303: SUCCESS, 172 tests + sandbox/package/FIT.
- NLI install verification, backup, rollback and package identity are NLI responsibilities.

Live work therefore tests only facts CI cannot know:

1. actual installed `wb-mqtt-serial` supports documented `port/Load`;
2. actual buses/devices answer read-only FC04/FC02 in acceptable time;
3. current object sensors are healthy before mutation;
4. after restart all required local M1W2 sensors obtain post-start proof;
5. #75 false runtime invalid does not recur on the real gazebo sensor;
6. boiler bus load/timing is adequate with the full required sensor set.

## Historical evidence is used before mutation

`field_retry.py history` and `preflight` read `wb-mqtt-db` through its documented MQTT-RPC API. They do not open SQLite directly and do not change database configuration. The helper also records the current db config summary so missing history is interpreted against the actual retention/channel policy.

### Gazebo

The history/preflight phase queries:

- current `921.10_TEMP_NONE/External Sensor 1` and `... OK`;
- recent history for raw floor/OK and 504 validity if those channels are stored;
- the whole local calendar day 2026-09-25 for the #75 incident;
- current air sensor `921.09_MSW_TH/Temperature`;
- one real read-only `wb-mqtt-serial/port/Load` pair: FC04 temperature + FC02 Sensor OK.

Known #75 live evidence already gives recurrence intervals 335, 370, 395 and 355 seconds. Therefore the minimum post-fix gazebo soak is 600 s: 1.5 × the worst observed interval, rounded up. History may strengthen the evidence but does not shorten the soak below 600 s.

### Boiler

The preflight uses one `get_channels` history inventory for all 19 required M1W2 temperature/OK pairs, then one compact history query for all OK channels and three representative temperatures. This avoids 38 separate history sessions.

If >=80% of expected history channels are present and no historical OK=0 is found in the recent window, post-install stability is 120 s after qualification. Otherwise use 180 s. Current live state still must be healthy for every required M1W2 before update.

## Gate A — gazebo first

Gazebo is the low-risk first target: the 3.1 gazebo payload is 624 + shared modules and has no physical actuator writes.

1. Optionally run `history --role gazebo` first; this is pure evidence collection and can be done before the maintenance window.
2. Run `preflight --role gazebo`.
3. STOP if any current sensor is unhealthy, NLI role/version is wrong, wb-rules/wb-mqtt-serial is inactive, or the representative `port/Load` proof fails.
4. Stage the exact draft manifest in NLI pinned mode. The helper:
   - downloads manifest from exact PR HEAD;
   - verifies the known manifest SHA256;
   - verifies runtime commit/version/role;
   - backs up only NLI config;
   - changes only `release_source` and `components.hhm.target`;
   - does not change baseline/state/services/HHM files.
5. `nli --json check hhm` must pass.
6. Operator must explicitly type `UPDATE GAZEBO` before mutation.
7. NLI performs the update.
8. Passive smoke runs for 600 s.

### Gazebo PASS criteria

- `nli verify hhm` exit 0;
- M1W2 `921.10...External Sensor 1` reaches runtime `VALID` after this restart;
- final `NL_combo_thermostat_504/floor_valid = 1`;
- final reason is not `FLOOR_SENSOR_INVALID`;
- `sensor_health_contract = m1w2-health-v1`;
- after the first runtime VALID, zero subsequent `FLOOR_SENSOR_INVALID` during the 600 s window;
- RPC proof warnings are recorded but only missing final qualification is blocking;
- fresh numeric publications are counted. Zero is stronger #75 evidence, but a natural temperature publication is not a failure.

If gazebo fails, do not touch boiler.

## Gate B — boiler only after gazebo PASS

1. Optionally run `history --role boiler` before the maintenance window.
2. Run `preflight --role boiler`.
3. Current retained state must show all 19 required M1W2 pairs with numeric value, OK=1 and no observed MQTT error.
4. One representative `port/Load` read on `wb-m1w2_170/External Sensor 1` must match the local value and OK=1.
5. Stage exact boiler manifest and run `nli --json check hhm`.
6. Operator must explicitly type `UPDATE BOILER`.
7. NLI update runs in a supervised window. Unlike gazebo, the existing `in_service` state can cause normal HHM output commands after wb-rules restart.
8. Passive smoke waits for all 19 required M1W2 paths to show runtime VALID, then applies the history-derived stability window (normally 120 s; 180 s if history is incomplete/less clean).

### Boiler PASS criteria

- `nli verify hhm` exit 0;
- all 19 required M1W2 paths observed runtime VALID after update;
- final `HHM3_FSE/sensor_health_contract = m1w2-health-v1`;
- no `RUNTIME_UNSUPPORTED` final runtime status;
- services remain active;
- proof transport warnings are preserved in report; a sensor that never reaches VALID is blocking.

There is no second 10-minute #75 soak on boiler: the same helper is already exercised on gazebo, while boiler testing is focused on full-set qualification and real bus load/timing.

## Failure handling

The helper never executes an automatic functional rollback.

- Technical install failure remains NLI's responsibility.
- Functional smoke failure prints `nli --json rollback hhm` as the recommended next action and stops.
- Review evidence before rollback. On boiler, because production outputs can resume after restart, decide promptly in the supervised window.
- Do not delete NLI pending/audit/backups.

## After both controllers PASS

1. Add live evidence to PR #73 / #68 / #75.
2. Only then decide PR merge and normal approved HHM release publication.
3. Return both controllers from temporary pinned target to normal approved discovery using `field_retry.py unstage` only after the final desired config is confirmed.
4. Verify `nli status`, `nli check hhm`, and current HHM after the config restore/publication transition.

## Time budget

Expected operator attention:

- gazebo preflight + stage/update: ~3–5 min;
- gazebo soak: 10 min unattended;
- boiler preflight + stage/update: ~3–5 min;
- boiler qualification/stability: normally ~2–4 min unattended.

The plan intentionally avoids repeating CI, avoids per-sensor manual RPC tests, and uses history to keep boiler observation short.

## Temporary live files

The helper writes only temporary evidence under:

`/tmp/hhm31-field-retry/`

NLI itself keeps its normal audit/backups under `/mnt/data`.

`stage` additionally creates:

- `/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry`
- one exact retry manifest in `/mnt/data/etc/neiro/nli/releases/`

`unstage` restores/removes only those known staging files. It never changes NLI state or HHM runtime.
