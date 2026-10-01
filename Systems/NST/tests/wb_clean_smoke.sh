#!/bin/sh
# Disposable CI rootfs only. No controller or real engineering service access.
set -eu
test "${NST_DISPOSABLE_CI:-}" = 1
test -f /.dockerenv
test ! -e /usr/bin/nli
test ! -e /mnt/data/etc/neiro/nli
apt-get update -qq
apt-get install -y /packages/nst_2.0_all.deb
test "$(dpkg-query -W -f='${Package} ${Version}' nst)" = 'nst 2.0'
test ! -e /usr/bin/nli
nst --json --version
PYTHONPATH=/usr/lib/nst python3 -B /tests/wb_clean_smoke.py
test ! -e /mnt/data/etc/neiro/nli
test ! -e /mnt/data/var/lib/neiro/nli
test ! -e /mnt/data/var/log/neiro/nli
test -f /mnt/data/etc/neirolinks/nst/config.json
test -f /mnt/data/var/lib/neirolinks/nst/platform.json
nst --json status
