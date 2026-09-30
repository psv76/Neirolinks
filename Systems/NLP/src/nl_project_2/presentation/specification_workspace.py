"""Permanent derived specification, budget and workshop-control workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.supply_filter)
        filters.addWidget(self.incomplete_filter)

        self.table = QTableWidget(0, 11, tab)
        self.table.setObjectName("specificationTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Позиция", "Артикул", "Количество", "Ед.", "Поставка",
                "Состояние", "В спецификации", "В смете", "Цена",
                "Стоимость", "Примечание",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.trace = QLabel("Выберите строку для трассы расчёта", tab)
        self.trace.setObjectName("specificationTrace")
        self.trace.setWordWrap(True)
        navigate = QPushButton("Перейти к источнику", tab)
        navigate.setObjectName("specificationNavigateButton")
        navigate.clicked.connect(self._navigate)
        self.search.textChanged.connect(self._filters_changed)
        self.supply_filter.currentIndexChanged.connect(self._filters_changed)
        self.incomplete_filter.currentIndexChanged.connect(self._filters_changed)
        self.table.horizontalHeader().sectionResized.connect(lambda *_: self._save_state())
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._save_state())
        layout = QVBoxLayout(tab)
        layout.addWidget(self.summary)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(self.trace)
        layout.addWidget(navigate)
        return tab

    def _build_workshop(self) -> QWidget:
        tab = QWidget(self)
        self.workshop = QTableWidget(0, 11, tab)
        self.workshop.setObjectName("workshopControlTable")
        self.workshop.setHorizontalHeaderLabels(
            [
                "Материал", "Расч. кол-во", "Расч. цена", "Расч. стоимость",
                "Кол-во цеха", "Цена цеха", "Предъявлено", "Δ кол-ва",
                "Δ стоимости", "Валюта", "Основание",
            ]
        )
        layout = QVBoxLayout(tab)
        layout.addWidget(self.workshop)
        return tab

    def refresh(self) -> None:
        selected_key = self._selected_key()
        result = self.service.build(self.project_id)
        self._rows = result["rows"]
        self.summary.setText(
            f"Известная сумма NEIROLINKS: {result['neirolinks_total']}; "
            f"позиций с неизвестной стоимостью: {result['unknown_budget_rows']}; "
            f"проверок: {len(result['issues'])}"
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._rows))
        selected_table_row = -1
        for index, row in enumerate(self._rows):
            status = _row_status(row)
            key = _row_key(row)
            values = (
                row.name,
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
                self.table.setItem(index, column, item)
            if key == selected_key:
                selected_table_row = index
        self.table.setSortingEnabled(True)
        if selected_table_row >= 0:
            self.table.selectRow(selected_table_row)
        self._load_workshop(result["workshop"])
        self.apply_filters()

    def _load_workshop(self, rows) -> None:
        self.workshop.setRowCount(len(rows))
        keys = (
            "material_kind", "calculated_quantity", "calculated_price",
            "calculated_cost", "workshop_quantity", "workshop_price",
            "claimed_cost", "quantity_deviation", "cost_deviation", "currency", "trace",
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
        for table_row in range(self.table.rowCount()):
            first = self.table.item(table_row, 0)
            searchable = " ".join(
                self.table.item(table_row, column).text() for column in (0, 1, 4, 5, 10)
            )
            visible = not phrase or phrase in searchable.casefold()
            visible = visible and (
                not supply or first.data(Qt.ItemDataRole.UserRole + 2) == supply
            )
            visible = visible and (
                not incomplete
                or first.data(Qt.ItemDataRole.UserRole + 3) == "Нужны данные"
            )
            self.table.setRowHidden(table_row, not visible)

    def _selected_row(self):
        selected = self.table.selectedItems()
        if not selected:
            return None
        return self._rows[int(selected[0].data(Qt.ItemDataRole.UserRole))]

    def _selected_key(self):
        selected = self.table.selectedItems()
        return None if not selected else selected[0].data(Qt.ItemDataRole.UserRole + 1)

    def _selection_changed(self) -> None:
        row = self._selected_row()
        if row is not None:
            self.trace.setText("\n".join(row.trace))
        self._save_state()

    def _navigate(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        sources = self.service.source_navigation(self.project_id, row)
        self.trace.setText("\n".join(item["trace"] for item in sources))
        if sources:
            self.sourceRequested.emit(sources[0]["source_kind"], sources[0]["source_id"])

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
                lambda kind, identifier: navigate_instance(identifier)
                if kind == "PROJECT_INSTANCE"
                else None
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
