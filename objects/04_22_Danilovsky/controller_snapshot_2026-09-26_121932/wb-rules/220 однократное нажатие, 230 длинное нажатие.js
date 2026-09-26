var pressCount3 = 0;

function onSwitchChange3() {
  pressCount3++; 
  switch (pressCount3) {
    case 1: 
      dev['wb-led_11/CCT1'] = true; 
      dev['wb-led_11/CCT1 Brightness'] = 50;
      dev['wb-led_239/CCT2'] = true; 
      dev['wb-led_239/CCT2 Brightness'] = 50;
      dev['wb-led_37/CCT1'] = true; 
      dev['wb-led_37/CCT1 Brightness'] = 50;
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-led_52/CCT2 Brightness'] = 50; 
      dev['wb-mr6c_206/K1'] = true; 
      break;
      case 2: 
      dev['wb-led_11/CCT1'] = true; 
      dev['wb-led_11/CCT1 Brightness'] = 5;
      dev['wb-led_239/CCT2'] = true; 
      dev['wb-led_239/CCT2 Brightness'] = 5;
      dev['wb-led_37/CCT1'] = true; 
      dev['wb-led_37/CCT1 Brightness'] = 5;
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-led_52/CCT2 Brightness'] = 5; 
      dev['wb-mr6c_206/K1'] = false; 
      break;
      case 3: 
      dev['wb-led_11/CCT1'] = false; 
      dev['wb-led_239/CCT2'] = false; 
      dev['wb-led_37/CCT1'] = false; 
      dev['wb-led_52/CCT2'] = false; 
      dev['wb-mr6c_206/K1'] = false; 
      pressCount3 = 0;
      break;
  }
}
defineRule("switch_control_lamps3", {
  whenChanged: ["wb-mr6c_138/Input 2 Single Press Counter","wb-mr6c_206/Input 2 Long Press Counter"],
  then: function () {
    onSwitchChange3();
  }
});