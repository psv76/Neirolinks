<div id="addressModal" class="modal-overlay">
    <div class="modal-content" style="max-width: 520px;">
        <h3 class="modal-title" id="modalTitle">Заявка на замер</h3>
        <p class="modal-subtitle">Для продолжения заполните все поля</p>
        
        <form id="addressForm">
            <!-- Адрес: Город и Улица -->
            <div class="form-group">
                <label class="form-label">Город</label>
                <input type="text" class="form-input" name="city" required placeholder="Введите город">
            </div>
            <div class="form-group">
                <label class="form-label">Улица</label>
                <input type="text" class="form-input" name="street" required placeholder="Введите улицу">
            </div>
            
            <!-- Ряд: Дом и Подъезд -->
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">№ дома</label>
                    <input type="text" class="form-input" name="house" required placeholder="12">
                </div>
                <div class="form-group">
                    <label class="form-label">№ подъезда</label>
                    <input type="text" class="form-input" name="entrance" placeholder="1">
                </div>
            </div>
            
            <!-- Ряд: Этаж и Квартира -->
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Этаж</label>
                    <input type="text" class="form-input" name="floor" placeholder="3">
                </div>
                <div class="form-group">
                    <label class="form-label">№ квартиры</label>
                    <input type="text" class="form-input" name="apartment" placeholder="45">
                </div>
            </div>
            
            <!-- Контактное лицо и Телефон -->
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Контактное лицо</label>
                    <input type="text" class="form-input" name="contact_person" required placeholder="ФИО">
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон <span style="color:#ef4444">*</span></label>
                    <input type="tel" class="form-input phone-input" name="phone" id="phoneInput" required placeholder="+7 (___) ___-__-__" maxlength="18">
                    <span class="phone-status" id="phoneStatus"></span>
                    <div class="phone-hint" id="phoneHint">В формате: +7 (999) 123-45-67</div>
                </div>
            </div>
            
            <!-- Комментарий -->
            <div class="form-group">
                <label class="form-label">Комментарий</label>
                <textarea class="form-textarea" name="address_comment" placeholder="Дополнительная информация"></textarea>
            </div>
            
            <!-- Кнопки -->
            <div class="modal-buttons">
                <button type="button" class="btn-modal btn-primary" id="submitBtn" onclick="submitAddress()">📤 Отправить заявку</button>
                <button type="button" class="btn-modal btn-secondary" onclick="printAgreement()">🖨️ Распечатать согласие</button>
                <button type="button" class="btn-modal btn-cancel" onclick="closeModal()">Отмена</button>
            </div>
        </form>
    </div>
</div>