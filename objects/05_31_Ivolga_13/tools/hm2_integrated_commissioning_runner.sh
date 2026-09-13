#!/bin/sh
# 05 31 Иволга 13 — HM2 integrated commissioning runner.
# Проверяет 501, 502, 503 последовательно и пишет полный лог.
# Production-скрипты не меняет.

LOG_DEFAULT="/mnt/data/hm2_integrated_commissioning_latest.log"
RUN_FLAG="--run"

if [ "${1:-}" != "$RUN_FLAG" ]; then
    mkdir -p /mnt/data
    rm -f "$LOG_DEFAULT"
    nohup "$0" "$RUN_FLAG" > "$LOG_DEFAULT" 2>&1 &
    echo "PID=$!"
    echo "LOG=$LOG_DEFAULT"
    exit 0
fi

TEST_MINUTES_501="${TEST_MINUTES_501:-18}"
TEST_MINUTES_502="${TEST_MINUTES_502:-18}"
TEST_MINUTES_503="${TEST_MINUTES_503:-14}"
STOP_WAIT_S="${STOP_WAIT_S:-70}"
SLEEP_STEP_S="${SLEEP_STEP_S:-60}"

TEST_FAILED=0
PASS_501=0
PASS_502=0
PASS_503=0

get() {
    mosquitto_sub -C 1 -W 1 -t "$1" 2>/dev/null || echo "NO DATA"
}

pub() {
    echo "PUB $1 = $2"
    mosquitto_pub -t "$1" -m "$2"
}

num_ge() {
    awk -v a="$1" -v b="$2" 'BEGIN { if ((a+0) >= (b+0)) exit 0; exit 1 }'
}

num_gt() {
    awk -v a="$1" -v b="$2" 'BEGIN { if ((a+0) > (b+0)) exit 0; exit 1 }'
}

check_eq() {
    NAME="$1"
    ACTUAL="$2"
    EXPECTED="$3"
    if [ "$ACTUAL" = "$EXPECTED" ]; then
        echo "CHECK PASS: $NAME = $ACTUAL"
        return 0
    fi
    echo "CHECK FAIL: $NAME expected $EXPECTED, actual $ACTUAL"
    TEST_FAILED=1
    return 1
}

check_num_ge() {
    NAME="$1"
    ACTUAL="$2"
    EXPECTED="$3"
    if num_ge "$ACTUAL" "$EXPECTED"; then
        echo "CHECK PASS: $NAME = $ACTUAL >= $EXPECTED"
        return 0
    fi
    echo "CHECK FAIL: $NAME expected >= $EXPECTED, actual $ACTUAL"
    TEST_FAILED=1
    return 1
}

mark_response() {
    STATUS="$1"
    case "$STATUS" in
        RESPONSE_OK|AT_TARGET|RETURN_WARM|SOURCE_HOT)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

all_thermostats_off() {
    echo
    echo "===== ALL TEST THERMOSTATS OFF ====="
    for z in 601 602 603 606 607 608 609 610 611 612 613 614 005 006 007 008 009 010; do
        pub "/devices/NL_simple_thermostat_${z}/controls/target_state/on" 0
    done
}

safe_physical_zero() {
    echo
    echo "===== FORCE PHYSICAL ZERO ====="
    for t in \
        "/devices/A03/controls/K1" \
        "/devices/A03/controls/K2" \
        "/devices/A03/controls/K3" \
        "/devices/A05/controls/Channel 1 Dimming Level" \
        "/devices/A05/controls/Channel 2 Dimming Level" \
        "/devices/A05/controls/Channel 1 Switch" \
        "/devices/A05/controls/Channel 2 Switch"; do
        pub "$t/on" 0
    done
}

disarm_contours() {
    echo
    echo "===== DISARM CONTOURS ====="
    for vd in hm2_501_tp_dom hm2_502_gp_dom hm2_503_rad_dom; do
        pub "/devices/${vd}/controls/local_permit/on" 0
        pub "/devices/${vd}/controls/manual_commissioning_grant/on" 0
        pub "/devices/${vd}/controls/outputs_enabled/on" 0
        pub "/devices/${vd}/controls/response_commissioned/on" 0
    done
}

