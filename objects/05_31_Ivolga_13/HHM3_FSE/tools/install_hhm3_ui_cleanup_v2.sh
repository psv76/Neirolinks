#!/bin/bash
set -Eeuo pipefail

# 05 31 Иволга 13 · HHM3 UI cleanup v2
# Installs only:
#   /etc/wb-rules/500_HHM3_FSE.js
#   /etc/wb-rules/620_thermostats.js
#
# Changes:
# - removes legacy HHM3_FSE circuits_json/source_json/last_event_json controls;
# - keeps operator-facing HHM3 status only;
# - fixes thermostat current_state switch writes to boolean.
#
# Does not touch 507, OT config, Sprut, MQTT config, setpoints or PersistentStorage.
# Does not press start_heating.

REPO="psv76/Neirolinks"
TARGET_COMMIT="a1ca874931343f29e8348fa2ba74832f7c1210e3"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13/HHM3_FSE"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE500="/etc/wb-rules/500_HHM3_FSE.js"
RULE620="/etc/wb-rules/620_thermostats.js"

# Accepted current live variants after the previous UI cleanup.
BASE_SHA_500="dbad805288bdfbc1ea066e0f49912cc2ed82d3db44b5ab379bacde84fcf3d420"
BASE_SHA_620_UI="cfee47376aa8443a7bbf9ca843aa8ad9a78858e41b268fe93873a6bb189f49b5"
BASE_SHA_620_BOOL="570874b06a045723feb3fac857f6f36fc007953ddc0b8ec0599a45837a0327fc"

TARGET_SHA_500="e22959fba4b9dfd40da7830b4fd8dd25559a596811ac800a6cb9c608cc522b83"
TARGET_SHA_620="570874b06a045723feb3fac857f6f36fc007953ddc0b8ec0599a45837a0327fc"

mqtt_once() {
    timeout 6 mosquitto_sub -h 127.0.0.1 -t "/devices/$1/controls/$2" -C 1 2>/dev/null || true
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "STOP: command not found: $1" >&2; exit 1; }
}

preflight() {
    [ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "STOP: wrong controller: $(hostname)" >&2; exit 1; }
    systemctl is-active --quiet wb-rules || { echo "STOP: wb-rules is not active" >&2; exit 1; }

    local active k1
    active="$(mqtt_once pressure_makeup active)"
    k1="$(mqtt_once A04 K1)"
    [ "$active" = "0" ] || { echo "STOP: pressure makeup is active: $active" >&2; exit 1; }
    [ "$k1" = "0" ] || { echo "STOP: A04/K1 is not confirmed OFF: $k1" >&2; exit 1; }
    echo "PREFLIGHT OK: makeup inactive; A04/K1 OFF; pressure value is not checked"
}

verify_live() {
    local s500 s620
    s500="$(sha256sum "$RULE500" | awk '{print $1}')"
    s620="$(sha256sum "$RULE620" | awk '{print $1}')"

    if [ "$s500" = "$TARGET_SHA_500" ] && [ "$s620" = "$TARGET_SHA_620" ]; then
        echo "ALREADY INSTALLED: both files match $TARGET_COMMIT"
        exit 0
    fi

    [ "$s500" = "$BASE_SHA_500" ] || {
        echo "STOP: unexpected 500 SHA: $s500" >&2
        exit 1
    }

    if [ "$s620" != "$BASE_SHA_620_UI" ] && [ "$s620" != "$BASE_SHA_620_BOOL" ]; then
        echo "STOP: unexpected 620 SHA: $s620" >&2
        exit 1
    fi

    echo "CURRENT FILES OK"
    echo "500 SHA: $s500"
    echo "620 SHA: $s620"
}

