#!/bin/bash
# HM2 / 05 31 Иволга 13 / Issue #26. Только фиксированные сценарии 501.
set -Eeuo pipefail
export LC_ALL=C.UTF-8
readonly VD=hm2_501_tp_dom
readonly ZONE=NL_simple_thermostat_601
readonly -a STOP_PATHS=(
    "$VD/response_commissioned" "$VD/manual_commissioning_grant"
    "$VD/outputs_enabled" "$VD/enabled" "$VD/commissioned" "$VD/local_permit"
    'A03/K1' 'A05/Channel 1 Dimming Level' 'A05/Channel 1 Switch'
)
stop_on_exit=0

usage() {
    printf '%s\n' 'Использование: hm2_501_test_runner.sh СЦЕНАРИЙ' \
        '  snapshot | safe-stop | enable-shadow | open-601 | close-601' \
        '  gate-tests | collect-journal | physical-start --physical' >&2
}
fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }
show() { printf '+ ' >&2; printf '%q ' "$@" >&2; printf '\n' >&2; }
run() { show "$@"; "$@"; }

# Брокер только на этом WB. Нет eval, произвольных команд, адресов или топиков из CLI.
read_value() {
    run timeout 5 mosquitto_sub -h localhost -t "/devices/${1%/*}/controls/${1##*/}" -C 1 -W 3
}
write_value() {
    # Без -r: управляющая команда /on не должна сохраняться как retained.
    run timeout 5 mosquitto_pub -h localhost -q 1 \
        -t "/devices/${1%/*}/controls/${1##*/}/on" -m "$2"
}
matches() {
    case "$2:$1" in
        0:0|0:0.0|0:false|0:OFF|1:1|1:true|1:ON) return 0 ;;
    esac
    [[ "$1" == "$2" ]]
}
expect() {
    local value
    value=$(read_value "$1") || return 1
    printf '%s = %s (ожидается %s)\n' "$1" "$value" "$2" >&2
    matches "$value" "$2"
}
set_checked() {
    local attempt
    write_value "$1" "$2" || return 1
    for attempt in 1 2 3; do
        if expect "$1" "$2"; then return 0; fi
        if [[ "$attempt" != 3 ]]; then run sleep 1; fi
    done
    printf 'Не подтверждена запись: %s = %s\n' "$1" "$2" >&2
    return 1
}
snapshot() {
    local cell value rc=0
    printf '\n=== SNAPSHOT 501 (MQTT, не доказательство протока/положения штока) ===\n'
    run date -Is
    for cell in enabled commissioned local_permit outputs_enabled \
        manual_commissioning_grant response_commissioned status state valid heat_demand \
        active_zone_count physical_active_output_count path_ready pump_cmd \
        grant_state fault_latched fault_text request_timestamp actuator_delay_s \
        period_s freeze source_temp_c supply_temp_c return_temp_c valve_position_cmd \
        response_status response_rise_c; do
        if value=$(read_value "$VD/$cell"); then
            printf '%s = %s\n' "$cell" "$value"
        else printf '%s = НЕТ ДАННЫХ\n' "$cell"; rc=1; fi
    done
    for cell in "$ZONE/target_state" "$ZONE/target_temperature" "$ZONE/current_state" \
        'A08/K1' 'A08/K4' 'A03/K1' 'A05/Channel 1 Dimming Level' 'A05/Channel 1 Switch'; do
        if value=$(read_value "$cell"); then printf '%s = %s\n' "$cell" "$value"
        else printf '%s = НЕТ ДАННЫХ\n' "$cell"; rc=1; fi
    done
    return "$rc"
}
safe_stop() {
    local path rc=0 attempt all_zero
    printf '\n=== ФИЗИЧЕСКИЙ STOP: снять разрешения, насос OFF, клапан 0 / OFF ===\n' >&2
    # Сначала попытаться послать ВСЕ девять команд, даже при отказе одной из них.
    for path in "${STOP_PATHS[@]}"; do
        if ! write_value "$path" 0; then rc=1; fi
    done
    for attempt in 1 2 3; do
        all_zero=1
        for path in "${STOP_PATHS[@]}"; do
            if ! expect "$path" 0; then all_zero=0; fi
        done
        if [[ "$all_zero" == 1 ]]; then break; fi
        if [[ "$attempt" != 3 ]]; then run sleep 1; fi
    done
    if [[ "$all_zero" != 1 ]]; then rc=1; fi
    if ! snapshot; then rc=1; fi
    if [[ "$rc" != 0 ]]; then
        printf 'STOP НЕ ПОДТВЕРЖДЁН. Нужен очный контроль насоса и клапана!\n' >&2
    fi
    return "$rc"
}
cleanup() {
    local rc=$?
    trap - EXIT
    # Во время аварийного stop повторный Ctrl-C не должен оборвать девять команд.
    trap '' INT TERM HUP
    if [[ "$stop_on_exit" == 1 ]]; then
        if ! safe_stop; then rc=1; fi
    fi
    exit "$rc"
}
disarm() {
    set_checked "$VD/outputs_enabled" 0
    set_checked "$VD/manual_commissioning_grant" 0
    set_checked "$VD/response_commissioned" 0
}
check_zero_outputs() {
    expect 'A03/K1' 0 && expect 'A05/Channel 1 Dimming Level' 0 && expect 'A05/Channel 1 Switch' 0
}
check_ready() {
    local cell stamp epoch now
    for cell in enabled commissioned local_permit valid heat_demand path_ready pump_cmd; do
        expect "$VD/$cell" 1 || fail "Нет готовности: $cell. Нужны enable-shadow, open-601 и ожидание actuator delay."
    done
    expect "$VD/fault_latched" 0 || fail 'Защёлкнута авария; runner не сбрасывает её.'
    expect "$VD/freeze" 0 || fail 'Ручной freeze включён; требуется инженерная проверка.'
    stamp=$(read_value "$VD/request_timestamp")
    epoch=$(run date -d "$stamp" +%s) || fail 'Некорректный request_timestamp.'
    now=$(run date +%s)
    (( now >= epoch && now - epoch <= 90 )) || fail 'Расчёт 501 устарел или часы расходятся.'
}
watch_gate() {
    local grant=$1 start=$SECONDS
    # 35 секунд покрывают максимальный period_s=30 текущего manager.
    while (( SECONDS - start < 35 )); do
        expect "$VD/response_commissioned" 0 || fail 'Изменился response_commissioned.'
        expect "$VD/manual_commissioning_grant" "$grant" || fail 'Изменился grant.'
        expect "$VD/outputs_enabled" 1 || fail 'Изменился outputs_enabled.'
        check_zero_outputs || fail 'Gate-test: ненулевой или недоступный физический выход!'
        printf 'Gate: %s / 35 секунд\n' "$((SECONDS - start))"
        run sleep 1
    done
    check_ready
    snapshot
}
observe_physical() {
    local start=$1 next=10 cell value
    while (( SECONDS - start < 300 )); do
        if (( SECONDS - start < next )); then
            run sleep "$((next - (SECONDS - start)))"
        fi
        if (( SECONDS - start >= 300 )); then break; fi
        printf '\nФИЗИЧЕСКИЙ ПУСК: %s / 300 секунд\n' "$((SECONDS - start))"
        for cell in source_temp_c supply_temp_c return_temp_c response_status fault_latched; do
            value=$(read_value "$VD/$cell")
            printf '%s = %s\n' "$cell" "$value"
            if [[ "$cell" == fault_latched ]]; then
                matches "$value" 0 || fail 'Авария 501 при физическом пуске.'
            fi
        done
        for cell in 'A03/K1' 'A05/Channel 1 Dimming Level' 'A05/Channel 1 Switch'; do
            value=$(read_value "$cell")
            printf '%s = %s\n' "$cell" "$value"
        done
        next=$((next + 10))
        (( SECONDS - start <= next )) || fail 'Чтение заняло более 10 секунд; наблюдение ненадёжно.'
    done
}

