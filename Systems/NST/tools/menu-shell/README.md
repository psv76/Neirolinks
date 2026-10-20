# Issue #215 — menu shell for WB 2609 (pilot, not released)

This is an **isolated, reversible pilot** for the requested first step of [Issue #215](https://github.com/psv76/Neirolinks/issues/215). It does not implement the planned NST, Input Detector, Sprut or documentation features. It is NOT an approved NST release.

## What it installs

- The native WB custom-menu drop-in at `/etc/wb-homeui/custom-menu/neirolinks.json`: a single root **NEIROLINKS**, with exactly **Сервис / Спрут / Документация**.
- Three static HTML placeholder pages at `/mnt/data/neirolinks-tools/pages/`. Only section titles are displayed.
- An nginx drop-in at `/etc/nginx/includes/default.wb.d/neirolinks-tools.conf` serving these pages at `/neirolinks-tools/{service,sprut,docs}.html`.

**No new daemon, gate, API, installed .deb, MQTT subscription, nst command, wb-rules rule or relay control.** No existing WB files are overwritten by the installer.

## Install (after selecting an authorized pilot WB 2609)

Copy this directory to the test controller, inspect files first, then run as root:

```sh
sh ./install.sh
```

The installer refuses collisions, validates the nginx config with `nginx -t` and reloads **nginx only**; it attempts rollback if installation fails. It does not reboot WB, restart wb-rules, or alter NST/Sprut/HHM.

## Verification

1. Refresh WB homeui in the browser. A single root NEIROLINKS with three nested items should appear.
2. Clicking each item should open its matching **empty HTML page in a new tab**, as per WB's documented `isExternal` + `openInNewTab` behavior.
3. Check HTTP responses: `curl -I http://127.0.0.1/neirolinks-tools/service.html` (and `sprut.html`, `docs.html`). Check `nginx -t`.
4. Existing homeui, dashboards, automations, NST CLI and other services must remain unchanged.

## Scope and security limits

- These are static placeholders only. `requiredRole: "admin"` hides menu items but **does not protect HTTP content**; the pages contain no object data or credentials. Do not put real service screens, sensitive content or write actions here without backend authorization and a reviewed gate.
- This is **not** a native React extension of WB homeui. Official WB `custom-menu` creates navigation entries, not custom React routes; external pages open separately.
- LAN access and persistence after controller reboot or updates have **not** been tested. WB Cloud compatibility has **not** been established.
- If an operator wants an actual in-homeui blank panel, use native WB dashboards instead, but those are distinct dashboards rather than future Tools web pages.

## Remove pilot

As root, after verifying these are the pilot's files, delete only:

```sh
rm -f /etc/wb-homeui/custom-menu/neirolinks.json
rm -f /etc/nginx/includes/default.wb.d/neirolinks-tools.conf
rm -rf /mnt/data/neirolinks-tools
nginx -t && systemctl reload nginx
```

Reload WB homeui in the browser. No changes to NST/Sprut/HHM or wb-rules should be needed.

## Sources

- WB Wiki: https://wiki.wirenboard.com/wiki/Third-party-services-web-ui
- Upstream homeui: https://github.com/wirenboard/homeui (custom-menu and nginx drop-in documentation)
