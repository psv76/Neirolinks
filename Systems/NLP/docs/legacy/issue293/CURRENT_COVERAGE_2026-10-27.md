# Issue #293 — матрица покрытия после исправления WB8.5 и WB-MGE

READY означает документированную модель/ресурсы в SOURCE-кандидате, НЕ автоматически мигрированные экземпляры и не пользовательскую приёмку.
Всего 43 legacy SKU; READY 40; NEEDS_VERIFICATION 3; MISSING 0.
Каталог-кандидат 51 паспорт / 67 товаров; live SQLite по-прежнему 20/33.

| Артикул | Статус | Паспорт | Товар | Причина |
|---|---|---|---|---|
| WB8-4G-64G-IND | READY | controller.wiren_board_8_5_modular_cellular | product.wirenboard.wb8_4g_64g_ind_modular_cellular | Corrected NEW WB8.5 variant provides 4 MOD slots and one dedicated MODEM slot; no preinstalled cellular interface, WBC2-4G requires typed installation. Old published passport/instances are NOT automatically migrated. |
| WBIO-DI-WD-14 | READY | module.wirenboard.wbio_di_wd_14 | product.wirenboard.wbio_di_wd_14 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBIO-DI-HVD-16 | READY | module.wirenboard.wbio_di_hvd_16 | product.wirenboard.wbio_di_hvd_16 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBIO-DI-HVD-8 | READY | module.wirenboard.wbio_di_hvd_8 | product.wirenboard.wbio_di_hvd_8 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-UPS v.3 | READY | power.wb_ups_v3 | product.wirenboard.wb_ups_v3 | 1 Vin 10–27 V, 1 Vout 9–25 V battery mode, 15 W continuous/20 W peak, internal 2×18650 battery, RS485 Modbus. The existing catalog reflects the electrical resources. |
| WBC2-4G | READY | module.wirenboard.wbc2_4g | product.wirenboard.wbc2_4g | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2R-R-ZIGBEE-SH | READY | module.wirenboard.wbe2r_r_zigbee_sh | product.wirenboard.wbe2r_r_zigbee_sh | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-KNX | READY | module.wirenboard.wbe2_i_knx | product.wirenboard.wbe2_i_knx | Exactly one KNX bus port (not RS485), 4 kV isolation, external KNX bus power, and one host MOD attachment. WB8.5 attachment supported by the current Constructor. |
| WBE2-I-RS232 | READY | module.wirenboard.wbe2_i_rs232 | product.wirenboard.wbe2_i_rs232 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-RS485-ISO | READY | module.wirenboard.wbe2_i_rs485_iso | product.wirenboard.wbe2_i_rs485_iso | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-OPENTHERM | READY | module.wirenboard.wbe2_i_opentherm | product.wirenboard.wbe2_i_opentherm | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WBE2-I-EBUS | READY | module.wirenboard.wbe2_i_ebus | product.wirenboard.wbe2_i_ebus | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRWM2 | READY | module.wirenboard.wb_mrwm2 | product.wirenboard.wb_mrwm2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6C v.2 | READY | controller.wb_mr6c_v2 | product.wirenboard.wb_mr6c_v2 | 6 NO relay outputs, COM1/COM2 with 3 outputs per group, group 30 A nominal, individual 10 A nominal/16 A maximum/80 A inrush at 20 ms, seven dry inputs 0–6, Modbus RTU. |
| WB-MR6C v.3 | READY | module.wirenboard.wb_mr6c_v3 | product.wirenboard.wb_mr6c_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6LV/S | READY | module.wirenboard.wb_mr6lv_s | product.wirenboard.wb_mr6lv_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR6CU v.2 | READY | module.wirenboard.wb_mr6cu_v2 | product.wirenboard.wb_mr6cu_v2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR3LV/S | READY | module.wirenboard.wb_mr3lv_s | product.wirenboard.wb_mr3lv_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MR3LV/I | READY | module.wirenboard.wb_mr3lv_i | product.wirenboard.wb_mr3lv_i | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRPS6/S | READY | module.wirenboard.wb_mrps6_s | product.wirenboard.wb_mrps6_s | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRWL3 | READY | module.wirenboard.wb_mrwl3 | product.wirenboard.wb_mrwl3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MRM2-mini v.3 | NEEDS_VERIFICATION | — | — | The v.3 device EXISTS as a distinct planned product with 2 relay outputs and FOUR configurable 1-Wire/DI/DO inputs. Manufacturer states UNDER DEVELOPMENT / NOT AVAILABLE. Do not substitute a v.2 passport. |
| WB-MAP3ET | READY | module.wirenboard.wb_map3et | product.wirenboard.wb_map3et | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-M1W2 v.3 | READY | module.wirenboard.wb_m1w2_v3 | product.wirenboard.wb_m1w2_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/1m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_1m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/3m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_3m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/5m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_5m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| DS18B20/10m | READY | module.wirenboard.ds18b20_probe | product.wirenboard.ds18b20_10m | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAI2-mini/CC v.3 | READY | module.wirenboard.wb_mai2_cc_v3 | product.wirenboard.wb_mai2_cc_v3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAI6 | READY | module.wirenboard.wb_mai6 | product.wirenboard.wb_mai6 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-LED | NEEDS_VERIFICATION | controller.wb_led_v1 | product.wirenboard.wb_led_v1 | Legacy article lacks explicit hardware revision, while the published canonical item is WB-LED v.1. Do not silently map unversioned legacy item to one revision. |
| WB-MDM3 | READY | module.wirenboard.wb_mdm3 | product.wirenboard.wb_mdm3 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-DALI3 | READY | gateway.wirenboard.wb_dali3 | product.wirenboard.wb_dali3 | 3 separate DA1/DA2/DA3 buses 200/100/100 mA, 7 dry inputs, separate upstream RS485 Modbus and both AC 230 V and DC 9–28 V power feeds. |
| WB-MAO4 | READY | module.wirenboard.wb_mao4 | product.wirenboard.wb_mao4 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MAO4-20mA | READY | module.wirenboard.wb_mao4_20ma | product.wirenboard.wb_mao4_20ma | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-AMPLED | READY | module.wirenboard.wb_ampled | product.wirenboard.wb_ampled | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-T120 | READY | module.wirenboard.wb_t120 | product.wirenboard.wb_t120 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MWAC | READY | module.wirenboard.wb_mwac_v2 | product.wirenboard.wb_mwac_v2 | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MCM8 | READY | module.wirenboard.wb_mcm8 | product.wirenboard.wb_mcm8 | 8 isolated-group dry contact/open-collector counter inputs, RS485 Modbus RTU, 9–28 VDC supply. No relay outputs. |
| WB-MCM8HV | READY | module.wirenboard.wb_mcm8hv | product.wirenboard.wb_mcm8hv | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MGE v.3 | READY | gateway.wirenboard.wb_mge_v3_shared_vout | product.wirenboard.wb_mge_v3_shared_vout | Corrected NEW variant preserves two physical Vout terminals but ONE shared switching group. Old published passport/instances are NOT automatically migrated. |
| WB-MIO | READY | module.wirenboard.wb_mio | product.wirenboard.wb_mio | Manufacturer-based resource model audited; not end-to-end user acceptance |
| WB-MDIO8 | NEEDS_VERIFICATION | — | — | Manufacturer states UNDER DEVELOPMENT with estimated first deliveries in 2027. Planned 8 button inputs, 6 LED/backlight outputs are preliminary and not an approved deliverable product. |

Важное ограничение: новые варианты WB8.5 и WB-MGE НЕ заменяют ранее опубликованные паспортные ресурсы и не мигрируют уже созданные экземпляры.
Неопубликованные/неопределённые WB-MRM2-mini v.3, WB-MDIO8 и WB-LED без аппаратной ревизии остаются NEEDS_VERIFICATION.
