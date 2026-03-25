// Мастер-выключатель. 
// Длительное нажатие выключает весь свет в доме.

defineRule({
  whenChanged: "wb-mr6cv3_137/Input 2 Long Press Counter",
  then: function (newValue, devName, cellName) {
	if (newValue) {

          dev["wb-mr6cv3_4/K1"] = false;
          dev["wb-mr6cv3_4/K2"] = false;
          dev["wb-mr6cv3_4/K3"] = false;
          dev["wb-mr6cv3_4/K4"] = false;
          dev["wb-mr6cv3_4/K5"] = false;
          dev["wb-mr6cv3_4/K6"] = false;
      
          dev["wb-mr6cv3_70/K1"] = false;
          dev["wb-mr6cv3_70/K2"] = false;
          dev["wb-mr6cv3_70/K3"] = false;
          dev["wb-mr6cv3_70/K4"] = false;
          dev["wb-mr6cv3_70/K5"] = false;
          dev["wb-mr6cv3_70/K6"] = false;

          dev["wb-mr6cv3_71/K1"] = false;
          dev["wb-mr6cv3_71/K2"] = false;
          dev["wb-mr6cv3_71/K3"] = false;
          dev["wb-mr6cv3_71/K4"] = false;
          dev["wb-mr6cv3_71/K5"] = false;
       // dev["wb-mr6cv3_71/K6"] = false;      
      
       // dev["wb-mr6cv3_72/K1"] = false;
       // dev["wb-mr6cv3_72/K2"] = false;
          dev["wb-mr6cv3_72/K3"] = false;
          dev["wb-mr6cv3_72/K4"] = false;
          dev["wb-mr6cv3_72/K5"] = false;
       // dev["wb-mr6cv3_72/K6"] = false;


          dev["wb-mr6c_46/K1"] = false;
          dev["wb-mr6c_46/K2"] = false;
          dev["wb-mr6c_46/K3"] = false;
          dev["wb-mr6c_46/K4"] = false;
       // dev["wb-mr6c_46/K5"] = false;
       // dev["wb-mr6c_46/K6"] = false;

      
   }
  }
});