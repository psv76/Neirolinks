var System = require("system");

function setCell(cell, value)
{
    if (dev["notification_service/" + cell] !== value)
        dev["notification_service/" + cell] = value;
}

function setSendResult(eventName, success, details)
{
    setCell("last_event", eventName + ": " + details);
    setCell("status_text", success ? "Отправка выполнена" : "Ошибка отправки");
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
        var message;
        var success;

        if (!newValue)
            return;

        message = System.buildMessage({
            buildingName: "Котельная",
            eventText: "ИНФО: Тест сервиса уведомлений",
            detailsText: "Отправка только на сервисный номер."
        });

        success = System.sendSMSToPhone("+79193691755", message);
        setSendResult("test_sms_me", success, "Номер: +79193691755");
    }
});

defineRule("notification_service_test_sms_all", {
    whenChanged: "notification_service/test_sms_all",
    then: function (newValue) {
        var sent;

        if (!newValue)
            return;

        sent = System.sendInfo(
            "Котельная",
            "Тест сервиса уведомлений",
            "Отправка на все номера из списка.",
            ""
        );

        setSendResult("test_sms_all", sent > 0, "Отправлено: " + sent);
    }
});
