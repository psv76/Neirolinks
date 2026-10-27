# Issue #293 — source inventory (read-only evidence)

2026-10-27. Original files under D:\NLP\catalogs were only read, not modified.

| Source | Records | SHA-256 |
|---|---:|---|
| wb_equipment_catalog.json | 43 | `d699b3bf65dca0d9e2e84173cc1e5ab41ebcddf31b976373ecfe903f10e4963f` |
| wb_module_catalog.json | 16 | `8a28d95422be036f2e4de0d6d25f89b7f02403c64892a482ba3c39846fd5955a` |
| wb_engineering_reference.json | 36 | `c2bd4a9cd5bb8c1ee512b372900e1684ac3a9c8dc6a98d5a2ca24f8442ac4946` |

Current canonical equipment_passports.json: 19 records; products.json: 32 records.

Counts are **not additive**: catalog articles, engineering type codes, and module entries describe overlapping products.

## Legacy engineering types

- `WB8`
- `WB-UPS_V3`
- `WBIO-DI-WD-14`
- `WBIO-DI-HVD-8`
- `WBIO-DI-HVD-16`
- `WBE2-I-RS485-ISO`
- `WBE2-I-OPENTHERM`
- `WBE2-I-EBUS`
- `WBE2-I-KNX`
- `WBE2-I-RS232`
- `WB-MR6C_V2`
- `WB-MR3LV_S`
- `WB-MR6CU_V2`
- `WB-MRPS6_S`
- `WB-MRWL3`
- `WB-MRWM2`
- `WB-LED`
- `WB-AMPLED`
- `WB-MCM8`
- `WB-MAO4`
- `WB-MAO4_20MA`
- `WB-MAP3ET`
- `WB-M1W2_V3`
- `WB-MAI2_CC_V3`
- `WB-MAI6`
- `WB-MWAC`
- `WB-MGE_V3`
- `WB-MIO`
- `WB-DALI3`
- `WBC2-4G`
- `WBE2R-R-ZIGBEE-SH`
- `WB-MR6C_V3`
- `WB-MR6LV_S`
- `WB-MR3LV_I`
- `WB-MDM3`
- `WB-T120`

## Canonical passport IDs

- `protection.circuit_breaker.1p`
- `protection.rcbo.1pn`
- `distribution.cross_module.3l_pen`
- `switching.modular_contactor.2no.230vac`
- `protection.inrush_current_limiter.1ph`
- `led_tape.constant_voltage.mono.24v`
- `led_tape.constant_voltage.cct.24v`
- `led_tape.constant_voltage.rgbw.24v`
- `power.acdc.24v.din`
- `power.acdc.48v.din`
- `controller.wb_mr6c_v2`
- `controller.wb_led_v1`
- `power.wb_ups_v3`
- `gateway.wirenboard.wb_dali3`
- `module.wirenboard.wbe2_i_knx`
- `module.wirenboard.wb_mcm8`
- `controller.wiren_board_8_5`
- `gateway.wirenboard.wb_mge_v3`
- `conduit.flexible_corrugated.pp`