scenario=${1-}
case "$scenario" in
    snapshot|safe-stop|enable-shadow|open-601|close-601|gate-tests|collect-journal)
        [[ $# == 1 ]] || { usage; exit 2; } ;;
    physical-start)
        [[ $# == 2 && ${2-} == --physical ]] || { usage; exit 2; } ;;
    *) usage; exit 2 ;;
esac

if [[ "$scenario" == collect-journal ]]; then
    show journalctl -u wb-rules --since '30 minutes ago' --no-pager
    show grep -E '501_tp_dom|hm2_501|MixingController|rule error|TypeError|ReferenceError|SyntaxError|Exception'
    # grep=1 означает отсутствие совпадений, но не ошибку journalctl.
    set +e
    journalctl -u wb-rules --since '30 minutes ago' --no-pager |
        grep -E '501_tp_dom|hm2_501|MixingController|rule error|TypeError|ReferenceError|SyntaxError|Exception'
    statuses=("${PIPESTATUS[@]}")
    set -e
    (( statuses[0] == 0 && statuses[1] <= 1 )) || fail 'Не удалось собрать журнал.'
    exit 0
fi
for dependency in timeout mosquitto_pub mosquitto_sub flock date sleep; do
    command -v "$dependency" >/dev/null || fail "Не найдена команда $dependency."
done
# Один runner на WB. Второй запуск не может случайно вмешаться в пуск.
show flock -n /run/lock/hm2_501_test_runner.lock
exec 9>/run/lock/hm2_501_test_runner.lock
flock -n 9 || fail 'Другой runner уже работает. Прервите его Ctrl-C для safe-stop.'
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

case "$scenario" in
    snapshot) snapshot ;;
    safe-stop)
        stop_on_exit=1
        safe_stop
        stop_on_exit=0 ;;
    enable-shadow)
        stop_on_exit=1
        printf 'SHADOW: физические выходы 501 будут удерживаться в нуле.\n'
        disarm
        set_checked "$VD/commissioned" 1
        set_checked "$VD/local_permit" 1
        set_checked "$VD/enabled" 1
        check_zero_outputs
        snapshot
        stop_on_exit=0 ;;
    open-601|close-601)
        stop_on_exit=1
        printf 'ФИЗИЧЕСКОЕ ДЕЙСТВИЕ: термостат 601 управляет приводами A08/K1 и K4 через 620.\n'
        disarm
        check_zero_outputs
        if [[ "$scenario" == open-601 ]]; then
            # Сначала безопасно задать уставку, затем включить термостат.
            set_checked "$ZONE/target_temperature" 26
            set_checked "$ZONE/target_state" 1
        else set_checked "$ZONE/target_state" 0; fi
        snapshot
        stop_on_exit=0 ;;
    gate-tests)
        stop_on_exit=1
        printf 'ОПАСНЫЙ ТЕСТ РАЗРЕШЕНИЙ: response_commissioned остаётся 0.\n'
        disarm
        check_zero_outputs
        check_ready
        set_checked "$VD/outputs_enabled" 1
        watch_gate 0
        set_checked "$VD/manual_commissioning_grant" 1
        watch_gate 1
        printf 'Обе выборочные проверки MQTT-нулей прошли; далее обязательный safe-stop.\n' ;;
    physical-start)
        printf '\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
        printf 'ОПАСНО: ФИЗИЧЕСКИЙ ПУСК НАСОСА И КЛАПАНА 501 НА 5 МИНУТ!\n'
        printf 'ПНР ЗАБЛОКИРОВАН до проверки источника 411 и гидравлики.\n'
        printf 'Продолжать только ОЧНО у котельной после снятия блокировки инженером.\n'
        printf 'Проверьте насос, клапан, арматуру, воздух, трубы и параметры response watchdog.\n'
        printf 'Нормальный теплоперенос ещё НЕ подтверждён. Ctrl-C вызывает safe-stop.\n'
        printf '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
        [[ -t 0 ]] || fail 'Требуется интерактивный терминал, ввод через pipe запрещён.'
        printf 'Для подтверждения введите EXACTLY: START 501 PHYSICAL\n> '
        IFS= read -r confirmation
        [[ "$confirmation" == 'START 501 PHYSICAL' ]] || fail 'Пуск отменён.'
        stop_on_exit=1
        expect "$VD/outputs_enabled" 0
        expect "$VD/manual_commissioning_grant" 0
        expect "$VD/response_commissioned" 0
        check_zero_outputs
        check_ready
        set_checked "$VD/outputs_enabled" 1
        set_checked "$VD/manual_commissioning_grant" 1
        physical_start=$SECONDS
        set_checked "$VD/response_commissioned" 1
        # Snapshot также входит в общий пятиминутный предел опасной секции.
        snapshot
        (( SECONDS - physical_start < 10 )) || fail 'Snapshot слишком медленный для физического наблюдения.'
        observe_physical "$physical_start"
        printf 'Наблюдение закончено; далее обязательный safe-stop.\n' ;;
esac
