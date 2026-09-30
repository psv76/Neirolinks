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

    cp /usr/share/neiro-nli/default-config.json /etc/neiro/nli/config.json
    nli --json status
    test ! -e /mnt/data/etc/neiro/nli
    test ! -e /mnt/data/var/lib/neiro/nli
    test ! -e /mnt/data/var/log/neiro/nli

    # Exact NLI 0.1.9 creates component state, backup, audit and pending.
    python3 -B /tests/wb_installed_smoke.py prepare_nli

    mkdir -p /var/lib/wirenboard
    printf '%s\n' ABF62SL > /var/lib/wirenboard/short_sn

    # Package-only migration: no package hooks may touch WB services or persistent data.
    apt-get install -y /packages/nst_2.0_all.deb
    test "$(nst_version)" = 2.0
    test ! -e /usr/bin/nli
    legacy_status="$(awk '
        $0 == "Package: neiro-nli" { found=1; next }
        found && /^Status:/ { print; exit }
        found && /^Package:/ { exit }
    ' /var/lib/dpkg/status)"
    test "$legacy_status" != "Status: install ok installed"
    test ! -e /usr/lib/neiro-nli
    test ! -e /usr/share/neiro-nli
    python3 -B /tests/wb_installed_smoke.py migrated

    apt-get install --reinstall -y /packages/nst_2.0_all.deb
    python3 -B /tests/wb_installed_smoke.py reinstall
else
    test "$1" = fit
    test ! -e /usr/bin/nst
    test -f /mnt/data/etc/neiro/nli/config.json
    mkdir -p /var/lib/wirenboard
    printf '%s\n' ABF62SL > /var/lib/wirenboard/short_sn
    apt-get install -y /packages/nst_2.0_all.deb
    test "$(nst_version)" = 2.0
    test ! -e /usr/bin/nli
    python3 -B /tests/wb_installed_smoke.py fit
fi

test -z "$(find /usr/lib/nst -name '*.pyc' -print)"
