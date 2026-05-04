/*********************************************************************
 system.js_sms_safe.js
 Общие настройки объекта и сервис SMS
 Черновик для проверки в Codex.
 Совместимо с wb-rules (ES5)
*********************************************************************/

var SYS = {};

/*********************************************************************
 ОБЪЕКТ
*********************************************************************/

SYS.objectName = "Иволга 13";
SYS.defaultBuildingName = "Котельная";

/*********************************************************************
 SMS
*********************************************************************/

SYS.smsEnabled = true;

SYS.smsPhones = [
    "+79193691755",
    "+79089133378"
];

/*********************************************************************
 СЛУЖЕБНЫЕ ФУНКЦИИ
*********************************************************************/

function safeLog(message)
{
    try
    {
        log(String(message));
    }
    catch (e)
    {
    }
}

function isNonEmptyString(value)
{
    return value !== undefined &&
           value !== null &&
           String(value).replace(/^\s+|\s+$/g, "") !== "";
}

function normalizeText(value)
{
    if (value === undefined || value === null)
        return "";

    return String(value)
        .replace(/\r\n/g, "\n")
        .replace(/\r/g, "\n");
}

function trimText(value)
{
    return normalizeText(value).replace(/^\s+|\s+$/g, "");
}

function makeSmsSafe(text)
{
    var s = normalizeText(text);

    s = s.replace(/🏡/g, "");
    s = s.replace(/⚠️/g, "АВАРИЯ:");
    s = s.replace(/⚠/g, "АВАРИЯ:");
    s = s.replace(/✅/g, "ВОССТАНОВЛЕНО:");
    s = s.replace(/ℹ️/g, "ИНФО:");
    s = s.replace(/ℹ/g, "ИНФО:");

    return trimText(s);
}

function buildMessage(params)
{
    var buildingName;
    var eventText;
    var detailsText;
    var recommendationText;
    var lines;
    var message;

    params = params || {};

    buildingName = isNonEmptyString(params.buildingName) ? trimText(params.buildingName) : SYS.defaultBuildingName;
    eventText = trimText(params.eventText || params.text || "");
    detailsText = trimText(params.detailsText || params.details || "");
    recommendationText = trimText(params.recommendationText || params.recommendation || "");

    lines = [];

    if (isNonEmptyString(buildingName))
        lines.push(buildingName);

    if (isNonEmptyString(eventText))
    {
        if (lines.length > 0)
            lines.push("");

        lines.push(eventText);
    }

    if (isNonEmptyString(detailsText))
        lines.push(detailsText);

    if (isNonEmptyString(recommendationText))
        lines.push(recommendationText);

    message = lines.join("\n");

    return makeSmsSafe(message);
}

function sendSMSToPhone(phone, message)
{
    if (!SYS.smsEnabled)
    {
        safeLog("[system.js] SMS disabled");
        return false;
    }

    if (!isNonEmptyString(phone))
    {
        safeLog("[system.js] SMS phone is not configured");
        return false;
    }

    if (!isNonEmptyString(message))
    {
        safeLog("[system.js] Empty SMS message");
        return false;
    }

    try
    {
        safeLog("[system.js] Sending SMS to " + phone);
        Notify.sendSMS(String(phone), String(message));
        safeLog("[system.js] SMS send call done for " + phone);
        return true;
    }
    catch (e)
    {
        safeLog("[system.js] Notify.sendSMS() failed: " + e);
        return false;
    }
}

function sendSMS(message)
{
    var i;
    var sent;
    var phones;
    var phone;
    var smsText;

    if (!SYS.smsEnabled)
        return 0;

    phones = SYS.smsPhones || [];
    sent = 0;
    smsText = makeSmsSafe(message);

    if (!phones.length)
    {
        safeLog("[system.js] SMS phone list is empty");
        return 0;
    }

    for (i = 0; i < phones.length; i++)
    {
        phone = phones[i];

        if (sendSMSToPhone(phone, smsText))
            sent++;
    }

    return sent;
}

function sendMessage(params)
{
    var message;

    message = buildMessage(params);

    if (!isNonEmptyString(message))
    {
        safeLog("[system.js] Empty built message");
        return 0;
    }

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

/*********************************************************************
 EXPORTS
*********************************************************************/

exports.SYS = SYS;
exports.safeLog = safeLog;
exports.normalizeText = normalizeText;
exports.trimText = trimText;
exports.makeSmsSafe = makeSmsSafe;
exports.buildMessage = buildMessage;
exports.sendSMSToPhone = sendSMSToPhone;
exports.sendSMS = sendSMS;
exports.sendMessage = sendMessage;
exports.sendAlert = sendAlert;
exports.sendRestore = sendRestore;
exports.sendInfo = sendInfo;