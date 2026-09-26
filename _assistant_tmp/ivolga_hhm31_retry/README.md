# Temporary assistant workspace — Ivolga HHM 3.1 retry

## Canonical decision

From 26.09.2026 NLI is the normal installer/updater on every managed NEIROLINKS WB.

For Ivolga this means:

- boiler: NLI 0.1.9 already configured;
- gazebo: install/adopt NLI first;
- HHM 3.1 on both controllers is deployed through NLI;
- no normal manual replacement of the four gazebo HHM files.

## Workspace files

- `PLAN.md` — canonical controlled-retry plan
- `field_retry.py` — field helper
- `field_retry.py.sha256` — helper checksum
- `hhm-gazebo-live-837b2c6.json` — exact reviewed current gazebo baseline

Persistent live `etc` is `/mnt/data/etc`.

## Current gazebo facts

Already proved; do not repeat:

- history collected;
- old false `FLOOR_SENSOR_INVALID` reproduced;
- `port/Load` FC04 + FC02 works on installed wb-mqtt-serial 2.268.0;
- temperature direct read 22.8125 °C;
- Sensor OK direct read healthy;
- RTT about 102 ms;
- current four managed files exactly match commit `837b2c6da31275cdb8964373f73b070fbbd31d6a`.

Current-baseline manifest SHA256:

`36aa0f6446043677a726bbd539b3f6664706ffcdf177277f89e95970eb26b932`

## Helper bundle

Immutable helper/checksum commit:

`3aed78ae7ebbff007e5d68a5dee4e1c0034e83ad`

Helper SHA256:

`a48ed4a489006d1c0a5f99958a1c45b5c9c8bcb969f6e7937357b31f51f17ada`

Refresh helper on gazebo:

```sh
cd /root/hhm31-retry

curl -fsSL -o field_retry.py \
https://raw.githubusercontent.com/psv76/Neirolinks/3aed78ae7ebbff007e5d68a5dee4e1c0034e83ad/_assistant_tmp/ivolga_hhm31_retry/field_retry.py

curl -fsSL -o field_retry.py.sha256 \
https://raw.githubusercontent.com/psv76/Neirolinks/3aed78ae7ebbff007e5d68a5dee4e1c0034e83ad/_assistant_tmp/ivolga_hhm31_retry/field_retry.py.sha256

sha256sum -c field_retry.py.sha256
python3 field_retry.py selftest
```

## Next step: NLI package + adoption inventory

The operator decision to install NLI on gazebo is already made.

Run:

```sh
python3 field_retry.py bootstrap-nli --execute-install
python3 field_retry.py adoption-inventory --role gazebo
```

`bootstrap-nli` installs only approved NLI 0.1.9. It verifies the fixed bootstrap SHA, runs the bootstrap in `--check` mode first, refuses to install if the approved catalog no longer resolves to exactly 0.1.9 with the expected package SHA, and checks that wb-rules / wb-mqtt-serial were not restarted.

It does not create object config and does not alter HHM.

`adoption-inventory` is read-only. It saves the complete JS inventory and prints a compact summary plus the JSON path.

After that JSON is reviewed, the helper will be updated with the exact unmanaged allowlist and one atomic gazebo adoption command. The operator will not manually edit HHM files or build the allowlist by hand.

## After adoption

Gazebo update:

```sh
python3 field_retry.py retry --role gazebo --skip-history --stability-seconds 600 --execute-update
```

Boiler follows only after gazebo PASS.

## Evidence

`/mnt/data/var/log/neiro/hhm31-field-retry/`

Do not delete evidence or NLI persistent state until the controlled retry is closed.
