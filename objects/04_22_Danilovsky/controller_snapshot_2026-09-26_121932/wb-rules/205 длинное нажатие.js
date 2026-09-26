var triggers = [
    "wb-led_245/Input 1 Long Press Counter"
];

var brightnessRelays = [
    "wb-led_245/RGB Strip Brightness",
    "wb-led_51/RGB Strip Brightness",
    "wb-led_224/RGB Strip Brightness"
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
