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

`bf8e51add07d359eecb68e2f1d790116430284aa`

```sh
install -d -m 0700 /root/hhm31-retry
cd /root/hhm31-retry

curl -fsSL -o field_retry.py \
https://raw.githubusercontent.com/psv76/Neirolinks/bf8e51add07d359eecb68e2f1d790116430284aa/_assistant_tmp/ivolga_hhm31_retry/field_retry.py

curl -fsSL -o field_retry.py.sha256 \
https://raw.githubusercontent.com/psv76/Neirolinks/bf8e51add07d359eecb68e2f1d790116430284aa/_assistant_tmp/ivolga_hhm31_retry/field_retry.py.sha256

sha256sum -c field_retry.py.sha256
python3 field_retry.py selftest
```

Expected helper SHA256:

`756f0bebd9bf9aa3cee25b6ea9f60e213db2d4deb7ccbb012eab3f952b053778`

## Current next step — gazebo

Gazebo 24 h history has already been collected. Do not repeat it.

Run only:

```sh
cd /root/hhm31-retry

LOG="/mnt/data/var/log/neiro/hhm31-field-retry/gazebo-preflight-$(date +%Y%m%d-%H%M%S).log"

python3 field_retry.py preflight \
  --role gazebo \
  --skip-history \
  >"$LOG" 2>&1

RC=$?

echo "===== PREFLIGHT EXIT ====="
echo "$RC"
echo "===== SAVED ====="
echo "$LOG"
echo "===== LAST 80 LINES ====="
tail -n 80 "$LOG"
```

Gazebo preflight checks:

- package/service state;
- current runtime files under `/mnt/data/etc` + hashes;
- 921.10 temperature/OK/errors;
- air sensor;
- live 504 frame;
- read-only `port/Load` FC04+FC02 proof.

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
