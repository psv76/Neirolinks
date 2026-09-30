from __future__ import annotations

from PySide6.QtCore import Qt

from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace
from nl_project_2.presentation.room_presentation import (
    ROOM_MARKERS_ROLE,
    RoomChipDelegate,
    RoomColorComboBox,
)


class CableStub:
    def line_cards(self, _project_id):
        return [
            {
                "id": "line-1",
                "designation": "101",
                "system_kind": "POWER",
                "load_name": "Розетки",
                "cable_type": "3x1,5",
                "board": "B.01",
                "building_names": "Дом",
                "room_names": "1. Прихожая, 4. Гостиная",
                "room_markers": (
                    {"id": "r1", "name": "1. Прихожая", "color": "#D7E3FC"},
                    {"id": "r4", "name": "4. Гостиная", "color": "#FAD2CF"},
                ),
                "mount_way": "По полу",
                "gofra_id": "001.PND25",
                "effective_m": "12.5",
                "load_type": "SOCKET_LIVING_LOW",
                "length_mode": "Автоматическая",
                "length_explanation": "Расчёт",
            }
        ]


class ConstructorStub:
    def list_cable_assignments(self, _project_id):
        return []


def test_lines_keep_repair02_layout_and_present_room_chips(qtbot):
    widget = LinesWorkspace(CableStub(), ConstructorStub(), "project")
    qtbot.addWidget(widget)
    room_column = next(
        index for index, column in enumerate(COLUMNS) if column.key == "room_names"
    )
    item = widget.table.item(0, room_column)
    assert item.text() == "1. Прихожая, 4. Гостиная"
    assert len(item.data(ROOM_MARKERS_ROLE)) == 2
    assert "4. Гостиная" in item.toolTip()
    assert isinstance(widget.table.itemDelegateForColumn(room_column), RoomChipDelegate)
    assert [column.group for column in COLUMNS[:9]] == [
        "ОТКУДА",
        "ОТКУДА",
        "КУДА",
        "КТО",
        "КТО",
        "ФИЗИКА",
        "ФИЗИКА",
        "ФИЗИКА",
        "ФИЗИКА",
    ]
    widget.table.selectRow(0)
    assert item.isSelected()


def test_room_color_control_is_fixed_palette_not_raw_hex_editor(qtbot):
    combo = RoomColorComboBox()
    qtbot.addWidget(combo)
    combo.set_color("#D7E3FC")
    assert combo.color() == "#D7E3FC"
    assert combo.count() >= 9
    assert combo.findData("#D7E3FC", Qt.ItemDataRole.UserRole) >= 0
