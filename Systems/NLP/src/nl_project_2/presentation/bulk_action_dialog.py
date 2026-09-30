"""Full preview/all-or-none UI adapter for P1_003 controlled bulk actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from nl_project_2.bulk_actions import BulkActionError
from nl_project_2.guided_actions import GuidedAction


class BulkActionDialog(QDialog):
    def __init__(self, service, action, project_id: str, owner_ids, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.action = GuidedAction(action)
        self.project_id = project_id
        self.owner_ids = tuple(owner_ids)
        self.preview = None
        self.receipt = None
        self.setObjectName("bulkActionDialog")
        self.setWindowTitle(f"Массово: {self.action.label}")
        self.resize(900, 620)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.variants = QTableWidget(0, 4, self)
        self.variants.setObjectName("bulkVariantsTable")
        self.variants.setHorizontalHeaderLabels(
            ["Вариант", "Существующих ресурсов", "Last-used", "Состояние"]
        )
        self.variants.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variants.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.variants.itemSelectionChanged.connect(self._selection_changed)
        self.designations = QLineEdit(self)
        self.designations.setObjectName("bulkNewDesignations")
        self.designations.setPlaceholderText("Например: QF.10, QF.11")
        form = QFormLayout()
        form.addRow("Новые обозначения (если нужны)", self.designations)
        self.preview_text = QTextEdit(self)
        self.preview_text.setObjectName("bulkPreviewText")
        self.preview_text.setReadOnly(True)
        self.preview_button = QPushButton("Сформировать полный preview", self)
        self.preview_button.setObjectName("bulkPreviewButton")
        self.preview_button.clicked.connect(self.build_preview)
        self.apply_button = QPushButton("Применить всё", self)
        self.apply_button.setObjectName("bulkConfirmButton")
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
        layout.addWidget(self.variants, 1)
        layout.addLayout(form)
        layout.addWidget(self.preview_text)
        layout.addLayout(buttons)
        self.refresh_variants()

    def refresh_variants(self) -> None:
        try:
            self.snapshot = self.service.selection_snapshot(
                self.action,
                project_id=self.project_id,
                owner_ids=self.owner_ids,
            )
            query = self.service.candidate_variants(self.snapshot)
        except BulkActionError as exc:
            self.summary.setText(f"Selection недоступен: {exc}")
            self.variants.setRowCount(0)
            self.preview_button.setEnabled(False)
            return
        invalid = [owner for owner in self.snapshot.owners if not owner.valid]
        if invalid:
            reasons = "; ".join(
                f"{owner.label}: {', '.join(owner.reason_codes)}" for owner in invalid
            )
            self.summary.setText(f"Операция заблокирована: {reasons}")
        else:
            self.summary.setText(
                f"Выбрано: {len(self.snapshot.owners)}. Статус вариантов: {query.status}"
            )
        self.variants.setRowCount(len(query.variants))
        first = None
        for row, variant in enumerate(query.variants):
            values = (
                variant.label,
                str(variant.existing_resource_count),
                "Да" if variant.preferred else "Нет",
                "Доступно" if variant.selectable else ", ".join(variant.reason_codes),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, variant.stable_identity)
                item.setData(Qt.ItemDataRole.UserRole + 1, variant.selectable)
                self.variants.setItem(row, column, item)
            if variant.selectable and first is None:
                first = row
        if first is not None:
            self.variants.selectRow(first)
        self.preview_button.setEnabled(first is not None and not invalid)

    def _selection_changed(self) -> None:
        self.preview = None
        self.apply_button.setEnabled(False)

    def _selected_variant(self):
        row = self.variants.currentRow()
        if row < 0:
            return None
        item = self.variants.item(row, 0)
        if item is None or not item.data(Qt.ItemDataRole.UserRole + 1):
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def build_preview(self) -> None:
        variant = self._selected_variant()
        if variant is None:
            return
        designations = tuple(
            value.strip() for value in self.designations.text().split(",") if value.strip()
        )
        try:
            self.preview = self.service.preview(
                self.snapshot,
                chosen_variant_identity=variant,
                proposed_designations=designations,
            )
        except BulkActionError as exc:
            QMessageBox.warning(self, "Preview не сформирован", str(exc))
            return
        lines = [
            f"{self.preview.action_label}: {self.preview.selected_owner_count} объектов",
            f"Вариант: {self.preview.chosen_variant_label}",
            f"Новых экземпляров: {self.preview.new_instance_count}",
            f"Новых фактов: {self.preview.canonical_fact_count}",
        ]
        lines.extend(
            f"{item.owner_label} → {item.instance_designation} / {', '.join(item.resource_labels)}"
            for item in self.preview.mappings
        )
        if self.preview.conflicts:
            lines.extend(("", "Конфликты:", *self.preview.conflicts))
        if self.preview.warnings:
            lines.extend(("", "Предупреждения:", *self.preview.warnings))
        self.preview_text.setPlainText("\n".join(lines))
        self.apply_button.setEnabled(self.preview.confirmable)

    def confirm_preview(self) -> None:
        if self.preview is None or not self.preview.confirmable:
            return
        answer = QMessageBox.question(
            self,
            "Подтверждение массовой операции",
            self.preview_text.toPlainText(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.receipt = self.service.confirm(self.preview, confirmed=True)
        except BulkActionError as exc:
            QMessageBox.warning(
                self,
                "Операция не выполнена",
                f"Проект изменился или preview устарел: {exc}. Обновите preview.",
            )
            self.refresh_variants()
            return
        self.accept()
