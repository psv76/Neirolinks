var SYS = {};

SYS.defaultBuildingName = "Котельная";
SYS.smsEnabled = true;
SYS.smsPhones = [
    "+79193691755",
    "+79089133378"
];

function safeLog(message)
{
    try { log(String(message)); } catch (e) {}
}

function normalizeText(value)
{
    if (value === undefined || value === null)
        return "";
    return String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function trimText(value)
{
    return normalizeText(value).replace(/^\s+|\s+$/g, "");
}

function isNonEmptyString(value)
{
    return trimText(value) !== "";
}

function buildMessage(params)
{
    var buildingName;
    var eventText;
    var detailsText;
    var recommendationText;
    var lines = [];

    params = params || {};
    buildingName = isNonEmptyString(params.buildingName) ? trimText(params.buildingName) : SYS.defaultBuildingName;
    eventText = trimText(params.eventText || params.text || "");
    detailsText = trimText(params.detailsText || params.details || "");
    recommendationText = trimText(params.recommendationText || params.recommendation || "");

    if (isNonEmptyString(buildingName))
        lines.push(buildingName);
    if (isNonEmptyString(eventText))
    {
        lines.push("");
        lines.push(eventText);
    }
    if (isNonEmptyString(detailsText))
        lines.push(detailsText);
    if (isNonEmptyString(recommendationText))
        lines.push(recommendationText);

    return trimText(lines.join("\n"));
}

function sendSMSToPhone(phone, message)
{
    if (!SYS.smsEnabled)
    {
        safeLog("[system] SMS отключены");
        return false;
    }
    if (!isNonEmptyString(phone))
    {
        safeLog("[system] Пропуск пустого номера");
        return false;
    }
    if (!isNonEmptyString(message))
    {
        safeLog("[system] Пропуск пустого сообщения");
        return false;
    }

    safeLog("[system] Попытка отправки SMS на " + String(phone));
    try
    {
        safeLog("[system] Вызов Notify.sendSMS(" + String(phone) + ")");
        Notify.sendSMS(String(phone), String(message));
        return true;
    }
    catch (e)
    {
        safeLog("[system] Ошибка Notify.sendSMS: " + e);
        return false;
    }
}

function sendSMS(message)
{
    var i;
    var phones = SYS.smsPhones || [];
    var sent = 0;

    if (!isNonEmptyString(message))
    {
        safeLog("[system] Пустое SMS не отправлено");
        return 0;
    }

    for (i = 0; i < phones.length; i++)
    {
        if (sendSMSToPhone(phones[i], message))
            sent++;
    }
    return sent;
}

function sendMessage(params)
{
    var message = buildMessage(params);
    return sendSMS(message);
}

function sendAlert(buildingName, eventText, detailsText, recommendationText)
{
    return sendMessage({
        buildingName: buildingName,
        eventText: "АВАРИЯ: " + trimText(eventText || ""),
        detailsText: detailsText,
        recommendationText: recommendationText
    });
}

function sendRestore(buildingName, eventText, detailsText, recommendationText)
{
    return sendMessage({
        buildingName: buildingName,
        eventText: "ВОССТАНОВЛЕНО: " + trimText(eventText || ""),
        detailsText: detailsText,
        recommendationText: recommendationText
    });
}

function sendInfo(buildingName, eventText, detailsText, recommendationText)
{
    return sendMessage({
        buildingName: buildingName,
        eventText: "ИНФО: " + trimText(eventText || ""),
        detailsText: detailsText,
        recommendationText: recommendationText
    });
}

exports.SYS = SYS;
exports.safeLog = safeLog;
exports.normalizeText = normalizeText;
exports.trimText = trimText;
exports.buildMessage = buildMessage;
exports.sendSMS = sendSMS;
exports.sendMessage = sendMessage;
exports.sendAlert = sendAlert;
exports.sendRestore = sendRestore;
exports.sendInfo = sendInfo;
