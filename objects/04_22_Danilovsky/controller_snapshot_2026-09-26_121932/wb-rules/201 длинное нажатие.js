var triggers = [
    "wb-led_58/Input 1 Long Press Counter"
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

                var value = dev[relay] - 5;

                if (value < 0) {
                    value = 0;
                }

                dev[relay] = value;
            });

        }
    });

});
