<div class="card card-full">
<div class="card-header" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;"><span>📦 Заказы</span></div>
<form method="GET" class="filters-bar">
    <input type="hidden" name="page" value="orders">
    <input type="text" name="search" placeholder=" Поиск..." value="<?= htmlspecialchars($search ?? '') ?>">
    <select name="status">
        <option value="">Все статусы</option>
        <?php foreach($statusMap as $k=>$v): ?><option value="<?= $k ?>" <?= ($statusFilter ?? '')===$k?'selected':'' ?>><?= $v ?></option><?php endforeach; ?>
    </select>
    <button type="submit">Применить</button>
    <?php if(!empty($search) || !empty($statusFilter)): ?><a href="?page=orders" style="color:#ef4444;text-decoration:none;margin-left:10px;"> Сброс</a><?php endif; ?>
</form>

<?php if (empty($orders)): ?>
    <div class="empty-state">Заказов не найдено. <a href="/index.php" class="link-primary">Оформить первый</a></div>
<?php else: ?>
<div class="table-wrap">
<table class="orders-table">
    <thead><tr><th>№</th><th>Дата</th><th>Позиций</th><th>Сумма</th><th>Маржа</th><th>Статус</th><th>Комментарий</th></tr></thead>
    <tbody>
    <?php foreach ($orders as $ord):
        $items = json_decode($ord['items_json'] ?? '[]', true) ?: [];
        $comm = $ord['comment'] ?? '';
        $commPrev = $comm ? (mb_strlen($comm)>40 ? mb_substr($comm,0,40).'...' : $comm) : '';
        $url = "?page=orders&view_order={$ord['id']}";
        if(!empty($search)) $url .= "&search=".urlencode($search);
        if(!empty($statusFilter)) $url .= "&status=$statusFilter";
    ?>
    <tr class="hover-row" onclick="window.location.href='<?= htmlspecialchars($url) ?>'">
        <td>#<?= $ord['id'] ?></td><td><?= date('d.m.Y', strtotime($ord['created_at'])) ?></td>
        <td><?= count($items) ?></td><td><?= number_format($ord['total_client'],0,'.',' ') ?> ₽</td>
        <td class="<?= ($ord['margin']>=0?'text-success':'text-danger') ?>"><?= ($ord['margin']>=0?'+':'') ?><?= number_format($ord['margin'],0,'.',' ') ?> ₽</td>
        <td><span class="order-status"><?= $statusMap[$ord['status']] ?? '🆕 Новый' ?></span></td>
        <td class="comment-cell"><?= $commPrev ?: '<em>Нет</em>' ?></td>
    </tr>
    <?php endforeach; ?>
    </tbody>
</table>
</div>
<?php if ($totalPages > 1): ?>
<div class="pagination">
    <?php for($i=1;$i<=$totalPages;$i++): ?>
    <a href="?page=orders&p=<?= $i ?><?= !empty($search)?"&search=".urlencode($search):'' ?><?= !empty($statusFilter)?"&status=$statusFilter":'' ?>" class="<?= $i===$currentPageNum?'active':'' ?>"><?= $i ?></a>
    <?php endfor; ?>
</div>
<?php endif; ?>
<?php endif; ?>
</div>