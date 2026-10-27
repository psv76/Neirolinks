# Issue #293: единая матрица фактического покрытия

Статус READY относится к данным паспорта и требует отдельной UI и startup-приёмки.
Legacy SKU: 43; passports: 49, products: 65; {'READY': 33, 'NEEDS_VERIFICATION': 10, 'MISSING': 0, 'DEPRECATED': 0}.

| Артикул | Код инженерный | Статус | Паспорт | Товар | Причина |
|---|---|---|---|---|---|
| WB8-4G-64G-IND | WB8 | NEEDS_VERIFICATION | controller.wiren_board_8_5 | product.wirenboard.wb8_4g_64g_ind | Published model needs full revision/resource audit |
| WBIO-DI-WD-14 | WBIO-DI-WD-14 | READY | module.wirenboard.wbio_di_wd_14 | product.wirenboard.wbio_di_wd_14 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBIO-DI-HVD-16 | WBIO-DI-HVD-16 | READY | module.wirenboard.wbio_di_hvd_16 | product.wirenboard.wbio_di_hvd_16 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBIO-DI-HVD-8 | WBIO-DI-HVD-8 | READY | module.wirenboard.wbio_di_hvd_8 | product.wirenboard.wbio_di_hvd_8 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-UPS v.3 | WB-UPS_V3 | NEEDS_VERIFICATION | power.wb_ups_v3 | product.wirenboard.wb_ups_v3 | Published model needs full revision/resource audit |
| WBC2-4G | WBC2-4G | READY | module.wirenboard.wbc2_4g | product.wirenboard.wbc2_4g | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2R-R-ZIGBEE-SH | WBE2R-R-ZIGBEE-SH | READY | module.wirenboard.wbe2r_r_zigbee_sh | product.wirenboard.wbe2r_r_zigbee_sh | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-KNX | WBE2-I-KNX | NEEDS_VERIFICATION | module.wirenboard.wbe2_i_knx | product.wirenboard.wbe2_i_knx | Published model needs full revision/resource audit |
| WBE2-I-RS232 | WBE2-I-RS232 | READY | module.wirenboard.wbe2_i_rs232 | product.wirenboard.wbe2_i_rs232 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-RS485-ISO | WBE2-I-RS485-ISO | READY | module.wirenboard.wbe2_i_rs485_iso | product.wirenboard.wbe2_i_rs485_iso | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-OPENTHERM | WBE2-I-OPENTHERM | READY | module.wirenboard.wbe2_i_opentherm | product.wirenboard.wbe2_i_opentherm | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-EBUS | WBE2-I-EBUS | READY | module.wirenboard.wbe2_i_ebus | product.wirenboard.wbe2_i_ebus | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRWM2 | WB-MRWM2 | READY | module.wirenboard.wb_mrwm2 | product.wirenboard.wb_mrwm2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6C v.2 | WB-MR6C_V2 | NEEDS_VERIFICATION | controller.wb_mr6c_v2 | product.wirenboard.wb_mr6c_v2 | Published model needs full revision/resource audit |
| WB-MR6C v.3 | WB-MR6C_V3 | READY | module.wirenboard.wb_mr6c_v3 | product.wirenboard.wb_mr6c_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6LV/S | WB-MR6LV_S | READY | module.wirenboard.wb_mr6lv_s | product.wirenboard.wb_mr6lv_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6CU v.2 | WB-MR6CU_V2 | READY | module.wirenboard.wb_mr6cu_v2 | product.wirenboard.wb_mr6cu_v2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR3LV/S | WB-MR3LV_S | READY | module.wirenboard.wb_mr3lv_s | product.wirenboard.wb_mr3lv_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR3LV/I | WB-MR3LV_I | READY | module.wirenboard.wb_mr3lv_i | product.wirenboard.wb_mr3lv_i | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRPS6/S | WB-MRPS6_S | READY | module.wirenboard.wb_mrps6_s | product.wirenboard.wb_mrps6_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRWL3 | WB-MRWL3 | READY | module.wirenboard.wb_mrwl3 | product.wirenboard.wb_mrwl3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRM2-mini v.3 | WB-MRM2-mini v.3 | NEEDS_VERIFICATION | — | — | Legacy v.3 does not match official published 2.x revision table; do not substitute blindly. |
| WB-MAP3ET | WB-MAP3ET | READY | module.wirenboard.wb_map3et | product.wirenboard.wb_map3et | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-M1W2 v.3 | WB-M1W2_V3 | READY | module.wirenboard.wb_m1w2_v3 | product.wirenboard.wb_m1w2_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/1m | DS18B20/1m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_1m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/3m | DS18B20/3m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_3m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/5m | DS18B20/5m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_5m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/10m | DS18B20/10m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_10m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAI2-mini/CC v.3 | WB-MAI2_CC_V3 | READY | module.wirenboard.wb_mai2_cc_v3 | product.wirenboard.wb_mai2_cc_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAI6 | WB-MAI6 | READY | module.wirenboard.wb_mai6 | product.wirenboard.wb_mai6 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-LED | WB-LED | NEEDS_VERIFICATION | controller.wb_led_v1 | product.wirenboard.wb_led_v1 | Legacy article lacks revision; existing product describes WB-LED v.1. Revision-specific UI/resource audit needed. |
| WB-MDM3 | WB-MDM3 | READY | module.wirenboard.wb_mdm3 | product.wirenboard.wb_mdm3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-DALI3 | WB-DALI3 | NEEDS_VERIFICATION | gateway.wirenboard.wb_dali3 | product.wirenboard.wb_dali3 | Published model needs full revision/resource audit |
| WB-MAO4 | WB-MAO4 | READY | module.wirenboard.wb_mao4 | product.wirenboard.wb_mao4 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAO4-20mA | WB-MAO4_20MA | READY | module.wirenboard.wb_mao4_20ma | product.wirenboard.wb_mao4_20ma | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-AMPLED | WB-AMPLED | READY | module.wirenboard.wb_ampled | product.wirenboard.wb_ampled | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-T120 | WB-T120 | READY | module.wirenboard.wb_t120 | product.wirenboard.wb_t120 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MWAC | WB-MWAC | READY | module.wirenboard.wb_mwac_v2 | product.wirenboard.wb_mwac_v2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MCM8 | WB-MCM8 | NEEDS_VERIFICATION | module.wirenboard.wb_mcm8 | product.wirenboard.wb_mcm8 | Published model needs full revision/resource audit |
| WB-MCM8HV | WB-MCM8HV | READY | module.wirenboard.wb_mcm8hv | product.wirenboard.wb_mcm8hv | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MGE v.3 | WB-MGE_V3 | NEEDS_VERIFICATION | gateway.wirenboard.wb_mge_v3 | product.wirenboard.wb_mge_v3 | Published model needs full revision/resource audit |
| WB-MIO | WB-MIO | READY | module.wirenboard.wb_mio | product.wirenboard.wb_mio | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MDIO8 | WB-MDIO8 | NEEDS_VERIFICATION | — | — | Manufacturer page describes a device under development and not available; no confirmed released revision. |

Рабочая база содержит предыдущий release 20/33, кандидат 49/65 ещё не установлен.
Техническое объединение 43 SKU, 36 инженерных типов и 16 определений не требует создания 95 паспортов.
WBIO требует отдельной проверенной установки по боковой шине, WBC2-4G устанавливается в модемный слот, а не в MOD.
WB-MRM2-mini v.3 и WB-MDIO8 не должны получать ложный статус READY без источников.
WB-LED v.1 и legacy WB-LED не объявлять тождественными без проверки ревизии.
