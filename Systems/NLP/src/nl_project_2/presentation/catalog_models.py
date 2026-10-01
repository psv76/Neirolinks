"""Injectable Qt models for viewing the SQLite-backed immutable catalog."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QTableView, QTabWidget, QVBoxLayout, QWidget


class CatalogTableModel(QAbstractTableModel):
    def __init__(self, rows: list[dict], columns: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._rows = tuple(dict(row) for row in rows)
        self._columns = tuple(columns)

    def rowCount(self, _parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, _parent: QModelIndex | None = None) -> int:
        return len(self._columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self._rows[index.row()].get(self._columns[index.column()][0])
        return "" if value is None else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._columns[section][1]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        return super().flags(index) & ~Qt.ItemFlag.ItemIsEditable


class CatalogBrowserWidget(QWidget):
    """Read-only browser; editing starts through a validated copy-on-write draft."""

    def __init__(self, queries, parent=None) -> None:
        super().__init__(parent)
        tabs = QTabWidget(self)
        passport_view = QTableView(tabs)
        passport_view.setModel(
            CatalogTableModel(
                queries.passports(),
                [
                    ("passport_key", "Passport"),
                    ("name", "Name"),
                    ("equipment_class", "Class"),
                    ("resource_definition_count", "Resources"),
                    ("product_count", "Products"),
                ],
                passport_view,
            )
        )
        product_view = QTableView(tabs)
        product_view.setModel(
            CatalogTableModel(
                queries.products(),
                [
                    ("product_key", "Product"),
                    ("manufacturer", "Manufacturer"),
                    ("article", "Article"),
                    ("name", "Name"),
                    ("passport_key", "Passport"),
                ],
                product_view,
            )
        )
        tabs.addTab(passport_view, "Passports")
        tabs.addTab(product_view, "Products")
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
