
defineRule("relay_off_on_counter_change", {
    whenChanged: "wb-mr6c_138/Input 5 Long Press Counter",
    then: function () {
      dev['wb-led_11/CCT1'] = true; 
      dev['wb-led_11/CCT1 Brightness'] = 5;
      dev['wb-led_239/CCT2'] = true; 
      dev['wb-led_239/CCT2 Brightness'] = 5;
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-led_52/CCT2 Brightness'] = 5;

      
    }
});