<?php
// 🔌 Подключение ядра и сессии
if (session_status() === PHP_SESSION_NONE) session_start();

// ИСПРАВЛЕНО: Поднимаемся на уровень выше (../), так как мы находимся в папке /cabinet/
require __DIR__ . '/../config/db.php';
require_once __DIR__ . '/../includes/auth_helper.php';

// 🛡️ Проверка доступа
if (!isset($_SESSION['user_id'])) {
    header('Location: /auth/login.php');
    exit;
}

// 🗑️ Обработка выхода
if (isset($_GET['logout'])) {
    session_destroy();
    header('Location: /auth/login.php');
    exit;
}

// 👤 Загрузка данных пользователя
$stmt = $pdo->prepare("SELECT * FROM users WHERE id = ?");
$stmt->execute([$_SESSION['user_id']]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$user) { session_destroy(); header('Location: /auth/login.php'); exit; }

$is_pending_approval = ($user['is_verified'] == 1 && empty($user['is_admin_approved']));
$currentPage = isset($_GET['page']) ? trim($_GET['page']) : 'orders';

// 📦 Справочники статусов
$statusMap = [
    'new' => '🆕 Новый', 'processing' => '⏳ В обработке', 'confirmed' => '✅ Подтверждён',
    'shipped' => '🚚 Отправлен', 'completed' => '📦 Выполнен', 'cancelled' => '❌ Отменён'
];
$measurementsMap = ['required' => '📐 Требуется замер', 'provided' => '✅ Замер предоставлен', 'matches' => '✔️ Соответствует сп-ции'];
$installationMap = ['required' => '🔧 Требуется', 'not_required' => '❌ Не требуется'];

