var pressCount5 = 0;

function onSwitchChange5() {

pressCount5++; 


  switch (pressCount5) {
    case 1: 
      dev['wb-led_40/CCT2'] = true; 
      dev['wb-led_37/CCT2'] = true; 
      break;
       case 2: 
       dev['wb-led_40/CCT2'] = false; 
      dev['wb-led_37/CCT2'] = false; 
      pressCount5 = 0; 
     break;
  }
}


defineRule("switch_control_lamps5", {
  whenChanged: "wb-mr6c_206/Input 3 Long Press Counter",
  then: function () {
    onSwitchChange5();
  }
});