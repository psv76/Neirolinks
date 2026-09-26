# Temporary assistant workspace — Ivolga HHM 3.1 retry

This directory is temporary field-engineering material and must **not** be merged into PR #73.

Files:

- `PLAN.md` — history-first controlled retry plan;
- `field_retry.py` — stdlib-only helper for history, preflight, staging, controlled update and passive smoke;
- `field_retry.py.sha256` — helper checksum.

The helper is read-only by default. Persistent NLI target staging is also guarded: standalone `stage` requires `--execute`. The only HHM runtime mutation path is:

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

## Bootstrap on a WB

Use the immutable helper/checksum commit `b746c59e7d18fafd793f304a087b63e2f669e85e`:

```sh
install -d -m 0700 /root/hhm31-retry
cd /root/hhm31-retry
curl -fL -o field_retry.py https://raw.githubusercontent.com/psv76/Neirolinks/b746c59e7d18fafd793f304a087b63e2f669e85e/_assistant_tmp/ivolga_hhm31_retry/field_retry.py
curl -fL -o field_retry.py.sha256 https://raw.githubusercontent.com/psv76/Neirolinks/b746c59e7d18fafd793f304a087b63e2f669e85e/_assistant_tmp/ivolga_hhm31_retry/field_retry.py.sha256
sha256sum -c field_retry.py.sha256
python3 field_retry.py selftest
```

Expected SHA256: `05c9b8702ec0b91d0c0ac47255be1c70f5a69f4b68c7ac00296446fa24d35f6c`.

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

Evidence is written under `/mnt/data/var/log/neiro/hhm31-field-retry/` so it survives service restart/reboot. NLI keeps its own normal audit/backups separately under `/mnt/data`.

`stage` additionally creates only:

- `/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry`;
- one exact retry manifest in `/mnt/data/etc/neiro/nli/releases/`.

`stage` is transactional before runtime mutation: failed `nli check hhm`, cancellation, or interruption before `nli update` restores the original target. After `nli update` starts, no automatic target restore or rollback is attempted.

`unstage` restores only the helper-created config backup and removes the exact helper-created retry manifest. It refuses to run while NLI has pending mutation state or if the current config no longer matches the exact staged target. It never changes HHM runtime. Do not use it until the desired final NLI target configuration has been decided.

## Removal

This workspace lives on a separate temporary GitHub branch. After field acceptance and after any required evidence has been copied into permanent issues/PRs, delete the temporary branch; no production cleanup commit is required.

On a WB, once evidence is no longer needed and the NLI target config is deliberately being restored:

```sh
python3 field_retry.py unstage --execute
rm -rf /mnt/data/var/log/neiro/hhm31-field-retry
```