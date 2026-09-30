from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetSelectionRange

from nl_project_2.local_state import UiStateStore
from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace


def _card(
    line_id: str,
    designation: str,
    load_name: str,
    *,
    room: str,
    board: str,
    system: str = "POWER",
) -> dict:
    return {
        "id": line_id,
        "designation": designation,
        "load_name": load_name,
        "load_type": "SOCKET",
        "board": board,
        "building_names": "Дом",
        "room_names": room,
        "system_kind": system,
        "cable_type": "3x2,5",
        "mount_way": "По полу",
        "gofra_id": "001.PND25",
        "effective_m": "12.5",
        "length_mode": "Автоматическая",
        "length_explanation": "Сумма уникальных физических сегментов",
    }


class FakeCableService:
    def __init__(self):
        self.cards = [
            _card("line-2", "2", "Кухонные розетки", room="Кухня", board="ЩР-1"),
            _card("line-10", "10", "Свет гостиной", room="Гостиная", board="ЩР-2"),
            _card("line-1", "1", "Розетка холла", room="Холл", board="ЩР-1"),
        ]
        self.calls = []

    def line_cards(self, _project_id):
        return deepcopy(self.cards)

    def batch_update_line_fields(self, *, project_id, edits):
        edits = tuple(deepcopy(tuple(edits)))
        if any(edit["value"] == "BAD" for edit in edits):
            raise ValueError("Недопустимое значение")
        self.calls.append((project_id, edits))
        by_id = {card["id"]: card for card in self.cards}
        field_map = {"BOARD": "board", "CABLE_TYPE": "cable_type"}
        for edit in edits:
            by_id[edit["cable_line_id"]][field_map[edit["field"]]] = edit["value"]


class FakeConstructor:
    @staticmethod
    def list_cable_assignments(_project_id):
        return [
            {
                "id": "assignment-1",
                "cable_line_id": "line-1",
                "cable_designation": "1",
                "output_resource_id": "resource-1",
                "project_instance_id": "instance-1",
                "user_label": "A01 / Channel1",
                "technical_identity": "A01 / PWM_OUTPUT[0]",
            }
        ]


def _column(key: str) -> int:
    return next(index for index, column in enumerate(COLUMNS) if column.key == key)


def _row(workspace, line_id: str) -> int:
    return next(
        row
        for row in range(workspace.table.rowCount())
        if workspace.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == line_id
    )


