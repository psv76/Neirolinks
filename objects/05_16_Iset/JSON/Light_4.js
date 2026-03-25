// Мастер-выключатель
// Двойное нажатие включает свет в подвале

defineRule({
  whenChanged: "wb-mr6cv3_137/Input 2 Double Press Counter",
  then: function (newValue, devName, cellName) {
	if (newValue) {

          dev["wb-mr6c_46/K1"] = true;
          dev["wb-mr6c_46/K2"] = true;
          dev["wb-mr6c_46/K3"] = true;
          dev["wb-mr6c_46/K4"] = true;

      
   }
  }
});