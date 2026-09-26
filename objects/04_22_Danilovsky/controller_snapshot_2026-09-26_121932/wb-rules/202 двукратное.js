var pressTrigger = "wb-mr6c_203/Input 3 Double Press Counter";

var rgbRelays = [
    "wb-led_58/RGB Palette",
    "wb-led_13/RGB Palette"
];


var colors = [
    "255;0;0",       // красный
    "255;128;0",     // оранжевый
    "255;255;0",     // желтый
    "0;255;0",       // зеленый
    "0;255;255",     // голубой
    "0;0;255",       // синий
    "128;0;255",     // фиолетовый
    "255;255;255"    // белый
];


var colorIndex = 0;

defineRule("rgb_color_cycle", {
    whenChanged: pressTrigger,

    then: function () {

        colorIndex++;

        if (colorIndex >= colors.length) {
            colorIndex = 0;
        }

        rgbRelays.forEach(function (relay) {
            dev[relay] = colors[colorIndex];
        });
    }
});