arm_source() {
    echo
    echo "===== ARM SOURCE MANAGER ====="
    pub "/devices/hm2_source_manager/controls/safe_off_setpoint_c/on" 35
    pub "/devices/hm2_source_manager/controls/source_commissioned/on" 1
    pub "/devices/hm2_source_manager/controls/source_endpoint_confirmed/on" 1
    pub "/devices/hm2_source_manager/controls/safe_off_commissioned/on" 1
    pub "/devices/hm2_source_manager/controls/source_fault_latch_enabled/on" 0
    pub "/devices/hm2_source_manager/controls/source_write_enabled/on" 1
    pub "/devices/hm2_source_manager/controls/manual_source_grant/on" 1
}

disarm_source_write() {
    echo
    echo "===== DISARM SOURCE WRITE ====="
    pub "/devices/hm2_source_manager/controls/manual_source_grant/on" 0
    pub "/devices/hm2_source_manager/controls/source_write_enabled/on" 0
}

stop_all() {
    echo
    echo "===== STOP ALL ====="
    date
    all_thermostats_off
    echo "WAIT source safe-off ${STOP_WAIT_S}s"
    sleep "$STOP_WAIT_S"
    disarm_source_write
    disarm_contours
    safe_physical_zero
    sleep 5
}

prepare_idle() {
    echo
    echo "===== PREPARE IDLE ====="
    date
    all_thermostats_off
    disarm_source_write
    disarm_contours
    safe_physical_zero
    sleep 5
}

trap 'stop_all; echo "===== INTERRUPTED ====="; exit 130' INT TERM

snapshot_source() {
    echo "SRC state=$(get '/devices/hm2_source_manager/controls/state')"
    echo "SRC source_state=$(get '/devices/hm2_source_manager/controls/source_state')"
    echo "SRC selected=$(get '/devices/hm2_source_manager/controls/selected_consumer')"
    echo "SRC requested=$(get '/devices/hm2_source_manager/controls/requested_heating_setpoint')"
    echo "SRC limited=$(get '/devices/hm2_source_manager/controls/limited_heating_setpoint')"
    echo "SRC written=$(get '/devices/hm2_source_manager/controls/written_heating_setpoint')"
    echo "SRC grant=$(get '/devices/hm2_source_manager/controls/physical_write_grant')"
    echo "SRC response=$(get '/devices/hm2_source_manager/controls/source_response_status')"
    echo "SRC block=$(get '/devices/hm2_source_manager/controls/write_block_reason')"
    echo "SRC status=$(get '/devices/hm2_source_manager/controls/status')"
    echo "OT setpoint=$(get '/devices/wbe2-i-opentherm_11/controls/Heating Setpoint')"
    echo "OT flame=$(get '/devices/wbe2-i-opentherm_11/controls/Boiler Flame Status')"
    echo "OT CH=$(get '/devices/wbe2-i-opentherm_11/controls/Boiler CH mode')"
    echo "OT modulation=$(get '/devices/wbe2-i-opentherm_11/controls/Burner Modulation Level')"
    echo "T411 source=$(get '/devices/wb-m1w2_170/controls/External Sensor 1')"
}

snapshot_arbiter() {
    echo "ARB state=$(get '/devices/hm2_request_arbiter/controls/state')"
    echo "ARB selected=$(get '/devices/hm2_request_arbiter/controls/selected_consumer')"
    echo "ARB temp=$(get '/devices/hm2_request_arbiter/controls/selected_requested_temperature')"
    echo "ARB no_demand=$(get '/devices/hm2_request_arbiter/controls/no_demand_contract')"
    echo "ARB active=$(get '/devices/hm2_request_arbiter/controls/active_candidate_count')"
    echo "ARB reason=$(get '/devices/hm2_request_arbiter/controls/selected_reason')"
}

