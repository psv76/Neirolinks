/* =========================================
   NEIROLINKS Motion | Личный кабинет
   File: /cabinet/assets/js/cabinet.js
   ========================================= */

let currentRequestType = '';
let phoneInput = null;
let phoneStatus = null;
let phoneHint = null;

// Инициализация элементов после загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    phoneInput = document.getElementById('phoneInput');
    phoneStatus = document.getElementById('phoneStatus');
    phoneHint = document.getElementById('phoneHint');
    
    if (phoneInput) {
        phoneInput.addEventListener('input', e => { 
            e.target.value = formatPhone(e.target.value); 
            updatePhoneState(); 
        });
        phoneInput.addEventListener('blur', updatePhoneState);
        phoneInput.addEventListener('focus', function() { 
            if(this.classList.contains('is-invalid')) { 
                this.classList.remove('is-invalid'); 
                if(phoneHint) {
                    phoneHint.textContent = '+7 (999) 123-45-67'; 
                    phoneHint.classList.remove('invalid');
                }
            } 
        });
    }
});

// 📱 Маска и валидация телефона
function formatPhone(v) {
    if (!v) return '';
    let d = v.replace(/\D/g, '');
    if (d.startsWith('8')) d = '7' + d.slice(1);
    if (!d.startsWith('7')) d = '7' + d;
    d = d.slice(0, 11);
    let f = '+7';
    if (d.length > 1) f += ' (' + d.slice(1, 4);
    if (d.length >= 5) f += ') ' + d.slice(4, 7);
    if (d.length >= 8) f += '-' + d.slice(7, 9);
    if (d.length >= 10) f += '-' + d.slice(9, 11);
    return f;
}

function isPhoneValid(v) { 
    return v.replace(/\D/g, '').length === 11 && v.replace(/\D/g, '').startsWith('7'); 
}

function updatePhoneState() {
    if (!phoneInput) return;
    const v = phoneInput.value, valid = isPhoneValid(v);
    phoneInput.classList.toggle('is-valid', valid);
    phoneInput.classList.toggle('is-invalid', !valid && v.length >= 10);
    if(phoneStatus) phoneStatus.textContent = valid ? '✓' : (v.length >= 10 ? '✗' : '');
    if(phoneHint) {
        phoneHint.textContent = valid ? 'Корректно ✓' : 'Проверьте формат';
        phoneHint.classList.toggle('valid', valid);
        phoneHint.classList.toggle('invalid', !valid && v.length >= 10);
    }
}

// 🔄 Дропдауны
function toggleDropdown(id) {
    if (window.event) window.event.stopPropagation();
    document.querySelectorAll('.status-dropdown').forEach(d => { 
        if(d.id !== id) d.classList.remove('show'); 
    });
    const dropdown = document.getElementById(id);
    if(dropdown) dropdown.classList.toggle('show');
}

function selectOption(val, txt, field, oid) {
    if (window.event) window.event.stopPropagation();
    if ((field==='measurements' && val==='required') || (field==='installation' && val==='required')) {
        checkExistingRequest(field, oid, txt); 
        return;
    }
    updateField(val, txt, field, oid);
}

// 🔧 Обновление поля + управление видимостью блоков заявок
function updateField(val, txt, field, oid) {
    const span = document.getElementById(field+'-text');
    if(span) span.textContent = txt;
    const hid = document.getElementById('order_'+field+'_hidden');
    if(hid) hid.value = val;
    const dd = document.getElementById(field+'-dropdown');
    if(dd) { 
        dd.querySelectorAll('.status-option').forEach(o => o.classList.toggle('active', o.dataset.value===val)); 
        dd.classList.remove('show'); 
    }
    
    // Управление контентом внутри единого блока
    if (field === 'measurements') {
        toggleBlockContent('measurementRequestsContent', val === 'required');
    }
    if (field === 'installation') {
        toggleBlockContent('installationRequestsContent', val === 'required');
    }
    
    // Обновляем видимость главного контейнера
    toggleRequestsSection();
}

// 👁️ Показ/скрытие внутреннего контента
function toggleBlockContent(id, show) {
    const el = document.getElementById(id);
    if(el) el.style.display = show ? 'block' : 'none';
}

