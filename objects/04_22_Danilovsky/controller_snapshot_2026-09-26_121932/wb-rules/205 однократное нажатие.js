var pressTrigger = ["wb-led_245/Input 1 Single Press Counter"];

var masterRelay = "wb-led_245/RGB Strip";

var slaveRelays = [
    "wb-led_51/RGB Strip",
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
