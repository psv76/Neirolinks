// wb-mrm2-mini_134/K1 - полное открытие
// wb-mrm2-mini_134/K2 - режим калитки

var GATE_CFG = {
    fullOpen: "wb-mrm2-mini_134/K1",
    wicketOpen: "wb-mrm2-mini_134/K2",
    pulseMs: 1000
};

var gateState = {
    fullTimer: null,
    wicketTimer: null,
    prevFull: false,
    prevWicket: false
};

function startPulse(channel, timerName)
{
    if (gateState[timerName]) {
        clearTimeout(gateState[timerName]);
    }

    gateState[timerName] = setTimeout(function () {
        dev[channel] = false;
        gateState[timerName] = null;
    }, GATE_CFG.pulseMs);
}

defineRule("gate_full_open_pulse", {
    whenChanged: GATE_CFG.fullOpen,
    then: function (newValue) {
        var curr = !!newValue;
        var prev = gateState.prevFull;

        gateState.prevFull = curr;

        // ловим только включение
        if (prev === false && curr === true) {
            startPulse(GATE_CFG.fullOpen, "fullTimer");
        }
    }
});

defineRule("gate_wicket_pulse", {
    whenChanged: GATE_CFG.wicketOpen,
    then: function (newValue) {
        var curr = !!newValue;
        var prev = gateState.prevWicket;

        gateState.prevWicket = curr;

        if (prev === false && curr === true) {
            startPulse(GATE_CFG.wicketOpen, "wicketTimer");
        }
    }
});

// инициализация
setTimeout(function () {
    gateState.prevFull = !!dev[GATE_CFG.fullOpen];
    gateState.prevWicket = !!dev[GATE_CFG.wicketOpen];
}, 1000);