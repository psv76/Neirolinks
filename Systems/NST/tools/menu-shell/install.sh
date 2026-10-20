#!/bin/sh
# Issue #215: install only the menu and static blank pages on a test WB 2609.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MENU_DIR=/etc/wb-homeui/custom-menu
NGINX_DIR=/etc/nginx/includes/default.wb.d
PAGES_DIR=/mnt/data/neirolinks-tools/pages
MENU_FILE="$MENU_DIR/neirolinks.json"
NGINX_FILE="$NGINX_DIR/neirolinks-tools.conf"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root on the test Wiren Board controller." >&2; exit 1
fi
if [ ! -d "$NGINX_DIR" ] || ! command -v nginx >/dev/null 2>&1; then
    echo "Expected WB homeui nginx drop-in support is missing; no changes made." >&2; exit 1
fi
if [ -e "$MENU_FILE" ] || [ -e "$NGINX_FILE" ] || [ -e /mnt/data/neirolinks-tools ]; then
    echo "Existing NEIROLINKS files detected; refusing to overwrite." >&2; exit 1
fi

rollback() {
    echo "Install failed; removing new files and restoring nginx configuration." >&2
    rm -f "$MENU_FILE" "$NGINX_FILE"
    rm -rf /mnt/data/neirolinks-tools
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
}
trap rollback EXIT HUP INT TERM
mkdir -p "$MENU_DIR" "$PAGES_DIR"
install -m 0644 "$SCRIPT_DIR/files/custom-menu/neirolinks.json" "$MENU_FILE"
install -m 0644 "$SCRIPT_DIR/files/pages/service.html" "$PAGES_DIR/service.html"
install -m 0644 "$SCRIPT_DIR/files/pages/sprut.html" "$PAGES_DIR/sprut.html"
install -m 0644 "$SCRIPT_DIR/files/pages/docs.html" "$PAGES_DIR/docs.html"
install -m 0644 "$SCRIPT_DIR/files/nginx/neirolinks-tools.conf" "$NGINX_FILE"
nginx -t
systemctl reload nginx
trap - EXIT HUP INT TERM
echo "NEIROLINKS static menu shell installed. Refresh the WB homeui page."
echo "Open /neirolinks-tools/{service,sprut,docs}.html for verification."
