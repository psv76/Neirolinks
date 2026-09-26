var pressTrigger = "wb-mr6c_138/Input 6 Single Press Counter";

var masterRelay = "wb-mr6c_138/K6";

var slaveRelays = [
    "wb-led_26/CCT2",
  
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