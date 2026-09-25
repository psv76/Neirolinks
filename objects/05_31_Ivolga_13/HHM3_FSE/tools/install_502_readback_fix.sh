#!/bin/bash
set -Eeuo pipefail

# Иволга 05 31 · HHM3 · PR #65 / 502 OFF-readback continuity
# Поверх уже установленного payload ca7b84a заменяет только 620_thermostats.js.
# Не трогает 500, HHM3Circuit, HHM3Runtime, 507, 624, MQTT, OT, Sprut,
# уставки и PersistentStorage. Не нажимает start_heating.

REPO="psv76/Neirolinks"
BASE_COMMIT="ca7b84aa8c3cae171de2827a097231d54df1d909"
TARGET_COMMIT="42e04d5e53cbc8beff3b11960bbf2dcac34b1f84"
RAW="https://raw.githubusercontent.com/${REPO}"
OBJ="objects/05_31_Ivolga_13/HHM3_FSE"
EXPECTED_HOST="wirenboard-ABF62SL"

RULE500="/etc/wb-rules/500_HHM3_FSE.js"
RULE620="/etc/wb-rules/620_thermostats.js"
MODCIR="/etc/wb-rules-modules/HHM3Circuit.js"
MODRUN="/etc/wb-rules-modules/HHM3Runtime.js"

BASE_SHA_500="fc71ce0255d46929854aea12f3c69fbeecdbe3b6d5b3f3cb0957b8a1c4421846"
BASE_SHA_620="828645f6387b696a34d4e09013d27cb98810a7dcaa046cc634a020b0c629b3cf"
BASE_SHA_CIR="024aba35631fc4607f35e64dae9490a2c358fb894f7cd7220e531e8f787b6a42"
BASE_SHA_RUN="67469decabfd44b0498c5822524ad734dc8b883bba91f272dfe1a048529ebe43"
TARGET_SHA_620="a33e62406d6ed146c497f270dbb303c074b61cb59a4fcb956a708c18c43abbc2"

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

verify_exact_live_base_or_target() {
    local sha500 sha620 shacir sharun
    sha500="$(sha256sum "$RULE500" | awk '{print $1}')"
    sha620="$(sha256sum "$RULE620" | awk '{print $1}')"
    shacir="$(sha256sum "$MODCIR" | awk '{print $1}')"
    sharun="$(sha256sum "$MODRUN" | awk '{print $1}')"

    [ "$sha500" = "$BASE_SHA_500" ] || { echo "STOP: 500 differs from installed PR #65 base" >&2; exit 1; }
    [ "$shacir" = "$BASE_SHA_CIR" ] || { echo "STOP: HHM3Circuit differs from installed PR #65 base" >&2; exit 1; }
    [ "$sharun" = "$BASE_SHA_RUN" ] || { echo "STOP: HHM3Runtime differs from installed PR #65 base" >&2; exit 1; }

    if [ "$sha620" = "$TARGET_SHA_620" ]; then
        echo "ALREADY INSTALLED: 620 matches $TARGET_COMMIT"
        exit 0
    fi
    [ "$sha620" = "$BASE_SHA_620" ] || { echo "STOP: 620 differs from expected installed PR #65 base" >&2; exit 1; }
    echo "CURRENT FILES OK: exact installed PR #65 payload; 620 ready for overlay"
}

install_fix() {
    need_cmd curl; need_cmd sha256sum; need_cmd awk; need_cmd mosquitto_sub; need_cmd systemctl
    check_preflight
    verify_exact_live_base_or_target

    local work target backup
    work="$(mktemp -d /root/hhm3_502_off_fix_XXXXXXXX)"
    target="$work/620_thermostats.js"
    backup="/root/hhm3_502_off_readback_rollback_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup"

    echo "=== DOWNLOAD PINNED TARGET ==="
    curl -fLsS --retry 2 --connect-timeout 10 \
      "$RAW/$TARGET_COMMIT/$OBJ/boiler/wb-rules/620_thermostats.js" -o "$target"
    printf '%s  %s\n' "$TARGET_SHA_620" "$target" | sha256sum -c -

    echo "=== BACKUP CURRENT 620 ==="
    cp -pL "$RULE620" "$backup/620_thermostats.js"
    echo "BACKUP=$backup"

    local changed=0
    rollback_on_error() {
        local rc=$?
        if [ "$changed" -eq 1 ]; then
            echo "ERROR: installation failed; restoring 620 from $backup" >&2
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
    journalctl -u wb-rules --since "2 minutes ago" --no-pager -l | grep -E 'ERROR:|exception|Exception|\[отопление\]' | tail -60 || true
}

rollback_fix() {
    [ "$#" -eq 1 ] || { echo "Usage: $0 rollback /root/hhm3_502_off_readback_rollback_YYYYMMDD_HHMMSS" >&2; exit 2; }
    local backup="$1"
    need_cmd mosquitto_sub; need_cmd systemctl
    check_preflight
    [ -f "$backup/620_thermostats.js" ] || { echo "STOP: missing $backup/620_thermostats.js" >&2; exit 1; }
    systemctl stop wb-rules
    cp -p "$backup/620_thermostats.js" "$RULE620"
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
