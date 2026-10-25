# NEIROLINKS Tools 1.0 — публикация

Отдельный read-only WebUI companion для NST 2.5, направленный на установку с одного автономного onboarding kit. Canonical source: `Systems/NST/tools-ui`.

1. CI: Python unit/security tests, `visudo -cf`, `sh -n` всех package hooks, `dpkg-deb --info/--contents`; проверить наличие точного `neirolinks-tools_1.0_all.deb` в Linux CI артефактах.
2. Сравнить имя/версию/байты с merge commit в `main`. Проверить SHA-256 и источники всех WB gate/custom-menu + sudoers.
3. Опубликовать новый immutable Release `neirolinks-tools-approved-package-1.0` (tag на merge commit), вложения: точный Debian CI пакет и offline onboarding kit (пакет NST 2.5 из неизменённого approved Release + Tools 1.0 + SHA256SUMS + install.sh).
4. На новом неизвестном WB в WebUI создать учётную запись администратора. Скопировать kit, выполнить `sh install.sh`. Система настраивает только отдельный systemd сервис Tools, WB HomeUI gate и меню; без `nst sync` и изменений оборудования.
5. Полевой acceptance: меню, admin gate deny для guest/operator, работа кнопок inventory/channel-map на **незарегистрированном serial**, checksum архива, отсутствие рестартов wb-rules и конфликтов nginx, удаление/восстановление меню.
6. Пилот Иволги содержит вручную установленный v5 и требует отдельной миграции; установка пакета автоматически блокируется во избежание перезаписи.
7. Gate не доступен через стандартный WB Cloud WebUI tunnel; штатный dedicated port требует LAN/Tailscale или отдельно согласованный сервис WB Cloud.

Никакой Release сам по себе не меняет live-контроллер. Пока не выполнен live acceptance, это approved пакет по CI, но не проверенная установка на двух новых объектах.