snapshot_contour() {
    VD="$1"
    PUMP_TOPIC="$2"
    VALVE_SW_TOPIC="$3"
    VALVE_POS_TOPIC="$4"
    SUPPLY_TOPIC="$5"
    RETURN_TOPIC="$6"
    ZONE_TOPIC_1="$7"
    ZONE_TOPIC_2="$8"

    echo "CNT state=$(get "/devices/${VD}/controls/state")"
    echo "CNT valid=$(get "/devices/${VD}/controls/valid")"
    echo "CNT heat_demand=$(get "/devices/${VD}/controls/heat_demand")"
    echo "CNT active_zone_count=$(get "/devices/${VD}/controls/active_zone_count")"
    echo "CNT path_ready=$(get "/devices/${VD}/controls/path_ready")"
    echo "CNT pump_cmd=$(get "/devices/${VD}/controls/pump_cmd")"
    echo "CNT response_status=$(get "/devices/${VD}/controls/response_status")"
    echo "CNT status=$(get "/devices/${VD}/controls/status")"
    echo "CNT supply_temp=$(get "/devices/${VD}/controls/supply_temp_c")"
    echo "CNT return_temp=$(get "/devices/${VD}/controls/return_temp_c")"
    echo "CNT source_temp=$(get "/devices/${VD}/controls/source_temp_c")"
    echo "PUMP physical=$(get "$PUMP_TOPIC")"
    if [ -n "$VALVE_SW_TOPIC" ]; then
        echo "VALVE switch=$(get "$VALVE_SW_TOPIC")"
    fi
    if [ -n "$VALVE_POS_TOPIC" ]; then
        echo "VALVE position=$(get "$VALVE_POS_TOPIC")"
    fi
    echo "SUPPLY raw=$(get "$SUPPLY_TOPIC")"
    echo "RETURN raw=$(get "$RETURN_TOPIC")"
    echo "ZONE1 raw=$(get "$ZONE_TOPIC_1")"
    if [ -n "$ZONE_TOPIC_2" ]; then
        echo "ZONE2 raw=$(get "$ZONE_TOPIC_2")"
    fi
}