// ==========================================
// 🔄 AJAX ОБРАБОТЧИКИ
// ==========================================
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // 💾 Сохранение заказа
    if (isset($_POST['save_and_exit'])) {
        $oid = (int)$_POST['view_order_id'];
        $chkStmt = $pdo->prepare("SELECT id FROM orders WHERE id = ? AND user_id = ?");
        $chkStmt->execute([$oid, $_SESSION['user_id']]);
        if ($chkStmt->fetch()) {
            $updStmt = $pdo->prepare("UPDATE orders SET status = COALESCE(NULLIF(?,''), status), comment = ?, measurements = COALESCE(NULLIF(?,''), measurements), installation = COALESCE(NULLIF(?,''), installation) WHERE id = ?");
            $updStmt->execute([
                $_POST['order_status'] ?? '', trim($_POST['comment']),
                $_POST['order_measurements'] ?? '', $_POST['order_installation'] ?? '', $oid
            ]);
            // УБРАНО: $_SESSION['success_msg'] = "✅ Изменения успешно сохранены!";
        }
        // ИСПРАВЛЕНО: Перенаправляем к списку заказов
        header("Location: ?page=orders");
        exit;
    }

    // JSON-обработчики
    if (isset($_POST['check_address_request']) || isset($_POST['submit_address_request'])) {
        if (ob_get_length()) ob_clean();
        header('Content-Type: application/json; charset=utf-8');

        if (isset($_POST['check_address_request'])) {
            $orderId = (int)$_POST['order_id'];
            $type = trim($_POST['type']);
            $chkStmt = $pdo->prepare("SELECT measurements, installation FROM orders WHERE id = ? AND user_id = ?");
            $chkStmt->execute([$orderId, $_SESSION['user_id']]);
            $order = $chkStmt->fetch();
            
            if ($order) {
                $currentStatus = ($type === 'measurements') ? ($order['measurements'] ?? '') : ($order['installation'] ?? '');
                $checkStmt = $pdo->prepare("SELECT id, city, street, house, entrance, floor, apartment, contact_person, phone, comment FROM address_requests WHERE order_id = ? AND request_type = ? LIMIT 1");
                $checkStmt->execute([$orderId, $type]);
                $existing = $checkStmt->fetch(PDO::FETCH_ASSOC);
                echo json_encode(['success' => true, 'exists' => (bool)$existing, 'data' => $existing ?: null, 'currentStatus' => $currentStatus], JSON_UNESCAPED_UNICODE);
            } else { 
                echo json_encode(['success'=>false,'message'=>'Заказ не найден'], JSON_UNESCAPED_UNICODE); 
            }
            exit;
        }

        if (isset($_POST['submit_address_request'])) {
            $orderId = (int)$_POST['order_id'];
            $type = trim($_POST['type']);
            $editId = (int)($_POST['request_id'] ?? 0);
            $fields = ['city','street','house','entrance','floor','apartment','contact_person','phone','address_comment'];
            $data = [];
            foreach($fields as $f) $data[$f] = trim($_POST[$f] ?? '');

            $chkStmt = $pdo->prepare("SELECT id FROM orders WHERE id = ? AND user_id = ?");
            $chkStmt->execute([$orderId, $_SESSION['user_id']]);
            if (!$chkStmt->fetch()) { 
                echo json_encode(['success'=>false,'message'=>'Заказ не найден'], JSON_UNESCAPED_UNICODE); 
                exit; 
            }

            try {
                if ($editId > 0) {
                    $pdo->prepare("UPDATE address_requests SET city=?,street=?,house=?,entrance=?,floor=?,apartment=?,contact_person=?,phone=?,comment=?,status='new',updated_at=NOW() WHERE id=? AND order_id=? AND user_id=?")
                        ->execute([$data['city'],$data['street'],$data['house'],$data['entrance'],$data['floor'],$data['apartment'],$data['contact_person'],$data['phone'],$data['address_comment'],$editId,$orderId,$_SESSION['user_id']]);
                } else {
                    $existsStmt = $pdo->prepare("SELECT id FROM address_requests WHERE order_id=? AND request_type=?");
                    $existsStmt->execute([$orderId, $type]);
                    if ($existsStmt->fetch()) {
                        $pdo->prepare("UPDATE address_requests SET city=?,street=?,house=?,entrance=?,floor=?,apartment=?,contact_person=?,phone=?,comment=?,status='new',updated_at=NOW() WHERE order_id=? AND request_type=?")
                            ->execute([$data['city'],$data['street'],$data['house'],$data['entrance'],$data['floor'],$data['apartment'],$data['contact_person'],$data['phone'],$data['address_comment'],$orderId,$type]);
                    } else {
                        $pdo->prepare("INSERT INTO address_requests (order_id,user_id,request_type,city,street,house,entrance,floor,apartment,contact_person,phone,comment) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")
                            ->execute([$orderId,$_SESSION['user_id'],$type,$data['city'],$data['street'],$data['house'],$data['entrance'],$data['floor'],$data['apartment'],$data['contact_person'],$data['phone'],$data['address_comment']]);
                    }
                }
                $statusField = ($type === 'measurements') ? 'measurements' : 'installation';
                $pdo->prepare("UPDATE orders SET $statusField = 'required' WHERE id = ? AND user_id = ?")->execute([$orderId, $_SESSION['user_id']]);
                
                echo json_encode(['success' => true, 'message' => 'Заявка сохранена'], JSON_UNESCAPED_UNICODE);
            } catch (Exception $e) {
                http_response_code(500);
                echo json_encode(['success'=>false,'message'=>'Ошибка сервера: '.$e->getMessage()], JSON_UNESCAPED_UNICODE);
            }
            exit;
        }
    }
}

// ==========================================
// 📊 ЗАГРУЗКА ДАННЫХ
// ==========================================
$viewOrderId = isset($_GET['view_order']) ? (int)$_GET['view_order'] : 0;
$detailOrder = null;
$addressRequests = [];

if ($viewOrderId > 0 && $currentPage === 'orders') {
    $dStmt = $pdo->prepare("SELECT * FROM orders WHERE id = ? AND user_id = ?");
    $dStmt->execute([$viewOrderId, $_SESSION['user_id']]);
    $detailOrder = $dStmt->fetch(PDO::FETCH_ASSOC);
    if ($detailOrder) {
        $reqStmt = $pdo->prepare("SELECT * FROM address_requests WHERE order_id = ? ORDER BY created_at DESC");
        $reqStmt->execute([$viewOrderId]);
        $addressRequests = $reqStmt->fetchAll(PDO::FETCH_ASSOC);
    } else { $viewOrderId = 0; }
}

