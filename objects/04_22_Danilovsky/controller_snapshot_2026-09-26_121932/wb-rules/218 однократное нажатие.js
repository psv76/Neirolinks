
var pressTrigger = ["wb-mr6c_206/Input 4 Single Press Counter", "wb-mr6c_206/Input 1 Single Press Counter"];

var masterRelay = "wb-mr6c_206/K4";

var slaveRelays = [
    "wb-led_52/Channels 1_2",
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