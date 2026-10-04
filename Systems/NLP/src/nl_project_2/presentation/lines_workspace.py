"""Permanent Lines workspace with spreadsheet behavior and a bottom selection card."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QItemSelectionModel, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyleOptionHeader,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.cables import RouteMethod
from nl_project_2.cables.domain import format_conduit_id
from nl_project_2.cables.presentation import format_cable_mark
from nl_project_2.guided_actions import GuidedAction

from .bulk_action_dialog import BulkActionDialog
from .guided_action_dialog import GuidedActionDialog
from .room_presentation import ROOM_MARKERS_ROLE, RoomChipDelegate


def _natural_key(value: str) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)
    )


class NaturalSortItem(QTableWidgetItem):
    def __lt__(self, other) -> bool:
        return _natural_key(self.text()) < _natural_key(other.text())


class CableMarkItem(NaturalSortItem):
    """Display a legacy-expanded mark while editing the stored canonical value."""

    def __init__(self, value: object) -> None:
        self._edit_value = "" if value is None else str(value)
        super().__init__(format_cable_mark(self._edit_value))

    def data(self, role: int):
        if role == Qt.ItemDataRole.EditRole:
            return self._edit_value
        return super().data(role)

    def setData(self, role: int, value) -> None:
        if role == Qt.ItemDataRole.EditRole:
            self._edit_value = "" if value is None else str(value)
            super().setData(Qt.ItemDataRole.DisplayRole, format_cable_mark(self._edit_value))
            return
        super().setData(role, value)


class SpreadsheetTable(QTableWidget):
    copyRequested = Signal()
    pasteRequested = Signal()
    fillDownRequested = Signal()
    editableMoveRequested = Signal(int)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyRequested.emit()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.pasteRequested.emit()
            return
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.fillDownRequested.emit()
            return
        if self.state() != QAbstractItemView.State.EditingState:
            if event.key() == Qt.Key.Key_Tab:
                self.editableMoveRequested.emit(1)
                return
            if event.key() == Qt.Key.Key_Backtab:
                self.editableMoveRequested.emit(-1)
                return
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                item = self.currentItem()
                if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
                    self.editItem(item)
                    return
        super().keyPressEvent(event)


@dataclass(frozen=True, slots=True)
class LineColumn:
    key: str
    title: str
    editable_field: str | None = None
    group: str = ""
    default_visible: bool = False


@dataclass(frozen=True, slots=True)
class GroupSpan:
    label: str
    logical_sections: tuple[int, ...]
    left: int
    width: int


class GroupedHeaderView(QHeaderView):
    """Two-level header whose top spans follow the current visible column order."""

    def __init__(self, columns, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._columns = tuple(columns)
        self._group_height = 24
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        return QSize(base.width(), max(50, base.height() + self._group_height))

    def group_spans(self) -> tuple[GroupSpan, ...]:
        visible = [
            self.logicalIndex(visual)
            for visual in range(self.count())
            if not self.isSectionHidden(self.logicalIndex(visual))
        ]
        runs: list[tuple[str, list[int]]] = []
        for logical in visible:
            label = self._columns[logical].group
            if not label:
                continue
            if runs and runs[-1][0] == label:
                runs[-1][1].append(logical)
            else:
                runs.append((label, [logical]))
        spans = []
        for label, logicals in runs:
            left = self.sectionViewportPosition(logicals[0])
            right = self.sectionViewportPosition(logicals[-1]) + self.sectionSize(logicals[-1])
            spans.append(GroupSpan(label, tuple(logicals), left, right - left))
        return tuple(spans)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        child = QRect(
            rect.left(),
            rect.top() + self._group_height,
            rect.width(),
            max(0, rect.height() - self._group_height),
        )
        if child.height() > 0:
            super().paintSection(painter, child, logical_index)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())
        top = QRect(0, 0, self.viewport().width(), self._group_height)
        painter.fillRect(top, self.palette().button())
        for span in self.group_spans():
            rect = QRect(span.left, 0, span.width, self._group_height)
            option = QStyleOptionHeader()
            self.initStyleOption(option)
            option.rect = rect
            option.text = span.label
            option.textAlignment = Qt.AlignmentFlag.AlignCenter
            option.position = QStyleOptionHeader.SectionPosition.Middle
            self.style().drawControl(QStyle.ControlElement.CE_Header, option, painter, self)
        painter.end()


COLUMNS = (
    LineColumn("building_names", "Здание", default_visible=True),
    LineColumn("board", "Источник", "BOARD", default_visible=True),
    LineColumn("room_names", "Помещение", default_visible=True),
    LineColumn("designation", "ID", default_visible=True),
    LineColumn("load_name", "Назначение", default_visible=True),
    LineColumn("cable_type", "Марка кабеля", "CABLE_TYPE", default_visible=True),
    LineColumn("mount_way", "Прокладка", default_visible=True),
    LineColumn("gofra_id", "Труба", default_visible=True),
    LineColumn("effective_m", "Длина, м", default_visible=True),
    LineColumn("user_status", "Состояние"),
    LineColumn("load_type", "Тип нагрузки"),
    LineColumn("system_kind", "Система"),
    LineColumn("length_mode", "Источник длины"),
    LineColumn("resource_labels", "Назначенный ресурс"),
)

_DEFAULT_COLUMN_WIDTHS = {
    "building_names": 130,
    "board": 115,
    "room_names": 190,
    "designation": 100,
    "load_name": 270,
    "cable_type": 185,
    "mount_way": 125,
    "gofra_id": 110,
    "effective_m": 90,
    "user_status": 155,
    "load_type": 150,
    "system_kind": 110,
    "length_mode": 145,
    "resource_labels": 230,
}

LINES_LAYOUT_VERSION = 4


def _column_index(key: str) -> int:
    return next(index for index, column in enumerate(COLUMNS) if column.key == key)


def _format_length(value) -> str:
    if value is None or str(value).strip() == "":
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{number:.2f}".rstrip("0").rstrip(".")


class LinesWorkspace(QWidget):
    resourceRequested = Signal(str)
    issueRequested = Signal(str)
    projectChanged = Signal()

    def __init__(
        self,
        cable_service,
        constructor_service,
        project_id: str,
        *,
        ui_state=None,
        guided_service=None,
        bulk_service=None,
        status_service=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.cables = cable_service
        self.constructor = constructor_service
        self.project_id = project_id
        self.ui_state = ui_state
        self.guided = guided_service
        self.bulk = bulk_service
        self.status_service = status_service
        self._cards: list[dict] = []
        self._cards_by_id: dict[str, dict] = {}
        self._assignments_by_line: dict[str, list[dict]] = {}
        self._refreshing = False
        # Keep constructor-time refresh signals from overwriting saved project state
        # before _restore_state() has had a chance to read it.
        self._restoring = ui_state is not None
        self.setObjectName("linesWorkspace")

        self.search = QLineEdit(self)
        self.search.setObjectName("linesSearchEdit")
        self.search.setPlaceholderText("Номер или назначение линии, помещение, щит")
        self.system_filter = QComboBox(self)
        self.system_filter.setObjectName("linesSystemFilter")
        self.room_filter = QComboBox(self)
        self.room_filter.setObjectName("linesRoomFilter")
        self.board_filter = QComboBox(self)
        self.board_filter.setObjectName("linesBoardFilter")
        self.status_filter = QComboBox(self)
        self.status_filter.setObjectName("linesStatusFilter")
        self.view_button = QToolButton(self)
        self.view_button.setObjectName("linesViewButton")
        self.view_button.setText("Вид")
        self.view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Фильтр / поиск", self))
        filter_row.addWidget(self.search, 2)
        filter_row.addWidget(self.system_filter)
        filter_row.addWidget(self.room_filter)
        filter_row.addWidget(self.board_filter)
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.view_button)

        self.table = SpreadsheetTable(0, len(COLUMNS), self)
        self.table.setObjectName("linesSpreadsheetTable")
        self.table.setHorizontalHeaderLabels([column.title for column in COLUMNS])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.setItemDelegateForColumn(
            _column_index("room_names"), RoomChipDelegate(self.table)
        )
        self.table.setStyleSheet(
            "QTableWidget::item:selected { background: #2f6fab; color: white; }"
            "QTableWidget::item:selected:!active { background: #607d99; color: white; }"
            "QTableWidget::item:disabled { background: #eceff1; color: #737b82; }"
        )
        header_font = self.table.horizontalHeader().font()
        header_font.setBold(True)
        if header_font.pointSize() > 0:
            header_font.setPointSize(header_font.pointSize() + 1)
        self.table.horizontalHeader().setFont(header_font)
        self.table.horizontalHeader().setMinimumHeight(32)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { border-right: 1px solid #d9dee7; padding: 5px 7px; }"
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemClicked.connect(self._table_item_clicked)
        self.table.itemDoubleClicked.connect(self._table_item_double_clicked)
        self.table.copyRequested.connect(self.copy_selection)
        self.table.pasteRequested.connect(self.paste_clipboard)
        self.table.fillDownRequested.connect(self.fill_down)
        self.table.editableMoveRequested.connect(self._move_editable)
        self.table.verticalScrollBar().valueChanged.connect(lambda *_: self._save_state())
        self.table.horizontalScrollBar().valueChanged.connect(lambda *_: self._save_state())
        header = self.table.horizontalHeader()
        header.sectionMoved.connect(lambda *_: self._save_state())
        header.sectionResized.connect(lambda *_: self._save_state())

        scalar_bulk = QPushButton("Изменить выбранные строки", self)
        scalar_bulk.setObjectName("linesScalarBulkButton")
        scalar_bulk.clicked.connect(self.bulk_edit_selected_rows)
        fill = QPushButton("Заполнить вниз (Ctrl+D)", self)
        fill.setObjectName("linesFillDownButton")
        fill.clicked.connect(self.fill_down)
        self.bulk_buttons = {}
        table_actions = QHBoxLayout()
        table_actions.addWidget(scalar_bulk)
        table_actions.addWidget(fill)
        for action in (
            GuidedAction.PROTECTION,
            GuidedAction.POWER,
            GuidedAction.OUTPUT,
        ):
            button = QPushButton(f"Массово: {action.label}", self)
            button.setObjectName(f"bulk{action.value.title()}Button")
            button.clicked.connect(lambda _checked=False, value=action: self.run_bulk_action(value))
            self.bulk_buttons[action] = button
            table_actions.addWidget(button)
        input_bulk = QPushButton("Массово: Назначить вход", self)
        input_bulk.setObjectName("bulkInputButton")
        input_bulk.setEnabled(False)
        input_bulk.setToolTip("Вход назначается выбранным физическим клавишам, не строкам линий")
        table_actions.addWidget(input_bulk)
        table_actions.addStretch(1)
        top = QWidget(self)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(filter_row)
        top_layout.addWidget(self.table, 1)

        self.card_title = QLabel("Линия не выбрана", self)
        self.card_title.setObjectName("lineCardTitle")
        self.card_title.setStyleSheet("font-weight: 600; font-size: 14px")
        self.card_fields = {
            key: QLabel("—", self)
            for key in (
                "location",
                "board",
                "cable",
                "route",
                "length",
                "resources",
                "status",
                "status_reason",
                "explanation",
            )
        }
        for label in self.card_fields.values():
            label.setWordWrap(True)
        details = QHBoxLayout()
        details.setSpacing(8)
        for title, rows in (
            (
                "Расположение",
                (("Здание / помещение", "location"), ("Щит", "board")),
            ),
            (
                "Кабель / трасса",
                (("Марка", "cable"), ("Трасса", "route"), ("Длина", "length")),
            ),
            (
                "Связи / состояние",
                (
                    ("Связи", "resources"),
                    ("Состояние", "status"),
                    ("Что требуется", "status_reason"),
                    ("Пояснение", "explanation"),
                ),
            ),
        ):
            group = QGroupBox(title, self)
            form = QFormLayout(group)
            form.setContentsMargins(8, 6, 8, 6)
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(2)
            for label, key in rows:
                form.addRow(label, self.card_fields[key])
            details.addWidget(group, 1)
        self.single_buttons = {}
        card_actions = QHBoxLayout()
        for action in (
            GuidedAction.PROTECTION,
            GuidedAction.POWER,
            GuidedAction.OUTPUT,
        ):
            button = QPushButton(action.label, self)
            button.setObjectName(f"guided{action.value.title()}Button")
            button.clicked.connect(
                lambda _checked=False, value=action: self.run_guided_action(value)
            )
            self.single_buttons[action] = button
            card_actions.addWidget(button)
        input_single = QPushButton("Назначить вход", self)
        input_single.setObjectName("guidedInputButton")
        input_single.setEnabled(False)
        input_single.setToolTip("Перейдите к физической клавише в разделе оборудования")
        card_actions.addWidget(input_single)
        self.open_resource = QPushButton("Открыть связанное оборудование", self)
        self.open_resource.setObjectName("lineOpenEquipmentButton")
        self.open_resource.clicked.connect(self._open_related_resource)
        card_actions.addWidget(self.open_resource)
        self.show_issue = QPushButton("Показать проблему", self)
        self.show_issue.setObjectName("lineShowIssueButton")
        self.show_issue.clicked.connect(self._show_issue)
        card_actions.addWidget(self.show_issue)
        card_actions.addStretch(1)
        bottom = QWidget(self)
        bottom.setObjectName("lineBottomCard")
        bottom.setMinimumHeight(165)
        bottom.setMaximumHeight(225)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(3)
        bottom_layout.addWidget(self.card_title)
        bottom_layout.addLayout(details)
        bottom_layout.addLayout(card_actions)

        physical = QWidget(self)
        physical.setObjectName("linePhysicalRoutePanel")
        physical_layout = QVBoxLayout(physical)
        physical_layout.setContentsMargins(8, 4, 8, 4)
        physical_layout.setSpacing(4)
        physical_layout.addWidget(QLabel("Физическая цепочка выбранной линии", physical))
        route_actions = QHBoxLayout()
        recalculate = QPushButton("Пересчитать длины линии", physical)
        recalculate.clicked.connect(self._recalculate_selected_line)
        summary = QPushButton("Метры по способам: весь объект", physical)
        summary.setObjectName("projectRouteBreakdownButton")
        summary.clicked.connect(self._show_project_route_breakdown)
        route_actions.addWidget(recalculate)
        route_actions.addWidget(summary)
        route_actions.addStretch()
        physical_layout.addLayout(route_actions)

        self.segment_summary = QLabel("Линия не выбрана", physical)
        self.segment_summary.setObjectName("lineRouteBreakdownLabel")
        self.segment_summary.setWordWrap(True)
        physical_layout.addWidget(self.segment_summary)

        self.segment_table = QTableWidget(0, 11, physical)
        self.segment_table.setObjectName("linePhysicalSegmentsTable")
        self.segment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.segment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.segment_table.setHorizontalHeaderLabels(
            [
                "Откуда",
                "Куда",
                "Прокладка",
                "Труба",
                "Трасса, м",
                "Кабель, м",
                "Статус",
                "Тип трубы",
                "Цвет трубы",
                "Длина трубы, м",
                "Товар трубы",
            ]
        )
        self.segment_table.setWordWrap(False)
        for column, width in enumerate((155, 155, 115, 105, 85, 85, 290, 100, 90, 115, 200)):
            self.segment_table.setColumnWidth(column, width)
        self.segment_table.itemSelectionChanged.connect(self._segment_selection_changed)
        physical_layout.addWidget(self.segment_table, 1)

        self.segment_route_combo = QComboBox(physical)
        for method, title in (
            (RouteMethod.FLOOR, "По полу"),
            (RouteMethod.CEILING, "По потолку"),
            (RouteMethod.WALL, "В стене"),
            (RouteMethod.TIMBER, "В брусе"),
            (RouteMethod.CABLE_CHANNEL, "В кабель-канале"),
        ):
            self.segment_route_combo.addItem(title, method)
        self.segment_gofra_type_edit = QLineEdit(physical)
        self.segment_gofra_color_edit = QLineEdit(physical)
        self.segment_gofra_id = QLabel("—", physical)
        self.segment_conduit_number = QSpinBox(physical)
        self.segment_conduit_number.setObjectName("segmentConduitNumber")
        self.segment_conduit_number.setRange(-1, 999)
        self.segment_conduit_number.setValue(-1)
        self.segment_conduit_number.setSpecialValueText("Авто")
        self.segment_conduit_number.setToolTip(
            "Номер трубы; суффикс определяется типом. Существующий номер "
            "с тем же типом и цветом назначает участок в эту трубу."
        )
        existing_conduit = QPushButton("Выбрать трубу…", physical)
        existing_conduit.clicked.connect(self._choose_segment_conduit)
        save_segment = QPushButton("Сохранить выбранный участок", physical)
        save_segment.setObjectName("savePhysicalSegmentButton")
        save_segment.clicked.connect(self._save_segment_route)
        self.save_segment_button = save_segment
        self.save_segment_button.setEnabled(False)
        segment_editor = QHBoxLayout()
        segment_editor.addWidget(QLabel("Прокладка", physical))
        segment_editor.addWidget(self.segment_route_combo)
        segment_editor.addWidget(QLabel("Тип трубы", physical))
        segment_editor.addWidget(self.segment_gofra_type_edit)
        segment_editor.addWidget(QLabel("Цвет", physical))
        segment_editor.addWidget(self.segment_gofra_color_edit)
        physical_layout.addLayout(segment_editor)
        segment_editor = QHBoxLayout()
        segment_editor.addWidget(QLabel("Номер трубы", physical))
        segment_editor.addWidget(self.segment_conduit_number)
        segment_editor.addWidget(existing_conduit)
        segment_editor.addStretch()
        segment_editor.addWidget(save_segment)
        physical_layout.addLayout(segment_editor)
        physical_layout.addWidget(self.segment_gofra_id)

        self._segment_rows: list[dict] = []
        self._expanded_line_ids: set[str] = set()

        bottom.hide()
        physical.hide()
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setObjectName("linesHorizontalSplitter")
        self.splitter.addWidget(top)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.splitterMoved.connect(lambda *_: self._save_state())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self._build_view_menu()
        self.search.textChanged.connect(self.apply_filters)
        for combo in (
            self.system_filter,
            self.room_filter,
            self.board_filter,
            self.status_filter,
        ):
            combo.currentIndexChanged.connect(self.apply_filters)
        self.refresh()
        self._restore_state()

    def _build_view_menu(self) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self.view_button)
        self.column_actions = {}
        for index, column in enumerate(COLUMNS):
            action = QAction(column.title, menu)
            action.setCheckable(True)
            action.setChecked(column.default_visible)
            action.toggled.connect(
                lambda visible, logical=index: self._set_column_visible(logical, visible)
            )
            menu.addAction(action)
            self.column_actions[column.key] = action
        self.view_button.setMenu(menu)

    def refresh(
        self,
        *,
        selected_line_id: str | None = None,
        selected_line_ids: tuple[str, ...] | None = None,
    ) -> None:
        if selected_line_ids is None:
            selected_line_ids = self.selected_line_ids()
        if selected_line_id is None:
            selected_line_id = self.current_line_id()
        self._refreshing = True
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        try:
            self._cards = list(self.cables.line_cards(self.project_id)) if self.cables else []
            statuses = (
                self.status_service.line_statuses(self.project_id)
                if self.status_service is not None
                else {}
            )
            assignments = (
                self.constructor.list_cable_assignments(self.project_id)
                if self.constructor is not None
                else []
            )
            self._assignments_by_line = {}
            for assignment in assignments:
                self._assignments_by_line.setdefault(assignment["cable_line_id"], []).append(
                    assignment
                )
            for card in self._cards:
                status = statuses.get(card["id"])
                card["status_summary"] = status
                card["user_status"] = (
                    status.status.value if status is not None else "Требуется действие"
                )
                card["resource_labels"] = ", ".join(
                    assignment["user_label"]
                    for assignment in self._assignments_by_line.get(card["id"], [])
                )
            self._cards_by_id = {card["id"]: card for card in self._cards}
            self.table.setRowCount(len(self._cards))
            for row, card in enumerate(self._cards):
                for column, definition in enumerate(COLUMNS):
                    value = card.get(definition.key)
                    text = (
                        (_format_length(value) if value is not None else "Нужны данные")
                        if definition.key == "effective_m"
                        else ("" if value is None else str(value))
                    )
                    if value == "MIXED" and definition.key in {"mount_way", "gofra_id"}:
                        text = "По участкам"
                    item = (
                        CableMarkItem(value)
                        if definition.key == "cable_type"
                        else NaturalSortItem(text)
                    )
                    item.setData(Qt.ItemDataRole.UserRole, card["id"])
                    item.setData(Qt.ItemDataRole.UserRole + 1, definition.key)
                    flags = item.flags()
                    if definition.editable_field is None:
                        flags &= ~Qt.ItemFlag.ItemIsEditable
                        item.setForeground(QBrush(QColor("#424a52")))
                    item.setFlags(flags)
                    if definition.key == "resource_labels":
                        technical = ", ".join(
                            assignment["technical_identity"]
                            for assignment in self._assignments_by_line.get(card["id"], [])
                        )
                        item.setToolTip(technical)
                    if definition.key == "room_names":
                        markers = tuple(card.get("room_markers") or ())
                        item.setData(ROOM_MARKERS_ROLE, markers)
                        item.setToolTip("\n".join(marker["name"] for marker in markers))
                    self.table.setItem(row, column, item)
            self._populate_filter(self.system_filter, (card["system_kind"] for card in self._cards))
            self._populate_filter(self.room_filter, (card["room_names"] for card in self._cards))
            self._populate_filter(self.board_filter, (card["board"] for card in self._cards))
            self._populate_filter(self.status_filter, (card["user_status"] for card in self._cards))
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            self._refreshing = False
        self.apply_filters()
        visible_rows = [
            row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)
        ]
        visible_ids = {
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in visible_rows
        }
        surviving = set(selected_line_ids) & visible_ids
        if surviving:
            self.table.clearSelection()
            for row in range(self.table.rowCount()):
                line_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if line_id in surviving:
                    self.table.setRangeSelected(
                        QTableWidgetSelectionRange(row, 0, row, self.table.columnCount() - 1),
                        True,
                    )
            if selected_line_id in surviving:
                self.table.setCurrentCell(
                    next(
                        row
                        for row in range(self.table.rowCount())
                        if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        == selected_line_id
                    ),
                    0,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        elif selected_line_id in visible_ids:
            self.select_line(selected_line_id)
        elif visible_rows:
            self.table.setCurrentCell(visible_rows[0], 0)
        else:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self._update_card(None)
        self._highlight_current_row()

    @staticmethod
    def _populate_filter(combo: QComboBox, values) -> None:
        current = combo.currentData()
        unique = sorted({str(value) for value in values if str(value).strip()}, key=_natural_key)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все", "")
        for value in unique:
            combo.addItem(value, value)
        index = combo.findData(current)
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def apply_filters(self) -> None:
        needle = self.search.text().strip().casefold()
        system = str(self.system_filter.currentData() or "")
        room = str(self.room_filter.currentData() or "")
        board = str(self.board_filter.currentData() or "")
        status = str(self.status_filter.currentData() or "")
        visible_rows = []
        for row in range(self.table.rowCount()):
            line_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            card = self._cards_by_id[line_id]
            searchable = " ".join(
                str(card.get(key) or "")
                for key in (
                    "designation",
                    "load_name",
                    "room_names",
                    "board",
                    "user_status",
                )
            ).casefold()
            visible = (
                (not needle or needle in searchable)
                and (not system or card["system_kind"] == system)
                and (not room or card["room_names"] == room)
                and (not board or card["board"] == board)
                and (not status or card["user_status"] == status)
            )
            self.table.setRowHidden(row, not visible)
            if visible:
                visible_rows.append(row)
        current = self.table.currentRow()
        if not visible_rows or current not in visible_rows:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self._update_card(None)
            self._highlight_current_row()
        self._save_state()

    def current_line_id(self) -> str | None:
        item = self.table.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def selected_line_ids(self) -> tuple[str, ...]:
        ids = {
            index.data(Qt.ItemDataRole.UserRole)
            for index in self.table.selectedIndexes()
            if index.data(Qt.ItemDataRole.UserRole)
        }
        return tuple(
            sorted(
                ids,
                key=lambda value: _natural_key(self._cards_by_id[value]["designation"]),
            )
        )

    def select_line(self, line_id: str) -> bool:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == line_id:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                return True
        return False

    def _selection_changed(self) -> None:
        self._highlight_current_row()
        self._update_card(self.current_line_id())
        self._save_state()

    def _highlight_current_row(self) -> None:
        current = self.table.currentRow()
        context = QBrush(QColor("#e7f1fb"))
        clear = QBrush()
        signals_were_blocked = self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                for column in range(self.table.columnCount()):
                    item = self.table.item(row, column)
                    if item is not None:
                        item.setBackground(context if row == current else clear)
        finally:
            self.table.blockSignals(signals_were_blocked)

    def _update_card(self, line_id: str | None) -> None:
        card = self._cards_by_id.get(line_id)
        if card is None:
            self.card_title.setText("Линия не выбрана")
            for label in self.card_fields.values():
                label.setText("—")
            for button in self.single_buttons.values():
                button.setEnabled(False)
            self.open_resource.setEnabled(False)
            self.show_issue.setEnabled(False)
            self._clear_physical_route()
            return
        identity = f"{card['designation']} — {card['load_name'] or 'Потребитель не указан'}"
        self.card_title.setText(identity)
        self.card_fields["location"].setText(
            " / ".join(value for value in (card["building_names"], card["room_names"]) if value)
            or "Не указано"
        )
        self.card_fields["board"].setText(card["board"] or "Не указан")
        self.card_fields["cable"].setText(
            f"{format_cable_mark(card['cable_type']) or 'Марка не указана'}; "
            f"{card['load_type'] or 'классификация не указана'}"
        )
        mount_way = "По участкам" if card["mount_way"] == "MIXED" else card["mount_way"]
        gofra_id = "по участкам" if card["gofra_id"] == "MIXED" else card["gofra_id"]
        self.card_fields["route"].setText(
            f"{mount_way or 'Не указана'}; труба: {gofra_id or 'не назначена'}"
        )
        length = (
            "Не определена"
            if card["effective_m"] is None
            else f"{_format_length(card['effective_m'])} м"
        )
        self.card_fields["length"].setText(f"{length}; {card['length_mode']}")
        self.card_fields["resources"].setText(card["resource_labels"] or "Не назначены")
        status = card.get("status_summary")
        self.card_fields["status"].setText(card["user_status"])
        self.card_fields["status_reason"].setText(
            status.result if status is not None else "Проверьте данные и назначения"
        )
        self.card_fields["explanation"].setText(card["length_explanation"])
        assignments = self._assignments_by_line.get(line_id, [])
        has_target = len(assignments) == 1
        self.single_buttons[GuidedAction.OUTPUT].setEnabled(self.guided is not None)
        self.single_buttons[GuidedAction.POWER].setEnabled(self.guided is not None and has_target)
        self.single_buttons[GuidedAction.PROTECTION].setEnabled(
            self.guided is not None and has_target
        )
        for action in (GuidedAction.POWER, GuidedAction.PROTECTION):
            self.single_buttons[action].setToolTip(
                "" if has_target else "Сначала назначьте линии выход/канал"
            )
        self.open_resource.setEnabled(bool(assignments))
        self.show_issue.setEnabled(card["user_status"] != "Готово")
        self._load_physical_route(line_id)

    def _clear_physical_route(self) -> None:
        self._segment_rows = []
        self.segment_table.setRowCount(0)
        self.segment_summary.setText("Линия не выбрана")
        self.segment_gofra_id.setText("—")
        self.segment_gofra_type_edit.clear()
        self.segment_gofra_color_edit.clear()
        self.save_segment_button.setEnabled(False)

    def _load_physical_route(self, line_id: str) -> None:
        previous_segment = self.segment_table.currentRow()
        previous_id = (
            self._segment_rows[previous_segment]["segment_id"]
            if 0 <= previous_segment < len(self._segment_rows)
            else None
        )
        try:
            topology = self.cables.topology(self.project_id, line_id)
        except Exception as exc:
            self._segment_rows = []
            self.segment_table.setRowCount(0)
            self.segment_summary.setText(f"Не удалось прочитать физическую цепочку: {exc}")
            self.save_segment_button.setEnabled(False)
            return

        self._segment_rows = list(topology.get("edges") or ())
        self.segment_table.blockSignals(True)
        try:
            self.segment_table.setRowCount(len(self._segment_rows))
            for row_index, edge in enumerate(self._segment_rows):
                source = str((edge.get("source") or {}).get("label") or "Источник")
                target = str((edge.get("target") or {}).get("label") or "Точка")
                source = f"{'  ' * int(edge.get('depth') or 0)}{source}"
                status = (
                    "Готово"
                    if edge.get("calculation_status") == "READY"
                    else edge.get("calculation_reason") or "Длина не рассчитана"
                )
                values = (
                    source,
                    target,
                    edge.get("mount_way") or "Не указана",
                    edge.get("gofra_id") or "—",
                    _format_length(edge.get("physical_length_m")),
                    _format_length(edge.get("cable_length_m")),
                    status,
                    edge.get("gofra_type") or "—",
                    edge.get("gofra_color") or "—",
                    (_format_length(edge.get("conduit_length_m")) or "Не задана")
                    if edge.get("gofra_id")
                    else "—",
                    (edge.get("conduit_product_name") or "Товар трубы не выбран")
                    if edge.get("gofra_id")
                    else "—",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setData(Qt.ItemDataRole.UserRole, edge["segment_id"])
                    item.setToolTip(str(value))
                    self.segment_table.setItem(row_index, column, item)
        finally:
            self.segment_table.blockSignals(False)

        parts = []
        for item in topology.get("route_breakdown") or ():
            physical_m = _format_length(item.get("physical_m"))
            cable_m = _format_length(item.get("cable_m"))
            incomplete = int(item.get("incomplete_segments") or 0)
            text = f"{item['mount_way']}: трасса {physical_m} м, кабель {cable_m} м"
            if incomplete:
                text += f", не рассчитано участков: {incomplete}"
            parts.append(text)
        reserve = _format_length(topology.get("board_reserve_m"))
        additional = _format_length(topology.get("additional_m"))
        if reserve not in {"", "0"}:
            parts.append(f"Запас кабеля у щита: {reserve} м")
        if additional not in {"", "0"}:
            parts.append(f"Дополнительная длина кабеля: {additional} м")
        if topology.get("manual_full_m") is not None:
            parts.append(
                f"Полная ручная длина линии: {_format_length(topology['manual_full_m'])} м"
            )
        self.segment_summary.setText(
            " | ".join(parts) if parts else "Физические участки не построены"
        )
        if self._segment_rows:
            self.segment_table.selectRow(
                next(
                    (
                        i
                        for i, edge in enumerate(self._segment_rows)
                        if edge["segment_id"] == previous_id
                    ),
                    0,
                )
            )
            self._segment_selection_changed()
        else:
            self.save_segment_button.setEnabled(False)

    def _segment_selection_changed(self) -> None:
        row = self.segment_table.currentRow()
        if row < 0 or row >= len(self._segment_rows):
            self.save_segment_button.setEnabled(False)
            return
        edge = self._segment_rows[row]
        route_index = self.segment_route_combo.findText(str(edge.get("mount_way") or ""))
        self.segment_route_combo.setCurrentIndex(max(route_index, 0))
        self.segment_gofra_type_edit.setText(str(edge.get("gofra_type") or ""))
        self.segment_gofra_color_edit.setText(str(edge.get("gofra_color") or ""))
        product = str(edge.get("conduit_product_name") or "")
        article = str(edge.get("conduit_product_article") or "")
        conduit = str(edge.get("gofra_id") or "—")
        self.segment_conduit_number.setValue(
            int(conduit.split(".")[0]) if conduit[:1].isdigit() else -1
        )
        if product:
            conduit += f" · {product}"
            if article:
                conduit += f" · арт. {article}"
        self.segment_gofra_id.setText(
            f"Труба: {conduit}"
            + (" · Товар трубы не выбран" if not product and edge.get("gofra_id") else "")
        )
        self.save_segment_button.setEnabled(True)

    def _save_segment_route(self) -> None:
        row = self.segment_table.currentRow()
        line_id = self.current_line_id()
        if row < 0 or row >= len(self._segment_rows) or line_id is None:
            return
        edge = self._segment_rows[row]
        try:
            conduit_type = self.segment_gofra_type_edit.text().strip()
            number = self.segment_conduit_number.value()
            self.cables.update_segment_route(
                project_id=self.project_id,
                cable_segment_id=edge["segment_id"],
                route_method=RouteMethod(self.segment_route_combo.currentData()),
                conduit_type=self.segment_gofra_type_edit.text(),
                conduit_color=self.segment_gofra_color_edit.text(),
                conduit_designation=format_conduit_id(number, conduit_type)
                if number >= 0 and conduit_type
                else "",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Участок не сохранён", str(exc))
            return
        self.refresh(selected_line_id=line_id)
        self.projectChanged.emit()

    def _choose_segment_conduit(self) -> None:
        conduits = self.cables.list_conduits(self.project_id)
        labels = [
            f"{row['designation']} · {row['conduit_type']} · {row['color'] or 'цвет не задан'}"
            for row in conduits
        ]
        if not labels:
            QMessageBox.information(
                self, "Трубы", "Труб пока нет. Укажите тип и новый номер либо оставьте «Авто»."
            )
            return
        label, accepted = QInputDialog.getItem(
            self, "Назначение выбранного участка", "Труба", labels, editable=False
        )
        if accepted:
            row = conduits[labels.index(label)]
            self.segment_conduit_number.setValue(row["conduit_number"])
            self.segment_gofra_type_edit.setText(row["conduit_type"])
            self.segment_gofra_color_edit.setText(row["color"] or "")

    def _recalculate_selected_line(self) -> None:
        line_id = self.current_line_id()
        if line_id is None:
            return
        try:
            self.cables.recalculate(project_id=self.project_id, cable_line_ids={line_id})
        except Exception as exc:
            QMessageBox.warning(self, "Пересчёт не выполнен", str(exc))
            return
        self.refresh(selected_line_id=line_id)
        self.projectChanged.emit()

    def _show_project_route_breakdown(self) -> None:
        report = self.cables.project_route_breakdown(self.project_id)
        dialog = QDialog(self)
        dialog.setWindowTitle("Метры по способам прокладки — весь объект")
        dialog.resize(780, 420)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(report["routes"]), 4, dialog)
        table.setHorizontalHeaderLabels(
            ["Прокладка", "Физическая трасса, м", "Кабель участков, м", "Не рассчитано участков"]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for index, row in enumerate(report["routes"]):
            for column, key in enumerate(
                ("mount_way", "physical_m", "cable_m", "incomplete_segments")
            ):
                table.setItem(index, column, QTableWidgetItem(str(row[key])))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        note = QLabel(
            f"Итог кабеля по рассчитанным линиям: {report['effective_m']} м. "
            f"Неполных линий: {report['incomplete_lines']}.\n"
            "Метры участков включают запас 0,5 м в брусе. Запас у щита, "
            "дополнительная и полная ручная длина учитываются в итоге линии; "
            "по способам прокладки не распределяются.",
            dialog,
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._refreshing:
            return
        column = COLUMNS[item.column()]
        if column.editable_field is None:
            return
        self._apply_edits(
            [
                {
                    "cable_line_id": item.data(Qt.ItemDataRole.UserRole),
                    "field": column.editable_field,
                    "value": item.data(Qt.ItemDataRole.EditRole),
                }
            ]
        )

    def _apply_edits(self, edits: list[dict]) -> bool:
        selected = self.current_line_id()
        selected_ids = self.selected_line_ids()
        try:
            self.cables.batch_update_line_fields(project_id=self.project_id, edits=edits)
        except Exception as exc:
            QMessageBox.warning(self, "Изменения не применены", str(exc))
            self.refresh(selected_line_id=selected, selected_line_ids=selected_ids)
            return False
        self.refresh(selected_line_id=selected, selected_line_ids=selected_ids)
        self.projectChanged.emit()
        return True

    def copy_selection(self) -> str:
        indexes = self.table.selectedIndexes()
        if not indexes:
            return ""
        rows = sorted({index.row() for index in indexes})
        columns = sorted(
            {index.column() for index in indexes},
            key=self.table.horizontalHeader().visualIndex,
        )
        selected = {(index.row(), index.column()) for index in indexes}
        text = "\n".join(
            "\t".join(
                self.table.item(row, column).text() if (row, column) in selected else ""
                for column in columns
            )
            for row in rows
        )
        QApplication.clipboard().setText(text)
        return text

    def paste_clipboard(self) -> bool:
        return self.paste_text(QApplication.clipboard().text())

    def paste_text(self, text: str) -> bool:
        anchor = self.table.currentIndex()
        if not anchor.isValid():
            return False
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        matrix = [line.split("\t") for line in lines]
        if not matrix or any(len(row) != len(matrix[0]) for row in matrix):
            QMessageBox.warning(self, "Вставка не выполнена", "Буфер не является прямоугольником")
            return False
        visible_columns = sorted(
            (
                column
                for column in range(self.table.columnCount())
                if not self.table.isColumnHidden(column)
            ),
            key=self.table.horizontalHeader().visualIndex,
        )
        try:
            visual_anchor = visible_columns.index(anchor.column())
        except ValueError:
            return False
        rows_overflow = anchor.row() + len(matrix) > self.table.rowCount()
        columns_overflow = visual_anchor + len(matrix[0]) > len(visible_columns)
        if rows_overflow or columns_overflow:
            QMessageBox.warning(self, "Вставка не выполнена", "Диапазон выходит за границы таблицы")
            return False
        edits = []
        for row_offset, values in enumerate(matrix):
            target_row = anchor.row() + row_offset
            if self.table.isRowHidden(target_row):
                QMessageBox.warning(self, "Вставка не выполнена", "Скрытые строки не изменяются")
                return False
            for column_offset, value in enumerate(values):
                target_column = visible_columns[visual_anchor + column_offset]
                definition = COLUMNS[target_column]
                if definition.editable_field is None:
                    QMessageBox.warning(
                        self,
                        "Вставка не выполнена",
                        f"Колонка «{definition.title}» доступна только для чтения",
                    )
                    return False
                edits.append(
                    {
                        "cable_line_id": self.table.item(target_row, 0).data(
                            Qt.ItemDataRole.UserRole
                        ),
                        "field": definition.editable_field,
                        "value": value,
                    }
                )
        return self._apply_edits(edits)

    def fill_down(self) -> bool:
        indexes = self.table.selectedIndexes()
        if len(indexes) < 2:
            return False
        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        if rows != list(range(rows[0], rows[-1] + 1)):
            QMessageBox.warning(self, "Заполнение не выполнено", "Выберите непрерывный диапазон")
            return False
        edits = []
        for column in columns:
            definition = COLUMNS[column]
            if definition.editable_field is None:
                QMessageBox.warning(
                    self,
                    "Заполнение не выполнено",
                    f"Колонка «{definition.title}» доступна только для чтения",
                )
                return False
            source = self.table.item(rows[0], column).text()
            for row in rows[1:]:
                edits.append(
                    {
                        "cable_line_id": self.table.item(row, 0).data(Qt.ItemDataRole.UserRole),
                        "field": definition.editable_field,
                        "value": source,
                    }
                )
        return bool(edits) and self._apply_edits(edits)

    def bulk_edit_selected_rows(self, *, value: str | None = None) -> bool:
        column_index = self.table.currentColumn()
        if column_index < 0 or COLUMNS[column_index].editable_field is None:
            QMessageBox.information(
                self,
                "Массовое изменение",
                "Выберите изменяемую колонку BOARD или CABLE_TYPE",
            )
            return False
        line_ids = self.selected_line_ids()
        if not line_ids:
            return False
        if value is None:
            value, accepted = QInputDialog.getText(
                self,
                "Массовое изменение",
                f"Новое значение «{COLUMNS[column_index].title}»",
            )
            if not accepted:
                return False
        edits = [
            {
                "cable_line_id": line_id,
                "field": COLUMNS[column_index].editable_field,
                "value": value,
            }
            for line_id in line_ids
        ]
        return self._apply_edits(edits)

    def _move_editable(self, direction: int) -> None:
        editable = [
            (row, column)
            for row in range(self.table.rowCount())
            if not self.table.isRowHidden(row)
            for column, definition in enumerate(COLUMNS)
            if definition.editable_field is not None and not self.table.isColumnHidden(column)
        ]
        if not editable:
            return
        current = (self.table.currentRow(), self.table.currentColumn())
        try:
            position = editable.index(current)
        except ValueError:
            position = -1 if direction > 0 else 0
        target = editable[(position + direction) % len(editable)]
        self.table.setCurrentCell(*target)

    def run_guided_action(self, action: GuidedAction) -> None:
        line_id = self.current_line_id()
        if line_id is None or self.guided is None:
            return
        if action == GuidedAction.OUTPUT:
            owner_id = line_id
        else:
            assignments = self._assignments_by_line.get(line_id, [])
            if len(assignments) != 1:
                QMessageBox.information(
                    self, action.label, "Сначала назначьте линии один выход/канал"
                )
                return
            owner_id = assignments[0]["output_resource_id"]
        dialog = GuidedActionDialog(self.guided, action, self.project_id, owner_id, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh(selected_line_id=line_id)
            self.projectChanged.emit()

    def run_bulk_action(self, action: GuidedAction) -> None:
        line_ids = self.selected_line_ids()
        if not line_ids or self.bulk is None:
            return
        if action == GuidedAction.OUTPUT:
            owner_ids = line_ids
        else:
            owner_ids = []
            for line_id in line_ids:
                assignments = self._assignments_by_line.get(line_id, [])
                if len(assignments) != 1:
                    QMessageBox.information(
                        self,
                        action.label,
                        f"Для {self._cards_by_id[line_id]['designation']} "
                        "сначала назначьте выход/канал",
                    )
                    return
                owner_ids.append(assignments[0]["output_resource_id"])
        dialog = BulkActionDialog(self.bulk, action, self.project_id, owner_ids, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh(selected_line_id=self.current_line_id())
            self.projectChanged.emit()

    def _open_related_resource(self) -> None:
        assignments = self._assignments_by_line.get(self.current_line_id(), [])
        if assignments:
            self._save_state()
            self.resourceRequested.emit(assignments[0]["output_resource_id"])

    def _show_issue(self) -> None:
        line_id = self.current_line_id()
        if line_id:
            self.issueRequested.emit(line_id)

    def _set_column_visible(self, logical: int, visible: bool) -> None:
        self.table.setColumnHidden(logical, not visible)
        self._save_state()

    def _project_state(self) -> tuple[dict, dict]:
        state = self.ui_state.load() if self.ui_state is not None else {"version": 1}
        workspace = dict(state.get("lines_workspace") or {})
        projects = dict(workspace.get("projects") or {})
        return workspace, dict(projects.get(self.project_id) or {})

    def _save_state(self) -> None:
        if self.ui_state is None or self._restoring or self._refreshing:
            return
        workspace, _project_state = self._project_state()
        state = {
            "search": self.search.text(),
            "system": self.system_filter.currentData() or "",
            "room": self.room_filter.currentData() or "",
            "board": self.board_filter.currentData() or "",
            "status": self.status_filter.currentData() or "",
            "selected_line_id": self.current_line_id(),
            "vertical_scroll": self.table.verticalScrollBar().value(),
            "horizontal_scroll": self.table.horizontalScrollBar().value(),
            "splitter_sizes": self.splitter.sizes(),
            "layout_version": LINES_LAYOUT_VERSION,
            "sort_column": COLUMNS[self.table.horizontalHeader().sortIndicatorSection()].key,
            "sort_order": int(self.table.horizontalHeader().sortIndicatorOrder().value),
            "columns": {
                column.key: {
                    "visual": self.table.horizontalHeader().visualIndex(index),
                    "width": self.table.columnWidth(index),
                    "visible": not self.table.isColumnHidden(index),
                }
                for index, column in enumerate(COLUMNS)
            },
        }
        projects = dict(workspace.get("projects") or {})
        projects[self.project_id] = state
        workspace["projects"] = projects
        self.ui_state.update(lines_workspace=workspace)

    def _restore_state(self) -> None:
        if self.ui_state is None:
            self._apply_default_layout()
            self.table.sortItems(_column_index("designation"), Qt.SortOrder.AscendingOrder)
            return
        self._restoring = True
        try:
            _workspace, state = self._project_state()
            self.search.setText(str(state.get("search") or ""))
            for combo, key in (
                (self.system_filter, "system"),
                (self.room_filter, "room"),
                (self.board_filter, "board"),
                (self.status_filter, "status"),
            ):
                index = combo.findData(state.get(key, ""))
                combo.setCurrentIndex(max(index, 0))
            layout_current = state.get("layout_version") == LINES_LAYOUT_VERSION
            columns = dict(state.get("columns") or {}) if layout_current else {}
            for logical, column in enumerate(COLUMNS):
                saved = dict(columns.get(column.key) or {})
                width = saved.get("width")
                if isinstance(width, int) and width > 20:
                    self.table.setColumnWidth(logical, width)
                elif not columns:
                    self.table.setColumnWidth(logical, _DEFAULT_COLUMN_WIDTHS[column.key])
                visible = saved.get("visible", column.default_visible)
                self.table.setColumnHidden(logical, not bool(visible))
                self.column_actions[column.key].setChecked(bool(visible))
            ordered = sorted(
                (
                    (
                        dict(columns.get(column.key) or {}).get("visual", logical),
                        logical,
                    )
                    for logical, column in enumerate(COLUMNS)
                )
            )
            for target_visual, (_saved_visual, logical) in enumerate(ordered):
                current_visual = self.table.horizontalHeader().visualIndex(logical)
                self.table.horizontalHeader().moveSection(current_visual, target_visual)
            sort_key = state.get("sort_column", "designation")
            sort_column = next(
                (index for index, column in enumerate(COLUMNS) if column.key == sort_key),
                0,
            )
            order_value = state.get("sort_order", int(Qt.SortOrder.AscendingOrder.value))
            order = (
                Qt.SortOrder.DescendingOrder
                if order_value == int(Qt.SortOrder.DescendingOrder.value)
                else Qt.SortOrder.AscendingOrder
            )
            self.table.sortItems(sort_column, order)
            sizes = state.get("splitter_sizes")
            valid_sizes = (
                isinstance(sizes, list)
                and len(sizes) == 3
                and all(isinstance(value, int) for value in sizes)
            )
            if valid_sizes and layout_current:
                self.splitter.setSizes(sizes)
            else:
                self.splitter.setSizes([460, 180, 360])
            selected = state.get("selected_line_id")
            if selected in self._cards_by_id:
                self.select_line(selected)
            self.apply_filters()
            self.table.verticalScrollBar().setValue(int(state.get("vertical_scroll", 0)))
            self.table.horizontalScrollBar().setValue(int(state.get("horizontal_scroll", 0)))
        finally:
            self._restoring = False

    def _apply_default_layout(self) -> None:
        for logical, column in enumerate(COLUMNS):
            self.table.setColumnWidth(logical, _DEFAULT_COLUMN_WIDTHS[column.key])
            self.table.setColumnHidden(logical, not column.default_visible)
            self.column_actions[column.key].setChecked(column.default_visible)
        self.splitter.setSizes([460, 180, 360])

    def save_state(self) -> None:
        self._save_state()
