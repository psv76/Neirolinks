# NST 1.0 pilot — 05 31 Ivolga / ABF62SL

Issue: #93.

## GitHub preparation

Controller identity:
- WB serial: `ABF62SL`
- object: `05_31_Ivolga_13`
- node / role: `boiler`
- human name: `Котельная`
- lifecycle: `active`

The pilot profile owns only object-specific files that are not already owned by a common component:
- `/etc/wb-rules-modules/system.js`
- `/etc/wb-rules/090_notification_service.js`
- `/etc/wb-rules/100_power_monitor.js`
- `/etc/wb-rules/610_Boiler_state.js`

HHM files remain owned by the approved `hhm` component. `507_Pressure_makeup.js` remains owned by the existing `pressure_makeup` component and MUST NOT be duplicated as object payload. Legacy HM2 managers and the Nevoton firmware-updater rule are not part of the NST pilot desired state.

Diagnostics use `Systems/NST/diagnostics/ivolga-boiler-hhm-v1.json`.

## Deliberate boundary before live work

This branch does not publish a platform release and does not access the live controller.

The current approved-component snapshot contains HHM 3.2–3.5 but no published approved `pressure_makeup` release. Therefore the pilot must not silently reinterpret 507 as an object file or fabricate approval metadata. Existing NLI/NST local registration for `pressure_makeup` remains valid, but complete remote desired-state coverage for that component requires a separately approved release.

Object-file mutation is also deliberately fail-closed in `nst sync` when object bytes differ. Read-only `status/check` can report exact/missing/drift. A no-op sync is possible only when the approved object payload is already exact; NST must not introduce a new object-file writer during the read-only pilot.

## Read-only field acceptance

After an NST 1.0 package/platform release is explicitly approved for field use, capture before/after service timestamps and run only:

```sh
nst --version
nst --json status
nst --json check
nst --json diagnostics collect hhm --since 6h
nst --json firmware check
nst --json cleanup check
```

Preserve:
- raw CLI JSON;
- exact registry/deployment identity;
- `systemctl show wb-rules wb-mqtt-serial -p Id -p ActiveEnterTimestampMonotonic` before and after;
- diagnostic archive SHA256;
- NST audit/state snapshot.

Acceptance: no service restart, no engineering output/setpoint write and no unexpected persistent mutation from the read-only commands.

## Mutation stage

Do not run `nst sync`, component update/rollback, firmware update/recover or cleanup until separate operator approval after the read-only evidence is reviewed.
