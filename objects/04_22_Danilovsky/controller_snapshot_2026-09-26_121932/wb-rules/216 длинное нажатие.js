var pressTrigger = "wb-mr6c_156/Input 6 Long Press Counter";

var masterRelay = "wb-mr6c_156/K6";

var slaveRelays = [
    "wb-mr6c_117/K1",
];

defineRule("relay_sync_input6_single", {
    whenChanged: pressTrigger,

    then: function () {

        setTimeout(function () {

            var state = dev[masterRelay];

            slaveRelays.forEach(function (relay) {
                dev[relay] = state;
            });

        }, 300);
    }
});