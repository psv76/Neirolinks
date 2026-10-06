"""Permanent derived specification, budget and workshop-control workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.integration.specification_export import export_specification_xlsx

_SCOPE_LABELS = {
    "NEIROLINKS": "Поставка NEIROLINKS",
    "CUSTOMER": "Поставка заказчика",
    "ASSEMBLY_WORKSHOP": "Сборочный цех",
    "BY_CONTRACT": "По договору",
    None: "Нужны данные",
}


class SpecificationWorkspace(QWidget):
    sourceRequested = Signal(str, str)

    def __init__(self, service, project_id: str, *, ui_state=None, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.ui_state = ui_state
        self._rows = ()
        self._expanded_keys: set[str] = set()
        self._restoring = False
        self.setObjectName("specificationWorkspace")

        tabs = QTabWidget(self)
        tabs.setObjectName("specificationTabs")
        tabs.addTab(self._build_specification(), "Спецификация")
        tabs.addTab(self._build_workshop(), "Контроль сборочного цеха")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)
        self.refresh()
        self._restore_state()

    def _build_specification(self) -> QWidget:
        tab = QWidget(self)
        self.summary = QLabel(tab)
        self.summary.setObjectName("specificationSummary")
        self.search = QLineEdit(tab)
        self.search.setObjectName("specificationSearch")
        self.search.setPlaceholderText("Поиск по позиции, артикулу и примечанию")
        self.supply_filter = QComboBox(tab)
        self.supply_filter.setObjectName("specificationSupplyFilter")
        self.supply_filter.addItem("Все области поставки", "")
        for value, label in _SCOPE_LABELS.items():
            self.supply_filter.addItem(label, "MISSING" if value is None else value)
        self.incomplete_filter = QComboBox(tab)
        self.incomplete_filter.setObjectName("specificationIncompleteFilter")
        self.incomplete_filter.addItem("Все позиции", "")
        self.incomplete_filter.addItem("Только «Нужны данные»", "NEEDS_DATA")
        export_button = QPushButton("Экспорт в Excel", tab)
        export_button.setObjectName("specificationExportExcelButton")
        export_button.clicked.connect(self.export_excel)
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.supply_filter)
        filters.addWidget(self.incomplete_filter)
        filters.addWidget(export_button)

        self.table = QTableWidget(0, 11, tab)
        self.table.setObjectName("specificationTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Позиция",
                "Артикул",
                "Количество",
                "Ед.",
                "Поставка",
                "Состояние",
                "В спецификации",
                "В смете",
                "Цена",
                "Стоимость",
                "Примечание",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemClicked.connect(self._table_item_clicked)
        self.table.itemDoubleClicked.connect(self._table_item_double_clicked)
        self.search.textChanged.connect(self._filters_changed)
        self.supply_filter.currentIndexChanged.connect(self._filters_changed)
        self.incomplete_filter.currentIndexChanged.connect(self._filters_changed)
        self.table.horizontalHeader().sectionResized.connect(lambda *_: self._save_state())
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._save_state())
        layout = QVBoxLayout(tab)
        layout.addWidget(self.summary)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        return tab

    def _build_workshop(self) -> QWidget:
        tab = QWidget(self)
        self.workshop = QTableWidget(0, 11, tab)
        self.workshop.setObjectName("workshopControlTable")
        self.workshop.setHorizontalHeaderLabels(
            [
                "Материал",
                "Расч. кол-во",
                "Расч. цена",
                "Расч. стоимость",
                "Кол-во цеха",
                "Цена цеха",
                "Предъявлено",
                "Δ кол-ва",
                "Δ стоимости",
                "Валюта",
                "Основание",
            ]
        )
        layout = QVBoxLayout(tab)
        layout.addWidget(self.workshop)
        return tab

    def refresh(self) -> None:
        selected_key = self._selected_key()
        self._expanded_keys.clear()
        result = self.service.build(self.project_id)
        self._rows = result["rows"]
        self.summary.setText(
            f"Известная сумма NEIROLINKS: {result['neirolinks_total']}; "
            f"позиций с неизвестной стоимостью: {result['unknown_budget_rows']}; "
            f"проверок: {len(result['issues'])}"
        )
        self.table.setSortingEnabled(False)
        self.table.clearSpans()
        self.table.setRowCount(len(self._rows))
        selected_table_row = -1
        for index, row in enumerate(self._rows):
            status = _row_status(row)
            key = _row_key(row)
            expandable = bool(row.source_refs)
            position = f"▸ {row.name}" if expandable else row.name
            values = (
                position,
                row.article or "Нужны данные",
                "Нужны данные" if row.quantity is None else row.quantity,
                row.unit,
                _SCOPE_LABELS.get(row.supply_scope, row.supply_scope or "Нужны данные"),
                status,
                "Да" if row.specification_included else "Нет",
                "Да" if row.budget_included else "Нет",
                "Стоимость не указана" if row.unit_price is None else row.unit_price,
                "Стоимость не указана" if row.cost is None else row.cost,
                row.note or "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setData(Qt.ItemDataRole.UserRole + 1, key)
                item.setData(Qt.ItemDataRole.UserRole + 2, row.supply_scope or "MISSING")
                item.setData(Qt.ItemDataRole.UserRole + 3, status)
                item.setData(Qt.ItemDataRole.UserRole + 4, "BASE")
                self.table.setItem(index, column, item)
            if key == selected_key:
                selected_table_row = index
        self.table.setSortingEnabled(True)
        if selected_table_row >= 0:
            self.table.selectRow(selected_table_row)
        self._load_workshop(result["workshop"])
        self.apply_filters()

    def export_excel(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт спецификации",
            "Спецификация.xlsx",
            "Excel (*.xlsx)",
        )
        if not filename:
            return
        if not filename.lower().endswith(".xlsx"):
            filename += ".xlsx"
        try:
            export_specification_xlsx(self.service, self.project_id, filename)
        except Exception as exc:
            QMessageBox.critical(self, "Экспорт спецификации", str(exc))
            return
        QMessageBox.information(
            self,
            "Экспорт спецификации",
            f"Файл сохранён:\n{filename}",
        )

    def _load_workshop(self, rows) -> None:
        self.workshop.setRowCount(len(rows))
        keys = (
            "material_kind",
            "calculated_quantity",
            "calculated_price",
            "calculated_cost",
            "workshop_quantity",
            "workshop_price",
            "claimed_cost",
            "quantity_deviation",
            "cost_deviation",
            "currency",
            "trace",
        )
        for row_index, row in enumerate(rows):
            for column, key in enumerate(keys):
                value = row[key]
                self.workshop.setItem(
                    row_index,
                    column,
                    QTableWidgetItem("Нужны данные" if value is None else str(value)),
                )

    def apply_filters(self) -> None:
        phrase = self.search.text().strip().casefold()
        supply = str(self.supply_filter.currentData() or "")
        incomplete = str(self.incomplete_filter.currentData() or "")
        parent_visible = True
        for table_row in range(self.table.rowCount()):
            first = self.table.item(table_row, 0)
            if first is None:
                continue
            row_kind = str(first.data(Qt.ItemDataRole.UserRole + 4) or "BASE")
            if row_kind == "SOURCE":
                self.table.setRowHidden(table_row, not parent_visible)
                continue
            searchable = " ".join(
                self.table.item(table_row, column).text()
                for column in (0, 1, 4, 5, 10)
                if self.table.item(table_row, column) is not None
            )
            parent_visible = not phrase or phrase in searchable.casefold()
            parent_visible = parent_visible and (
                not supply or first.data(Qt.ItemDataRole.UserRole + 2) == supply
            )
            parent_visible = parent_visible and (
                not incomplete or first.data(Qt.ItemDataRole.UserRole + 3) == "Нужны данные"
            )
            self.table.setRowHidden(table_row, not parent_visible)

    def _selected_row(self):
        selected = self.table.selectedItems()
        if not selected:
            return None
        first = selected[0]
        if str(first.data(Qt.ItemDataRole.UserRole + 4) or "BASE") != "BASE":
            return None
        index = first.data(Qt.ItemDataRole.UserRole)
        return None if index is None else self._rows[int(index)]

    def _selected_key(self):
        selected = self.table.selectedItems()
        return None if not selected else selected[0].data(Qt.ItemDataRole.UserRole + 1)

    def _selection_changed(self) -> None:
        self._save_state()

    def _table_item_clicked(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        if str(item.data(Qt.ItemDataRole.UserRole + 4) or "BASE") != "BASE":
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        row = self._rows[int(index)]
        if not row.source_refs:
            return
        key = _row_key(row)
        if key in self._expanded_keys:
            self._collapse_sources(item.row(), key, row)
        else:
            self._expand_sources(item.row(), key, row)

    def _table_item_double_clicked(self, item: QTableWidgetItem) -> None:
        if str(item.data(Qt.ItemDataRole.UserRole + 4) or "") != "SOURCE":
            return
        source_kind = item.data(Qt.ItemDataRole.UserRole + 5)
        source_id = item.data(Qt.ItemDataRole.UserRole + 6)
        if source_kind and source_id:
            self.sourceRequested.emit(str(source_kind), str(source_id))

    def _expand_sources(self, base_row: int, key: str, row) -> None:
        sources = self.service.source_navigation(self.project_id, row)
        if not sources:
            return
        self.table.setSortingEnabled(False)
        insert_at = base_row + 1
        for source in sources:
            self.table.insertRow(insert_at)
            trace = str(source.get("trace") or "Источник")
            child = QTableWidgetItem(f"   └─ {trace}")
            child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsEditable)
            child.setData(Qt.ItemDataRole.UserRole, self._rows.index(row))
            child.setData(Qt.ItemDataRole.UserRole + 1, key)
            child.setData(Qt.ItemDataRole.UserRole + 4, "SOURCE")
            child.setData(Qt.ItemDataRole.UserRole + 5, source.get("source_kind"))
            child.setData(Qt.ItemDataRole.UserRole + 6, source.get("source_id"))
            child.setToolTip("Двойной щелчок — перейти к источнику")
            self.table.setItem(insert_at, 0, child)
            self.table.setSpan(insert_at, 0, 1, self.table.columnCount())
            insert_at += 1
        self._expanded_keys.add(key)
        first = self.table.item(base_row, 0)
        if first is not None:
            first.setText(f"▾ {row.name}")
        self.apply_filters()

    def _collapse_sources(self, base_row: int, key: str, row) -> None:
        child_row = base_row + 1
        while child_row < self.table.rowCount():
            first = self.table.item(child_row, 0)
            if first is None or str(first.data(Qt.ItemDataRole.UserRole + 4) or "") != "SOURCE":
                break
            if first.data(Qt.ItemDataRole.UserRole + 1) != key:
                break
            self.table.removeRow(child_row)
        self._expanded_keys.discard(key)
        first = self.table.item(base_row, 0)
        if first is not None:
            first.setText(f"▸ {row.name}")
        if not self._expanded_keys:
            self.table.setSortingEnabled(True)
        self.apply_filters()

    def _filters_changed(self, *_args) -> None:
        self.apply_filters()
        self._save_state()

    def _state(self) -> tuple[dict, dict]:
        if self.ui_state is None:
            return {}, {}
        root = self.ui_state.load()
        workspace = dict(root.get("specification_workspace") or {})
        projects = dict(workspace.get("projects") or {})
        return workspace, dict(projects.get(self.project_id) or {})

    def _save_state(self) -> None:
        if self.ui_state is None or self._restoring:
            return
        workspace, _ = self._state()
        projects = dict(workspace.get("projects") or {})
        projects[self.project_id] = {
            "search": self.search.text(),
            "supply": self.supply_filter.currentData() or "",
            "incomplete": self.incomplete_filter.currentData() or "",
            "selected": self._selected_key(),
            "sort_column": self.table.horizontalHeader().sortIndicatorSection(),
            "sort_order": int(self.table.horizontalHeader().sortIndicatorOrder().value),
            "columns": [self.table.columnWidth(index) for index in range(self.table.columnCount())],
        }
        workspace["projects"] = projects
        self.ui_state.update(specification_workspace=workspace)

    def _restore_state(self) -> None:
        _workspace, state = self._state()
        if not state:
            self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
            return
        self._restoring = True
        try:
            self.search.setText(str(state.get("search") or ""))
            for combo, key in (
                (self.supply_filter, "supply"),
                (self.incomplete_filter, "incomplete"),
            ):
                index = combo.findData(state.get(key) or "")
                combo.setCurrentIndex(max(index, 0))
            for column, width in enumerate(state.get("columns") or []):
                if isinstance(width, int) and width > 20 and column < self.table.columnCount():
                    self.table.setColumnWidth(column, width)
            order = (
                Qt.SortOrder.DescendingOrder
                if state.get("sort_order") == int(Qt.SortOrder.DescendingOrder.value)
                else Qt.SortOrder.AscendingOrder
            )
            self.table.sortItems(int(state.get("sort_column", 0)), order)
            selected = state.get("selected")
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) == selected:
                    self.table.selectRow(row)
                    break
            self.apply_filters()
        finally:
            self._restoring = False


class SpecificationWorkspaceDialog(QDialog):
    """Compatibility wrapper; the primary route is the permanent Documents tab."""

    def __init__(self, service, project_id: str, parent=None, navigate_instance=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Спецификация и стоимость")
        self.resize(1280, 760)
        workspace = SpecificationWorkspace(service, project_id, parent=self)
        self.workspace = workspace
        self.table = workspace.table
        self.workshop = workspace.workshop
        self.summary = workspace.summary
        if navigate_instance is not None:
            workspace.sourceRequested.connect(
                lambda kind, identifier: (
                    navigate_instance(identifier) if kind == "PROJECT_INSTANCE" else None
                )
            )
        layout = QVBoxLayout(self)
        layout.addWidget(workspace)


def _row_status(row) -> str:
    if row.article is None or row.quantity is None or row.supply_scope is None:
        return "Нужны данные"
    if row.budget_included and row.cost is None:
        return "Нужны данные"
    return "Готово"


def _row_key(row) -> str:
    return f"{row.item_key}|{row.supply_scope}|{row.unit}"
