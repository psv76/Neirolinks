# Temporary assistant workspace — Ivolga HHM 3.1 retry

This directory is temporary and exists only for the controlled retry work.

Files:

- `PLAN.md` — canonical history-first retry plan;
- `field_retry.py` — stdlib-only field helper;
- `field_retry.py.sha256` — helper checksum.

## Live topology rule

Gazebo and boiler are intentionally treated differently.

### Gazebo

Current live baseline:

- `624_combo_besedka.js` + shared `HHM3Config / HHM3Wire / HHM3Runtime`;
- no full HHM controller;
- no NLI;
- publishes the non-retained 504 frame over the existing MQTT bridge.

Therefore:

- gazebo `history`, `preflight`, and `smoke` are supported;
- gazebo `stage` / NLI `retry` are deliberately NOT supported;
- missing `nli` on gazebo is expected and is not a preflight failure;
- first-time NLI installation on gazebo is a separate migration decision.

### Boiler

Boiler already has NLI 0.1.9. Boiler `stage`, `retry`, and `unstage` use that existing NLI installation.

## Filesystem rule

Persistent configuration is read from:

`/mnt/data/etc`

The helper uses that path directly for runtime inventory and config summaries.

Important paths:

- `/mnt/data/etc/wb-rules/`
- `/mnt/data/etc/wb-rules-modules/`
- `/mnt/data/etc/wb-mqtt-serial.conf`
- `/mnt/data/etc/wb-mqtt-db.conf`
- boiler NLI: `/mnt/data/etc/neiro/nli/`

Do not use `/etc` as the source of truth for field inventory.

## Safety model

Read-only by default.

The only direct Modbus operation is one bounded read-only `wb-mqtt-serial/port/Load` pair using FC04 + FC02 on one representative M1W2.

The helper does not:

- restart `wb-mqtt-serial`;
- update/recover firmware;
- create artificial numeric republishes;
- deliberately force sensor failures;
- modify 507;
- auto-rollback on HHM business state.

Boiler mutation requires:

```sh
python3 field_retry.py retry --role boiler --execute-update
```

and then an interactive confirmation phrase.

## Immutable helper bootstrap

Use helper/checksum commit:

`5c41cdacafd13e9d85416993c3f4d3f742b9b0fe`

```sh
install -d -m 0700 /root/hhm31-retry
cd /root/hhm31-retry

curl -fsSL -o field_retry.py \
https://raw.githubusercontent.com/psv76/Neirolinks/5c41cdacafd13e9d85416993c3f4d3f742b9b0fe/_assistant_tmp/ivolga_hhm31_retry/field_retry.py

curl -fsSL -o field_retry.py.sha256 \
https://raw.githubusercontent.com/psv76/Neirolinks/5c41cdacafd13e9d85416993c3f4d3f742b9b0fe/_assistant_tmp/ivolga_hhm31_retry/field_retry.py.sha256

sha256sum -c field_retry.py.sha256
python3 field_retry.py selftest
```

Expected helper SHA256:

`a06520efe1581468a0bfafbc5e135b767af859122cbc8f98c8939951624e772c`

## Current next step — gazebo

Gazebo 24 h history has already been collected. Do not repeat it.

Run only:

```sh
cd /root/hhm31-retry
python3 field_retry.py preflight --role gazebo --skip-history
```

The terminal output is intentionally compact. The helper automatically saves the complete JSON report under `/mnt/data/var/log/neiro/hhm31-field-retry/<timestamp>-gazebo-preflight/preflight.json` and prints that exact path as `FULL_REPORT`.

Gazebo preflight checks:

- package/service state;
- current runtime files under `/mnt/data/etc` + hashes;
- live 504 frame (freshness, `valid`, floor value);
- air sensor;
- direct MQTT visibility of 921.10/OK as **informational only** — silence is expected for unchanged values and is not a failure;
- read-only `port/Load` FC04+FC02 proof, performed even when those MQTT controls are silent; the bus temperature is compared with the fresh 504 frame floor value.

It does not call or require NLI.

After gazebo preflight PASS, stop and explicitly choose the delivery method for the new 624 + shared modules. Do not install NLI automatically.

After that separately approved gazebo deployment, acceptance is:

```sh
python3 field_retry.py smoke --role gazebo --stability-seconds 600
```

## Boiler sequence — only after gazebo PASS

First run one read-only boiler preflight with history:

```sh
python3 field_retry.py preflight --role boiler --hours 24
```

Review its `recommended_stability_s` value. Then the mutation command reuses that already-reviewed history and repeats only current-state checks:

```sh
python3 field_retry.py retry --role boiler --skip-history --stability-seconds 120 --execute-update
```

Use `180` instead of `120` when the reviewed history recommends the conservative interval.

Boiler preflight requires existing NLI 0.1.9 and no pending mutation. The retry still repeats current sensor/service/NLI checks immediately before staging; only the history query is skipped.

## Evidence

History and preflight print compact summaries to the terminal and automatically save their complete JSON reports. This avoids terminal scrollback loss.

Persistent evidence:

`/mnt/data/var/log/neiro/hhm31-field-retry/`

Boiler-only staging files:

- `/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry`
- one helper retry manifest in `/mnt/data/etc/neiro/nli/releases/`

## Cleanup after the work is complete

Do not clean up until live acceptance and final target state are confirmed.

Temporary GitHub directory:

`_assistant_tmp/ivolga_hhm31_retry/`

Temporary branch:

`assistant/ivolga-hhm31-controlled-retry`

The exact deletion steps will be given after the controlled retry is finished.


Observed live on 26.09.2026: a fresh valid 504 frame contained floor=22.95 while a short direct MQTT snapshot of 921.10/OK saw no publication. This is not sensor failure; it is the silent-unchanged condition the new post-start serial proof is designed to handle. The helper must never gate `port/Load` on seeing a fresh MQTT sample first.


## Live gazebo preflight result 26.09.2026

The pre-deploy field gate now distinguishes hardware health from the known old-runtime defect.

Observed simultaneously on the gazebo WB:

- fresh 504 frame: `valid=false`, `reason=FLOOR_SENSOR_INVALID`, `floor=null`;
- air remained valid;
- direct MQTT snapshot of 921.10/OK saw no new publication;
- read-only `port/Load` succeeded:
  - FC04 temperature = 22.8125 °C;
  - FC02 Sensor OK = healthy;
  - RTT about 102 ms for each read.

This is a live reproduction of the old #75 behavior, not a hardware failure. Therefore gazebo **pre-deploy** PASS is based on hardware proof (`port/Load` + healthy air + fresh frame transport), while the old frame's `FLOOR_SENSOR_INVALID` is recorded as `old_runtime_false_invalid_reproduced=true`.

After installing the fixed 624/shared modules, the 600 s smoke reverses that expectation: any `FLOOR_SENSOR_INVALID` is then a failure.