run_contour_test() {
    NAME="$1"
    VD="$2"
    THERM="$3"
    TARGET="$4"
    PUMP_TOPIC="$5"
    VALVE_SW_TOPIC="$6"
    VALVE_POS_TOPIC="$7"
    SUPPLY_TOPIC="$8"
    RETURN_TOPIC="$9"
    EXPECT_SETPOINT="${10}"
    MINUTES="${11}"
    ZONE_TOPIC_1="${12}"
    ZONE_TOPIC_2="${13}"

    RESPONSE_SEEN=0
    PUMP_SEEN=0
    SOURCE_SETPOINT_SEEN=0
    ARBITER_SEEN=0
    ZONE_SEEN=0

    echo
    echo "================================================================"
    echo "===== TEST $NAME START ====="
    echo "================================================================"
    date

    prepare_idle
    arm_source

    echo
    echo "===== ARM $VD ====="
    pub "/devices/${VD}/controls/enabled/on" 1
    pub "/devices/${VD}/controls/commissioned/on" 1
    pub "/devices/${VD}/controls/outputs_enabled/on" 1
    pub "/devices/${VD}/controls/local_permit/on" 1
    pub "/devices/${VD}/controls/manual_commissioning_grant/on" 1
    pub "/devices/${VD}/controls/response_commissioned/on" 1

    echo
    echo "===== DEMAND $THERM ====="
    pub "/devices/${THERM}/controls/target_temperature/on" "$TARGET"
    pub "/devices/${THERM}/controls/target_state/on" 1

    i=0
    while [ "$i" -le "$MINUTES" ]; do
        echo
        echo "===== $NAME MINUTE $i ====="
        date
        echo "THERM target_state=$(get "/devices/${THERM}/controls/target_state")"
        echo "THERM target_temperature=$(get "/devices/${THERM}/controls/target_temperature")"
        echo "THERM state=$(get "/devices/${THERM}/controls/state")"
        snapshot_contour "$VD" "$PUMP_TOPIC" "$VALVE_SW_TOPIC" "$VALVE_POS_TOPIC" "$SUPPLY_TOPIC" "$RETURN_TOPIC" "$ZONE_TOPIC_1" "$ZONE_TOPIC_2"
        snapshot_arbiter
        snapshot_source

        Z1="$(get "$ZONE_TOPIC_1")"
        Z2=""
        [ -n "$ZONE_TOPIC_2" ] && Z2="$(get "$ZONE_TOPIC_2")"
        PUMP_NOW="$(get "$PUMP_TOPIC")"
        RESP_NOW="$(get "/devices/${VD}/controls/response_status")"
        ARB_NOW="$(get '/devices/hm2_request_arbiter/controls/selected_consumer')"
        OT_NOW="$(get '/devices/wbe2-i-opentherm_11/controls/Heating Setpoint')"

        if [ "$Z1" = "1" ] || [ "$Z2" = "1" ]; then ZONE_SEEN=1; fi
        if [ "$PUMP_NOW" = "1" ]; then PUMP_SEEN=1; fi
        if [ "$ARB_NOW" = "$VD" ]; then ARBITER_SEEN=1; fi
        if [ "$OT_NOW" = "$EXPECT_SETPOINT" ]; then SOURCE_SETPOINT_SEEN=1; fi
        if mark_response "$RESP_NOW"; then RESPONSE_SEEN=1; fi

        [ "$i" -eq "$MINUTES" ] && break
        sleep "$SLEEP_STEP_S"
        i=$((i + 1))
    done

    echo
    echo "===== $NAME CHECKS BEFORE STOP ====="
    check_eq "$NAME zone opened" "$ZONE_SEEN" "1"
    check_eq "$NAME pump physical seen" "$PUMP_SEEN" "1"
    check_eq "$NAME arbiter selected" "$ARBITER_SEEN" "1"
    check_eq "$NAME source setpoint seen" "$SOURCE_SETPOINT_SEEN" "1"
    check_eq "$NAME thermal response seen" "$RESPONSE_SEEN" "1"

    if [ "$ZONE_SEEN$PUMP_SEEN$ARBITER_SEEN$SOURCE_SETPOINT_SEEN$RESPONSE_SEEN" = "11111" ]; then
        echo "RESULT $NAME = PASS"
        case "$NAME" in
            501*) PASS_501=1 ;;
            502*) PASS_502=1 ;;
            503*) PASS_503=1 ;;
        esac
    else
        echo "RESULT $NAME = FAIL"
        TEST_FAILED=1
    fi

    stop_all

    echo
    echo "===== $NAME FINAL SAFE CHECK ====="
    FINAL_THERM="$(get "/devices/${THERM}/controls/target_state")"
    FINAL_PUMP="$(get "$PUMP_TOPIC")"
    FINAL_SRC_GRANT="$(get '/devices/hm2_source_manager/controls/physical_write_grant')"
    FINAL_OT="$(get '/devices/wbe2-i-opentherm_11/controls/Heating Setpoint')"
    echo "FINAL thermostat=$FINAL_THERM"
    echo "FINAL pump=$FINAL_PUMP"
    echo "FINAL source grant=$FINAL_SRC_GRANT"
    echo "FINAL OT setpoint=$FINAL_OT"
    check_eq "$NAME final thermostat off" "$FINAL_THERM" "0"
    check_eq "$NAME final pump off" "$FINAL_PUMP" "0"
    check_eq "$NAME final source grant off" "$FINAL_SRC_GRANT" "0"
    check_eq "$NAME final OT safe-off" "$FINAL_OT" "35"
}

