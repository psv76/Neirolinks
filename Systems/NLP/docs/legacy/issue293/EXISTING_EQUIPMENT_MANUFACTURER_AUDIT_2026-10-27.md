# Issue #293 — проверка исходных паспортов по производителю

**Область:** аудит восьми существующих WB паспортов и двух неопубликованных legacy моделей. Не заменяет UI/workflow acceptance.
Матрица: 43 legacy SKU; READY 38, NEEDS_VERIFICATION 5, MISSING 0.
Текущий релиз-кандидат в GitHub: 49 паспортов и 65 товаров. Рабочая SQLite остаётся на 20/33.

## Подтверждённые действующие паспорта

### WB-UPS v.3

Паспорт: power.wb_ups_v3

1 Vin 10–27 V, 1 Vout 9–25 V battery mode, 15 W continuous/20 W peak, internal 2×18650 battery, RS485 Modbus. The existing catalog reflects the electrical resources.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-UPS_v.3_Backup_power_supply

### WBE2-I-KNX

Паспорт: module.wirenboard.wbe2_i_knx

Exactly one KNX bus port (not RS485), 4 kV isolation, external KNX bus power, and one host MOD attachment. WB8.5 attachment supported by the current Constructor.

Manufacturer: https://wiki.wirenboard.com/wiki/index.php/KNX_Module_for_WB6_%28WBE2-I-KNX%29

### WB-MR6C v.2

Паспорт: controller.wb_mr6c_v2

6 NO relay outputs, COM1/COM2 with 3 outputs per group, group 30 A nominal, individual 10 A nominal/16 A maximum/80 A inrush at 20 ms, seven dry inputs 0–6, Modbus RTU.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-MR6C_v.2_Modbus_Relay_Modules

### WB-DALI3

Паспорт: gateway.wirenboard.wb_dali3

3 separate DA1/DA2/DA3 buses 200/100/100 mA, 7 dry inputs, separate upstream RS485 Modbus and both AC 230 V and DC 9–28 V power feeds.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-DALI_Modbus-to-DALI_Gateway_%283-channel%29

### WB-MCM8

Паспорт: module.wirenboard.wb_mcm8

8 isolated-group dry contact/open-collector counter inputs, RS485 Modbus RTU, 9–28 VDC supply. No relay outputs.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-MCM8_Modbus_Count_Inputs/en

## Заблокированные позиции

Публикация новых/изменённых ресурсов старых паспортов невозможна простой подменой JSON: каталог immutable и требуется поддержка версии, миграции и UI.

### WB8-4G-64G-IND

WB8-4G-64G-IND denotes 4 GB RAM and 64 GB eMMC (not an installed LTE modem). Its WB8.5 hardware has 2 native RS485 and 4 MOD slots, but the current base passport unconditionally materializes optional CELLULAR_MODEM. Requires typed optional resource/product configuration without altering existing instances.

Manufacturer: https://wiki.wirenboard.com/wiki/Wiren_Board_8.5
Official SKU listing (memory configuration): https://wirenboard.com/ru/catalog/pricelist/

### WB-MGE v.3

2 RS485 and 2 Vout terminals confirmed; Vout are switched as ONE GROUP, not independently. Existing per-port resources lack shared actuator semantics; addition/change to immutable published passport requires versioned successor plus live-preserving migration.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-MGE_v.3_Modbus_Ethernet_Gateway/en

### WB-LED

Legacy article lacks explicit hardware revision, while the published canonical item is WB-LED v.1. Do not silently map unversioned legacy item to one revision.

Manufacturer: https://wiki.wirenboard.com/wiki/WB-LED_v.1_Modbus_LED_Dimmer

### WB-MRM2-mini v.3

The v.3 device EXISTS as a distinct planned product with 2 relay outputs and FOUR configurable 1-Wire/DI/DO inputs. Manufacturer states UNDER DEVELOPMENT / NOT AVAILABLE. Do not substitute a v.2 passport.

Manufacturer: https://wirenboard.com/en/product/WB-MRM2-mini-v3/

### WB-MDIO8

Manufacturer states UNDER DEVELOPMENT with estimated first deliveries in 2027. Planned 8 button inputs, 6 LED/backlight outputs are preliminary and not an approved deliverable product.

Manufacturer: https://wirenboard.com/ru/contents/product/WB-MDIO8/

## Приёмка

Проверка официальных фактов добавлена в tests/catalog/test_issue293_existing_audit.py; база/DWG не изменены.
Готовность этих пяти паспортов относится к предметной модели (resource count and type), а не пользовательскому сценарию.
