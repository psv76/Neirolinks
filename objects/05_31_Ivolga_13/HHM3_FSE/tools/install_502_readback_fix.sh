#!/bin/bash
set -Eeuo pipefail

# Иволга 05 31 · HHM3 · PR #65 / 502 readback continuity
# Устанавливает только 4 production-файла из pinned GitHub commit ca7b84a.
# Не трогает 507, 624, MQTT, OT, Sprut, уставки и PersistentStorage.

REPO="psv76/Neirolinks"
BASE_COMMIT="94ce2ca29cca7451c0713be498cd977815fdca60"
TARGET_COMMIT="ca7b84aa8c3cae171de2827a097231d54df1d909"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13/HHM3_FSE"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE500="/etc/wb-rules/500_HHM3_FSE.js"
RULE620="/etc/wb-rules/620_thermostats.js"
MODCIR="/etc/wb-rules-modules/HHM3Circuit.js"
MODRUN="/etc/wb-rules-modules/HHM3Runtime.js"

TARGET_SHA_500="fc71ce0255d46929854aea12f3c69fbeecdbe3b6d5b3f3cb0957b8a1c4421846"
TARGET_SHA_620="828645f6387b696a34d4e09013d27cb98810a7dcaa046cc634a020b0c629b3cf"
TARGET_SHA_CIR="024aba35631fc4607f35e64dae9490a2c358fb894f7cd7220e531e8f787b6a42"
TARGET_SHA_RUN="67469decabfd44b0498c5822524ad734dc8b883bba91f272dfe1a048529ebe43"

mqtt_once() {
    timeout 6 mosquitto_sub -h 127.0.0.1 -t "/devices/$1/controls/$2" -C 1 2>/dev/null || true
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "STOP: command not found: $1" >&2; exit 1; }
}

check_preflight() {
    [ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "STOP: wrong controller: $(hostname)" >&2; exit 1; }
    systemctl is-active --quiet wb-rules || { echo "STOP: wb-rules is not active" >&2; exit 1; }

    local k1 active
    k1="$(mqtt_once A04 K1)"
    active="$(mqtt_once pressure_makeup active)"

    [ "$k1" = "0" ] || { echo "STOP: A04/K1 is not confirmed OFF: $k1" >&2; exit 1; }
    [ "$active" = "0" ] || { echo "STOP: pressure makeup is active: $active" >&2; exit 1; }
    echo "PREFLIGHT OK: makeup inactive; A04/K1 OFF; pressure value is not checked"
}

download_file() {
    local commit="$1" rel="$2" out="$3"
    curl -fLsS --retry 2 --connect-timeout 10 "$RAW/$commit/$OBJ/$rel" -o "$out"
}

verify_target_stage() {
    local stage="$1"
    printf '%s  %s\n' \
      "$TARGET_SHA_500" "$stage/500_HHM3_FSE.js" \
      "$TARGET_SHA_620" "$stage/620_thermostats.js" \
      "$TARGET_SHA_CIR" "$stage/HHM3Circuit.js" \
      "$TARGET_SHA_RUN" "$stage/HHM3Runtime.js" | sha256sum -c -
}

assert_live_matches_base_or_target() {
    local base="$1"
    local all_target=1
    printf '%s  %s\n' \
      "$TARGET_SHA_500" "$RULE500" \
      "$TARGET_SHA_620" "$RULE620" \
      "$TARGET_SHA_CIR" "$MODCIR" \
      "$TARGET_SHA_RUN" "$MODRUN" | sha256sum -c - >/dev/null 2>&1 || all_target=0
    if [ "$all_target" -eq 1 ]; then
        echo "ALREADY INSTALLED: all four target files match $TARGET_COMMIT"
        exit 0
    fi

    cmp -s "$RULE500" "$base/500_HHM3_FSE.js" || { echo "STOP: current 500_HHM3_FSE.js differs from base $BASE_COMMIT" >&2; exit 1; }
    cmp -s "$RULE620" "$base/620_thermostats.js" || { echo "STOP: current 620_thermostats.js differs from base $BASE_COMMIT" >&2; exit 1; }
    cmp -s "$MODCIR" "$base/HHM3Circuit.js" || { echo "STOP: current HHM3Circuit.js differs from base $BASE_COMMIT" >&2; exit 1; }
    cmp -s "$MODRUN" "$base/HHM3Runtime.js" || { echo "STOP: current HHM3Runtime.js differs from base $BASE_COMMIT" >&2; exit 1; }
    echo "CURRENT FILES OK: exact base $BASE_COMMIT"
}

