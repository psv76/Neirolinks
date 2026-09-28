/*
 * PROJECT: 05 16 Исеть
 * SCRIPT: 23_heating_living_manager.js
 *
 * Восемь воздушных термостатов Home Assistant управляют
 * нормально открытыми сервоприводами конвекторов/радиаторов K1..K11.
 *
 * HA формирует final demand и heartbeat.
 * HM2 является единственным writer K1..K11 и насоса жилого контура K4.
 *
 * Сервоприводы NO:
 *   0 = открыт, тепло идёт;
 *   1 = закрыт.
 *
 * При потере HA heartbeat все K1..K11 закрываются, насос K4 выключается.
 * Контроль температурного отклика — диагностика; он не блокирует отопление.
 * Тёплый пол K12..K16 этот файл не читает и не пишет.
 *
 * Совместимость: ES5 / wb-rules 2.40.0-wb100.
 */

var HC = require("HeatingCommon");
var CFG = require("HeatingConfig");

var hc = HC.create(
    {
        dev: dev,
        log: log,
        trackMqtt: trackMqtt,
        defineVirtualDevice: defineVirtualDevice
    },
    "Heating_living_manager",
    CFG.ttl,
    {
        allowedOutputs: CFG.allowedOutputs.Heating_living_manager || []
    }
);

var LIVING_PUMP = "wb-mr6cu_37/K4";

var livingReady = HC.stableGate();
var livingWatch = HC.responseWatch();

var zoneOpenSince = {};
var livingOutdoorLast = null;

hc.device("heating_living", "Отопление / Жилая зона", {
    zones_requesting: hc.cell("—", "Комнаты, которым нужно тепло"),
    paths_status: hc.cell("—", "Сервоприводы"),
    pump_status: hc.cell("НЕИЗВЕСТНО", "Насос жилого контура"),
    transfer_ui: hc.cell("Не контролируется", "Диагностика нагрева")
}, true);

hc.watch(CFG.haHeartbeat);
hc.watch(CFG.channels.outdoor);
hc.watch(CFG.channels.common);
hc.watch(CFG.channels.living);
hc.watch(LIVING_PUMP);

function livingAllOutputs(zone) {
    return zone && zone.outputs && zone.outputs.length ?
        zone.outputs :
        [];
}

function livingOutputsReadback(zone, expectedClosed) {
    var outputs = livingAllOutputs(zone);
    var i;
    var actual;

    if (!outputs.length) {
        return false;
    }

    for (i = 0; i < outputs.length; i++) {
        actual = hc.bool(outputs[i]);

        if (actual === null || actual !== expectedClosed) {
            return false;
        }
    }

    return true;
}

function livingCommandZone(zone, demand, haFresh) {
    var outputs = livingAllOutputs(zone);
    var shouldOpen = haFresh && demand === true;

    /* NO-сервопривод:
     * false / 0 = открыт;
     * true / 1 = закрыт.
     */
    var desiredClosed = !shouldOpen;
    var accepted = true;
    var i;

    for (i = 0; i < outputs.length; i++) {
        if (!hc.output(
                outputs[i],
                desiredClosed,
                CFG.outputsEnabled
            ) && CFG.outputsEnabled) {

            accepted = false;
        }
    }

    return {
        shouldOpen: shouldOpen,
        desiredClosed: desiredClosed,
        accepted: accepted,
        readbackOk: livingOutputsReadback(zone, desiredClosed)
    };
}

