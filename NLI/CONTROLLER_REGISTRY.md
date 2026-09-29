# NST controller identity and registry

Scope: GitHub Issue #86.

## Hardware identity

- Operational identity is the WB hardware serial read locally from `/var/lib/wirenboard/short_sn`.
- `/var/lib/wirenboard/short_sn.conf` is accepted only as a compatibility fallback.
- Hostname, IP, installed scripts and MQTT are not identity sources.
- If available, CPU/eMMC identifiers are reduced to a SHA256 hardware fingerprint. A pinned mismatch blocks mutation.
- WB serial is a lookup key, not cryptographic proof.

## Object-local profile

Profiles live at `objects/<object>/controllers/<SERIAL>.json`. CI builds `NLI/generated/controller-registry.json` with `NLI/tools/build_controller_registry.py`.

`planned` and `retired` controllers cannot mutate production state. Unknown serials and unavailable identity/registry also fail closed. Only an `active` assignment with matching object/role can pass the NST mutation guard.

Registry generation rejects duplicate serials, invalid schema/role, missing diagnostics references and more than one active serial for the same object/node/role assignment.

The registry is local/package data in #86; approved deployment discovery and desired-state resolution belong to #87.
