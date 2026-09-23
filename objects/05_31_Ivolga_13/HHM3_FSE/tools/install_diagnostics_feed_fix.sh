#!/bin/bash
set -Eeuo pipefail

# 05 31 Иволга 13 · HHM3 compact diagnostics feed
# Replaces only:
#   /etc/wb-rules/500_HHM3_FSE.js
#   /etc/wb-rules/600_Heat_diagnostics.js
#
# Purpose:
# - keep raw circuits_json/source_json removed;
# - restore heat_diagnostics request_501..505 from six tiny scalar HHM3 channels;
# - preserve existing dashboard IDs.
#
# Does not touch 620, 507, OT config, Sprut, MQTT config, setpoints or PersistentStorage.
# Does not press start_heating.

REPO="psv76/Neirolinks"
TARGET_COMMIT="919c231842e1677d895cc7c557217ad01a01cca0"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE500="/etc/wb-rules/500_HHM3_FSE.js"
RULE600="/etc/wb-rules/600_Heat_diagnostics.js"
RULE620="/etc/wb-rules/620_thermostats.js"

BASE_SHA_500="cb92dc00f57be3e757b89d6c7b624e2b5e0c6e3cc0e419059206257230d8ec9e"
REQUIRED_SHA_620="570874b06a045723feb3fac857f6f36fc007953ddc0b8ec0599a45837a0327fc"

TARGET_SHA_500="03d4ec69dadcef8872b4ca792236bdb37b62fbed849dac52e201aae08995d501"
TARGET_SHA_600="9da57502274f44351f98cec29f173d7c62ab02ca3e15b9fc3e8968a99a1701fa"

mqtt_once() {
    timeout 6 mosquitto_sub -h 127.0.0.1 -t "/devices/$1/controls/$2" -C 1 2>/dev/null || true
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "STOP: command not found: $1" >&2; exit 1; }
}

preflight() {
    [ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "STOP: wrong controller: $(hostname)" >&2; exit 1; }
    systemctl is-active --quiet wb-rules || { echo "STOP: wb-rules is not active" >&2; exit 1; }
    [ -f "$RULE500" ] || { echo "STOP: missing $RULE500" >&2; exit 1; }
    [ -f "$RULE600" ] || { echo "STOP: missing $RULE600" >&2; exit 1; }
    [ -f "$RULE620" ] || { echo "STOP: missing $RULE620" >&2; exit 1; }

    local active k1 s500 s600 s620
    active="$(mqtt_once pressure_makeup active)"
    k1="$(mqtt_once A04 K1)"
    [ "$active" = "0" ] || { echo "STOP: pressure makeup is active: $active" >&2; exit 1; }
    [ "$k1" = "0" ] || { echo "STOP: A04/K1 is not confirmed OFF: $k1" >&2; exit 1; }

    s500="$(sha256sum "$RULE500" | awk '{print $1}')"
    s600="$(sha256sum "$RULE600" | awk '{print $1}')"
    s620="$(sha256sum "$RULE620" | awk '{print $1}')"

    if [ "$s500" = "$TARGET_SHA_500" ] && [ "$s600" = "$TARGET_SHA_600" ] && [ "$s620" = "$REQUIRED_SHA_620" ]; then
        echo "ALREADY INSTALLED: compact diagnostics feed target is present"
        exit 0
    fi

    [ "$s500" = "$BASE_SHA_500" ] || { echo "STOP: unexpected 500 SHA: $s500" >&2; exit 1; }
    [ "$s620" = "$REQUIRED_SHA_620" ] || { echo "STOP: unexpected 620 SHA: $s620" >&2; exit 1; }

    # Current live 600 is the detailed dashboard version that still consumes raw JSON.
    grep -q "function hdReport" "$RULE600" || { echo "STOP: current 600 is not the expected detailed diagnostics variant" >&2; exit 1; }
    grep -q "HHM3_FSE/circuits_json" "$RULE600" || { echo "STOP: current 600 does not contain expected circuits_json dependency" >&2; exit 1; }
    grep -q "heat_diagnostics" "$RULE600" || { echo "STOP: current 600 is not heat diagnostics" >&2; exit 1; }

    echo "PREFLIGHT OK"
    echo "500 SHA: $s500"
    echo "600 SHA: $s600 (semantic base check passed)"
    echo "620 SHA: $s620"
}

