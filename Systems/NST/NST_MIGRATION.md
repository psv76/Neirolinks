# NST 1.0 migration from NLI 0.1.9

Scope: GitHub Issue #88.

## Identity

- Debian package: `neiro-nst` version `1.0.0`.
- Primary CLI: `/usr/bin/nst`.
- Temporary compatibility CLI: `/usr/bin/nli`; it executes the same NST runtime.
- Runtime: `/usr/lib/neiro-nst`.
- Package data: `/usr/share/neiro-nst`.
- Package documentation: `/usr/share/doc/neiro-nst`.
- The internal Python package remains named `nli` in NST 1.0 to avoid rewriting the accepted transaction engine.

## Durable storage is intentionally not renamed

The following accepted NLI 0.1.9 paths remain the NST 1.0 storage schema:

- `/mnt/data/etc/neiro/nli`
- `/mnt/data/var/lib/neiro/nli`
- `/mnt/data/var/log/neiro/nli`

This is deliberate. Moving backups, pending records, audit or rollback metadata during a package rename would create a larger failure surface and would break the already proven FIT model.

The Debian package owns none of these paths. Package install/reinstall therefore cannot silently rewrite them.

## Debian replacement

`neiro-nst 1.0.0` declares `Conflicts/Replaces: neiro-nli (<= 0.1.9)` and contains no maintainer scripts, triggers or conffiles.

The exact CI migration path is:

1. install the historical NLI package chain through exact NLI 0.1.9;
2. create reviewed component state, backup, rollback point, audit and a real component pending record using NLI 0.1.9 code;
3. snapshot all persistent bytes and metadata;
4. install `neiro-nst_1.0.0_all.deb`;
5. prove old rootfs runtime is gone, `nst` and compatibility `nli` both report 1.0.0, and the persistent snapshot is byte-identical;
6. load the existing pending/backup using NST;
7. reinstall NST and prove persistent data remains unchanged;
8. start from a fresh rootfs with the same `/mnt/data`, install NST and complete rollback using the original NLI rollback point.

No engineering service restart is part of the package rename.

## Platform metadata

NST adds optional platform metadata at the preserved state root:

`/mnt/data/var/lib/neiro/nli/platform.json`

Schema v1 reserves:

- controller identity/assignment;
- last approved registry metadata;
- last approved deployment metadata;
- desired-state metadata.

If the file does not exist, read-only commands return an in-memory empty schema and do not create it. Population belongs to desired-state/status integration in #89.

## Recovery

A component `pending.json` is not cleared by migration. Existing backups and rollback references remain valid.

An old package-level `self-update.json` also remains visible and blocks component mutation. It is not silently discarded by the rename. Package-level recovery/publication is completed in #92.
