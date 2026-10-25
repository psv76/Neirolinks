#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root on Wiren Board." >&2
  exit 1
fi
for p in nst_2.5_all.deb neirolinks-tools_1.0_all.deb SHA256SUMS; do
  if [ ! -f "$p" ]; then echo "Missing installer file: $p" >&2; exit 1; fi
done
sha256sum -c SHA256SUMS
if ! command -v wb-homeui-gates >/dev/null 2>&1; then
  echo "WB homeui-gates not installed; update WB firmware before installation." >&2
  exit 1
fi
if ! wb-homeui-users list | grep -Eq ' \(admin\)$'; then
  echo "First configure a WB administrator in Settings -> Users, then run again." >&2
  exit 1
fi
if [ -e /etc/systemd/system/neirolinks-tools.service ] || [ -e /etc/wb-homeui/custom-menu/neirolinks.json ] || [ -e /etc/nginx/includes/default.wb.d/neirolinks-tools.conf ]; then
  echo "Manual NEIROLINKS pilot found. Do not overwrite: use a reviewed migration." >&2
  exit 1
fi
apt-get install -y ./nst_2.5_all.deb ./neirolinks-tools_1.0_all.deb
systemctl is-active --quiet neirolinks-tools.service
wb-homeui-gates check
echo "NEIROLINKS Tools installed: refresh WB WebUI menu and select Service."
