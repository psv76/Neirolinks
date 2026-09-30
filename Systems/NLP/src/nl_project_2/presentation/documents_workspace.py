"""Permanent in-app cable journal, checks and user operation journal."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .specification_workspace import SpecificationWorkspace
from .validation_center import ValidationCenterWidget


def _natural_key(value: str) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)
    )


def _format_length(value) -> str:
    if value is None or str(value).strip() == "":
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{number:.2f}".rstrip("0").rstrip(".")


class NaturalTreeItem(QTreeWidgetItem):
    def __lt__(self, other) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        return _natural_key(self.text(column)) < _natural_key(other.text(column))


class CableJournalWidget(QWidget):
    lineRequested = Signal(str)

    HEADERS = (
        "CABLE_ID",
        "Потребитель",
        "Тип / система",
        "Щит / источник",
        "Здание",
        "Помещение",
        "Тип кабеля",
        "Прокладка",
        "Труба / трасса",
        "Итоговая длина, м",
        "Источник длины",
        "Состояние",
    )

    def __init__(self, service, project_id: str, *, ui_state=None, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.ui_state = ui_state
        self.rows = ()
        self.search = QLineEdit(self)
        self.search.setObjectName("cableJournalSearch")
        self.search.setPlaceholderText("CABLE_ID, потребитель, помещение или щит")
        self.status_filter = QComboBox(self)
        self.status_filter.setObjectName("cableJournalStatusFilter")
        self.status_filter.addItem("Все состояния", "")
        for status in ("Готово", "Требуется действие", "Нужны данные", "Ошибка проекта"):
            self.status_filter.addItem(status, status)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Поиск", self))
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("cableJournalTree")
        self.tree.setColumnCount(len(self.HEADERS))
        self.tree.setHeaderLabels(self.HEADERS)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open_line())
        open_line = QPushButton("Открыть линию", self)
        open_line.setObjectName("cableJournalOpenLineButton")
        open_line.clicked.connect(self._open_line)
        copy_button = QPushButton("Копировать видимый текст", self)
        copy_button.setObjectName("cableJournalCopyButton")
        copy_button.clicked.connect(self.copy_visible_text)
        actions = QHBoxLayout()
        actions.addWidget(open_line)
        actions.addWidget(copy_button)
        actions.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)
        self.search.textChanged.connect(self.apply_filters)
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        self.tree.itemSelectionChanged.connect(self._save_state)
        self.refresh()
        self._restore_state()

    def refresh(self) -> None:
        selected = self.selected_line_id()
        self.rows = tuple(self.service.cable_journal_rows(self.project_id))
        self.tree.clear()
        for row in self.rows:
            parent = NaturalTreeItem(
                self.tree,
                [
                    row.cable_id,
                    row.load_name,
                    row.load_type,
                    row.board,
                    row.building,
                    row.room,
                    row.cable_type,
                    row.mount_way,
                    row.conduit,
                    _format_length(row.total_length_m) or "Не определена",
                    row.length_mode,
                    row.status.value,
                ],
            )
            parent.setData(0, Qt.ItemDataRole.UserRole, row.cable_line_id)
            parent.setData(0, Qt.ItemDataRole.UserRole + 1, "LINE")
            parent.setToolTip(10, row.length_explanation)
            for segment in row.segments:
                child = NaturalTreeItem(
                    parent,
                    [
                        "",
                        f"Участок: {segment.source_label} → {segment.target_label}",
                        "Физический сегмент",
                        "",
                        "",
                        "",
                        "",
                        segment.mount_way,
                        segment.conduit_label,
                        _format_length(segment.length_m) or "Не определена",
                        "Расчёт сегмента",
                        "",
                    ],
                )
                child.setData(0, Qt.ItemDataRole.UserRole, row.cable_line_id)
                child.setData(0, Qt.ItemDataRole.UserRole + 1, "SEGMENT")
                child.setToolTip(1, f"Technical segment ID: {segment.segment_id}")
            if row.cable_line_id == selected:
                self.tree.setCurrentItem(parent)
        self.apply_filters()

    def selected_line_id(self) -> str | None:
        item = self.tree.currentItem()
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def select_line(self, line_id: str) -> bool:
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == line_id:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                return True
        return False

    def apply_filters(self) -> None:
        phrase = self.search.text().strip().casefold()
        status = str(self.status_filter.currentData() or "")
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            searchable = " ".join(item.text(column) for column in (0, 1, 3, 4, 5))
            visible = (not phrase or phrase in searchable.casefold()) and (
                not status or item.text(11) == status
            )
            item.setHidden(not visible)
        self._save_state()

    def copy_visible_text(self) -> str:
        lines = ["\t".join(self.HEADERS)]
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.isHidden():
                continue
            lines.append("\t".join(item.text(column) for column in range(len(self.HEADERS))))
            if item.isExpanded():
                for child_index in range(item.childCount()):
                    child = item.child(child_index)
                    lines.append(
                        "\t".join(child.text(column) for column in range(len(self.HEADERS)))
                    )
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        return text

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_visible_text()
            return
        super().keyPressEvent(event)

    def _open_line(self) -> None:
        line_id = self.selected_line_id()
        if line_id:
            self.lineRequested.emit(line_id)

    def _state(self) -> dict:
        if self.ui_state is None:
            return {}
        state = self.ui_state.load()
        documents = dict(state.get("documents_workspace") or {})
        projects = dict(documents.get("projects") or {})
        return dict(projects.get(self.project_id) or {})

    def _save_state(self) -> None:
        if self.ui_state is None:
            return
        state = self.ui_state.load()
        documents = dict(state.get("documents_workspace") or {})
        projects = dict(documents.get("projects") or {})
        project_state = dict(projects.get(self.project_id) or {})
        project_state.update(
            cable_search=self.search.text(),
            cable_status=self.status_filter.currentData() or "",
            cable_selected_line_id=self.selected_line_id(),
            cable_columns=[self.tree.columnWidth(index) for index in range(len(self.HEADERS))],
        )
        projects[self.project_id] = project_state
        documents["projects"] = projects
        self.ui_state.update(documents_workspace=documents)

    def _restore_state(self) -> None:
        state = self._state()
        self.search.setText(str(state.get("cable_search") or ""))
        index = self.status_filter.findData(state.get("cable_status") or "")
        self.status_filter.setCurrentIndex(max(index, 0))
        widths = state.get("cable_columns")
        if isinstance(widths, list):
            for column, width in enumerate(widths[: len(self.HEADERS)]):
                if isinstance(width, int) and width > 20:
                    self.tree.setColumnWidth(column, width)
        selected = state.get("cable_selected_line_id")
        if selected:
            self.select_line(selected)


class OperationJournalWidget(QWidget):
    def __init__(self, service, project_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.rows = ()
        self.search = QLineEdit(self)
        self.search.setObjectName("operationJournalSearch")
        self.search.setPlaceholderText("Действие, результат или сущность")
        self.status_filter = QComboBox(self)
        self.status_filter.setObjectName("operationJournalStatusFilter")
        self.status_filter.addItem("Все результаты", "")
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        self.table = QTableWidget(0, 5, self)
        self.table.setObjectName("operationJournalTable")
        self.table.setHorizontalHeaderLabels(
            ["Дата / время", "Действие", "Результат", "Статус", "Контекст"]
        )
        self.table.setSortingEnabled(True)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self.apply_filters)
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        self.refresh()

    def refresh(self) -> None:
        self.rows = tuple(self.service.operation_rows(self.project_id))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))
        statuses = []
        for row_index, row in enumerate(self.rows):
            statuses.append(row.status)
            values = (row.occurred_at, row.action, row.summary, row.status, row.context)
            details = (
                f"Источник: {row.source_kind}\n"
                f"Revision: {row.revision_before} → {row.revision_after}\n"
                f"Correlation ID: {row.correlation_id}\nCommand ID: {row.command_id}"
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row_index)
                item.setToolTip(details)
                self.table.setItem(row_index, column, item)
        current = self.status_filter.currentData()
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        self.status_filter.addItem("Все результаты", "")
        for value in sorted(set(statuses)):
            self.status_filter.addItem(value, value)
        self.status_filter.setCurrentIndex(max(self.status_filter.findData(current), 0))
        self.status_filter.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.apply_filters()

    def apply_filters(self) -> None:
        phrase = self.search.text().strip().casefold()
        status = str(self.status_filter.currentData() or "")
        for row in range(self.table.rowCount()):
            searchable = " ".join(self.table.item(row, column).text() for column in range(5))
            visible = (not phrase or phrase in searchable.casefold()) and (
                not status or self.table.item(row, 3).text() == status
            )
            self.table.setRowHidden(row, not visible)


class DocumentsWorkspace(QWidget):
    lineRequested = Signal(str)
    issueRequested = Signal(object)
    specificationRequested = Signal()
    specificationSourceRequested = Signal(str, str)

    def __init__(
        self,
        service,
        project_id: str,
        *,
        ui_state=None,
        specification_service=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("documentsTabs")
        self.cable_journal = CableJournalWidget(service, project_id, ui_state=ui_state, parent=self)
        self.validation = ValidationCenterWidget(
            service,
            project_id,
            self,
            navigate=self.issueRequested.emit,
            ui_state=ui_state,
        )
        self.operations = OperationJournalWidget(service, project_id, self)
        self.tabs.addTab(self.cable_journal, "Кабельный журнал")
        self.tabs.addTab(self.validation, "Проверки")
        self.tabs.addTab(self.operations, "Журнал операций")
        self.specification = None
        if specification_service is not None:
            self.specification = SpecificationWorkspace(
                specification_service,
                project_id,
                ui_state=ui_state,
                parent=self,
            )
            self.specification.sourceRequested.connect(self.specificationSourceRequested.emit)
            self.tabs.addTab(self.specification, "Спецификация и стоимость")
        self.cable_journal.lineRequested.connect(self.lineRequested)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        self.cable_journal.refresh()
        self.validation.refresh()
        self.operations.refresh()
        if self.specification is not None:
            self.specification.refresh()

    def show_specification(self) -> None:
        if self.specification is not None:
            self.tabs.setCurrentWidget(self.specification)

    def show_issue_for(self, source_kind: str, source_id: str) -> None:
        self.tabs.setCurrentWidget(self.validation)
        self.validation.refresh()
        self.validation.select_source(source_kind, source_id)
