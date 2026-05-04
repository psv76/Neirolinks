/*********************************************************************
 01_power_monitor.js
 Контроль питания ИБП
*********************************************************************/

var System = require("system");
var SYS = System.SYS;
var safeLog = System.safeLog;
var sendAlert = System.sendAlert;
var sendRestore = System.sendRestore;
var sendInfo = System.sendInfo;

var UPS1 = {
    name: "UPS1",

    /* канал контроля сети */
    powerInput: "ups1/power",

    /* защита от дребезга сети */
    powerFailDelay: 10,

    powerLost: false,
    timer: null
};


/*********************************************************************
 ПОТЕРЯ СЕТИ
*********************************************************************/

function handlePowerLost()
{
    if (UPS1.powerLost)
        return;

    UPS1.powerLost = true;

    sys.sendAlert(
        "Котельная",
        "Пропало питание " + UPS1.name,
        "ИБП перешёл на работу от аккумулятора.\nАвтономность ИБП ограничена.",
        "Проверьте вводное питание котельной или автомат питания ИБП."
    );
}


/*********************************************************************
 ВОССТАНОВЛЕНИЕ СЕТИ
*********************************************************************/

function handlePowerRestore()
{
    if (!UPS1.powerLost)
        return;

    UPS1.powerLost = false;

    sys.sendRestore(
        "Котельная",
        "Питание " + UPS1.name + " восстановлено",
        "ИБП вернулся на питание от сети."
    );
}


/*********************************************************************
 ОБРАБОТКА СОБЫТИЙ
*********************************************************************/

defineRule("ups1_power_monitor", {
    whenChanged: UPS1.powerInput,

    then: function(newValue)
    {
        /* сеть есть */
        if (newValue)
        {
            if (UPS1.timer)
            {
                clearTimeout(UPS1.timer);
                UPS1.timer = null;
            }

            handlePowerRestore();
            return;
        }

        /* сеть пропала */
        if (UPS1.timer)
            return;

        UPS1.timer = setTimeout(function()
        {
            UPS1.timer = null;

            if (!dev[UPS1.powerInput])
                handlePowerLost();

        }, UPS1.powerFailDelay * 1000);
    }
});