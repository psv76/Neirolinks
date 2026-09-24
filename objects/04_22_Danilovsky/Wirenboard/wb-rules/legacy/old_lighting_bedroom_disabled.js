// Управление светом на кухне над островом и рабочая зона через счетчик срабатывания
// Инициализируем переменную для отслеживания состояния нажатий
var pressCount = 0;

function onSwitchChange() {
  // Увеличиваем счетчик нажатий
  pressCount++; 

  // Определяем действие в зависимости от количества нажатий
  switch (pressCount) {
    case 1: // Первое нажатие
      dev['wb-led_52/CCT1'] = true; 
      dev['wb-mr6c_206/K4'] = true; 
      break;
    case 2: // Второе нажатие
      dev['wb-led_52/CCT1'] = false; 
      dev['wb-mr6c_206/K4'] = false; 
      pressCount = 0; // Сбрасываем счетчик нажатий
      break;
  }
}
// Подписываемся на изменения состояния выключателя около входа в котельную
defineRule("switch_control_lamps", {
  whenChanged:  ["wb-mr6c_206/Input 4 Single Press Counter", "wb-mr6c_206/Input 1 Single Press Counter" ],
  then: function () {
    onSwitchChange();
  }
});

// ============================================================================
// ОТКЛЮЧЕНО 25.09.2026.
// Эта старая часть больше не управляет спальней.
// Кнопка 212, короткое нажатие, теперь обслуживается отдельным правилом
// 41_lighting_bedroom.js: оно выключает подсветки 311 и 311.1,
// а работа основного света 312 остаётся за самим модулем Wiren Board.
// Старый код оставлен ниже полностью, но выключен знаками //, чтобы его можно было посмотреть.
// ============================================================================
//===========================================================
// Управление светом в спальне выкл весь свет
// Инициализируем переменную для отслеживания состояния нажатий
// var pressCount1 = 0;
//
// function onSwitchChange1() {
  // Увеличиваем счетчик нажатий
//   pressCount1++; 
//
  // Определяем действие в зависимости от количества нажатий
//   switch (pressCount1) {
//     case 1: // Второе нажатие
//       dev['wb-led_23/CCT2'] = false; 
//       dev['wb-led_42/CCT1'] = false; 
//       pressCount1 = 0; // Сбрасываем счетчик нажатий
//       break;
//   }
// }
//
// Подписываемся на изменения состояния выключателя около входа в котельную
// defineRule("switch_control_lamps1", {
//   whenChanged: "wb-mr6c_156/Input 0 counter",
//   then: function () {
//     onSwitchChange1();
//   }
// });

// ============================================================================
// ОТКЛЮЧЕНО 25.09.2026.
// Эта старая часть больше не управляет длинным нажатием кнопки 211.
// Теперь это делает отдельное правило 41_lighting_bedroom.js:
// длинное нажатие 211 включает или выключает вместе группы 311 и 311.1
// по их фактическому состоянию, без старого счёта «первое/второе нажатие».
// Старый код сохранён ниже, но выключен знаками //.
// ============================================================================
//===========================================================
// Управление светом в спальне вкл выкл подсветка у кровати клавишша
// Инициализируем переменную для отслеживания состояния нажатий
// var pressCount2 = 0;
//
// function onSwitchChange2() {
  // Увеличиваем счетчик нажатий
//   pressCount2++; 
//
  // Определяем действие в зависимости от количества нажатий
//   switch (pressCount2) {
//     case 1: // Второе нажатие
//       dev['wb-led_23/CCT2'] = true; 
//       dev['wb-led_42/CCT1'] = true; 
//       break;
//        case 2: // Второе нажатие
//       dev['wb-led_23/CCT2'] = false; 
//       dev['wb-led_42/CCT1'] = false; 
//       pressCount2 = 0; // Сбрасываем счетчик нажатий
//       break;
//   }
// }
//
// Подписываемся на изменения состояния выключателя около входа в котельную
// defineRule("switch_control_lamps2", {
//   whenChanged: "wb-mr6c_156/Input 3 Long Press Counter",
//   then: function () {
//     onSwitchChange2();
//   }
// });

