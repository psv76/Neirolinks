var pressTrigger = "wb-mr6c_218/Input 2 Long Press Counter";

var masterRelay = "wb-mr6c_218/K2";

var slaveRelays = [
    "wb-mr6c_218/K3",

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