$orders = [];
$totalPages = 1;
$currentPageNum = 1;
$search = '';
$statusFilter = '';

if ($currentPage === 'orders' && !$viewOrderId) {
    $currentPageNum = isset($_GET['p']) ? max(1, (int)$_GET['p']) : 1;
    $perPage = 10;
    $offset = ($currentPageNum - 1) * $perPage;
    $search = trim($_GET['search'] ?? '');
    $statusFilter = trim($_GET['status'] ?? '');

    $where = "user_id = ?";
    $params = [$_SESSION['user_id']];
    if ($search !== '') {
        $where .= " AND (id LIKE ? OR created_at LIKE ? OR items_json LIKE ?)";
        $like = "%$search%";
        $params[] = $like; $params[] = $like; $params[] = $like;
    }
    if ($statusFilter !== '') {
        $where .= " AND status = ?";
        $params[] = $statusFilter;
    }

    $stmtCount = $pdo->prepare("SELECT COUNT(*) FROM orders WHERE $where");
    $stmtCount->execute($params);
    $totalOrders = $stmtCount->fetchColumn();
    $totalPages = max(1, ceil($totalOrders / $perPage));

    $stmtOrd = $pdo->prepare("SELECT * FROM orders WHERE $where ORDER BY created_at DESC LIMIT ? OFFSET ?");
    $stmtOrd->execute(array_merge($params, [$perPage, $offset]));
    $orders = $stmtOrd->fetchAll(PDO::FETCH_ASSOC);
}

$pageTitle = ($currentPage === 'orders' ? 'Заказы' : ($currentPage === 'contacts' ? 'Контакты' : 'Личный кабинет'));
?>
<?php require __DIR__ . '/templates/cab_header.php'; ?>

<div class="main-grid">
<?php if ($is_pending_approval): ?>
    <div class="pending-overlay">
        <div class="pending-box">
            <h2>⏳ Ожидает подтверждения</h2>
            <p>Ваш email подтверждён, но доступ будет открыт после проверки администратором.</p>
            <a href="/auth/logout.php" class="btn btn-outline">🚪 Выйти</a>
        </div>
    </div>
<?php else: ?>
    <?php if ($currentPage === 'contacts'): ?>
        <div class="card card-full">
            <div class="card-header">📞 Контакты и поддержка</div>
            <div class="contacts-grid">
                <div class="contact-card"><h3>🏢 Офис компании</h3><div class="contact-item"><strong>Адрес:</strong> г. Екатеринбург, ул. Кондратьева 2а/2</div><div class="contact-item"><strong>Телефон:</strong> +7 (343) 382-92-43</div></div>
                <div class="contact-card"><h3>👥 Отдел продаж</h3><div class="contact-item"><strong>Телефон:</strong> +7 (343) 382-92-43 (доб. 101)</div><div class="contact-item"><strong>Email:</strong> sales@neirolinks.ru</div></div>
                <div class="contact-card"><h3>🔧 Тех. поддержка</h3><div class="contact-item"><strong>Телефон:</strong> +7 (343) 382-92-43 (доб. 102)</div><div class="contact-item"><strong>Email:</strong> support@neirolinks.ru</div></div>
            </div>
        </div>
    <?php elseif ($viewOrderId && $detailOrder): ?>
        <?php require __DIR__ . '/templates/order_detail.php'; ?>
    <?php else: ?>
        <?php require __DIR__ . '/templates/orders_list.php'; ?>
    <?php endif; ?>
<?php endif; ?>
</div>

<?php if (!$is_pending_approval && $currentPage !== 'contacts'): ?>
    <?php require __DIR__ . '/templates/modals/address_request.php'; ?>
<?php endif; ?>

<?php require __DIR__ . '/templates/cab_footer.php'; ?>