// 👁️ Управление главным блоком заявок
function toggleRequestsSection() {
    const mBlock = document.getElementById('measurementRequestsContent');
    const iBlock = document.getElementById('installationRequestsContent');
    const mainSection = document.getElementById('requestsSection');
    
    if (mainSection && mBlock && iBlock) {
        const mVisible = mBlock.style.display !== 'none';
        const iVisible = iBlock.style.display !== 'none';
        mainSection.style.display = (mVisible || iVisible) ? 'block' : 'none';
    }
}

// 🔍 ПРОВЕРКА СУЩЕСТВУЮЩЕЙ ЗАЯВКИ
function checkExistingRequest(type, oid, txt) {
    const badge = document.querySelector(`[onclick*="${type}-dropdown"]`);
    const span = document.getElementById(type+'-text');
    const orig = span ? span.textContent : '';
    if(badge) badge.classList.add('loading');
    if(span) span.textContent = '⏳ Проверка...';

    const fd = new FormData(); 
    fd.append('check_address_request','1'); 
    fd.append('order_id', oid); 
    fd.append('type', type);
    
    fetch('/cabinet/cabinet.php', { method:'POST', body:fd })
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(d => {
        if(d.success) {
            if(d.exists) {
                updateField('required', txt, type, oid);
                showNotification('ℹ️ Данные уже заполнены. Нажмите "Сохранить и выйти" для применения.', 'success');
            } else {
                currentRequestType = type;
                const f = document.getElementById('addressForm');
                const eid = document.getElementById('edit_request_id'); 
                if(eid) eid.value='';
                if(f) f.reset(); 
                const title = document.getElementById('modalTitle');
                if(title) title.textContent = type==='measurements' ? '📐 Заявка на замер' : '🔧 Заявка на монтаж';
                openModal();
            }
        } else { 
            if(span) span.textContent = orig; 
            showNotification('⚠️ '+d.message,'error'); 
        }
    }).catch(()=>{ 
        if(span) span.textContent = orig; 
        currentRequestType = type; 
        openModal(); 
    })
    .finally(()=>{ if(badge) badge.classList.remove('loading'); });
}

// 📤 Модальное окно
function openModal() { 
    const modal = document.getElementById('addressModal');
    if(modal) {
        modal.classList.add('show'); 
        document.body.classList.add('modal-open');
        updatePhoneState(); 
    }
}

function closeModal() { 
    const modal = document.getElementById('addressModal');
    if(modal) {
        modal.classList.remove('show'); 
        document.body.classList.remove('modal-open');
    }
    const form = document.getElementById('addressForm');
    if(form) form.reset();
    const e = document.getElementById('edit_request_id'); 
    if(e) e.value=''; 
    updatePhoneState(); 
}

// ✏️ Редактирование заявки - ГЛОБАЛЬНАЯ ФУНКЦИЯ
window.editRequest = function(id, type, data) {
    console.log('🔵 Edit clicked:', {id, type, data}); // Debug
    
    try {
        currentRequestType = type;
        const f = document.getElementById('addressForm');
        if(!f) {
            console.error('❌ Form not found!');
            alert('Ошибка: форма не найдена');
            return;
        }
        
        // Заполняем поля данными из заявки
        // ВАЖНО: В базе поле называется 'comment', а в форме input name="address_comment"
        const fields = ['city', 'street', 'house', 'entrance', 'floor', 'apartment', 'contact_person', 'phone'];
        
        fields.forEach(k => {
            const i = f.querySelector(`[name="${k}"]`); 
            if(i && data[k]) {
                i.value = data[k];
                console.log(`✅ Заполнено поле ${k}:`, data[k]);
            }
        });

        // Специальная обработка для комментария
        const commentInput = f.querySelector('[name="address_comment"]');
        if(commentInput && data.comment) {
            commentInput.value = data.comment;
            console.log('✅ Заполнен комментарий:', data.comment);
        }

        // Маска телефона при редактировании
        if(data.phone && phoneInput) {
            phoneInput.value = formatPhone(data.phone);
            console.log('📱 Телефон:', phoneInput.value);
        }
        
        // Создаем или обновляем скрытое поле ID
        let hid = document.getElementById('edit_request_id');
        if(!hid) { 
            hid = document.createElement('input'); 
            hid.type = 'hidden'; 
            hid.name = 'edit_request_id'; 
            hid.id = 'edit_request_id'; 
            f.appendChild(hid); 
        }
        hid.value = id;
        console.log('🔑 ID заявки:', id);
        
        // Обновляем заголовок модалки
        const title = document.getElementById('modalTitle');
        if(title) {
            title.textContent = type==='measurements' ? '✏️ Редактирование замера' : '✏️ Редактирование монтажа';
        }
        
        openModal();
        console.log('✅ Модалка открыта');
    } catch(err) {
        console.error('❌ Ошибка в editRequest:', err);
        alert('Ошибка при редактировании: ' + err.message);
    }
}

