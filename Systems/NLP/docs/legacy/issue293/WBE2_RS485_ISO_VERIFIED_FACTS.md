# Issue #293 — verified WBE2-I-RS485-ISO engineering facts (2026-10-27)

This is source evidence, **not a released EquipmentPassport**.

## Official manufacturer sources

- https://wiki.wirenboard.com/wiki/WBE2-I-RS485-ISO_RS485_Extension_Module
- https://wiki.wirenboard.com/wiki/Wiren_Board_6%3A_Extension_Modules
- https://wiki.wirenboard.com/wiki/Wiren_Board_8.5
- https://wiki.wirenboard.com/wiki/Wiren_Board_8.5%3A_Peripherals

## Verified device behavior

| Property | Verified value |
|---|---|
| Interface | One additional galvanically isolated RS-485 |
| Isolation | 1.5 kV |
| Speed | Up to 1 Mbit/s |
| Built-in terminator | 120 ohm, jumper enabled |
| Contacts | O1=A (D+), O2=B (D−), O3=isolated common |
| WB8.5 mounting | MOD1, MOD2, MOD3 or MOD4 (manufacturer compatibility table) |
| Linux port in WB8.5 | `/dev/ttyMOD1`, `/dev/ttyMOD2`, `/dev/ttyMOD3`, `/dev/ttyMOD4` according to occupied slot |
| Controller native interfaces | `RS485-1`, `RS485-2` independent of module port |

## Catalog contract for implementation

- Model as a distinct module instance attached to **exactly one** typed controller `MOD1…MOD4` resource.
- Do not synthesize an RS485 bus source on empty controller slots.
- Module supplies one assignable `RS485_INTERFACE` resource, suitable for `Bus.root_resource_id` only when module has a valid parent/slot relationship.
- Reject duplicate installation on the same physical slot, incompatible host revisions and cross-protocol bus selection.
- No unverified nominal/peak power, module supply figures, or invented ports.
- Requires constructor relation persistence and roundtrip/reopen acceptance before release.

## Outstanding verification

The legacy WB device listing establishes article identity, but the current constructor implementation must be audited for typed installation edges before changes to runtime catalog. Working SQLite successor/migration and smoke required for issue acceptance.
