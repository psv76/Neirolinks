from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace
from nl_project_2.presentation.room_presentation import (
    ROOM_MARKERS_ROLE,
    RoomChipDelegate,
)


class _RecordingDelegate(RoomChipDelegate):
    def __init__(self):
        super().__init__()
        self.base_options = []
        self.chip_names = []

    def _paint_base_without_text(self, painter, option):
        self.base_options.append(QStyleOptionViewItem(option))

    def _draw_chip(self, painter, rect, marker):
        self.chip_names.append(str(marker.get("name") or ""))


class _PainterStub:
    def save(self):
        pass

    def restore(self):
        pass


def _paint_room_cell(markers, *, selected=False):
    table = QTableWidget(1, 1)
    item = QTableWidgetItem(", ".join(marker["name"] for marker in markers))
    item.setData(ROOM_MARKERS_ROLE, tuple(markers))
    table.setItem(0, 0, item)
    option = QStyleOptionViewItem()
    option.initFrom(table)
    option.widget = table
    option.rect = QRect(0, 0, 320, 34)
    if selected:
        option.state |= QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_Active
    painter = _PainterStub()
    delegate = _RecordingDelegate()
    delegate.paint(painter, option, table.model().index(0, 0))
    return delegate.base_options, delegate.chip_names


def test_room_marker_delegate_does_not_ask_base_style_to_paint_raw_text(qapp):
    markers = ({"name": "1. Прихожая", "color": "#D7E3FC"},)
    base_options, chip_names = _paint_room_cell(markers)
    assert [option.text for option in base_options] == [""]
    assert chip_names == ["1. Прихожая"]


def test_multiple_room_markers_and_selected_cell_have_no_underlying_text(qapp):
    markers = (
        {"name": "1. Прихожая", "color": "#D7E3FC"},
        {"name": "5. Кухня-ниша", "color": "#FEEFC3"},
    )
    base_options, chip_names = _paint_room_cell(markers, selected=True)
    assert [option.text for option in base_options] == [""]
    assert base_options[0].state & QStyle.StateFlag.State_Selected
    assert chip_names == ["1. Прихожая", "5. Кухня-ниша"]


class _CableStub:
    def line_cards(self, _project_id):
        return []


class _ConstructorStub:
    def list_cable_assignments(self, _project_id):
        return []


def test_lines_header_is_single_level_and_manually_resizable(qtbot):
    widget = LinesWorkspace(_CableStub(), _ConstructorStub(), "project")
    qtbot.addWidget(widget)
    widget.resize(760, 520)
    widget.show()
    qtbot.wait(10)
    header = widget.table.horizontalHeader()
    assert header.sectionResizeMode(0) == header.ResizeMode.Interactive
    original = widget.table.columnWidth(5)
    widget.table.setColumnWidth(5, original + 37)
    assert widget.table.columnWidth(5) == original + 37
    assert [COLUMNS[i].title for i in range(9)] == [
        "Здание",
        "Источник",
        "Помещение",
        "ID",
        "Назначение",
        "Марка кабеля",
        "Прокладка",
        "Труба",
        "Длина, м",
    ]