install_update() {
    need_cmd curl
    need_cmd sha256sum
    need_cmd awk
    need_cmd grep
    need_cmd mosquitto_sub
    need_cmd systemctl

    preflight

    local work f500 f600 backup changed restart_mark
    work="$(mktemp -d /root/hhm3_diag_feed_XXXXXXXX)"
    f500="$work/500_HHM3_FSE.js"
    f600="$work/600_Heat_diagnostics.js"
    backup="/root/hhm3_diag_feed_rollback_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup"
    changed=0

    echo "=== DOWNLOAD PINNED TARGET ==="
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$TARGET_COMMIT/objects/05_31_Ivolga_13/HHM3_FSE/boiler/wb-rules/500_HHM3_FSE.js" -o "$f500"
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$TARGET_COMMIT/objects/05_31_Ivolga_13/Wirenboard/wb-rules/600_Heat_diagnostics.js" -o "$f600"
    printf '%s  %s\n' "$TARGET_SHA_500" "$f500" | sha256sum -c -
    printf '%s  %s\n' "$TARGET_SHA_600" "$f600" | sha256sum -c -

    echo "=== BACKUP CURRENT FILES ==="
    cp -pL "$RULE500" "$backup/500_HHM3_FSE.js"
    cp -pL "$RULE600" "$backup/600_Heat_diagnostics.js"
    echo "BACKUP=$backup"

    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: install failed; restoring 500 + 600 from $backup" >&2
            cp -p "$backup/500_HHM3_FSE.js" "$RULE500" || true
            cp -p "$backup/600_Heat_diagnostics.js" "$RULE600" || true
            systemctl start wb-rules || true
        fi
        exit "$rc"
    }
    trap rollback_on_error ERR

    echo "=== STOP WB-RULES ==="
    systemctl stop wb-rules
    changed=1

    echo "=== INSTALL 500 + 600 ==="
    install -m 0644 "$f500" "$RULE500"
    install -m 0644 "$f600" "$RULE600"
    printf '%s  %s\n' "$TARGET_SHA_500" "$RULE500" | sha256sum -c -
    printf '%s  %s\n' "$TARGET_SHA_600" "$RULE600" | sha256sum -c -

    restart_mark="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "=== START WB-RULES ==="
    systemctl start wb-rules
    sleep 15
    systemctl is-active --quiet wb-rules

    changed=0
    trap - ERR

    echo "=== POSTCHECK ==="
    echo "runtime_status: $(mqtt_once HHM3_FSE runtime_status)"
    echo "source_status:  $(mqtt_once HHM3_FSE source_status)"
    echo "circuit_502:   $(mqtt_once HHM3_FSE circuit_502)"
    echo
    echo "Compact HHM3 feed:"
    for c in diag_request_501 diag_request_502 diag_request_503 diag_request_504 diag_request_505 diag_request_boiler; do
        printf "%-24s %s\n" "$c:" "$(mqtt_once HHM3_FSE "$c")"
    done
    echo
    echo "Dashboard diagnostics:"
    for c in request_501 request_502 request_503 request_504 request_505 request_boiler; do
        printf "%-18s %s\n" "$c:" "$(mqtt_once heat_diagnostics "$c")"
    done

    echo
    echo "=== RAW JSON CONTROLS MUST STAY ABSENT ==="
    for c in circuits_json source_json last_event_json; do
        if timeout 2 mosquitto_sub -h 127.0.0.1 -t "/devices/HHM3_FSE/controls/$c/meta/type" -C 1 2>/dev/null | grep -q .; then
            echo "WARNING: legacy raw JSON control reappeared: $c"
        else
            echo "OK: absent: $c"
        fi
    done

    echo
    echo "=== ERRORS AFTER THIS RESTART ==="
    if journalctl -u wb-rules --since "$restart_mark" --no-pager -l |         grep -E "500_HHM3|600_Heat_diagnostics|current_state: write ignored|can't convert control value" |         grep -E "ERROR|exception|Exception|write ignored"; then
        echo "WARNING: relevant errors found above"
    else
        echo "OK: no relevant errors after this restart"
    fi

    echo
    echo "makeup active: $(mqtt_once pressure_makeup active)"
    echo "A04/K1:        $(mqtt_once A04 K1)"
    echo "BACKUP=$backup"
    echo "INSTALLED_COMMIT=$TARGET_COMMIT"
    echo "Do NOT press start_heating."
}

rollback_update() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_diag_feed_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd systemctl
    [ -f "$backup/500_HHM3_FSE.js" ] || { echo "STOP: missing backup 500" >&2; exit 1; }
    [ -f "$backup/600_Heat_diagnostics.js" ] || { echo "STOP: missing backup 600" >&2; exit 1; }
    systemctl stop wb-rules
    cp -p "$backup/500_HHM3_FSE.js" "$RULE500"
    cp -p "$backup/600_Heat_diagnostics.js" "$RULE600"
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
