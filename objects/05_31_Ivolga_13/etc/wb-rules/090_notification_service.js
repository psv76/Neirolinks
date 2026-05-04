var System = require("system");

function setCell(cell, value)
{
    if (dev["notification_service/" + cell] !== value)
        dev["notification_service/" + cell] = value;
}

function setStatus(eventText, statusText)
{
    setCell("last_event", eventText);
    setCell("status_text", statusText);
}

defineVirtualDevice("notification_service", {
    title: "Сервис уведомлений",
    cells: {
        test_sms_me: { type: "pushbutton", title: "Тест SMS на сервисный номер" },
        test_sms_all: { type: "pushbutton", title: "Тест SMS на все номера" },
        last_event: { type: "text", title: "Последнее событие", value: "", readonly: true },
        status_text: { type: "text", title: "Состояние уведомлений", value: "Готов", readonly: true }
    }
});

defineRule("notification_service_test_sms_me", {
    whenChanged: "notification_service/test_sms_me",
    then: function (newValue) {
        if (!newValue)
            return;
        var msg = System.buildMessage({ buildingName: "Котельная", eventText: "ИНФО: Тест сервиса уведомлений", detailsText: "Отправка только на сервисный номер." });
        Notify.sendSMS("+79193691755", msg);
        setStatus("test_sms_me", "Отправлен тест на сервисный номер");
    }
});

defineRule("notification_service_test_sms_all", {
    whenChanged: "notification_service/test_sms_all",
    then: function (newValue) {
        if (!newValue)
            return;
        System.sendInfo("Котельная", "Тест сервиса уведомлений", "Отправка на все номера из списка.", "");
        setStatus("test_sms_all", "Отправлен тест на все номера");
    }
});
