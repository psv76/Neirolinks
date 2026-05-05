<?php 
// Показываем сообщение об успехе и сразу очищаем сессию
$successMsg = $_SESSION['success_msg'] ?? '';
unset($_SESSION['success_msg']);

// ✅ ОПРЕДЕЛЯЕМ переменные для проверки наличия заявок
$hasMeasurementRequests = ($detailOrder['measurements'] === 'required' && !empty(array_filter($addressRequests, fn($r) => $r['request_type'] === 'measurements')));
$hasInstallationRequests = ($detailOrder['installation'] === 'required' && !empty(array_filter($addressRequests, fn($r) => $r['request_type'] === 'installation')));
?>

<?php if ($successMsg): ?>
<div class="msg-success"><?= htmlspecialchars($successMsg) ?></div>
<?php endif; ?>

<div class="detail-card">
<div class="detail-header">
    <h2 style="margin:0;">📦 Заказ №<?= $detailOrder['id'] ?></h2>
    <div class="status-row">
        <?php 
        $fields = [
            ['key'=>'measurements','label'=>'Замеры','map'=>$measurementsMap],
            ['key'=>'installation','label'=>'Установка','map'=>$installationMap],
            ['key'=>'status','label'=>'Статус','map'=>$statusMap]
        ];
        foreach($fields as $f): 
            $val = $detailOrder[$f['key']] ?? '';
            $txt = (!empty($val) && isset($f['map'][$val])) ? $f['map'][$val] : 'Выбрать';
        ?>
        <div class="dropdown-group">
            <span class="dropdown-label"><?= $f['label'] ?></span>
            <div class="status-selector">
                <span class="status-badge" onclick="toggleDropdown('<?= $f['key'] ?>-dropdown')">
                    <span id="<?= $f['key'] ?>-text"><?= $txt ?></span> <span>▼</span>
                </span>
                <div id="<?= $f['key'] ?>-dropdown" class="status-dropdown">
                    <?php foreach($f['map'] as $k=>$v): ?>
                    <div class="status-option <?= $k===$val?'active':'' ?>" data-value="<?= $k ?>" onclick="selectOption('<?= $k ?>','<?= htmlspecialchars($v,ENT_QUOTES) ?>','<?= $f['key'] ?>', <?= $detailOrder['id'] ?>)"><?= $v ?></div>
                    <?php endforeach; ?>
                </div>
            </div>
        </div>
        <?php endforeach; ?>
    </div>
</div>

<div class="detail-grid">
    <div class="detail-item"><strong>📅 ДАТА</strong><span style="font-weight:bold;"><?= date('d.m.Y H:i', strtotime($detailOrder['created_at'])) ?></span></div>
    <?php
    $itemsForCalc = json_decode($detailOrder['items_json'] ?? '[]', true) ?: [];
    $totalRrc = $totalDisc = 0;
    foreach($itemsForCalc as $it) { $base=($it['r']??0)*($it['q']??1); $totalRrc+=$base; $totalDisc+=$base*(1-($it['dis']??0)/100); }
    ?>
    <div class="detail-item"><strong>💸 СКИДКА</strong><span style="color:#ef4444; font-weight:bold;">- <?= number_format($totalRrc-$totalDisc,0,'.',' ') ?> ₽</span></div>
    <div class="detail-item"><strong>💰 ИТОГО</strong><span style="font-weight:bold;"><?= number_format($totalDisc,0,'.',' ') ?> ₽</span></div>
    <div class="detail-item">
        <strong>📈 МАРЖА</strong>
        <span style="font-weight:bold; color: <?= ($detailOrder['margin']>=0?'#10b981':'#ef4444') ?>;">
            <?= ($detailOrder['margin']>=0?'+':'') ?><?= number_format($detailOrder['margin'],0,'.',' ') ?> ₽
        </span>
    </div>
</div>

<h3 style="margin:20px 0 10px;">📋 Состав заказа</h3>
<div class="table-wrap">
<table class="items-table">
    <thead><tr><th>Товар</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
    <tbody>
    <?php foreach($itemsForCalc as $it): $p=round($it['r']*(1-($it['dis']??0)/100)); ?>
    <tr><td><?= htmlspecialchars($it['name']) ?></td><td><?= $it['q'] ?></td><td><?= number_format($p,0,'.',' ') ?> ₽</td><td><?= number_format($p*$it['q'],0,'.',' ') ?> ₽</td></tr>
    <?php endforeach; ?>
    </tbody>
</table>
</div>

