# Temporary assistant workspace — Ivolga HHM 3.1 retry

This directory is temporary field-engineering material and must **not** be merged into PR #73.

Files:

- `PLAN.md` — history-first controlled retry plan;
- `field_retry.py` — stdlib-only helper for history, preflight, staging, controlled update and passive smoke;
- `field_retry.py.sha256` — helper checksum.

The helper is read-only by default. The only HHM mutation path is:

```sh
python3 field_retry.py retry --role <gazebo|boiler> --execute-update
```

It still requires a second interactive confirmation (`UPDATE GAZEBO` / `UPDATE BOILER`) immediately before `nli update hhm`.

It never:

- updates firmware;
- restarts `wb-mqtt-serial` directly;
- writes Modbus registers directly;
- writes actuator MQTT topics directly;
- changes 507;
- auto-rolls back after a functional smoke failure;
- merges or publishes PR #73.

The only direct Modbus operation outside HHM is a bounded **read-only** `wb-mqtt-serial/port/Load` probe using FC04 and FC02 on one representative M1W2 per controller.

## Recommended sequence

Before the maintenance window:

```sh
python3 field_retry.py selftest
python3 field_retry.py history --role gazebo --hours 24
python3 field_retry.py preflight --role gazebo
```

For the controlled gazebo retry, only after preflight PASS:

```sh
python3 field_retry.py retry --role gazebo --execute-update
```

Do not run the boiler retry until gazebo returns PASS. Then:

```sh
python3 field_retry.py history --role boiler --hours 24
python3 field_retry.py preflight --role boiler
python3 field_retry.py retry --role boiler --execute-update
```

Evidence is written under `/tmp/hhm31-field-retry/`. NLI keeps its own normal audit/backups under `/mnt/data`.

`stage` additionally creates only:

- `/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry`;
- one exact retry manifest in `/mnt/data/etc/neiro/nli/releases/`.

`unstage` restores only the helper-created config backup and removes the helper-created retry manifest. It never changes NLI state or HHM runtime. Do not use it until the desired final NLI target configuration has been decided.

## Removal

This workspace lives on a separate temporary GitHub branch. After field acceptance and after any required evidence has been copied into permanent issues/PRs, delete the temporary branch; no production cleanup commit is required.

On a WB, once evidence is no longer needed and the NLI target config is deliberately being restored:

```sh
python3 field_retry.py unstage --execute
rm -rf /tmp/hhm31-field-retry
```