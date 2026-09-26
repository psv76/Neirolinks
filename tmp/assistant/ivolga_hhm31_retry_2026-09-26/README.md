# Temporary assistant workspace — Ivolga HHM 3.1 retry

This directory is not production runtime and must not be merged into PR #73.

Files:

- `bootstrap.sh` — immutable downloader/verifier for the compressed helper.
- `PLAN.md` — complete history-first controlled retry plan.
- `field_retry.py.gz` — compressed temporary helper used on either WB. It is decompressed by the immutable bootstrap command supplied with the workspace.

The helper defaults to non-mutating modes. The only mutation path is:

`retry --role <gazebo|boiler> --execute-update`

It still requires a second interactive confirmation (`UPDATE GAZEBO` / `UPDATE BOILER`) before `nli update hhm`.

It never:

- updates firmware;
- restarts wb-mqtt-serial;
- writes Modbus registers directly;
- writes actuator MQTT topics directly;
- changes 507;
- auto-rolls back after a functional smoke failure;
- merges/publishes PR #73.

The only direct Modbus action outside HHM is a bounded read-only `wb-mqtt-serial/port/Load` probe using FC04 and FC02 on one representative M1W2 per controller.

Before field use, install the helper from the immutable archive and verify its self-test:

```sh
curl -fsSL https://raw.githubusercontent.com/psv76/Neirolinks/32d3007dc65cd7071367057741a7cd8bd63e396d/tmp/assistant/ivolga_hhm31_retry_2026-09-26/bootstrap.sh | sh
```

Then run:

```sh
python3 field_retry.py selftest
python3 field_retry.py history --role gazebo --hours 24
python3 field_retry.py preflight --role gazebo
```

`history` is read-only and can be run before the maintenance window. `preflight` is also non-mutating with respect to HHM/NLI configuration; its only bus action is the bounded read-only `port/Load` capability probe.

Do not run boiler retry until gazebo controlled retry is PASS.

## Removal

This workspace is kept on a separate temporary GitHub branch. When the controlled retry is complete, delete the branch; no production branch cleanup commit is required.

On each WB, after evidence is no longer needed and NLI staging has been deliberately restored:

```sh
python3 field_retry.py unstage
rm -rf /tmp/hhm31-field-retry
```

Do not run `unstage` while a retry is still under investigation or before deciding which NLI target configuration should remain.