<!-- ОДИН ОБЩИЙ БЛОК ЗАЯВОК -->
<div class="detail-card" style="margin-top:20px; display: <?= ($hasMeasurementRequests || $hasInstallationRequests) ? 'block' : 'none' ?>;" id="requestsSection">
    <h3>📋 Заявки</h3>
    
    <!-- Контент: Замер -->
    <div id="measurementRequestsContent" style="display: <?= $hasMeasurementRequests ? 'block' : 'none' ?>;">
        <?php 
        $measurementReqs = array_filter($addressRequests, fn($r) => $r['request_type'] === 'measurements');
        foreach($measurementReqs as $req): ?>
        <div class="request-card type-measurements">
            <div class="request-header">
                <strong>📐 Замер</strong>
                <div style="display:flex;gap:8px;align-items:center">
                    <span style="color:#64748b;font-size:0.85rem"><?= date('d.m.Y H:i', strtotime($req['created_at'])) ?></span>
                    <!-- КНОПКА РЕДАКТИРОВАНИЯ -->
                    <button type="button" class="btn-edit-request" onclick="editRequest(<?= $req['id'] ?>, 'measurements', <?= json_encode($req, JSON_UNESCAPED_UNICODE | JSON_HEX_APOS) ?>)" style="padding:4px 10px;background:#3b82f6;color:#fff;border:none;border-radius:4px;font-size:0.8rem;cursor:pointer">✏️ Ред.</button>
                </div>
            </div>
            <div class="request-body">
                <div>📍 <?= htmlspecialchars($req['city']) ?>, <?= htmlspecialchars($req['street']) ?>, <?= htmlspecialchars($req['house']) ?><?= $req['entrance']?", под. {$req['entrance']}":'' ?><?= $req['floor']?", эт. {$req['floor']}":'' ?><?= $req['apartment']?", кв. {$req['apartment']}":'' ?></div>
                <div>👤 <?= htmlspecialchars($req['contact_person']) ?> | 📞 <?= htmlspecialchars($req['phone']) ?></div>
                
                <!-- Комментарий заявки -->
                <?php if(!empty($req['comment'])): ?>
                <div style="margin-top:8px; padding:8px; background:#f8fafc; border-radius:6px; font-size:0.85rem; color:#475569; border-left:3px solid #3b82f6;">
                    <strong>💬 Комментарий:</strong> <?= htmlspecialchars($req['comment']) ?>
                </div>
                <?php endif; ?>
                
            </div>
        </div>
        <?php endforeach; ?>
    </div>

    <!-- Контент: Монтаж -->
    <div id="installationRequestsContent" style="display: <?= $hasInstallationRequests ? 'block' : 'none' ?>;">
        <?php 
        $installationReqs = array_filter($addressRequests, fn($r) => $r['request_type'] === 'installation');
        foreach($installationReqs as $req): ?>
        <div class="request-card type-installation">
            <div class="request-header">
                <strong>🔧 Монтаж</strong>
                <div style="display:flex;gap:8px;align-items:center">
                    <span style="color:#64748b;font-size:0.85rem"><?= date('d.m.Y H:i', strtotime($req['created_at'])) ?></span>
                    <!-- КНОПКА РЕДАКТИРОВАНИЯ -->
                    <button type="button" class="btn-edit-request install-edit" onclick="editRequest(<?= $req['id'] ?>, 'installation', <?= json_encode($req, JSON_UNESCAPED_UNICODE | JSON_HEX_APOS) ?>)" style="padding:4px 10px;background:#10b981;color:#fff;border:none;border-radius:4px;font-size:0.8rem;cursor:pointer">✏️ Ред.</button>
                </div>
            </div>
            <div class="request-body">
                <div>📍 <?= htmlspecialchars($req['city']) ?>, <?= htmlspecialchars($req['street']) ?>, <?= htmlspecialchars($req['house']) ?><?= $req['entrance']?", под. {$req['entrance']}":'' ?><?= $req['floor']?", эт. {$req['floor']}":'' ?><?= $req['apartment']?", кв. {$req['apartment']}":'' ?></div>
                <div>👤 <?= htmlspecialchars($req['contact_person']) ?> | 📞 <?= htmlspecialchars($req['phone']) ?></div>
                
                <!-- Комментарий заявки -->
                <?php if(!empty($req['comment'])): ?>
                <div style="margin-top:8px; padding:8px; background:#f8fafc; border-radius:6px; font-size:0.85rem; color:#475569; border-left:3px solid #10b981;">
                    <strong>💬 Комментарий:</strong> <?= htmlspecialchars($req['comment']) ?>
                </div>
                <?php endif; ?>

            </div>
        </div>
        <?php endforeach; ?>
    </div>
</div>

<div class="comment-form">
    <h3>💬 Комментарий</h3>
    <form method="POST">
        <input type="hidden" name="view_order_id" value="<?= $detailOrder['id'] ?>">
        <input type="hidden" name="order_status" id="order_status_hidden" value="<?= htmlspecialchars($detailOrder['status']) ?>">
        <input type="hidden" name="order_measurements" id="order_measurements_hidden" value="<?= htmlspecialchars($detailOrder['measurements'] ?? '') ?>">
        <input type="hidden" name="order_installation" id="order_installation_hidden" value="<?= htmlspecialchars($detailOrder['installation'] ?? '') ?>">
        <textarea name="comment" placeholder="Заметка, вопрос менеджеру..."><?= htmlspecialchars($detailOrder['comment'] ?? '') ?></textarea>
        <div class="action-panel">
            <a href="?page=orders<?= !empty($search)?"&search=".urlencode($search):'' ?><?= !empty($statusFilter)?"&status=$statusFilter":'' ?>" class="btn-back">← Назад</a>
            <button type="submit" name="save_and_exit" class="btn-save">💾 Сохранить и выйти</button>
        </div>
    </form>
</div>
</div>

<script>window.cabOrderId = <?= $detailOrder['id'] ?>;</script>