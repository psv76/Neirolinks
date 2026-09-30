"""Human-first preview/confirm dialog for P1_001 guided actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from nl_project_2.guided_actions import GuidedAction, GuidedActionError


class GuidedActionDialog(QDialog):
    """Keep unavailable candidates visible and require an explicit preview and confirmation."""

    def __init__(self, service, action, project_id: str, owner_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.action = GuidedAction(action)
        self.project_id = project_id
        self.owner_id = owner_id
        self.preview = None
        self.receipt = None
        self.setObjectName("guidedActionDialog")
        self.setWindowTitle(self.action.label)
        self.resize(760, 520)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.candidates = QTableWidget(0, 3, self)
        self.candidates.setObjectName("guidedCandidatesTable")
        self.candidates.setHorizontalHeaderLabels(["Цель", "Состояние", "Объяснение"])
        self.candidates.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.candidates.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.candidates.itemSelectionChanged.connect(self._selection_changed)
        self.preview_text = QTextEdit(self)
        self.preview_text.setObjectName("guidedPreviewText")
        self.preview_text.setReadOnly(True)
        self.preview_button = QPushButton("Показать preview", self)
        self.preview_button.setObjectName("guidedPreviewButton")
        self.preview_button.clicked.connect(self.build_preview)
        self.apply_button = QPushButton("Подтвердить назначение", self)
        self.apply_button.setObjectName("guidedConfirmButton")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.confirm_preview)
        cancel = QPushButton("Отмена", self)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.apply_button)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.candidates, 1)
        layout.addWidget(self.preview_text)
        layout.addLayout(buttons)
        self.refresh_candidates()

    def refresh_candidates(self) -> None:
        try:
            query = self.service.candidates(self.action, self.project_id, self.owner_id)
        except GuidedActionError as exc:
            self.summary.setText(f"Действие недоступно: {exc}")
            self.candidates.setRowCount(0)
            self.preview_button.setEnabled(False)
            return
        self.query = query
        self.summary.setText(f"{query.owner_label}. {query.explanation}")
        self.candidates.setRowCount(len(query.candidates))
        first_selectable = None
        for row, candidate in enumerate(query.candidates):
            state = "Доступно" if candidate.selectable else "Недоступно"
            values = (candidate.target_label, state, candidate.explanation)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, candidate.candidate_id)
                item.setData(Qt.ItemDataRole.UserRole + 1, candidate.selectable)
                if candidate.technical_identity:
                    item.setToolTip(candidate.technical_identity)
                self.candidates.setItem(row, column, item)
            if candidate.selectable and first_selectable is None:
                first_selectable = row
        if first_selectable is not None:
            self.candidates.selectRow(first_selectable)
        self.preview_button.setEnabled(first_selectable is not None)
        self.apply_button.setEnabled(False)
        self.preview = None

    def _selected_candidate(self):
        row = self.candidates.currentRow()
        if row < 0:
            return None
        item = self.candidates.item(row, 0)
        if item is None or not item.data(Qt.ItemDataRole.UserRole + 1):
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _selection_changed(self) -> None:
        self.preview = None
        self.apply_button.setEnabled(False)
        self.preview_button.setEnabled(self._selected_candidate() is not None)

    def build_preview(self) -> None:
        candidate_id = self._selected_candidate()
        if candidate_id is None:
            return
        try:
            self.preview = self.service.preview(
                self.action, self.project_id, self.owner_id, candidate_id
            )
        except GuidedActionError as exc:
            QMessageBox.warning(self, "Preview не сформирован", str(exc))
            self.refresh_candidates()
            return
        parts = [*self.preview.changes]
        if self.preview.existing_state:
            parts.extend(("", "Существующее состояние:", *self.preview.existing_state))
        if self.preview.warnings:
            parts.extend(("", "Предупреждения:", *self.preview.warnings))
        self.preview_text.setPlainText("\n".join(parts))
        self.apply_button.setEnabled(True)

    def confirm_preview(self) -> None:
        if self.preview is None:
            return
        answer = QMessageBox.question(
            self,
            "Подтверждение назначения",
            self.preview_text.toPlainText(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.receipt = self.service.confirm(self.preview, confirmed=True)
        except GuidedActionError as exc:
            QMessageBox.warning(
                self,
                "Назначение не выполнено",
                f"Данные изменились или цель недоступна: {exc}. Обновите preview.",
            )
            self.refresh_candidates()
            return
        self.accept()
