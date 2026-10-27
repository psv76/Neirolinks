# Issue #293 — вариантные паспорта WB8.5 и WB-MGE v.3

**Дата:** 27.10.2026. **Статус:** кандидаты в исходном каталоге; не устанавливать без финальной GUI и live-приёмки.

## WB8-4G-64G-IND: опциональный LTE-модем

Официальное обозначение 4G/64G относится к **4 ГБ RAM / 64 ГБ eMMC**:
- https://www-direct.wirenboard.com/en/catalog/pricelist/
- https://wiki.wirenboard.com/wiki/Wiren_Board_8.5

Сам 4G (LTE) — физически отдельный WBC2-4G для WB7.4/WB8:
- https://wiki.wirenboard.com/wiki/WBC2-4G
- https://wirenboard.com/en/product/WBC2-4G/

Проверенная модель нового варианта:
- `controller.wiren_board_8_5_modular_cellular`;
- товар `product.wirenboard.wb8_4g_64g_ind_modular_cellular`;
- **две штатные RS485 и четыре обычных MOD1–MOD4** остаются без изменений;
- физический слот `INTERNAL_MODEM_SLOT` ×1, отдельно от MOD1–MOD4;
- **отсутствуют** фиктивные `CELLULAR_MODEM` и `NANOSIM` как функциональные ресурсы *голого контроллера*;
- модем `module.wirenboard.wbc2_4g` устанавливается через отдельную типизированную `MODEM_INSTALLATION`, ресурс `MODEM_SLOT_ATTACHMENT`.
- `WBC2-4G` продолжает владеть `CELLULAR_DATA` и SIM-capability, не создаётся сам на контроллере без установки.
- создание связи допускает лишь `INTERNAL_MODEM_SLOT` данного варианта WB8.5 → attachment именно WBC2-4G, блокирует повторное занятие и использование MOD3 вместо MODEM.
- SKU производителя **не создавался новый**: у variant Product поле `article=null`, в `official_source.reference_article` хранится исходный `WB8-4G-64G-IND`; так не нарушается уникальность существующего manufacturer/article.

## WB-MGE v.3: два Vout и одна команда

Официальный источник:
- https://wiki.wirenboard.com/wiki/WB-MGE_v.3_Modbus_Ethernet_Gateway
- В документации: два Vout, включаются/выключаются **одновременно одной группой**, допустимая суммарная нагрузка, а не два независимо управляемых канала.

Проверенная модель нового варианта:
- `gateway.wirenboard.wb_mge_v3_shared_vout`;
- товар `product.wirenboard.wb_mge_v3_shared_vout`;
- `Vout-1` и `Vout-2` остаются **двумя разными физическими выходными ресурсами** для проводных связей;
- каждому присвоен **общий** `group_key=VOUT_SHARED_SWITCH`, и `independently_switchable=false`;
- в столбце «Группа» UI должно появляться «Общее включение Vout-1 и Vout-2»;
- `combined_maximum_current_a=2.5` не трактовать как отдельный предел на каждый выход.
- не дублировать SKU: `article=null` и `official_source.reference_article=WB-MGE v.3`.

## Иммутабельность, охват и приёмка

Исходные паспорта `controller.wiren_board_8_5` и `gateway.wirenboard.wb_mge_v3`, товары, resource IDs и live-привязки оставлены **неизменными**. Введение исправленных variant IDs — добавочный successor, не репаспортизация исторических экземпляров.

Кандидат: `nlp3.equipment.2026-10-27.wb-optional-modem-shared-vout`, **51 паспорт / 67 товаров**. Предшественник live: `nlp3.equipment.2026-10-27.wbe2-rs485-iso` (20/33), нет schema migration.

Тесты `tests/catalog/test_issue293_modem_and_grouped_vout.py` проверяют реализацию на **одноразовой SQLite**, а полный successor репетирован на копии реальной БД: `D:\NLP_3_BACKUPS\issue293_51_67_rehearsal\successor_rehearsal_receipt.json` — PASS, старые instance/resource/bus ID сохранены, integrity/FK PASS, idempotence PASS.

**Не заявлять, что старые WB8 или WB-MGE экземпляры автоматически исправлены.** Следующий gate: UI acceptance новых вариантов на отдельном объекте, политика миграции активных экземпляров и старых output/control назначений с сохранением их ID; затем verified backup и штатная установка рабочего каталога. DWG/рабочая SQLite на этом этапе не изменяются.