//===========================================================
// Управление светом в кухня гостинная выключатели 218-219
// Инициализируем переменную для отслеживания состояния нажатий
var pressCount3 = 0;

function onSwitchChange3() {
  // Увеличиваем счетчик нажатий
  pressCount3++; 

  // Определяем действие в зависимости от количества нажатий
  switch (pressCount3) {
    case 1: // Второе нажатие
      dev['wb-led_11/CCT1'] = true; 
      dev['wb-led_11/CCT1 Brightness'] = 50;
      dev['wb-led_239/Channels 3_4'] = true; 
      dev['wb-led_239/Channels 3_4 Brightness'] = 50;
      dev['wb-led_37/CCT1'] = true; 
      dev['wb-led_37/CCT1 Brightness'] = 50;
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-led_52/CCT2 Brightness'] = 50; 
      dev['wb-mr6c_206/K1'] = true; 
      break;
      case 2: // Второе нажатие
      dev['wb-led_11/CCT1'] = true; 
      dev['wb-led_11/CCT1 Brightness'] = 5;
      dev['wb-led_239/Channels 3_4'] = true; 
      dev['wb-led_239/Channels 3_4 Brightness'] = 5;
      dev['wb-led_37/CCT1'] = true; 
      dev['wb-led_37/CCT1 Brightness'] = 5;
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-led_52/CCT2 Brightness'] = 5; 
      dev['wb-mr6c_206/K1'] = false; 
      break;

       case 3: // Второе нажатие
       dev['wb-led_11/CCT1'] = false; 
      dev['wb-led_239/Channels 3_4'] = false; 
      dev['wb-led_37/CCT1'] = false; 
      dev['wb-led_52/CCT2'] = false; 
      dev['wb-mr6c_206/K1'] = false; 
      pressCount3 = 0; // Сбрасываем счетчик нажатий
      break;
  }
}

// Подписываемся на изменения состояния выключателя около входа в котельную
defineRule("switch_control_lamps3", {
  whenChanged: "wb-mr6c_138/Input 2 Single Press Counter",
  then: function () {
    onSwitchChange3();
  }
});

//===========================================================
// Управление светом в кухня гостинная выключатели 218-219
// Инициализируем переменную для отслеживания состояния нажатий
//var pressCount4 = 0;

//function onSwitchChange4() {
  // Увеличиваем счетчик нажатий
//  pressCount4++; 

  // Определяем действие в зависимости от количества нажатий
 // switch (pressCount4) {
 //   case 1: // Второе нажатие
 //     dev['wb-led_40/CCT1'] = true; 
 //     dev['wb-led_37/CCT1'] = true; 
 //     break;
//       case 2: // Второе нажатие
//       dev['wb-led_40/CCT1'] = false; 
//      dev['wb-led_37/CCT1'] = false; 
//      pressCount4 = 0; // Сбрасываем счетчик нажатий
//      break;
//  }
//}

// Подписываемся на изменения состояния выключателя около входа в котельную
//defineRule("switch_control_lamps4", {
 // whenChanged: "wb-mr6c_206/Input 3 Single Press Counter",
 // then: function () {
 //   onSwitchChange4();
 // }
//});

//===========================================================
// Управление светом в кухня гостинная выключатели 218-219
// Инициализируем переменную для отслеживания состояния нажатий
//var pressCount5 = 0;

//function onSwitchChange5() {
  // Увеличиваем счетчик нажатий
//  pressCount5++; 

  // Определяем действие в зависимости от количества нажатий
//  switch (pressCount5) {
//    case 1: // Второе нажатие
 //     dev['wb-led_40/CCT1'] = true; 
//      dev['wb-led_37/CCT1'] = true; 
 //     break;
//       case 2: // Второе нажатие
//       dev['wb-led_40/CCT1'] = false; 
//      dev['wb-led_37/CCT1'] = false; 
//      pressCount5 = 0; // Сбрасываем счетчик нажатий
 //     break;
//  }
//}

// Подписываемся на изменения состояния выключателя около входа в котельную
//defineRule("switch_control_lamps5", {
 // whenChanged: "wb-mr6c_206/Input 3 Long Press Counter",
 // then: function () {
 //   onSwitchChange5();
 // }
