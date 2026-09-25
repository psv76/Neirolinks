#!/bin/bash
set -Eeuo pipefail

# 05 31 Иволга 13 · HHM3 thermostat UI hotfix
# Fixes only current_state datatype writes in 620_thermostats.js:
# numeric 0/1 -> boolean false/true for WB switch controls.
# Does not modify heating logic, 500, 507, OT, Sprut, MQTT config or PersistentStorage.
# Does not press start_heating.

REPO="psv76/Neirolinks"
TARGET_COMMIT="d69153cd23a2f9d392085f6f4f8753ea7d5a0102"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13/HHM3_FSE"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE620="/etc/wb-rules/620_thermostats.js"
BASE_SHA_620="cfee47376aa8443a7bbf9ca843aa8ad9a78858e41b268fe93873a6bb189f49b5"
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

install_fix() {
    need_cmd curl
    need_cmd sha256sum
    need_cmd awk
    need_cmd mosquitto_sub
    need_cmd systemctl

    preflight

    local current
    current="$(sha256sum "$RULE620" | awk '{print $1}')"
    if [ "$current" = "$TARGET_SHA_620" ]; then
        echo "ALREADY INSTALLED: 620 matches $TARGET_COMMIT"
        exit 0
    fi
    [ "$current" = "$BASE_SHA_620" ] || {
        echo "STOP: unexpected 620 SHA: $current" >&2
        exit 1
    }
    echo "CURRENT 620 OK: $current"

    local work target backup changed
    work="$(mktemp -d /root/hhm3_620_bool_fix_XXXXXXXX)"
    target="$work/620_thermostats.js"
    backup="/root/hhm3_620_bool_fix_rollback_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup"
    changed=0

    echo "=== DOWNLOAD PINNED TARGET ==="
    curl -fLsS --retry 2 --connect-timeout 10       "$RAW/$TARGET_COMMIT/$OBJ/boiler/wb-rules/620_thermostats.js" -o "$target"
    printf '%s  %s\n' "$TARGET_SHA_620" "$target" | sha256sum -c -

    echo "=== BACKUP CURRENT 620 ==="
    cp -pL "$RULE620" "$backup/620_thermostats.js"
    echo "BACKUP=$backup"

    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: install failed; restoring 620 from $backup" >&2
            cp -p "$backup/620_thermostats.js" "$RULE620" || true
            systemctl start wb-rules || true
        fi
        exit "$rc"
    }
    trap rollback_on_error ERR

    echo "=== STOP WB-RULES ==="
    systemctl stop wb-rules
    changed=1

    echo "=== INSTALL 620 ONLY ==="
    install -m 0644 "$target" "$RULE620"
    printf '%s  %s\n' "$TARGET_SHA_620" "$RULE620" | sha256sum -c -

    echo "=== START WB-RULES ==="
    systemctl start wb-rules
    sleep 10
    systemctl is-active --quiet wb-rules

    changed=0
    trap - ERR

    echo "=== POSTCHECK ==="
    echo "runtime_status: $(mqtt_once HHM3_FSE runtime_status)"
    echo "circuit_502:   $(mqtt_once HHM3_FSE circuit_502)"
    echo "makeup active: $(mqtt_once pressure_makeup active)"
    echo "A04/K1:        $(mqtt_once A04 K1)"
    echo "BACKUP=$backup"
    echo "INSTALLED_COMMIT=$TARGET_COMMIT"
    echo "Do NOT press start_heating."
    echo
    echo "=== CURRENT_STATE TYPE ERRORS SINCE RESTART ==="
    journalctl -u wb-rules --since "30 seconds ago" --no-pager -l |       grep -E "NL_simple_thermostat_.*/current_state: write ignored|can't convert control value" ||       echo "No current_state datatype errors"
}

rollback_fix() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_620_bool_fix_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd systemctl
    [ -f "$backup/620_thermostats.js" ] || { echo "STOP: missing backup 620" >&2; exit 1; }
    systemctl stop wb-rules
    cp -p "$backup/620_thermostats.js" "$RULE620"
    systemctl start wb-rules
    sleep 10
    systemctl is-active --quiet wb-rules
    echo "ROLLBACK OK: $backup"
    echo "Do NOT press start_heating."
}

case "${1:-install}" in
    install) install_fix ;;
    rollback) shift; rollback_fix "$@" ;;
    *) echo "Usage: $0 [install|rollback BACKUP_DIR]" >&2; exit 2 ;;
esac