def test_lines_layout_identity_search_natural_sort_and_bottom_card(qtbot):
    workspace = LinesWorkspace(FakeCableService(), FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()

    assert workspace.splitter.orientation() == Qt.Orientation.Vertical
    assert workspace.splitter.widget(0).findChild(type(workspace.table)) is workspace.table
    assert workspace.splitter.widget(1).objectName() == "lineBottomCard"
    designation = _column("designation")
    assert [workspace.table.item(row, designation).text() for row in range(3)] == [
        "1",
        "2",
        "10",
    ]
    workspace.search.setText("кухонные")
    assert sum(not workspace.table.isRowHidden(row) for row in range(3)) == 1
    workspace.search.setText("ЩР-2")
    assert sum(not workspace.table.isRowHidden(row) for row in range(3)) == 1
    workspace.search.clear()
    workspace.select_line("line-1")
    assert "1 — Розетка холла" in workspace.card_title.text()
    assert workspace.card_fields["resources"].text() == "A01 / Channel1"
    assert "Автоматическая" in workspace.card_fields["length"].text()
    assert workspace.table.item(_row(workspace, "line-1"), _column("load_type")).text() == (
        "SOCKET"
    )


def test_copy_paste_fill_down_bulk_edit_and_read_only_rejection(qtbot, monkeypatch):
    service = FakeCableService()
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

    board_column = _column("board")
    cable_column = _column("cable_type")
    first_row = _row(workspace, "line-1")
    workspace.table.clearSelection()
    workspace.table.setRangeSelected(
        QTableWidgetSelectionRange(first_row, board_column, first_row, cable_column), True
    )
    copied = workspace.copy_selection()
    assert copied == "ЩР-1\tХолл\t1\tРозетка холла\tВВГнг(А)-LS 3х2,5"

    for key in ("room_names", "designation", "load_name"):
        workspace.table.setColumnHidden(_column(key), True)
    workspace.table.setCurrentCell(_row(workspace, "line-2"), board_column)
    assert workspace.paste_text("ЩР-9\t5x2,5")
    assert len(service.calls[-1][1]) == 2
    calls_before = len(service.calls)
    workspace.table.setCurrentCell(_row(workspace, "line-2"), _column("load_name"))
    assert not workspace.paste_text("Нельзя")
    assert len(service.calls) == calls_before

    workspace.table.clearSelection()
    workspace.table.setRangeSelected(
        QTableWidgetSelectionRange(0, board_column, 2, board_column), True
    )
    source_value = workspace.table.item(0, board_column).text()
    assert workspace.fill_down()
    assert all(card["board"] == source_value for card in service.cards)

    workspace.table.clearSelection()
    workspace.table.setCurrentCell(0, cable_column)
    workspace.table.setRangeSelected(
        QTableWidgetSelectionRange(0, cable_column, 1, cable_column), True
    )
    assert workspace.bulk_edit_selected_rows(value="4x1,5")
    assert sum(card["cable_type"] == "4x1,5" for card in service.cards) == 2


def test_keyboard_path_multi_selection_refresh_and_state_restore(qtbot, tmp_path):
    service = FakeCableService()
    store = UiStateStore(tmp_path / "state")
    workspace = LinesWorkspace(service, FakeConstructor(), "project", ui_state=store)
    qtbot.addWidget(workspace)
    workspace.show()
    board_column = _column("board")

    workspace.table.setCurrentCell(0, 0)
    qtbot.keyClick(workspace.table, Qt.Key.Key_Tab)
    assert workspace.table.currentColumn() == board_column
    qtbot.keyClick(workspace.table, Qt.Key.Key_Backtab)
    assert COLUMNS[workspace.table.currentColumn()].editable_field is not None
    workspace.table.clearSelection()
    workspace.table.setRangeSelected(
        QTableWidgetSelectionRange(0, board_column, 1, board_column), True
    )
    before = set(workspace.selected_line_ids())
    workspace.refresh()
    assert set(workspace.selected_line_ids()) == before

    workspace.search.setText("розетка")
    workspace.table.setColumnWidth(board_column, 177)
    workspace.table.horizontalHeader().moveSection(
        workspace.table.horizontalHeader().visualIndex(board_column), 1
    )
    workspace.column_actions["load_type"].setChecked(False)
    workspace.select_line("line-1")
    workspace.splitter.setSizes([420, 180])
    workspace.save_state()

    reopened = LinesWorkspace(service, FakeConstructor(), "project", ui_state=store)
    qtbot.addWidget(reopened)
    reopened.show()
    qtbot.wait(10)
    assert reopened.search.text() == "розетка"
    assert reopened.table.columnWidth(board_column) == 177
    assert reopened.table.isColumnHidden(_column("load_type"))
    assert reopened.table.horizontalHeader().visualIndex(board_column) == 1
    assert reopened.current_line_id() == "line-1"
    assert reopened.splitter.sizes()[0] > reopened.splitter.sizes()[1]


def test_project_scoped_state_and_stale_identity_clear_safely(qtbot, tmp_path):
    store = UiStateStore(tmp_path / "state")
    store.update(
        lines_workspace={
            "projects": {
                "project-a": {"selected_line_id": "missing", "search": "Кухня"},
                "project-b": {"selected_line_id": "line-10", "search": "Гостиная"},
            }
        }
    )
    first = LinesWorkspace(FakeCableService(), FakeConstructor(), "project-a", ui_state=store)
    second = LinesWorkspace(FakeCableService(), FakeConstructor(), "project-b", ui_state=store)
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    assert first.search.text() == "Кухня"
    assert first.current_line_id() != "missing"
    assert second.search.text() == "Гостиная"
    assert second.current_line_id() == "line-10"
