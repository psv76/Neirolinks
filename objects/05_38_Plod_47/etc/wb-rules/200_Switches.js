// Управление освещением через WB-MCM8

// ==============================================
// Выключатель возле входной двери дома на фасаде
// ==============================================

// Левая клавиша, одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 7 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L05/K1"] = !dev["L05/K1"]; // 315 Свет терраса 1 этаж
        }
    }
});

// Левая клавиша, двойное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 7 Double Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_25/K2"] = !dev["wb-mr6c_25/K2"]; // 352 Столбы на парковку
        }
    }
});

// Левая клавиша, длительное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 7 Long Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K2"] = !dev["L04/K2"]; // 313 Неоновая подсветка
        }
    }
});

// Правая клавиша, одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 8 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_25/K1"] = !dev["wb-mr6c_25/K1"]; // 351 Ландшафтное освещение
        }
    }
});

// Правая клавиша, двойное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 8 Double Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_25/K3"] = !dev["wb-mr6c_25/K3"]; // 353 Столбы на дорогу
        }
    }
});


// ==================================================
// Выключатель на фасаде у выхода из кухни на террасу
// ==================================================

// Левая клавиша, одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 5 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K3"] = !dev["L04/K3"]; // 314 Бра на фасаде 1 этаж
        }
    }
});

// Левая клавиша, двойное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 5 Double Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_25/K1"] = !dev["wb-mr6c_25/K1"]; // 351 Ландшафтное освещение
        }
    }
});

// Левая клавиша, длительное нажатие (включает наружное освещение)
defineRule({
    whenChanged: "wb-mcm8_50/Input 5 Long Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K2"] = true;        // 313 Неоновая подсветка
            dev["L04/K3"] = true;        // 314 Бра на фасаде 1 этаж
            dev["L05/K1"] = true;        // 315 Свет терраса 1 этаж
            dev["wb-mr6c_25/K2"] = true; // 352 Столбы на парковку
            dev["wb-mr6c_25/K3"] = true; // 353 Столбы на дорогу
            dev["wb-mr6c_35/K1"] = true; // 354 Свет костровище
            dev["wb-mr6c_50/K1"] = true; // 370 Свет терраса бани
        }
    }
});

// Правая клавиша, одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 6 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L05/K1"] = !dev["L05/K1"]; // 315 Свет терраса 1 этаж
        }
    }
});

// Правая клавиша, двойное нажатие
defineRule({
    whenChanged: "wb-mcm8_50/Input 6 Double Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_35/K1"] = !dev["wb-mr6c_35/K1"]; // 354 Свет костровище
        }
    }
});

// Правая клавиша, длительное нажатие (выключает наружное освещение)
defineRule({
    whenChanged: "wb-mcm8_50/Input 6 Long Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K2"] = false;        // 313 Неоновая подсветка
            dev["L04/K3"] = false;        // 314 Бра на фасаде 1 этаж
            dev["L05/K1"] = false;        // 315 Свет терраса 1 этаж
            dev["wb-mr6c_25/K2"] = false; // 352 Столбы на парковку
            dev["wb-mr6c_25/K3"] = false; // 353 Столбы на дорогу
            dev["wb-mr6c_35/K1"] = false; // 354 Свет костровище
            dev["wb-mr6c_50/K1"] = false; // 370 Свет терраса бани
        }
    }
});

// ==============================================
// Выключатель у лестницы первого этажа
// ==============================================

// Одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_103/Input 1 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L01/K2"] = !dev["L01/K2"]; // Общее освещение в гостиной
        }
    }
});

// ==============================================
// Двухклавишный выключатель у дивана
// ==============================================

// Левая клавиша, одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_103/Input 2 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L02/K1"] = !dev["L02/K1"]; // Свет бра над диваном
        }
    }
});

// Правая клавиша (wb-mcm8_103/Input 3) управляет подсветкой карнизов 331 (wb-led_40/CCT1) в отдельном скрипте


// ==============================================
// Выключатель у тумбы у окна в спальне
// ==============================================

// Одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_103/Input 4 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L06/K1"] = !dev["L06/K1"]; // Общее освещение в спальне
        }
    }
});


// ==============================================
// Выключатель у выхода на балкон в спальне
// ==============================================

// Одинарное нажатие
defineRule({
    whenChanged: "wb-mcm8_103/Input 5 Single Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["wb-mr6c_25/K1"] = true; // 351 Ландшафтное освещение
            dev["wb-mr6c_25/K2"] = true; // 352 Столбы на парковку
            dev["wb-mr6c_25/K3"] = true; // 353 Столбы на дорогу
            dev["wb-mr6c_35/K1"] = true; // 354 Свет костровище
            dev["wb-mr6c_50/K1"] = true; // 370 Свет терраса бани
        }
    }
});

// Двойное нажатие
defineRule({
    whenChanged: "wb-mcm8_103/Input 5 Double Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K2"] = !dev["L04/K2"]; // 313 Неоновая подсветка
        }
    }
});

// Длительное нажатие выключает наружное освещение, кроме 1-го этажа
defineRule({
    whenChanged: "wb-mcm8_103/Input 5 Long Press Counter",
    then: function (newValue, devName, cellName) {
        if (newValue) {
            dev["L04/K2"] = false;        // 313 Неоновая подсветка
            dev["wb-mr6c_25/K1"] = false;  // 351 Ландшафтное освещение
            dev["wb-mr6c_25/K2"] = false; // 352 Столбы на парковку
            dev["wb-mr6c_25/K3"] = false; // 353 Столбы на дорогу
            dev["wb-mr6c_35/K1"] = false; // 354 Свет костровище
            dev["wb-mr6c_50/K1"] = false; // 370 Свет терраса бани
        }
    }
});