//});
//===========================================================
// Управление светом 229 gr 301-302
// Инициализируем переменную для отслеживания состояния нажатий
var pressCount6 = 0;

function onSwitchChange6() {
  // Увеличиваем счетчик нажатий
  pressCount6++; 

  // Определяем действие в зависимости от количества нажатий
  switch (pressCount6) {
    case 1: // Второе нажатие
      dev['wb-mr6c_138/K1'] = false; 
      dev['wb-mr6c_138/K2'] = false; 
      dev['wb-mr6c_138/K3'] = false; 
      pressCount6 = 0; // Сбрасываем счетчик нажатий
      break;
  }
}

// Подписываемся на изменения состояния выключателя около входа в котельную
defineRule("switch_control_lamps6", {
  whenChanged: "wb-mr6c_156/Input 5 Long Press Counter",
  then: function () {
    onSwitchChange6();
  }
});

//===========================================================
// Управление светом в кухня гостинная выключател 230
// Инициализируем переменную для отслеживания состояния нажатий
var pressCount7 = 0;

function onSwitchChange7() {
  // Увеличиваем счетчик нажатий
  pressCount7++; 

  // Определяем действие в зависимости от количества нажатий
  switch (pressCount7) {
    case 1: // Второе нажатие
      dev['wb-mr6c_138/K3'] = true; 
      dev['wb-led_239/Channels 3_4'] = true; 
      dev['wb-led_52/CCT2'] = true; 
      dev['wb-mr6c_206/K1'] = true; 
      break;
       case 2: // Второе нажатие
       dev['wb-mr6c_138/K3'] = false; 
      dev['wb-led_239/Channels 3_4'] = false; 
      dev['wb-led_52/CCT2'] = false; 
      dev['wb-mr6c_206/K1'] = false; 
      pressCount7 = 0; // Сбрасываем счетчик нажатий
      break;
  }
}

// Подписываемся на изменения состояния выключателя около входа в котельную
defineRule("switch_control_lamps7", {
  whenChanged: "wb-mr6c_206/Input 2 Long Press Counter",
  then: function () {
    onSwitchChange7();
  }
});

// ============================================================================
// ОТКЛЮЧЕНО 25.09.2026.
// Эта старая часть больше не управляет длинным нажатием кнопки 212.
// Теперь это делает отдельное правило 41_lighting_bedroom.js:
// длинное нажатие 212 переключает яркость групп 311 и 311.1
// между режимами «День» 80% и «Ночь» 10%.
// Старые значения 50% / 5% и третий шаг «выкл» больше не используются.
// Старый код сохранён ниже, но выключен знаками //.
// ============================================================================
//=================================================================
//===========================================================
// Управление светом в спальне 212 длинное нажатие
// Инициализируем переменную для отслеживания состояния нажатий
// var pressCount8 = 0;
//
// function onSwitchChange8() {
  // Увеличиваем счетчик нажатий
//   pressCount8++; 
//
  // Определяем действие в зависимости от количества нажатий
//   switch (pressCount8) {
//     case 1: // Второе нажатие
//       dev['wb-led_23/CCT2'] = true; 
//       dev['wb-led_23/CCT2 Brightness'] = 50;
//       dev['wb-led_42/CCT1'] = true; 
//       dev['wb-led_42/CCT1 Brightness'] = 50;
//       break;
//       case 2: // Второе нажатие
//       dev['wb-led_23/CCT2'] = true; 
//       dev['wb-led_23/CCT2 Brightness'] = 5;
//       dev['wb-led_42/CCT1'] = true; 
//       dev['wb-led_42/CCT1 Brightness'] = 5;
//       break;
//
//        case 3: // Второе нажатие
//       dev['wb-led_23/CCT2'] = false; 
//       dev['wb-led_42/CCT1'] = false; 
//       pressCount8 = 0; // Сбрасываем счетчик нажатий
//       break;
//   }
// }
//
// Подписываемся на изменения состояния выключателя около входа в котельную
// defineRule("switch_control_lamps8", {
//   whenChanged: "wb-mr6c_156/Input 0 Long Press Counter",
//   then: function () {
//     onSwitchChange8();
//   }
// });