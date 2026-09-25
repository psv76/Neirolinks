#!/bin/bash
set -Eeuo pipefail

# 05 31 Иволга 13 · HHM3 retained legacy JSON purge
# Replaces only 500_HHM3_FSE.js.
# 620 must already be the boolean current_state build from UI cleanup v2.
# Does not touch 507, OT config, Sprut, MQTT config, setpoints or PersistentStorage.
# Does not press start_heating.

REPO="psv76/Neirolinks"
TARGET_COMMIT="4190f9fb5236b8766074e689314097e0d19b1ba1"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13/HHM3_FSE"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE500="/etc/wb-rules/500_HHM3_FSE.js"
RULE620="/etc/wb-rules/620_thermostats.js"

BASE_SHA_500="e22959fba4b9dfd40da7830b4fd8dd25559a596811ac800a6cb9c608cc522b83"
TARGET_SHA_500="cb92dc00f57be3e757b89d6c7b624e2b5e0c6e3cc0e419059206257230d8ec9e"
REQUIRED_SHA_620="570874b06a045723feb3fac857f6f36fc007953ddc0b8ec0599a45837a0327fc"

mqtt_once() {
    timeout 6 mosquitto_sub -h 127.0.0.1 -t "/devices/$1/controls/$2" -C 1 2>/dev/null || true
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "STOP: command not found: $1" >&2; exit 1; }
}

preflight() {
    [ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "STOP: wrong controller: $(hostname)" >&2; exit 1; }
    systemctl is-active --quiet wb-rules || { echo "STOP: wb-rules is not active" >&2; exit 1; }

    local active k1 s500 s620
    active="$(mqtt_once pressure_makeup active)"
    k1="$(mqtt_once A04 K1)"
    [ "$active" = "0" ] || { echo "STOP: pressure makeup is active: $active" >&2; exit 1; }
    [ "$k1" = "0" ] || { echo "STOP: A04/K1 is not confirmed OFF: $k1" >&2; exit 1; }

    s500="$(sha256sum "$RULE500" | awk '{print $1}')"
    s620="$(sha256sum "$RULE620" | awk '{print $1}')"

    if [ "$s500" = "$TARGET_SHA_500" ] && [ "$s620" = "$REQUIRED_SHA_620" ]; then
        echo "ALREADY INSTALLED: target 500 and required 620 are present"
        exit 0
    fi

    [ "$s500" = "$BASE_SHA_500" ] || { echo "STOP: unexpected 500 SHA: $s500" >&2; exit 1; }
    [ "$s620" = "$REQUIRED_SHA_620" ] || { echo "STOP: 620 boolean hotfix is not installed: $s620" >&2; exit 1; }

    echo "PREFLIGHT OK"
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

    local work target backup changed restart_mark
    work="$(mktemp -d /root/hhm3_legacy_json_purge_XXXXXXXX)"
    target="$work/500_HHM3_FSE.js"
    backup="/root/hhm3_legacy_json_purge_rollback_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup"
    changed=0

    echo "=== DOWNLOAD PINNED TARGET ==="
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$TARGET_COMMIT/$OBJ/boiler/wb-rules/500_HHM3_FSE.js" -o "$target"
    printf '%s  %s\n' "$TARGET_SHA_500" "$target" | sha256sum -c -

    echo "=== BACKUP CURRENT 500 ==="
    cp -pL "$RULE500" "$backup/500_HHM3_FSE.js"
    echo "BACKUP=$backup"

    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: install failed; restoring 500 from $backup" >&2
            cp -p "$backup/500_HHM3_FSE.js" "$RULE500" || true
            systemctl start wb-rules || true
        fi
        exit "$rc"
    }
    trap rollback_on_error ERR

    echo "=== STOP WB-RULES ==="
    systemctl stop wb-rules
    changed=1

    echo "=== INSTALL 500 ONLY ==="
    install -m 0644 "$target" "$RULE500"
    printf '%s  %s\n' "$TARGET_SHA_500" "$RULE500" | sha256sum -c -

    restart_mark="$(date '+%Y-%m-%d %H:%M:%S')"
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
    echo "=== LEGACY JSON CONTROLS AFTER RESTART ==="
    local found=0
    for c in circuits_json source_json last_event_json; do
        if timeout 2 mosquitto_sub -h 127.0.0.1 -t "/devices/HHM3_FSE/controls/$c/meta/type" -C 1 2>/dev/null | grep -q .; then
            echo "WARNING: legacy control still retained: $c"
            found=1
        else
            echo "OK: legacy control absent: $c"
        fi
    done

    echo
    echo "=== CURRENT_STATE TYPE ERRORS AFTER THIS RESTART ==="
    if journalctl -u wb-rules --since "$restart_mark" --no-pager -l |         grep -E "NL_simple_thermostat_.*/current_state: write ignored|can't convert control value"; then
        echo "WARNING: current_state datatype errors still occur after this restart"
    else
        echo "OK: no current_state datatype errors after this restart"
    fi

    [ "$found" -eq 0 ] || {
        echo "WARNING: legacy controls are still retained; do not rerun start_heating."
        exit 3
    }
}

rollback_update() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_legacy_json_purge_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd systemctl
    [ -f "$backup/500_HHM3_FSE.js" ] || { echo "STOP: missing backup 500" >&2; exit 1; }
    systemctl stop wb-rules
    cp -p "$backup/500_HHM3_FSE.js" "$RULE500"
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
