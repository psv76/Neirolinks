#!/bin/sh
# Never run this on a WB. Only disposable CI Docker rootfs with synthetic data.
set -eu
nli_version() { nli --version | tail -n 1 | awk '{print $NF}'; }
nst_version() { nst --version | tail -n 1 | awk '{print $NF}'; }
test "${NLI_DISPOSABLE_CI:-}" = 1
test -f /.dockerenv
test "$(hostname)" = wirenboard-ABF62SL
printf '%s\n' 'path-exclude /usr/share/doc/*' 'path-include /usr/share/doc/*/copyright' > /etc/dpkg/dpkg.cfg.d/01_nodoc
apt-get update -qq

if [ "$1" = first ]; then
    # Historical package chain remains covered up through the exact approved NLI 0.1.9.
    for v in 0.1.0 0.1.1 0.1.2 0.1.3 0.1.4 0.1.5 0.1.6 0.1.7 0.1.8 0.1.9; do
        apt-get install -y "/old/neiro-nli_${v}_all.deb"
        test "$(nli_version)" = "$v"
        if [ "$v" = 0.1.0 ]; then
            printf '%s\n' '{"object":"legacy-reviewed","role":"boiler","hostname":"wirenboard-ABF62SL","components":{}}' > /etc/neiro/nli/config.json
            sha256sum /etc/neiro/nli/config.json > /evidence/old-conffile.sha256
        fi
    done
    sha256sum -c /evidence/old-conffile.sha256
    if nli --json status > /evidence/legacy-status.json; then
        echo 'Configured legacy profile was silently discarded' >&2
        exit 1
    fi
    grep LEGACY_MIGRATION_REQUIRED /evidence/legacy-status.json

    # Reset ONLY the synthetic obsolete /etc fixture; persistent NLI state is created below.
    cp /usr/share/neiro-nli/default-config.json /etc/neiro/nli/config.json
    nli --json status
    test ! -e /mnt/data/etc/neiro/nli
    test ! -e /mnt/data/var/lib/neiro/nli
    test ! -e /mnt/data/var/log/neiro/nli
    python3 -B /tests/wb_installed_smoke.py prepare_nli

    # Package rename must not need controller/service hooks. Identity exists only for later NST CLI reads.
    mkdir -p /var/lib/wirenboard
    printf '%s\n' ABF62SL > /var/lib/wirenboard/short_sn
    apt-get install -y /packages/neiro-nst_1.0.0_all.deb
    test "$(nst_version)" = 1.0.0
    test "$(nli_version)" = 1.0.0
    if dpkg-query -W neiro-nli >/dev/null 2>&1; then
        echo 'Legacy neiro-nli package still installed after NST migration' >&2
        exit 1
    fi
    test ! -e /usr/lib/neiro-nli
    test ! -e /usr/share/neiro-nli
    python3 -B /tests/wb_installed_smoke.py migrated

    apt-get install --reinstall -y /packages/neiro-nst_1.0.0_all.deb
    python3 -B /tests/wb_installed_smoke.py reinstall
else
    test "$1" = fit
    # Fresh rootfs loses /usr and dpkg database, but mounts exactly the same /mnt/data.
    test ! -e /usr/bin/nst
    test -f /mnt/data/etc/neiro/nli/config.json
    mkdir -p /var/lib/wirenboard
    printf '%s\n' ABF62SL > /var/lib/wirenboard/short_sn
    apt-get install -y /packages/neiro-nst_1.0.0_all.deb
    test "$(nst_version)" = 1.0.0
    test "$(nli_version)" = 1.0.0
    python3 -B /tests/wb_installed_smoke.py fit
fi

test -z "$(find /usr/lib/neiro-nst -name '*.pyc' -print)"