install_fix() {
    need_cmd curl; need_cmd sha256sum; need_cmd cmp; need_cmd mosquitto_sub; need_cmd systemctl
    check_preflight

    local work stage base backup
    work="$(mktemp -d /root/hhm3_502_fix_XXXXXXXX)"
    stage="$work/target"
    base="$work/base"
    backup="/root/hhm3_502_readback_rollback_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$stage" "$base" "$backup"

    echo "=== DOWNLOAD PINNED BASE AND TARGET ==="
    download_file "$BASE_COMMIT"   "boiler/wb-rules/500_HHM3_FSE.js" "$base/500_HHM3_FSE.js"
    download_file "$BASE_COMMIT"   "boiler/wb-rules/620_thermostats.js" "$base/620_thermostats.js"
    download_file "$BASE_COMMIT"   "modules/HHM3Circuit.js" "$base/HHM3Circuit.js"
    download_file "$BASE_COMMIT"   "modules/HHM3Runtime.js" "$base/HHM3Runtime.js"
    download_file "$TARGET_COMMIT" "boiler/wb-rules/500_HHM3_FSE.js" "$stage/500_HHM3_FSE.js"
    download_file "$TARGET_COMMIT" "boiler/wb-rules/620_thermostats.js" "$stage/620_thermostats.js"
    download_file "$TARGET_COMMIT" "modules/HHM3Circuit.js" "$stage/HHM3Circuit.js"
    download_file "$TARGET_COMMIT" "modules/HHM3Runtime.js" "$stage/HHM3Runtime.js"

    echo "=== VERIFY TARGET SHA256 ==="
    verify_target_stage "$stage"
    echo "=== VERIFY CURRENT INSTALLATION ==="
    assert_live_matches_base_or_target "$base"

    echo "=== BACKUP CURRENT FOUR FILES ==="
    cp -pL "$RULE500" "$RULE620" "$MODCIR" "$MODRUN" "$backup/"
    echo "BACKUP=$backup"

    local changed=0
    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: installation failed; restoring four files from $backup" >&2
            cp -p "$backup/500_HHM3_FSE.js" "$RULE500" || true
            cp -p "$backup/620_thermostats.js" "$RULE620" || true
            cp -p "$backup/HHM3Circuit.js" "$MODCIR" || true
            cp -p "$backup/HHM3Runtime.js" "$MODRUN" || true
            systemctl start wb-rules || true
        fi
        exit "$rc"
    }
    trap rollback_on_error ERR

    echo "=== STOP WB-RULES ==="
    systemctl stop wb-rules
    changed=1

    echo "=== INSTALL EXACT FOUR FILES ==="
    install -m 0644 "$stage/500_HHM3_FSE.js" "$RULE500"
    install -m 0644 "$stage/620_thermostats.js" "$RULE620"
    install -m 0644 "$stage/HHM3Circuit.js" "$MODCIR"
    install -m 0644 "$stage/HHM3Runtime.js" "$MODRUN"

    echo "=== VERIFY INSTALLED SHA256 ==="
    printf '%s  %s\n' \
      "$TARGET_SHA_500" "$RULE500" \
      "$TARGET_SHA_620" "$RULE620" \
      "$TARGET_SHA_CIR" "$MODCIR" \
      "$TARGET_SHA_RUN" "$MODRUN" | sha256sum -c -

    echo "=== START WB-RULES ==="
    systemctl start wb-rules
    sleep 8
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
    journalctl -u wb-rules --since "2 minutes ago" --no-pager -l | grep -E 'ERROR:|exception|Exception|\[отопление\]' | tail -40 || true
}

rollback_fix() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_502_readback_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd mosquitto_sub; need_cmd systemctl
    check_preflight
    for f in 500_HHM3_FSE.js 620_thermostats.js HHM3Circuit.js HHM3Runtime.js; do
        [ -f "$backup/$f" ] || { echo "STOP: missing $backup/$f" >&2; exit 1; }
    done
    systemctl stop wb-rules
    cp -p "$backup/500_HHM3_FSE.js" "$RULE500"
    cp -p "$backup/620_thermostats.js" "$RULE620"
    cp -p "$backup/HHM3Circuit.js" "$MODCIR"
    cp -p "$backup/HHM3Runtime.js" "$MODRUN"
    systemctl start wb-rules
    sleep 8
    systemctl is-active --quiet wb-rules
    echo "ROLLBACK OK: $backup"
    echo "Do NOT press start_heating."
}

case "${1:-install}" in
    install) install_fix ;;
    rollback) shift; rollback_fix "$@" ;;
    *) echo "Usage: $0 [install|rollback BACKUP_DIR]" >&2; exit 2 ;;
esac
