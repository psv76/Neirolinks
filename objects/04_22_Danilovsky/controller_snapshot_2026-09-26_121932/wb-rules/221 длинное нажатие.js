var pressTrigger = "wb-mr6c_138/Input 1 Long Press Counter";

var masterRelay = "wb-mr6c_138/K3";

var slaveRelays = [
    "wb-mr6c_138/K1",
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