#!/bin/sh
# Never run this on a WB. Only disposable CI Docker rootfs with synthetic data.
set -eu
test "${NLI_DISPOSABLE_CI:-}" = 1
test -f /.dockerenv
test "$(hostname)" = wirenboard-ABF62SL
printf '%s\n' 'path-exclude /usr/share/doc/*' 'path-include /usr/share/doc/*/copyright' > /etc/dpkg/dpkg.cfg.d/01_nodoc
apt-get update -qq
if [ "$1" = first ]; then
    apt-get install -y /old/neiro-nli_0.1.0_all.deb
    test "$(nli --version)" = 0.1.0
    printf '%s\n' '{"object":"legacy-reviewed","role":"boiler","hostname":"wirenboard-ABF62SL","components":{}}' > /etc/neiro/nli/config.json
    sha256sum /etc/neiro/nli/config.json > /evidence/old-conffile.sha256
    apt-get install -y /old/neiro-nli_0.1.1_all.deb
    test "$(nli --version)" = 0.1.1
    apt-get install -y /packages/neiro-nli_0.1.2_all.deb
    sha256sum -c /evidence/old-conffile.sha256
    test "$(nli --version)" = 0.1.2
    if nli --json status > /evidence/legacy-status.json; then
        echo 'Configured legacy profile was silently discarded' >&2
        exit 1
    fi
    grep LEGACY_MIGRATION_REQUIRED /evidence/legacy-status.json
    # Reset ONLY the synthetic legacy fixture to the unchanged 0.1.0 default.
    cp /usr/share/neiro-nli/default-config.json /etc/neiro/nli/config.json
    nli --json status
    test ! -e /mnt/data/etc/neiro/nli
    test ! -e /mnt/data/var/lib/neiro/nli
    test ! -e /mnt/data/var/log/neiro/nli
    test ! -e /var/lib/neiro/nli
    test ! -e /var/log/neiro/nli
    python3 -B /tests/wb_installed_smoke.py bootstrap
    apt-get install --reinstall -y /packages/neiro-nli_0.1.2_all.deb
    python3 -B /tests/wb_installed_smoke.py reinstall
    # Modified legacy obsolete conffile is neither replaced nor deleted on reinstall.
    printf '%s\n' '{"object":"legacy-reviewed","role":"boiler","hostname":"wirenboard-ABF62SL","components":{}}' > /etc/neiro/nli/config.json
    sha256sum /etc/neiro/nli/config.json > /evidence/modified-conffile.sha256
    apt-get install --reinstall -y /packages/neiro-nli_0.1.2_all.deb
    sha256sum -c /evidence/modified-conffile.sha256
    python3 -B /tests/wb_installed_smoke.py reinstall
else
    test "$1" = fit
    # Fresh container loses /usr and dpkg database, but mounts the same /mnt/data.
    test ! -e /usr/bin/nli
    test -f /mnt/data/etc/neiro/nli/config.json
    apt-get install -y /packages/neiro-nli_0.1.2_all.deb
    python3 -B /tests/wb_installed_smoke.py fit
fi
test -z "$(find /usr/lib/neiro-nli -name '*.pyc' -print)"