final_snapshot() {
    echo
    echo "================================================================"
    echo "===== FINAL SYSTEM SNAPSHOT ====="
    echo "================================================================"
    date

    echo
    echo "===== MANAGERS ====="
    for vd in hm2_501_tp_dom hm2_502_gp_dom hm2_503_rad_dom; do
        echo "--- $vd ---"
        for c in state valid heat_demand active_zone_count path_ready pump_cmd status fault_latched; do
            printf "%s=" "$c"
            get "/devices/${vd}/controls/${c}"
        done
    done

    echo
    echo "===== ARBITER ====="
    snapshot_arbiter

    echo
    echo "===== SOURCE ====="
    snapshot_source

    echo
    echo "===== PHYSICAL OUTPUTS ====="
    for t in \
        "/devices/A03/controls/K1" \
        "/devices/A03/controls/K2" \
        "/devices/A03/controls/K3" \
        "/devices/A05/controls/Channel 1 Switch" \
        "/devices/A05/controls/Channel 1 Dimming Level" \
        "/devices/A05/controls/Channel 2 Switch" \
        "/devices/A05/controls/Channel 2 Dimming Level" \
        "/devices/A08/controls/K3" \
        "/devices/A13/controls/K1" \
        "/devices/A09/controls/K4" \
        "/devices/A09/controls/K5"; do
        printf "%s=" "$t"
        get "$t"
    done

    echo
    echo "===== RECENT HM2 LOGS ====="
    journalctl -u wb-rules --since "2 hours ago" --no-pager | \
        grep -Ei "501_tp_dom|502_gp_dom|503_rad_dom|HM2_source_manager|HM2_arbiter_request|ReferenceError|TypeError|SyntaxError|Exception|ERROR" || echo "No recent HM2 errors"
}

summary() {
    echo
    echo "================================================================"
    echo "===== SUMMARY ====="
    echo "================================================================"
    echo "PASS_501=$PASS_501"
    echo "PASS_502=$PASS_502"
    echo "PASS_503=$PASS_503"
    echo "TEST_FAILED=$TEST_FAILED"
    if [ "$TEST_FAILED" -eq 0 ] && [ "$PASS_501" -eq 1 ] && [ "$PASS_502" -eq 1 ] && [ "$PASS_503" -eq 1 ]; then
        echo "OVERALL=PASS"
    else
        echo "OVERALL=FAIL"
    fi
    date
}

echo "===== HM2 INTEGRATED COMMISSIONING RUNNER START ====="
date

echo
printf "RUNNER_PATH="
pwd
printf "HOSTNAME="
hostname

prepare_idle

run_contour_test \
    "501 ТП дом / паркет" \
    "hm2_501_tp_dom" \
    "NL_simple_thermostat_603" \
    "26" \
    "/devices/A03/controls/K1" \
    "/devices/A05/controls/Channel 1 Switch" \
    "/devices/A05/controls/Channel 1 Dimming Level" \
    "/devices/wb-m1w2_141/controls/External Sensor 1" \
    "/devices/wb-m1w2_141/controls/External Sensor 2" \
    "35" \
    "$TEST_MINUTES_501" \
    "/devices/A08/controls/K3" \
    ""

run_contour_test \
    "502 ГП дом / плитка" \
    "hm2_502_gp_dom" \
    "NL_simple_thermostat_606" \
    "29" \
    "/devices/A03/controls/K2" \
    "/devices/A05/controls/Channel 2 Switch" \
    "/devices/A05/controls/Channel 2 Dimming Level" \
    "/devices/wb-m1w2_167/controls/External Sensor 1" \
    "/devices/wb-m1w2_167/controls/External Sensor 2" \
    "37" \
    "$TEST_MINUTES_502" \
    "/devices/A13/controls/K1" \
    ""

run_contour_test \
    "503 Радиаторы дом" \
    "hm2_503_rad_dom" \
    "NL_simple_thermostat_010" \
    "28" \
    "/devices/A03/controls/K3" \
    "" \
    "" \
    "/devices/wb-m1w2_170/controls/External Sensor 1" \
    "/devices/wb-m1w2_121/controls/External Sensor 1" \
    "45" \
    "$TEST_MINUTES_503" \
    "/devices/A09/controls/K4" \
    "/devices/A09/controls/K5"

stop_all
final_snapshot
summary

echo
if [ "$TEST_FAILED" -eq 0 ] && [ "$PASS_501" -eq 1 ] && [ "$PASS_502" -eq 1 ] && [ "$PASS_503" -eq 1 ]; then
    exit 0
fi
exit 1
