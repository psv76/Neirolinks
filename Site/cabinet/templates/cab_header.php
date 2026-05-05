<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title><?= htmlspecialchars($pageTitle ?? 'Личный кабинет') ?> | NEIROLINKS</title>
<link rel="icon" href="/icon-32.png">
<link rel="stylesheet" href="/cabinet/assets/css/cabinet.css">
</head>
<body>
<div class="container">
    <header class="header">
        <div class="header-brand">
            <img src="/logo.png" alt="NEIROLINKS Motion" class="logo" onerror="this.style.display='none'">
            <div class="header-text">
                <span class="header-title">NEIROLINKS Motion |</span>
                <span class="header-subtitle" style="font-size: 1.2rem;">Личный кабинет</span>
            </div>
        </div>
        <div class="header-info">
            <div>
                <b>👤 <?= htmlspecialchars($user['company'] ?? 'Пользователь') ?></b>
                <span style="background:#e0e7ff;color:#3730a3;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:6px;">
                    <?= htmlspecialchars($user['role'] === 'admin' ? 'Админ' : ($user['role'] === 'dealer' ? 'Дилер' : 'Агент')) ?>
                </span>
            </div>
            <div>ООО «Нейролинкс» | ИНН <?= htmlspecialchars($user['inn'] ?? '6658578360') ?></div>
            <div>📍 г. Екатеринбург, ул. Кондратьева 2а/2</div>
            <div>📞 <?= htmlspecialchars($user['phone'] ?? '+7 (343) 382-92-43') ?> | 📧 <?= htmlspecialchars($user['email'] ?? 'neirolinks@yandex.ru') ?></div>
            <div style="margin-top:8px;">
                <a href="/index.php" style="color:#3b82f6;text-decoration:none;font-weight:500;font-size:0.85rem;margin-right:15px;">🌐 Портал</a>
                <a href="?page=orders" style="color:<?= $currentPage==='orders'?'#3b82f6':'#64748b' ?>;text-decoration:none;font-weight:500;font-size:0.85rem;margin-right:15px;">📦 Заказы</a>
                <a href="?page=contacts" style="color:<?= $currentPage==='contacts'?'#3b82f6':'#64748b' ?>;text-decoration:none;font-weight:500;font-size:0.85rem;margin-right:15px;">📞 Контакты</a>
                <?php if ($user['role'] === 'admin'): ?>
                <a href="/admin/" style="color:#dc3545;text-decoration:none;font-weight:500;font-size:0.85rem;margin-right:15px;">🛡️ Админка</a>
                <?php endif; ?>
                <a href="?logout=1" style="color:#ef4444;text-decoration:none;font-weight:500;font-size:0.85rem;">🚪 Выйти</a>
            </div>
        </div>
    </header>