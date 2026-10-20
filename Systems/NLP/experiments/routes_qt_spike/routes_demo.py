"""Standalone, read-only PySide6 A/B UI spike for NL Project 3.0 Routes.

Run: python routes_demo.py --variant A|B|both
Requires: PySide6 6.6+.
The ONLY data source is fixture.load_fixture(): no DB, CAD, imports from
production services, network access or state persistence.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableView, QTreeView,
    QVBoxLayout, QWidget
)

from fixture import Conduit, Segment, Snapshot, load_fixture

HEADERS = (
    "Вид", "Обозначение", "Начало", "Конец", "Труба", "Параметры трубы",
    "Кабели / состав", "Длина, м", "Состояние / замечание",
)
WIDTHS = (115, 202, 160, 210, 142, 154, 224, 102, 275)
ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1
KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 2
DIM = QColor("#526071")
GROUP_BG = QColor("#eef2f6")
WARN_BG = QColor("#fff5dc")


@dataclass(frozen=True)
class Display:
    kind: str                   # CONDUIT, SEGMENT, GROUP
    identity: str
    conduit: Conduit | None = None
    segment: Segment | None = None
    count: int = 0


def row_cells(row: Display) -> tuple[str, ...]:
    if row.kind == "SEGMENT":
        seg = row.segment
        assert seg is not None
        tube = row.conduit
        return (
            "Сегмент", f"{seg.line} / {seg.id.removeprefix('segment-')}",
            seg.source, seg.target,
            tube.designation if tube is not None else "Без трубы",
            tube.pipe_type if tube is not None else "—",
            seg.cable,
            seg.geometry_m if seg.geometry_m is not None else "—",
            seg.tube_need or (seg.note if seg.note else "Назначен"),
        )
    if row.kind == "GROUP":
        return ("Группа", "Без трубы", "—", "—", "—", "—",
                f"{row.count} сегм.", "—", "Все сегменты без назначения")
    tube = row.conduit
    assert tube is not None
    return (
        "Труба", tube.designation, tube.source, tube.target,
        tube.designation, tube.pipe_type,
        f"{row.count} сегм. · {row.count} кабелей",
        tube.final_m if tube.final_m is not None else "—",
        tube.note or ("Длина не рассчитана" if tube.final_m is None else "Назначена"),
    )


def searches(needle: str, *values: str) -> bool:
    return not needle or any(needle in str(v).casefold() for v in values)


def filtered_snapshot(
    snapshot: Snapshot, search: str, membership: str, sort_name: str
) -> tuple[list[tuple[Conduit, list[Segment]]], list[Segment]]:
    needle = search.strip().casefold()
    tubes = {t.id: t for t in snapshot.conduits}
    grouped: list[tuple[Conduit, list[Segment]]] = []
    for tube in snapshot.conduits:
        if membership in ("Без трубы", "Требует трубы"):
            continue
        matches_tube = searches(
            needle, tube.designation, tube.source, tube.target, tube.pipe_type
        )
        segments = [
            s for s in snapshot.segments
            if s.conduit_id == tube.id and (
                matches_tube or searches(
                    needle, s.id, s.line, s.source, s.target, s.cable, s.note
                )
            )
        ]
        if segments:
            segments.sort(key=lambda s: (s.line, s.id))
            grouped.append((tube, segments))
    if sort_name == "Длина трубы ↓":
        grouped.sort(key=lambda p: (
            -(float(p[0].final_m) if p[0].final_m is not None else -1), p[0].designation
        ))
    else:
        grouped.sort(key=lambda p: p[0].designation)
    unassigned: list[Segment] = []
    if membership != "В трубе":
        unassigned = [
            s for s in snapshot.segments
            if s.conduit_id is None
            and (membership != "Требует трубы" or s.tube_need == "Требуется")
            and searches(
                needle, s.id, s.line, s.source, s.target,
                s.cable, s.note, "Без трубы", s.tube_need
            )
        ]
        unassigned.sort(key=lambda s: (s.line, s.id))
    return grouped, unassigned


class TableBModel(QAbstractTableModel):
    """Flat QTableView; expanded content is flattened into the SAME model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[Display] = []
        self.expanded: set[str] = set()

    def set_rows(self, rows: list[Display]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        cell = row_cells(row)[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                if row.kind == "SEGMENT":
                    return "    ↳ Сегмент"
                return ("▾ " if row.identity in self.expanded else "▸ ") + (
                    "Труба" if row.kind == "CONDUIT" else "Без трубы"
                )
            return cell
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 7:
                return ("Геометрия G одного CableSegment" if row.kind == "SEGMENT"
                        else "Итоговая длина Conduit (final)" if row.kind == "CONDUIT"
                        else "Нет суммарной длины")
            return cell
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.kind != "SEGMENT":
                return QBrush(GROUP_BG)
            if row.segment is not None and row.segment.tube_need == "Требуется" and index.column() == 8:
                return QBrush(WARN_BG)
        if role == Qt.ItemDataRole.FontRole and row.kind != "SEGMENT":
            font = QFont("Segoe UI", 9)
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 7:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == ID_ROLE:
            return row.identity
        if role == KIND_ROLE:
            return row.kind
        return None

    def flags(self, index):
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if index.isValid() else Qt.ItemFlag.NoItemFlags)


class FlatTable(QTableView):
    toggleRequested = Signal(str)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            index = self.currentIndex()
            if index.isValid() and index.data(KIND_ROLE) != "SEGMENT":
                self.toggleRequested.emit(index.data(ID_ROLE))
                return
        # Delete has NO action; all cells are read-only.
        if event.key() == Qt.Key.Key_Delete:
            return
        super().keyPressEvent(event)


class RoutesPrototype(QWidget):
    """Common toolbar, source data, selection semantics, and style for A and B."""

    def __init__(self, snapshot: Snapshot, variant: str):
        super().__init__()
        self.snapshot = snapshot
        self.variant = variant
        self.saved_selection: set[str] = set()
        self._restoring = False
        self.expanded: set[str] = {"tube-001", "group:none"}
        self.filtered_groups: list[tuple[Conduit, list[Segment]]] = []
        self.filtered_unassigned: list[Segment] = []
        self.setWindowTitle(f"NL Project 3.0 — Трассы · вариант {variant} (UI-прототип)")
        self.setObjectName(f"routesPrototype{variant}")
        self.resize(1380, 790)
        self.setMinimumSize(910, 520)

        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 6)
        main.setSpacing(7)

        heading = QHBoxLayout()
        title = QLabel("Трассы")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        heading.addWidget(title)
        synthetic = QLabel("UI-прототип · только фиктивные данные · запись отключена")
        synthetic.setStyleSheet("color: #5f6b7a")
        heading.addWidget(synthetic)
        heading.addStretch()
        self.variant_label = QLabel(f"Вариант {variant}")
        self.variant_label.setStyleSheet("font-weight: 600; color: #4b5563")
        heading.addWidget(self.variant_label)
        main.addLayout(heading)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(7)
        toolbar.addWidget(QLabel("Фильтр / поиск"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Труба, сегмент, кабель, начало или конец")
        self.search.setMinimumWidth(270)
        toolbar.addWidget(self.search, 2)
        self.membership = QComboBox()
        self.membership.addItems(("Все", "В трубе", "Без трубы", "Требует трубы"))
        self.membership.setMinimumWidth(136)
        toolbar.addWidget(self.membership)
        self.sort = QComboBox()
        self.sort.addItems(("Обозначение", "Длина трубы ↓"))
        toolbar.addWidget(self.sort)
        self.reset_button = QPushButton("Сброс")
        toolbar.addWidget(self.reset_button)
        self.expand_button = QPushButton("Раскрыть всё")
        toolbar.addWidget(self.expand_button)
        self.collapse_button = QPushButton("Свернуть всё")
        toolbar.addWidget(self.collapse_button)
        main.addLayout(toolbar)

        if variant == "A":
            self.view = QTreeView(self)
            self.view.setObjectName("routesTreeView")
            self.view.setRootIsDecorated(True)
            self.view.setItemsExpandable(True)
            self.view.setExpandsOnDoubleClick(True)
            self.view.setIndentation(17)
            self.tree_model = QStandardItemModel(0, len(HEADERS), self)
            self.tree_model.setHorizontalHeaderLabels(HEADERS)
            self.view.setModel(self.tree_model)
            self.view.expanded.connect(self._tree_expand)
            self.view.collapsed.connect(self._tree_collapse)
        else:
            self.view = FlatTable(self)
            self.view.setObjectName("routesFlatTable")
            self.flat_model = TableBModel(self)
            self.view.setModel(self.flat_model)
            self.view.toggleRequested.connect(self._flat_toggle)
            self.view.clicked.connect(self._flat_click)
            self.view.doubleClicked.connect(self._flat_double)

        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setWordWrap(False)
        self.view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.view.setStyleSheet(
            "QTreeView::item:selected, QTableView::item:selected"
            " {background: #2f6fab; color: white;}"
            "QTreeView::item:selected:!active, QTableView::item:selected:!active"
            " {background: #607d99; color: white;}"
        )
        header = self.view.header() if variant == "A" else self.view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setMinimumHeight(32)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hf = header.font()
        hf.setBold(True)
        if hf.pointSize() > 0:
            hf.setPointSize(hf.pointSize() + 1)
        header.setFont(hf)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStyleSheet(
            "QHeaderView::section { border-right: 1px solid #d9dee7; padding: 5px 7px; }"
        )
        for col, width in enumerate(WIDTHS):
            self.view.setColumnWidth(col, width)
        self.view.setUniformRowHeights(True) if variant == "A" else None
        if variant == "B":
            self.view.verticalHeader().setVisible(False)
            self.view.verticalHeader().setDefaultSectionSize(28)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        main.addWidget(self.view, 1)

        actions = QHBoxLayout()
        for label in ("Привязать к трубе", "Перенести", "Убрать из трубы"):
            button = QPushButton(label)
            button.setEnabled(False)
            button.setToolTip("UI-прототип: запись отключена")
            actions.addWidget(button)
        actions.addStretch()
        self.match_label = QLabel()
        actions.addWidget(self.match_label)
        main.addLayout(actions)
        self.selection_label = QLabel()
        self.selection_label.setStyleSheet("color: #4b5563")
        main.addWidget(self.selection_label)

        self.search.textChanged.connect(self.rebuild)
        self.membership.currentIndexChanged.connect(self.rebuild)
        self.sort.currentIndexChanged.connect(self.rebuild)
        self.reset_button.clicked.connect(self.reset_filters)
        self.expand_button.clicked.connect(lambda: self.set_expand_all(True))
        self.collapse_button.clicked.connect(lambda: self.set_expand_all(False))
        self.rebuild()

    def _group_rows(self) -> list[tuple[Display, list[Display]]]:
        groups: list[tuple[Display, list[Display]]] = []
        for tube, segments in self.filtered_groups:
            root = Display("CONDUIT", tube.id, conduit=tube, count=len(segments))
            children = [
                Display("SEGMENT", seg.id, conduit=tube, segment=seg)
                for seg in segments
            ]
            groups.append((root, children))
        if self.filtered_unassigned:
            groups.append((
                Display("GROUP", "group:none", count=len(self.filtered_unassigned)),
                [Display("SEGMENT", s.id, segment=s) for s in self.filtered_unassigned],
            ))
        return groups

    def rebuild(self, *_args):
        self._restoring = True
        self.filtered_groups, self.filtered_unassigned = filtered_snapshot(
            self.snapshot, self.search.text(),
            self.membership.currentText(), self.sort.currentText()
        )
        groups = self._group_rows()
        if self.variant == "A":
            model = self.tree_model
            model.clear()
            model.setColumnCount(len(HEADERS))
            model.setHorizontalHeaderLabels(HEADERS)
            for root, children in groups:
                items = self._make_tree_row(root)
                model.appendRow(items)
                for child in children:
                    items[0].appendRow(self._make_tree_row(child))
            for row_no, (root, _children) in enumerate(groups):
                index = model.index(row_no, 0)
                self.view.setExpanded(index, root.identity in self.expanded)
        else:
            flat_rows = []
            for root, children in groups:
                flat_rows.append(root)
                if root.identity in self.expanded:
                    flat_rows.extend(children)
            self.flat_model.expanded = set(self.expanded)
            self.flat_model.set_rows(flat_rows)
        self._restore_selection()
        self._restoring = False
        count = sum(len(segments) for _, segments in self.filtered_groups)
        count += len(self.filtered_unassigned)
        self.match_label.setText(
            f"Найдено: {count} сегм. · {len(self.filtered_groups)} труб"
            + (" · состав отфильтрован" if self.search.text().strip() else "")
        )
        self._selection_status()

    def _make_tree_row(self, row: Display):
        items = []
        for column, text in enumerate(row_cells(row)):
            item = QStandardItem(text)
            item.setEditable(False)
            item.setData(row.identity, ID_ROLE)
            item.setData(row.kind, KIND_ROLE)
            if row.kind != "SEGMENT":
                item.setBackground(GROUP_BG)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            elif row.segment and row.segment.tube_need == "Требуется" and column == 8:
                item.setBackground(WARN_BG)
            if column == 7:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(
                    "Геометрия G CableSegment" if row.kind == "SEGMENT"
                    else "Итоговая длина Conduit (final)"
                )
            else:
                item.setToolTip(text)
            items.append(item)
        return items

    def _selection_indexes(self):
        return self.view.selectionModel().selectedRows(0)

    def _visible_indexes(self):
        if self.variant == "B":
            return [self.flat_model.index(i, 0) for i in range(self.flat_model.rowCount())]
        model = self.tree_model
        result = []
        for i in range(model.rowCount()):
            parent = model.index(i, 0)
            result.append(parent)
            if self.view.isExpanded(parent):
                result.extend(
                    model.index(j, 0, parent)
                    for j in range(model.rowCount(parent))
                )
        return result

    def _restore_selection(self):
        from PySide6.QtCore import QItemSelectionModel
        model = self.view.selectionModel()
        model.blockSignals(True)
        model.clearSelection()
        for index in self._visible_indexes():
            if index.data(ID_ROLE) in self.saved_selection:
                model.select(
                    index, QItemSelectionModel.SelectionFlag.Select |
                    QItemSelectionModel.SelectionFlag.Rows
                )
        model.blockSignals(False)

    def _selection_changed(self, *_args):
        if self._restoring:
            return
        visible = {idx.data(ID_ROLE) for idx in self._visible_indexes()}
        selected = {idx.data(ID_ROLE) for idx in self._selection_indexes()}
        self.saved_selection.difference_update(visible - selected)
        self.saved_selection.update(selected)
        self._selection_status()

    def _selection_status(self):
        visible = {idx.data(ID_ROLE) for idx in self._visible_indexes()}
        selected_segments = sum(s.startswith("segment-") for s in self.saved_selection)
        selected_tubes = sum(s.startswith("tube-") for s in self.saved_selection)
        hidden = len(self.saved_selection - visible)
        self.selection_label.setText(
            f"Выбрано: {selected_segments} сегм. · {selected_tubes} труб"
            f" · скрыто выбранных: {hidden}"
            "    |    Выбор трубы не выбирает её сегменты. Запись отключена."
        )

    def _tree_expand(self, index):
        if self._restoring:
            return
        self.expanded.add(index.data(ID_ROLE))
        self._restore_selection()
        self._selection_status()

    def _tree_collapse(self, index):
        if self._restoring:
            return
        self.expanded.discard(index.data(ID_ROLE))
        self._selection_status()

    def _flat_toggle(self, identity: str):
        if identity in self.expanded:
            self.expanded.discard(identity)
        else:
            self.expanded.add(identity)
        self.rebuild()

    def _flat_click(self, index):
        if index.column() == 0 and index.data(KIND_ROLE) != "SEGMENT":
            self._flat_toggle(index.data(ID_ROLE))

    def _flat_double(self, index):
        if index.data(KIND_ROLE) != "SEGMENT" and index.column() != 0:
            self._flat_toggle(index.data(ID_ROLE))

    def set_expand_all(self, expand: bool):
        groups = self._group_rows()
        if expand:
            self.expanded.update(root.identity for root, _ in groups)
        else:
            self.expanded.difference_update(root.identity for root, _ in groups)
        self.rebuild()

    def reset_filters(self):
        self.search.clear()
        self.membership.setCurrentIndex(0)
        self.sort.setCurrentIndex(0)
        self.rebuild()


def main():
    parser = argparse.ArgumentParser(description="Read-only NL Project Routes Qt UI spike")
    parser.add_argument("--variant", choices=("A", "B", "both"), default="both")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    fixture = load_fixture()
    windows = []
    for variant in (("A", "B") if args.variant == "both" else (args.variant,)):
        win = RoutesPrototype(fixture, variant)
        win.show()
        windows.append(win)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
