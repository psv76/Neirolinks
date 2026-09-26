var pressTrigger = "wb-mr6c_206/Input 3 Single Press Counter";

var masterRelay = "wb-mr6c_206/K3";

var slaveRelays = [
  "wb-led_40/CCT2",
  "wb-led_37/CCT2",
  "wb-led_11/CCT1",
  "wb-led_239/CCT2",
  "wb-led_52/CCT2",
  "wb-mr6c_206/K1"
];

defineRule("relay_sync_input6_single", {
    whenChanged: pressTrigger,

    then: function () {

        setTimeout(function () {

            var state = dev[masterRelay];

            slaveRelays.forEach(function (relay) {
                dev[relay] = state;

                if (state === true) {
                    dev[relay + " Brightness"] = 50;
                }
            });

        }, 300);
    }
});