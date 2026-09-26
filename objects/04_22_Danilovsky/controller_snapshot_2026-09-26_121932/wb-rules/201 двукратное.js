var pressTrigger = ["wb-led_58/Input 1 Double Press Counter"];

var masterRelay = "wb-led_58/RGB Strip";

var slaveRelays = [
    "wb-led_13/RGB Strip",
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
