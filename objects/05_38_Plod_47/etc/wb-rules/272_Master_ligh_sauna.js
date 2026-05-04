// Выключатель вентилятора 
// Длительное нажатие выключает весь свет в бане.

defineRule({
  whenChanged: "wb-mr6c_50/Input 6 Long Press Counter",
  then: function (newValue, devName, cellName) {
	if (newValue) {

          dev["wb-mr6c_50/K2"] = false; // свет душевая
          dev["wb-mr6c_50/K3"] = false; // свет комната отдыха
          dev["wb-mr6c_50/K4"] = false; // свет с/у бани
          dev["wb-mr6c_35/K2"] = false; // подсветка комната отдыха
          dev["wb-mr6c_35/K3"] = false; // подсветка зеркала туалет
          dev["wb-led_232/Channel 1"]= false; // LED душевая
          dev["wb-led_232/Channel 3"]= false; // LED парилка
      
   }
  }
});