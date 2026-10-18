info = {
    name: "414 — Push-уведомления о подпитке отопления",
    description: "Уведомления о работе, блокировках и восстановлении автоматической подпитки отопления",
    version: "1.1",
    author: "NEIROLINKS",
    onStart: true,
    sourceServices: [HS.Switch, HS.C_Option],
    sourceCharacteristics: [HC.On, HC.C_String],
    variables: {
        last: {}
    },
    options: {}
};

function trigger(source, value, variables, options, context) {
    if (!source) return;

    var accessory = source.getAccessory();
    if (!accessory) return;

    // Обрабатываем только рабочее устройство подпитки отопления.
    if (String(accessory.getSerial()) !== "lastochka_pressure_makeup")
        return;

    var service = source.getService();
    if (!service) return;

    var name = String(service.getName());
    var raw = value === null || value === undefined
        ? "" : String(value);

    var state = raw;
    var message = "";

    // Разрешение автоматической подпитки.
    if (name === "Автоподпитка") {
        if (raw === "true" || raw === "1")
            state = "on";
        else if (raw === "false" || raw === "0")
            state = "off";
        else
            return;
    }

    // Определяем активную работу и успешное завершение цикла.
    else if (name === "Состояние") {
        if (raw.indexOf("Подпитка: клапан включён") === 0 ||
            raw.indexOf("Подпитка: клапан выключен") === 0)
            state = "active";
        else if (raw.indexOf("Подпитка завершена;") === 0)
            state = "complete";
        else
            state = "idle";
    }

    // Остальные контролируемые характеристики.
    else if (name !== "Аварийная блокировка" &&
             name !== "Датчик давления" &&
             name !== "Низкое давление" &&
             name !== "Авторежим WB")
        return;

    // Независимая история для каждого сервиса.
    // Также корректно обрабатываем старое значение last,
    // если оно осталось от предыдущей версии сценария.
    if (!variables.last ||
        typeof variables.last !== "object" ||
        Array.isArray(variables.last)) {
        variables.last = {};
    }

    var previous = variables.last[name] || "";
    variables.last[name] = state;

    // Не отправляем стартовые и повторные уведомления.
    if (!previous || previous === state)
        return;

    if (name === "Автоподпитка") {
        if (state === "off")
            message = "Автоматическая подпитка отопления отключена.";
        else if (state === "on")
            message = "Автоматическая подпитка отопления разрешена.";
    }

    else if (name === "Состояние") {
        if (state === "active" && previous !== "active")
            message = "Началась автоматическая подпитка отопления.";
        else if (state === "complete" && previous !== "complete")
            message = "Автоматическая подпитка отопления завершена. Давление восстановлено.";
    }

    else if (name === "Аварийная блокировка") {
        if (state === "Авария")
            message = "Автоматическая подпитка отопления заблокирована. Проверьте причину аварии.";
        else if (state === "Нет блокировки" && previous === "Авария")
            message = "Аварийная блокировка автоматической подпитки отопления снята.";
    }

    else if (name === "Авторежим WB") {
        if (state === "Выключен в WB")
            message = "Автоматическая подпитка отопления: авторежим отключён.";
        else if (state === "Разрешён инженером" &&
                 previous === "Выключен в WB")
            message = "Автоматическая подпитка отопления: авторежим восстановлен.";
    }

    else if (name === "Датчик давления") {
        if (state === "Ошибка датчика — давлению не доверять")
            message = "Ошибка датчика давления отопления. Автоматическая подпитка недоступна.";
        else if (state === "Ошибки датчика нет" &&
                 previous === "Ошибка датчика — давлению не доверять")
            message = "Датчик давления отопления восстановлен.";
    }

    else if (name === "Низкое давление") {
        if (state === "Низкое давление")
            message = "Давление отопления ниже аварийного уровня. Проверьте систему.";
        else if (state === "Нет сигнала низкого давления" &&
                 previous === "Низкое давление")
            message = "Аварийно низкое давление отопления устранено.";
    }

    // Рассылка всем клиентам всех доступных служб уведомлений.
    if (message)
        Notify.text(message).send();
}
