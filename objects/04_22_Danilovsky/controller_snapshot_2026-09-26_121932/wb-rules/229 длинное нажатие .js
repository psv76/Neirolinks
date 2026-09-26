var pressCount6 = 0;

function onSwitchChange6() {
  pressCount6++; 

  switch (pressCount6) {
    case 1: 
      dev['wb-mr6c_138/K1'] = false; 
      dev['wb-mr6c_138/K2'] = false; 
      dev['wb-mr6c_138/K3'] = false; 
      pressCount6 = 0;
      break;
  }
}

defineRule("switch_control_lamps6", {
  whenChanged: "wb-mr6c_156/Input 5 Long Press Counter",
  then: function () {
    onSwitchChange6();
  }
});