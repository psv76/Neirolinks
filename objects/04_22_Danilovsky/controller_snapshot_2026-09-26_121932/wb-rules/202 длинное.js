var triggers = [
    "wb-mr6c_203/Input 3 Long Press Counter"
];

var brightnessRelays = [
    "wb-led_58/RGB Strip Brightness",
    "wb-led_13/RGB Strip Brightness"
];


triggers.forEach(function (trigger, i) {

    defineRule("brightness_minus_5_" + i, {
        whenChanged: trigger,

        then: function () {

            brightnessRelays.forEach(function (relay) {

                var value = dev[relay] + 5;

                if (value > 100) {
                    value = 100;
                }

                dev[relay] = value;
            });

        }
    });

});
