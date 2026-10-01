"""Unified errors and warnings with source-aware navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ValidationCenterWidget(QWidget):
    """Action-oriented issue table; machine identity is secondary tooltip data."""

    def __init__(
        self, service, project_id: str, parent=None, navigate=None, *, ui_state=None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.navigate = navigate
        self.ui_state = ui_state
        self._restoring = True
        self._refreshing = False
        self._items = ()
        self.severity = QComboBox(self)
        self.severity.setObjectName("validationSeverityFilter")
        for label, value in (
            ("Все состояния", "ALL"),
            ("Ошибка проекта", "ERROR"),
            ("Нужны данные", "DATA"),
            ("Требуется действие", "WARNING"),
        ):
            self.severity.addItem(label, value)
        self.section_filter = QComboBox(self)
        self.section_filter.setObjectName("validationSectionFilter")
        self.section_filter.addItem("Все разделы", "")
        self.text_filter = QLineEdit(self)
        self.text_filter.setObjectName("validationTextFilter")
        self.text_filter.setPlaceholderText("Причина, действие, сущность или раздел")
        self.severity.currentIndexChanged.connect(self.refresh)
        self.section_filter.currentIndexChanged.connect(self.refresh)
        self.text_filter.textChanged.connect(self.refresh)
        filters = QHBoxLayout()
        filters.addWidget(self.severity)
        filters.addWidget(self.section_filter)
        filters.addWidget(self.text_filter)
        self.table = QTableWidget(0, 6, self)
        self.table.setObjectName("validationCenterTable")
        self.table.setHorizontalHeaderLabels(
            ["Состояние", "Что проверяется", "Причина", "Влияние", "Блокирует", "Действие"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header_font = header.font()
        header_font.setBold(True)
        header.setFont(header_font)
        for column, width in enumerate((145, 190, 330, 260, 95, 300)):
            self.table.setColumnWidth(column, width)
        header.sectionMoved.connect(lambda *_: self._save_table_state())
        header.sectionResized.connect(lambda *_: self._save_table_state())
        self.table.cellDoubleClicked.connect(lambda *_: self._navigate())
        self.navigate_button = QPushButton("Перейти к месту исправления", self)
        self.navigate_button.setObjectName("validationNavigateButton")
        self.navigate_button.clicked.connect(self._navigate)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(self.navigate_button)
        self.refresh()
        self._restore_table_state()

    def refresh(self) -> None:
        self._refreshing = True
        status = self.severity.currentData()
        section = str(self.section_filter.currentData() or "")
        phrase = self.text_filter.text().strip().casefold()
        source_items = tuple(self.service.validation_items(self.project_id))
        sections = sorted({str(item.section) for item in source_items})
        current_section = self.section_filter.currentData()
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.addItem("Все разделы", "")
        for value in sections:
            self.section_filter.addItem(value, value)
        index = self.section_filter.findData(current_section)
        self.section_filter.setCurrentIndex(max(index, 0))
        self.section_filter.blockSignals(False)
        self._items = tuple(
            item
            for item in source_items
            if (status == "ALL" or _status_text(item) == _filter_status_text(status))
            and (not section or item.section == section)
            and (
                not phrase
                or phrase
                in " ".join(
                    (
                        item.code,
                        item.section,
                        _title(item),
                        item.message,
                        _impact(item),
                        _required_action(item),
                    )
                ).casefold()
            )
        )
        try:
            self.table.setRowCount(len(self._items))
            for row_index, item in enumerate(self._items):
                values = (
                    _status_text(item),
                    _title(item),
                    item.message,
                    _impact(item),
                    "Да" if _blocking(item) else "Нет",
                    _required_action(item),
                )
                details = _engineering_tooltip(item)
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, row_index)
                    cell.setToolTip(details)
                    self.table.setItem(row_index, column, cell)
        finally:
            self._refreshing = False

    def _navigate(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.navigate is None:
            return
        self.navigate(self._items[row])

    def select_source(self, source_kind: str, source_id: str) -> bool:
        for row, item in enumerate(self._items):
            if item.source_kind == source_kind and item.source_id == source_id:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                return True
        return False

    def _save_table_state(self) -> None:
        if self.ui_state is None or self._restoring or self._refreshing:
            return
        state = self.ui_state.load()
        workspace = dict(state.get("validation_workspace") or {})
        projects = dict(workspace.get("projects") or {})
        projects[self.project_id] = {
            "columns": [
                {
                    "visual": self.table.horizontalHeader().visualIndex(column),
                    "width": self.table.columnWidth(column),
                }
                for column in range(self.table.columnCount())
            ]
        }
        workspace["projects"] = projects
        self.ui_state.update(validation_workspace=workspace)

    def _restore_table_state(self) -> None:
        try:
            if self.ui_state is None:
                return
            state = self.ui_state.load()
            workspace = dict(state.get("validation_workspace") or {})
            projects = dict(workspace.get("projects") or {})
            columns = (projects.get(self.project_id) or {}).get("columns")
            if not isinstance(columns, list):
                return
            for logical, saved in enumerate(columns[: self.table.columnCount()]):
                if not isinstance(saved, dict):
                    continue
                width = saved.get("width")
                if isinstance(width, int) and width > 20:
                    self.table.setColumnWidth(logical, width)
            ordered = sorted(
                (
                    (saved.get("visual", logical), logical)
                    for logical, saved in enumerate(columns[: self.table.columnCount()])
                    if isinstance(saved, dict)
                )
            )
            for target_visual, (_saved_visual, logical) in enumerate(ordered):
                current_visual = self.table.horizontalHeader().visualIndex(logical)
                self.table.horizontalHeader().moveSection(current_visual, target_visual)
        finally:
            self._restoring = False


class ValidationCenterDialog(QDialog):
    def __init__(self, service, project_id: str, parent=None, navigate=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Центр проверок")
        self.resize(1250, 650)
        self.content = ValidationCenterWidget(service, project_id, self, navigate=navigate)
        self.table = self.content.table
        self.severity = self.content.severity
        self.section_filter = self.content.section_filter
        self.text_filter = self.content.text_filter
        layout = QVBoxLayout(self)
        layout.addWidget(self.content)


def _status_text(item) -> str:
    status = getattr(item, "status", None)
    if status is not None:
        return str(getattr(status, "value", status))
    return "Ошибка проекта" if item.severity == "ERROR" else "Требуется действие"


def _filter_status_text(value: str) -> str:
    return {
        "ERROR": "Ошибка проекта",
        "DATA": "Нужны данные",
        "WARNING": "Требуется действие",
    }.get(value, value)


def _title(item) -> str:
    return str(getattr(item, "title", None) or item.section)


def _impact(item) -> str:
    return str(getattr(item, "impact", None) or "Требуется проверить результат")


def _blocking(item) -> bool:
    return bool(getattr(item, "blocking", item.severity == "ERROR"))


def _required_action(item) -> str:
    return str(getattr(item, "required_action", None) or "Перейдите к источнику и исправьте данные")


def _engineering_tooltip(item) -> str:
    engineering = getattr(item, "engineering", None)
    if engineering is None:
        return f"Код: {item.code}; источник: {item.source_kind}"
    details = [
        f"Код: {engineering.machine_code}",
        f"Правило: {engineering.rule}",
        f"Источник: {engineering.source}",
    ]
    if engineering.technical_ids:
        details.append("Technical ID: " + ", ".join(engineering.technical_ids))
    if engineering.evidence:
        details.append("Evidence: " + "; ".join(engineering.evidence))
    return "\n".join(value for value in details if not value.endswith(": "))