function livingTick() {
    var now = hc.now();

    var haFresh =
        CFG.livingMapConfirmed &&
        CFG.livingZones.length > 0 &&
        hc.heartbeatFresh(
            CFG.haHeartbeat,
            CFG.ttl.haHeartbeat
        );

    var active = false;
    var unknown = false;
    var anyReady = false;
    var outputProblem = false;

    var paths = {};
    var demands = {};

    var i;
    var j;
    var z;
    var demand;
    var command;
    var outputs;
    var pathReady;

    /* HA рассчитывает final demand; HM2 управляет K1..K11,
     * ждёт открытия приводов и управляет насосом K4. */
    for (i = 0; i < CFG.livingZones.length; i++) {
        z = CFG.livingZones[i];

        demand = hc.haBool(
            z.demand,
            CFG.haHeartbeat
        );

        demands[z.id] =
            demand === null ? "UNKNOWN" :
            demand ? "ON" :
            "OFF";

        if (!haFresh || demand === null) {
            unknown = true;
        }

        if (haFresh && demand === true) {
            active = true;
        }

        command = livingCommandZone(
            z,
            demand,
            haFresh
        );

        outputs = livingAllOutputs(z);

        if (!command.accepted || !command.readbackOk) {
            outputProblem = true; /* diagnostic; other zones may have a valid open path */
        }

        /* Не считать старое readback подтверждением открытия после перезапуска. */
        if (command.shouldOpen && command.accepted && command.readbackOk) {
            if (zoneOpenSince[z.id] === undefined ||
                zoneOpenSince[z.id] === null) {

                zoneOpenSince[z.id] = now;
            }

            pathReady =
                now - zoneOpenSince[z.id] >=
                CFG.ttl.actuatorOpen;
        } else {
            zoneOpenSince[z.id] = null;
            pathReady = false;
        }

        paths[z.id] = pathReady;

        if (demand === true && pathReady) {
            anyReady = true;
        }

        for (j = 0; j < outputs.length; j++) {
            if (hc.bool(outputs[j]) === null) {
                outputProblem = true;
            }
        }
    }

    var outdoorMeasured = hc.num(
        CFG.channels.outdoor,
        -60,
        60,
        CFG.ttl.outdoor
    );
    if (outdoorMeasured !== null) livingOutdoorLast = outdoorMeasured;
    var outdoor = outdoorMeasured === null ? livingOutdoorLast : outdoorMeasured;

    var readyCondition =
        haFresh &&
        !unknown &&
        outdoor !== null; /* one failed zone readback never vetoes healthy zones */

    var ready = livingReady(
        readyCondition,
        now,
        CFG.ttl.recovery
    );

    var state =
        ready ?
            (active ? "ACTIVE" : "INACTIVE") :
            "UNKNOWN";

    var reason =
        !CFG.livingMapConfirmed ?
            "LIVING_MAP_NOT_COMMISSIONED" :

        !haFresh ?
            "HA_HEARTBEAT_LOST" :

        unknown ?
            "HA_DEMAND_UNKNOWN" :

        outputProblem && active && !anyReady ?
            "ACTUATOR_COMMAND_OR_READBACK_FAILED" :

        !ready ?
            "STARTUP_OR_RECOVERY" :

        active ?
            "ZONE_REQUEST" :

            "NO_DEMAND";

    /* Погодная кривая без повторного расчёта комнатного термостата HA. */
    var base =
        outdoor === null ? 0 :

        outdoor >= 0 ?
            48 - HC.clamp(outdoor, 0, 10) :

        outdoor >= -10 ?
            48 - outdoor :

            58 +
            HC.clamp(-outdoor - 10, 0, 15) *
            10 / 15;

    var requested = HC.clamp(
        base,
        35,
        75
    );

    var common = hc.num(
        CFG.channels.common,
        5,
        95
    );

    var branch = hc.num(
        CFG.channels.living,
        5,
        95
    );

    /* Насос: active final demand, готовый путь, разрешение арбитра. */
    var pumpWanted =
        state === "ACTIVE" &&
        anyReady &&
        hc.permit("living");

    hc.output(
        LIVING_PUMP,
        pumpWanted,
        CFG.outputsEnabled
    );

    var transfer = livingWatch(
        CFG.outputsEnabled &&
        pumpWanted &&
        hc.bool(LIVING_PUMP) === true &&
        common !== null &&
        common >= requested &&
        branch !== null &&
        branch < requested - 2,

        branch,
        now,
        CFG.response.branchWindow,
        CFG.response.branchRise
    );

    /* Отсутствие +2 °C за 10 минут не доказывает отсутствие протока.
     * Пишем диагностическое событие, но не выключаем K4 и не аннулируем запрос. */
    hc.changed("living_heat_response", "СОСТОЯНИЕ", transfer === "NO_RESPONSE" ?
        "Недостаточный рост температуры (диагностика)" : "Контроль нагрева: норма", {});

    var p = HC.request(
        state,
        requested,
        "COMFORT",
        reason,
        now
    );

    p.transfer = transfer;
    p.fault_latched = false;
    p.outdoor_fallback = outdoorMeasured === null && outdoor !== null;
    p.path_ready = paths;
    p.zone_demands = demands;

    p.ha_heartbeat =
        haFresh ?
            "VALID" :
            "UNKNOWN";

    var required = [
        CFG.haHeartbeat,
        CFG.channels.outdoor,
        LIVING_PUMP
    ];

    for (i = 0; i < CFG.livingZones.length; i++) {
        required.push(
            CFG.livingZones[i].demand
        );

        outputs = livingAllOutputs(
            CFG.livingZones[i]
        );

        for (j = 0; j < outputs.length; j++) {
            required.push(outputs[j]);
        }
    }

    p.commissioned =
        CFG.livingMapConfirmed &&
        hc.commissioned(required);

    p.pump_suppression =
        state === "ACTIVE" && !anyReady ?
            "ACTUATOR_OPEN_DELAY" :

        !haFresh ?
            "HA_HEARTBEAT_LOST" :

        outputProblem ?
            "ACTUATOR_COMMAND_OR_READBACK_FAILED" :

            reason;

    hc.publish(
        "heating_living",
        p
    );

    var requestingUi = [], pendingUi = [], readyUi = [];
    for (i = 0; i < CFG.livingZones.length; i++) {
        z = CFG.livingZones[i];
        if (demands[z.id] === "ON") {
            requestingUi.push(z.title || z.id);
            if (paths[z.id]) readyUi.push(z.title || z.id);
            else pendingUi.push(z.title || z.id);
        }
    }
    dev["heating_living/zones_requesting"] = requestingUi.length ?
        requestingUi.join(", ") : "Нет активных запросов";
    dev["heating_living/paths_status"] = pendingUi.length ?
        "Открываются / не готовы: " + pendingUi.join(", ") :
        readyUi.length ? "Готовы: " + readyUi.join(", ") : "Нет активных путей";
    dev["heating_living/pump_status"] = hc.bool(LIVING_PUMP) === true ? "ВКЛ" :
        hc.bool(LIVING_PUMP) === false ? "ВЫКЛ" : "НЕТ ДАННЫХ";
    dev["heating_living/transfer_ui"] = transfer === "RESPONSE_CONFIRMED" ? "Передача тепла подтверждена" :
        transfer === "OBSERVING" ? "Идёт проверка реакции" :
        transfer === "NO_RESPONSE" ? "Нет ожидаемого роста температуры" : "Не контролируется";
}

/* Подписки на final demand и фактические K1..K11. */
for (var li = 0; li < CFG.livingZones.length; li++) {
    var lz = CFG.livingZones[li];
    var outs = livingAllOutputs(lz);

    hc.watch(lz.demand);

    for (var oi = 0; oi < outs.length; oi++) {
        hc.watch(outs[oi]);
    }
}

setInterval(
    livingTick,
    CFG.ttl.tick * 1000
);

livingTick();