install_update() {
    need_cmd curl
    need_cmd sha256sum
    need_cmd awk
    need_cmd mosquitto_sub
    need_cmd systemctl

    preflight
    verify_live

    local work backup f500 f620 changed
    work="$(mktemp -d /root/hhm3_ui_cleanup_v2_XXXXXXXX)"
    backup="/root/hhm3_ui_cleanup_v2_rollback_$(date +%Y%m%d_%H%M%S)"
    f500="$work/500_HHM3_FSE.js"
    f620="$work/620_thermostats.js"
    mkdir -p "$backup"
    changed=0

    echo "=== DOWNLOAD PINNED TARGET ==="
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$TARGET_COMMIT/$OBJ/boiler/wb-rules/500_HHM3_FSE.js" -o "$f500"
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$TARGET_COMMIT/$OBJ/boiler/wb-rules/620_thermostats.js" -o "$f620"
    printf '%s  %s\n' "$TARGET_SHA_500" "$f500" | sha256sum -c -
    printf '%s  %s\n' "$TARGET_SHA_620" "$f620" | sha256sum -c -

    echo "=== BACKUP CURRENT FILES ==="
    cp -pL "$RULE500" "$backup/500_HHM3_FSE.js"
    cp -pL "$RULE620" "$backup/620_thermostats.js"
    echo "BACKUP=$backup"

    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: install failed; restoring backup" >&2
            cp -p "$backup/500_HHM3_FSE.js" "$RULE500" || true
            cp -p "$backup/620_thermostats.js" "$RULE620" || true
            systemctl start wb-rules || true
        fi
        exit "$rc"
    }
    trap rollback_on_error ERR

    echo "=== STOP WB-RULES ==="
    systemctl stop wb-rules
    changed=1

    echo "=== INSTALL 500 + 620 ==="
    install -m 0644 "$f500" "$RULE500"
    install -m 0644 "$f620" "$RULE620"
    printf '%s  %s\n' "$TARGET_SHA_500" "$RULE500" | sha256sum -c -
    printf '%s  %s\n' "$TARGET_SHA_620" "$RULE620" | sha256sum -c -

    echo "=== START WB-RULES ==="
    systemctl start wb-rules
    sleep 12
    systemctl is-active --quiet wb-rules

    changed=0
    trap - ERR

    echo "=== POSTCHECK ==="
    echo "runtime_status: $(mqtt_once HHM3_FSE runtime_status)"
    echo "source_status:  $(mqtt_once HHM3_FSE source_status)"
    echo "circuit_502:   $(mqtt_once HHM3_FSE circuit_502)"
    echo "makeup active: $(mqtt_once pressure_makeup active)"
    echo "A04/K1:        $(mqtt_once A04 K1)"
    echo "BACKUP=$backup"
    echo "INSTALLED_COMMIT=$TARGET_COMMIT"
    echo "Do NOT press start_heating."
    echo
    echo "=== LEGACY JSON CONTROLS ==="
    for c in circuits_json source_json last_event_json; do
        if timeout 2 mosquitto_sub -h 127.0.0.1 -t "/devices/HHM3_FSE/controls/$c/meta/type" -C 1 2>/dev/null | grep -q .; then
            echo "WARNING: legacy control still present: $c"
        else
            echo "OK: legacy control absent: $c"
        fi
    done
    echo
    echo "=== CURRENT_STATE TYPE ERRORS SINCE RESTART ==="
    journalctl -u wb-rules --since "30 seconds ago" --no-pager -l |       grep -E "NL_simple_thermostat_.*/current_state: write ignored|can't convert control value" ||       echo "No current_state datatype errors"
}

rollback_update() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_ui_cleanup_v2_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd systemctl
    [ -f "$backup/500_HHM3_FSE.js" ] || { echo "STOP: missing backup 500" >&2; exit 1; }
    [ -f "$backup/620_thermostats.js" ] || { echo "STOP: missing backup 620" >&2; exit 1; }
    systemctl stop wb-rules
    cp -p "$backup/500_HHM3_FSE.js" "$RULE500"
    cp -p "$backup/620_thermostats.js" "$RULE620"
    systemctl start wb-rules
    sleep 10
    systemctl is-active --quiet wb-rules
    echo "ROLLBACK OK: $backup"
    echo "Do NOT press start_heating."
}

case "${1:-install}" in
    install) install_update ;;
    rollback) shift; rollback_update "$@" ;;
    *) echo "Usage: $0 [install|rollback BACKUP_DIR]" >&2; exit 2 ;;
esac
