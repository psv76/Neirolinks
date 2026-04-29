<?php
if (session_status() === PHP_SESSION_NONE) {
    session_start();
}

require __DIR__ . '/../config/db.php';
require __DIR__ . '/../includes/auth_helper.php';

$error = '';
$success = '';

function post_value(string $key): string
{
    return isset($_POST[$key]) ? trim((string) $_POST[$key]) : '';
}

function normalize_spaces(?string $value): string
{
    $value = trim((string) $value);
    return preg_replace('/\s+/u', ' ', $value);
}

function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $role = post_value('role');
    $email = post_value('email');
    $phone = post_value('phone');
    $password = isset($_POST['password']) ? (string) $_POST['password'] : '';
    $confirm = isset($_POST['confirm_password']) ? (string) $_POST['confirm_password'] : '';
    $agree = isset($_POST['agree']);

    $company_name = '';
    $full_name = '';
    $contact = '';

    if ($role === 'dealer') {
        $company_name = normalize_spaces(post_value('company_name'));
        $contact = normalize_spaces(post_value('contact'));
    } elseif ($role === 'agent') {
        $full_name = normalize_spaces(post_value('full_name'));
    }

    $fioRegex = '/^[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}$/u';
    $ipRegex = '/^ИП\s+[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}$/u';
    $oooRegex = '/^ООО\s+"[А-ЯЁ][А-ЯЁа-яё0-9\s\-]+"$/u';
    $emailRegex = '/^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/';
    $phoneRegex = '/^\+7\s\(\d{3}\)\s\d{3}-\d{2}-\d{2}$/';

    if ($role !== 'dealer' && $role !== 'agent') {
        $error = '⚠️ Выберите статус партнера';
    } elseif ($email === '' || $phone === '' || $password === '' || $confirm === '') {
        $error = '⚠️ Заполните все обязательные поля';
    } elseif (!$agree) {
        $error = '⚠️ Необходимо дать согласие на обработку данных';
    } elseif ($role === 'dealer' && $company_name === '') {
        $error = '⚠️ Для дилера обязательно название компании';
    } elseif ($role === 'dealer' && $contact === '') {
        $error = '⚠️ Для дилера обязательно контактное лицо';
    } elseif ($role === 'dealer' && !preg_match($fioRegex, $contact)) {
        $error = '⚠️ Контактное лицо: Фамилия Имя Отчество (каждое слово с заглавной буквы).';
    } elseif ($role === 'dealer' && !preg_match($ipRegex, $company_name) && !preg_match($oooRegex, $company_name)) {
        $error = '⚠️ Компания: ИП Фамилия Имя Отчество или ООО "Название"';
    } elseif ($role === 'agent' && $full_name === '') {
        $error = '⚠️ Для агента обязательно ФИО';
    } elseif ($role === 'agent' && !preg_match($fioRegex, $full_name)) {
        $error = '⚠️ ФИО: Фамилия Имя Отчество (каждое слово с заглавной буквы).';
    } elseif (!preg_match($emailRegex, $email)) {
        $error = '⚠️ Email должен быть на английском';
    } elseif (!preg_match($phoneRegex, $phone)) {
        $error = '⚠️ Телефон: +7 (999) 123-45-67';
    } elseif ($password !== $confirm) {
        $error = '❌ Пароли не совпадают';
    } elseif (strlen($password) < 6) {
        $error = '❌ Пароль минимум 6 символов';
    }

    if ($error === '') {
        try {
            $stmt = $pdo->prepare('SELECT id FROM users WHERE email = ? LIMIT 1');
            $stmt->execute([$email]);

            if ($stmt->fetch()) {
                $error = '⚠️ Этот Email уже зарегистрирован. <a href="/auth/login.php" style="color:#b91c1c; text-decoration:underline; font-weight:500;">Войти</a>';
            } else {
                $hash = password_hash($password, PASSWORD_DEFAULT);
                $token = bin2hex(random_bytes(32));

                $company_value = $role === 'agent' ? $full_name : $company_name;
                $contact_value = $role === 'agent' ? $full_name : $contact;

                $stmt = $pdo->prepare(
                    'INSERT INTO users (company, role, contact_person, email, phone, password_hash, verification_token, is_verified)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 0)'
                );
                $stmt->execute([$company_value, $role, $contact_value, $email, $phone, $hash, $token]);

                $host = preg_replace('/[^a-zA-Z0-9.\-:]/', '', $_SERVER['HTTP_HOST'] ?? 'localhost');
                $host = $host !== '' ? $host : 'localhost';
                $mailDomain = preg_replace('/:\d+$/', '', $host);
                $protocol = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
                $link = $protocol . '://' . $host . '/auth/verify.php?token=' . urlencode($token);

                $subject = '=?UTF-8?B?' . base64_encode('Подтверждение регистрации NEIROLINKS') . '?=';
                $message = "Здравствуйте!\n\nДля активации аккаунта перейдите по ссылке:\n$link";
                $headers = "From: NEIROLINKS <noreply@{$mailDomain}>\r\n"
                    . "MIME-Version: 1.0\r\n"
                    . "Content-Type: text/plain; charset=UTF-8\r\n";

                @mail($email, $subject, $message, $headers);

                $success = '✅ Регистрация успешна! Ссылка отправлена на Email.';
                $_POST = [];
            }
        } catch (PDOException $e) {
            error_log('Registration DB error: ' . $e->getMessage());
            $error = '❌ Ошибка БД. Попробуйте позже.';
        } catch (Exception $e) {
            error_log('Registration error: ' . $e->getMessage());
            $error = '❌ Ошибка регистрации. Попробуйте позже.';
        }
    }
}
?>
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Регистрация | NEIROLINKS</title>
<link rel="stylesheet" href="/style.css">
<style>
.checkbox-group { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 1.2rem; }
.checkbox-group input { width: auto !important; margin-top: 3px; flex-shrink: 0; }
.checkbox-group label { font-weight: 400; font-size: 0.85rem; line-height: 1.4; cursor: pointer; }
.checkbox-group a { color: #3b82f6; text-decoration: underline; }
.form-group.hidden { display: none !important; }
.form-group.error input, .form-group.error select { border-color: #dc2626; background-color: #fef2f2; }
.form-group.valid input, .form-group.valid select { border-color: #10b981; }
.error-hint { color: #dc2626; font-size: 0.75rem; margin-top: 4px; display: none; }
.form-group.error .error-hint { display: block; }
.password-wrapper { position: relative; display: flex; align-items: center; }
.password-wrapper input { padding-right: 40px !important; }
.toggle-password { position: absolute; right: 12px; cursor: pointer; user-select: none; opacity: 0.6; }
.toggle-password:hover { opacity: 1; }
</style>
</head>
<body>
<div class="auth-wrapper">
<div class="card">
<div class="login-header">
    <img src="/logo.png" alt="NEIROLINKS" class="login-logo" onerror="this.style.display='none'">
    <div class="login-title-block">
        <h2>NEIROLINKS Motion</h2>
        <p class="login-subtitle">регистрация партнёра</p>
    </div>
</div>

<?php if ($error): ?>
    <div class="error"><?= $error ?></div>
<?php endif; ?>

<?php if ($success): ?>
    <div class="success" style="background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; padding: 12px; border-radius: 8px; margin-bottom: 1rem;">
        <?= e($success) ?>
    </div>
<?php else: ?>
<form method="POST" id="registrationForm" novalidate>
    <div class="form-group">
        <label>Статус партнера *</label>
        <select name="role" id="role" required>
            <option value="" disabled <?= !isset($_POST['role']) ? 'selected' : '' ?>>Выберите статус</option>
            <option value="dealer" <?= (isset($_POST['role']) && $_POST['role'] === 'dealer') ? 'selected' : '' ?>>Дилер</option>
            <option value="agent" <?= (isset($_POST['role']) && $_POST['role'] === 'agent') ? 'selected' : '' ?>>Агент</option>
        </select>
        <div class="error-hint">⚠️ Выберите статус партнера</div>
    </div>

    <div class="form-group hidden" id="companyGroup">
        <label>Название компании *</label>
        <input type="text" name="company_name" id="company_name" placeholder='ООО "Название" или ИП Фамилия Имя Отчество' value="<?= e(isset($_POST['company_name']) ? (string) $_POST['company_name'] : '') ?>" autocomplete="off">
        <div class="error-hint">⚠️ Пример: ИП Иванов Иван Иванович или ООО "Ромашка"</div>
    </div>

    <div class="form-group hidden" id="contactGroup">
        <label>Контактное лицо *</label>
        <input type="text" name="contact" id="contact" placeholder="Фамилия Имя Отчество" value="<?= e(isset($_POST['contact']) ? (string) $_POST['contact'] : '') ?>" autocomplete="off">
        <div class="error-hint">⚠️ Фамилия Имя Отчество (3 слова, каждое с заглавной буквы)</div>
    </div>

    <div class="form-group hidden" id="fullNameGroup">
        <label>ФИО *</label>
        <input type="text" name="full_name" id="full_name" placeholder="Фамилия Имя Отчество" value="<?= e(isset($_POST['full_name']) ? (string) $_POST['full_name'] : '') ?>" autocomplete="off">
        <div class="error-hint">⚠️ Фамилия Имя Отчество (3 слова, каждое с заглавной буквы)</div>
    </div>

    <div class="form-group">
        <label>Телефон *</label>
        <input type="tel" name="phone" id="phone" required placeholder="+7 (999) 123-45-67" value="<?= e(isset($_POST['phone']) ? (string) $_POST['phone'] : '') ?>">
        <div class="error-hint">⚠️ Формат: +7 (999) 123-45-67</div>
    </div>

    <div class="form-group">
        <label>Email *</label>
        <input type="text" name="email" id="email" required placeholder="name@company.ru" value="<?= e(isset($_POST['email']) ? (string) $_POST['email'] : '') ?>">
        <div class="error-hint">⚠️ Email должен быть на английском</div>
    </div>

    <div class="form-group">
        <label>Пароль *</label>
        <div class="password-wrapper">
            <input type="password" name="password" id="password" required placeholder="••••••••">
            <span class="toggle-password" onclick="togglePassword(this)">👁️</span>
        </div>
        <div class="error-hint">⚠️ Минимум 6 символов</div>
    </div>

    <div class="form-group">
        <label>Подтвердите пароль *</label>
        <div class="password-wrapper">
            <input type="password" name="confirm_password" id="confirm_password" required placeholder="••••••••">
            <span class="toggle-password" onclick="togglePassword(this)">👁️</span>
        </div>
        <div class="error-hint">⚠️ Пароли должны совпадать</div>
    </div>

    <div class="checkbox-group">
        <input type="checkbox" name="agree" id="agree" required <?= isset($_POST['agree']) ? 'checked' : '' ?>>
        <label for="agree">Я согласен на обработку <a href="/privacy" target="_blank">персональных данных</a></label>
    </div>

    <button type="submit">Зарегистрироваться</button>
</form>
<?php endif; ?>

<div class="links">
    Уже есть аккаунт? <a href="/auth/login.php">Войти в систему</a>
</div>
</div>
</div>

<script>
const fioRegex = /^[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}$/u;
const ipRegex = /^ИП\s+[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}$/u;
const oooRegex = /^ООО\s+"[А-ЯЁ][А-ЯЁа-яё0-9\s-]+"$/u;
const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
const phoneRegex = /^\+7\s\(\d{3}\)\s\d{3}-\d{2}-\d{2}$/;

function togglePassword(btn) {
    const input = btn.previousElementSibling;
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈';
    } else {
        input.type = 'password';
        btn.textContent = '👁️';
    }
}

function setState(field, isValid, showError) {
    const group = field.closest('.form-group');
    if (!group) return isValid;

    group.classList.toggle('valid', isValid && field.value.trim() !== '');
    group.classList.toggle('error', showError && !isValid);

    return isValid;
}

function validateRequired(field, showError = true) {
    return setState(field, field.value.trim() !== '', showError);
}

function validatePattern(field, regex, showError = true) {
    const value = field.value.trim();
    return setState(field, value !== '' && regex.test(value), showError);
}

function validateCompany(showError = true) {
    const field = document.getElementById('company_name');
    const value = field.value.trim();
    return setState(field, value !== '' && (ipRegex.test(value) || oooRegex.test(value)), showError);
}

function validateConfirmPassword(showError = true) {
    const password = document.getElementById('password').value;
    const confirm = document.getElementById('confirm_password');
    return setState(confirm, confirm.value !== '' && confirm.value === password, showError);
}

function toggleFields() {
    const role = document.getElementById('role').value;
    const isDealer = role === 'dealer';
    const isAgent = role === 'agent';

    document.getElementById('companyGroup').classList.toggle('hidden', !isDealer);
    document.getElementById('contactGroup').classList.toggle('hidden', !isDealer);
    document.getElementById('fullNameGroup').classList.toggle('hidden', !isAgent);

    document.getElementById('company_name').required = isDealer;
    document.getElementById('contact').required = isDealer;
    document.getElementById('full_name').required = isAgent;
}

function validateAll(showErrors = true) {
    const role = document.getElementById('role');
    const email = document.getElementById('email');
    const phone = document.getElementById('phone');
    const password = document.getElementById('password');
    const agree = document.getElementById('agree');
    let valid = true;

    valid = setState(role, role.value === 'dealer' || role.value === 'agent', showErrors) && valid;

    if (role.value === 'dealer') {
        valid = validateCompany(showErrors) && valid;
        valid = validatePattern(document.getElementById('contact'), fioRegex, showErrors) && valid;
    }

    if (role.value === 'agent') {
        valid = validatePattern(document.getElementById('full_name'), fioRegex, showErrors) && valid;
    }

    valid = validatePattern(email, emailRegex, showErrors) && valid;
    valid = validatePattern(phone, phoneRegex, showErrors) && valid;
    valid = setState(password, password.value.length >= 6, showErrors) && valid;
    valid = validateConfirmPassword(showErrors) && valid;

    if (!agree.checked) {
        valid = false;
    }

    return valid;
}

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('registrationForm');
    if (!form) return;

    const role = document.getElementById('role');
    const email = document.getElementById('email');
    const phone = document.getElementById('phone');
    const password = document.getElementById('password');
    const confirm = document.getElementById('confirm_password');
    const company = document.getElementById('company_name');
    const contact = document.getElementById('contact');
    const fullName = document.getElementById('full_name');

    toggleFields();

    role.addEventListener('change', function () {
        toggleFields();
        validateAll(false);
    });

    email.addEventListener('blur', function () { validatePattern(email, emailRegex); });
    phone.addEventListener('blur', function () { validatePattern(phone, phoneRegex); });
    company.addEventListener('blur', function () { validateCompany(); });
    contact.addEventListener('blur', function () { validatePattern(contact, fioRegex); });
    fullName.addEventListener('blur', function () { validatePattern(fullName, fioRegex); });
    password.addEventListener('blur', function () {
        setState(password, password.value.length >= 6, true);
        validateConfirmPassword(false);
    });
    confirm.addEventListener('blur', function () { validateConfirmPassword(); });

    phone.addEventListener('input', function (e) {
        let value = e.target.value.replace(/\D/g, '');
        if (value.length > 1 && (value[0] === '7' || value[0] === '8')) {
            value = value.substring(1);
        }

        let formatted = '+7';
        if (value.length > 0) formatted += ' (' + value.substring(0, 3);
        if (value.length >= 3) formatted += ') ' + value.substring(3, 6);
        if (value.length >= 6) formatted += '-' + value.substring(6, 8);
        if (value.length >= 8) formatted += '-' + value.substring(8, 10);

        e.target.value = formatted;
    });

    form.addEventListener('submit', function (e) {
        if (!validateAll(true)) {
            e.preventDefault();
        }
    });
});
</script>
</body>
</html>