function submitAddress() {
    const f = document.getElementById('addressForm'), btn = document.getElementById('submitBtn');
    if(phoneInput && phoneInput.value && !isPhoneValid(phoneInput.value)) { 
        phoneInput.classList.add('is-invalid'); 
        if(phoneHint) {
            phoneHint.textContent='⚠️ Исправьте номер'; 
            phoneHint.classList.add('invalid');
        }
        phoneInput.focus(); 
        return; 
    }
    if(!f || !f.checkValidity()) { 
        if(f) f.reportValidity(); 
        return; 
    }
    
    const fd = new FormData(f); 
    fd.append('submit_address_request','1'); 
    fd.append('order_id', window.cabOrderId || 0); 
    fd.append('type', currentRequestType);
    
    if(btn) {
        btn.disabled = true; 
        btn.innerHTML = '⏳ Отправка...';
    }
    
    fetch('/cabinet/cabinet.php', { method:'POST', body:fd })
    .then(r => r.json())
    .then(d => {
        if(d.success) {
            const t = currentRequestType==='measurements' ? '📐 Требуется замер' : '🔧 Требуется';
            updateField('required', t, currentRequestType, window.cabOrderId);
            closeModal();
            showNotification('✅ Данные сохранены! Теперь нажмите "Сохранить и выйти" в форме заказа.','success');
        } else {
            showNotification('❌ '+d.message,'error');
        }
    }).catch(() => showNotification('❌ Ошибка сети','error'))
    .finally(() => { 
        if(btn) {
            btn.disabled=false; 
            btn.innerHTML='📤 Отправить заявку';
        }
    });
}

// 🖨️ Печать согласия
function printAgreement() {
    const f = document.getElementById('addressForm'); 
    if(!f || !f.checkValidity()) { 
        if(f) f.reportValidity(); 
        return; 
    }
    const d = Object.fromEntries(new FormData(f));
    const txt = currentRequestType==='measurements' ? 'замера' : 'монтажа';
    const w = window.open('','_blank');
    w.document.write(`<html><head><title>Согласие на ${txt}</title><style>body{font-family:Arial;padding:40px}h1{border-bottom:2px solid #3b82f6;padding-bottom:10px}.row{margin:10px 0}b{color:#64748b}sig{margin-top:60px;border-top:1px solid #ccc;padding-top:10px;display:inline-block;width:300px}</style></head><body><h1>СОГЛАСИЕ на ${txt}</h1><div class="row"><b>Город:</b> ${d.city||''}</div><div class="row"><b>Улица:</b> ${d.street||''}</div><div class="row"><b>Дом:</b> ${d.house||''}</div>${d.entrance?`<div class="row"><b>Подъезд:</b> ${d.entrance}</div>`:''}${d.floor?`<div class="row"><b>Этаж:</b> ${d.floor}</div>`:''}${d.apartment?`<div class="row"><b>Кв:</b> ${d.apartment}</div>`:''}<div class="row"><b>Контакт:</b> ${d.contact_person||''}</div><div class="row"><b>Тел:</b> ${d.phone||''}</div>${d.address_comment?`<div class="row"><b>Прим:</b> ${d.address_comment}</div>`:''}<sig>Подпись: _______________</sig></body></html>`);
    w.document.close(); 
    w.print();
}

function showNotification(msg, type='success') {
    document.querySelectorAll('.toast-notification').forEach(t => t.remove());
    const t = document.createElement('div'); 
    t.className = `toast-notification toast-${type}`; 
    t.textContent = msg; 
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity='0'; setTimeout(()=>t.remove(), 300); }, 3000);
}

// Закрытие дропдаунов при клике вне
document.addEventListener('click', e => { 
    if(!e.target.closest('.status-selector')) 
        document.querySelectorAll('.status-dropdown').forEach(d => d.classList.remove('show')); 
});

// Закрытие модалки при клике на оверлей
const modalOverlay = document.getElementById('addressModal');
if(modalOverlay) {
    modalOverlay.addEventListener('click', e => { if(e.target === modalOverlay) closeModal(); });
}