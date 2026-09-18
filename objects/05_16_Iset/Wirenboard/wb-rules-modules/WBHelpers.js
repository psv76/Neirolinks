/*
 * WBHelpers.js
 * Объект: 05 16 Исеть
 *
 * Общий инфраструктурный модуль уведомлений.
 * Формирует эксплуатационные сообщения и отправляет Email
 * через штатный Notify.sendEmail().
 *
 * ВАЖНО:
 * Notify.sendEmail() не предоставляет callback о результате SMTP-доставки.
 * Поэтому модуль подтверждает только передачу команды на отправку в wb-rules.
 * Фактическую SMTP-отправку подтверждает системный журнал ssmtp.
 *
 * Физическими каналами не управляет.
 */

var OBJECT_NAME = "05 16 Исеть";
var BUILDING_NAME = "Котельная";
var EMAIL_PREFIX = "[05 16 Исеть] ";

/*
 * Сейчас подтверждён один рабочий получатель.
 * Адрес заказчика добавляется отдельной строкой после его получения.
 */
var EMAIL_RECIPIENTS = [
  "psv76@yandex.ru"
];

function toText(value) {
  if (value === undefined || value === null) return "";
  return String(value);
}

function trimText(value) {
  return toText(value).replace(/^\s+|\s+$/g, "");
}

function isNonEmpty(value) {
  return trimText(value) !== "";
}

function round1(value) {
  var n = Number(value);
  if (isNaN(n)) return null;
  return Math.round(n * 10) / 10;
}

function logInfo(message) {
  try {
    log.info(String(message));
    return;
  } catch (e1) {}

  try {
    log(String(message));
  } catch (e2) {}
}

function logWarning(message) {
  try {
    log.warning(String(message));
    return;
  } catch (e1) {}

  logInfo(message);
}

function logError(message) {
  try {
    log.error(String(message));
    return;
  } catch (e1) {}

  logInfo(message);
}

function buildBody(eventText, detailsText, recommendationText) {
  var lines = [];

  lines.push(OBJECT_NAME);
  lines.push(BUILDING_NAME);

  if (isNonEmpty(eventText)) {
    lines.push("");
    lines.push(trimText(eventText));
  }

  if (isNonEmpty(detailsText)) {
    lines.push("");
    lines.push(trimText(detailsText));
  }

  if (isNonEmpty(recommendationText)) {
    lines.push("");
    lines.push(trimText(recommendationText));
  }

  return lines.join("\n");
}

function recipientCount() {
  return EMAIL_RECIPIENTS.length;
}

function recipientListText() {
  return EMAIL_RECIPIENTS.join(", ");
}

function sendEmailTo(address, subject, body) {
  var fullSubject = EMAIL_PREFIX + trimText(subject);
  var text = trimText(body);

  if (!isNonEmpty(address)) {
    logError(
      "[уведомления][email][send]; ОШИБКА=Пустой адрес получателя; " +
      "тема=" + fullSubject
    );
    return false;
  }

  try {
    Notify.sendEmail(
      String(address),
      fullSubject,
      text
    );

    logInfo(
      "[уведомления][email][send]; КОМАНДА=Передана команда отправки email; " +
      "кому=" + address + "; тема=" + fullSubject
    );

    return true;
  } catch (e) {
    logError(
      "[уведомления][email][send]; ОШИБКА=Исключение Notify.sendEmail; " +
      "кому=" + address + "; тема=" + fullSubject + "; причина=" +
      String(e.message || e)
    );

    return false;
  }
}

function sendEmail(subject, body) {
  var subjectText = trimText(subject);
  var bodyText = trimText(body);
  var queuedCount = 0;
  var i;

  if (!isNonEmpty(subjectText)) {
    logError("[уведомления][email][send]; ОШИБКА=Не задана тема письма");
    return 0;
  }

  if (!isNonEmpty(bodyText)) {
    logError("[уведомления][email][send]; ОШИБКА=Пустое письмо");
    return 0;
  }

  if (!EMAIL_RECIPIENTS.length) {
    logError("[уведомления][email][send]; АВАРИЯ=Нет настроенных получателей Email");
    return 0;
  }

  logInfo(
    "[уведомления][email][send]; КОМАНДА=Отправить email; " +
    "получателей=" + EMAIL_RECIPIENTS.length + "; тема=" + EMAIL_PREFIX + subjectText
  );

  for (i = 0; i < EMAIL_RECIPIENTS.length; i++) {
    if (sendEmailTo(EMAIL_RECIPIENTS[i], subjectText, bodyText)) {
      queuedCount += 1;
    }
  }

  return queuedCount;
}

function sendAlert(subject, eventText, detailsText, recommendationText) {
  return sendEmail(
    "АВАРИЯ — " + trimText(subject),
    buildBody(
      "⚠️ " + trimText(eventText),
      detailsText,
      recommendationText
    )
  );
}

function sendRestore(subject, eventText, detailsText, recommendationText) {
  return sendEmail(
    "ВОССТАНОВЛЕНО — " + trimText(subject),
    buildBody(
      "✅ " + trimText(eventText),
      detailsText,
      recommendationText
    )
  );
}

function sendInfo(subject, eventText, detailsText, recommendationText) {
  return sendEmail(
    trimText(subject),
    buildBody(eventText, detailsText, recommendationText)
  );
}

exports.OBJECT_NAME = OBJECT_NAME;
exports.BUILDING_NAME = BUILDING_NAME;
exports.EMAIL_RECIPIENTS = EMAIL_RECIPIENTS;
exports.EMAIL_PREFIX = EMAIL_PREFIX;
exports.trimText = trimText;
exports.isNonEmpty = isNonEmpty;
exports.round1 = round1;
exports.logInfo = logInfo;
exports.logWarning = logWarning;
exports.logError = logError;
exports.buildBody = buildBody;
exports.recipientCount = recipientCount;
exports.recipientListText = recipientListText;
exports.sendEmail = sendEmail;
exports.sendAlert = sendAlert;
exports.sendRestore = sendRestore;
exports.sendInfo = sendInfo;
