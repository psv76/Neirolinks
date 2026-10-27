from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QTableWidget, QTableWidgetSelectionRange

from nl_project_2.local_state import UiStateStore
from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace
from nl_project_2.presentation.physical_tree import (
    compact_physical_edge_rows,
    physical_edge_layout,
)


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
        "conduit_count": 1,
        "incomplete_segments": 0,
        "known_segment_m": "12.5",
        "unresolved_room_names": (),
    }


class FakeCableService:
    def __init__(self):
        self.cards = [
            _card("line-2", "2", "Кухонные розетки", room="Кухня", board="ЩР-1"),
            _card("line-10", "10", "Свет гостиной", room="Гостиная", board="ЩР-2"),
            _card("line-1", "1", "Розетка холла", room="Холл", board="ЩР-1"),
        ]
        self.calls = []
        self.segment_calls = []

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

    def topology(self, _project_id, cable_line_id):
        card = next(card for card in self.cards if card["id"] == cable_line_id)
        return {
            "cable_line_id": cable_line_id,
            "designation": card["designation"],
            "root_endpoint": {"label": f"Щит {card['board']}"},
            "edges": (
                {
                    "segment_id": f"segment-{cable_line_id}",
                    "depth": 0,
                    "source": {"label": f"Щит {card['board']}"},
                    "target": {
                        "label": f"{card['designation']}.01",
                        "point_kind": "DEVICE_POINT",
                        "description": card["load_name"],
                        "room_names": card["room_names"],
                        "building_names": card["building_names"],
                        "room_unresolved": False,
                    },
                    "mount_way": "По полу",
                    "gofra_type": "ПНД25",
                    "gofra_color": "Синий",
                    "gofra_id": "001.PND25",
                    "physical_length_m": "10",
                    "cable_length_m": "10",
                    "calculation_status": "READY",
                    "calculation_reason": "",
                    "conduit_product_name": "",
                    "conduit_product_article": "",
                },
            ),
            "route_breakdown": (
                {
                    "mount_way": "По полу",
                    "physical_m": "10",
                    "cable_m": "10",
                    "incomplete_segments": 0,
                },
            ),
            "board_reserve_m": "1.5",
            "additional_m": "0",
            "manual_full_m": None,
        }

    def update_segment_route(
        self,
        *,
        project_id,
        cable_segment_id,
        route_method,
        conduit_type="",
        conduit_color="",
        conduit_designation=None,
    ):
        self.segment_calls.append(
            (project_id, cable_segment_id, route_method, conduit_type, conduit_color)
        )


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


def test_lines_layout_identity_search_natural_sort_and_clean_main_workspace(qtbot):
    workspace = LinesWorkspace(FakeCableService(), FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()

    assert workspace.splitter.orientation() == Qt.Orientation.Vertical
    assert workspace.splitter.widget(0).findChild(type(workspace.table)) is workspace.table
    assert workspace.splitter.count() == 1
    designation = _column("designation")
    assert [workspace.table.item(row, designation).text() for row in range(3)] == [
        "▸ 1",
        "▸ 2",
        "▸ 10",
    ]
    workspace.search.setText("кухонные")
    assert sum(not workspace.table.isRowHidden(row) for row in range(3)) == 1
    workspace.search.setText("ЩР-2")
    assert sum(not workspace.table.isRowHidden(row) for row in range(3)) == 1
    workspace.search.clear()
    workspace.select_line("line-1")
    assert not workspace.card_title.isVisible()
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
    workspace.resize(1440, 1000)
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
    workspace.save_state()

    reopened = LinesWorkspace(service, FakeConstructor(), "project", ui_state=store)
    qtbot.addWidget(reopened)
    reopened.resize(1440, 1000)
    reopened.show()
    qtbot.wait(10)
    assert reopened.search.text() == "розетка"
    assert reopened.table.columnWidth(board_column) == 177
    assert reopened.table.isColumnHidden(_column("load_type"))
    assert reopened.table.horizontalHeader().visualIndex(board_column) == 1
    assert reopened.current_line_id() == "line-1"
    assert reopened.splitter.count() == 1


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


def test_selected_line_shows_physical_segments_breakdown_and_edits_exact_segment(qtbot):
    service = FakeCableService()
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()

    workspace.select_line("line-1")
    assert workspace.segment_table.rowCount() == 1
    assert workspace.segment_table.item(0, 0).text() == "Щит ЩР-1"
    assert workspace.segment_table.item(0, 1).text() == "1.01"
    assert workspace.segment_table.item(0, 3).text() == "001.PND25"
    assert "По полу: трасса 10 м, кабель 10 м" in workspace.segment_summary.text()
    assert "Запас кабеля у щита: 1.5 м" in workspace.segment_summary.text()

    workspace.segment_table.selectRow(0)
    wall_index = workspace.segment_route_combo.findText("В стене")
    workspace.segment_route_combo.setCurrentIndex(wall_index)
    workspace.segment_gofra_type_edit.clear()
    workspace.segment_gofra_color_edit.clear()
    workspace._save_segment_route()

    assert service.segment_calls
    project_id, segment_id, route_method, conduit_type, conduit_color = service.segment_calls[-1]
    assert project_id == "project"
    assert segment_id == "segment-line-1"
    assert route_method.value == "WALL"
    assert conduit_type == ""
    assert conduit_color == ""


def test_local_warning_click_keeps_exact_cell_and_segment_context(qtbot):
    service = FakeCableService()
    card = next(item for item in service.cards if item["id"] == "line-1")
    card["room_names"] = "Дет. ванная 2"
    card["unresolved_room_names"] = ("Дет. ванная 2",)
    card["effective_m"] = None
    card["known_segment_m"] = "6"
    card["incomplete_segments"] = 1

    original_topology = service.topology

    def topology(project_id, line_id):
        value = deepcopy(original_topology(project_id, line_id))
        edge = dict(value["edges"][0])
        target = dict(edge["target"])
        target["room_names"] = "Дет. ванная 2"
        target["room_unresolved"] = True
        edge["target"] = target
        edge["cable_length_m"] = None
        edge["physical_length_m"] = None
        edge["calculation_status"] = "INCOMPLETE"
        edge["calculation_reason"] = "Приёмник: нет помещения (канонической связи)"
        value["edges"] = (edge,)
        return value

    service.topology = topology
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()
    captured = []
    workspace.issueRequested.connect(captured.append)

    base_row = _row(workspace, "line-1")
    room_item = workspace.table.item(base_row, _column("room_names"))
    assert not room_item.icon().isNull()
    workspace._table_item_clicked(room_item)
    assert captured[-1]["issue_kind"] == "ROOM"
    assert captured[-1]["column_key"] == "room_names"
    assert captured[-1]["line_id"] == "line-1"
    assert captured[-1]["fix_action"] == "SYNC_DWG"

    length_item = workspace.table.item(base_row, _column("effective_m"))
    workspace._table_item_clicked(length_item)
    assert captured[-1]["issue_kind"] == "LENGTH"
    assert "Приёмник: нет помещения (канонической связи)" in captured[-1]["reason"]
    assert captured[-1]["fix_action"] == "SYNC_DWG"

    workspace._toggle_line_tree(base_row, "line-1")
    child_row = next(
        row
        for row in range(workspace.table.rowCount())
        if workspace._row_kind(row) == "CHILD"
        and workspace.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "line-1"
    )
    child_length = workspace.table.item(child_row, _column("effective_m"))
    assert child_length.text() == "⚠ нет расчёта"
    assert child_length.toolTip() == "Приёмник: нет помещения (канонической связи)"
    # The inline warning glyph is the only visible warning indicator.
    # Keep tooltip and exact clickable issue context; no second Qt warning icon.
    assert child_length.icon().isNull()
    workspace.table.scrollToItem(child_length)
    qtbot.mouseClick(
        workspace.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=workspace.table.visualItemRect(child_length).center(),
    )
    assert captured[-1]["row_kind"] == "CHILD"
    assert captured[-1]["segment_id"] == "segment-line-1"
    assert captured[-1]["target_label"] == "1.01"
    assert captured[-1]["column_key"] == "effective_m"


def _graph_endpoint(reference: str, *, kind: str = "TOPOLOGY_POINT", box: bool = False) -> dict:
    return {
        "kind": kind,
        "reference": reference,
        "label": reference,
        "point_kind": "EL_BOX" if box else "DEVICE_POINT",
    }


def _graph_edge(
    source: str,
    target: str,
    *,
    source_kind: str = "TOPOLOGY_POINT",
    box: bool = False,
    issue: bool = False,
) -> dict:
    return {
        "segment_id": f"segment-{source}-{target}",
        "source": _graph_endpoint(source, kind=source_kind),
        "target": _graph_endpoint(target, box=box),
        "depth": 0,  # Intentionally wrong: topology edges, not depth, own the tree.
        "mount_way": "По полу",
        "gofra_id": f"tube-{target}",
        "cable_length_m": "1.5",
        "physical_length_m": "1.5",
        "calculation_status": "INCOMPLETE" if issue else "READY",
        "calculation_reason": "Нет помещения" if issue else "",
    }


def test_physical_tree_roots_and_real_box_branches_not_synthetic_trunks():
    edges = [
        _graph_edge("BOX", "A"),
        _graph_edge("BOARD", "BOX", source_kind="BOARD_OUTPUT", box=True),
        _graph_edge("BOARD", "S", source_kind="BOARD_OUTPUT"),
        _graph_edge("BOX", "B"),
    ]
    rows = physical_edge_layout(edges)
    assert [row.index for row in rows] == [1, 0, 3, 2]
    assert [row.parent_index for row in rows] == [None, 1, 1, None]
    assert [row.is_root for row in rows] == [True, False, False, True]
    assert [row.prefix for row in rows] == ["↳ ", "   ├─ ", "   └─ ", "↳ "]
    assert rows[0].is_branch_point
    assert not rows[-1].is_branch_point
    # Compact mode may omit leaves but must not omit either physical root.
    shown, _ = compact_physical_edge_rows(rows, threshold=2)
    assert {row.index for row in shown}.issuperset({1, 2})


def test_physical_tree_uses_typed_references_instead_of_matching_labels():
    # Equal labels from distinct endpoint kinds must not create an artificial splice.
    edges = [
        _graph_edge("BOARD", "same", source_kind="BOARD_OUTPUT"),
        _graph_edge("same", "child", source_kind="FIELD_PORT"),
    ]
    rows = physical_edge_layout(edges)
    assert [row.parent_index for row in rows] == [None, None]


def test_compact_tree_retains_box_fork_issue_and_full_parent_chain():
    edges = [
        _graph_edge(
            "BOARD" if index == 0 else f"S{index}",
            f"S{index + 1}",
            source_kind="BOARD_OUTPUT" if index == 0 else "TOPOLOGY_POINT",
            box=index == 5,
            issue=index == 7,
        )
        for index in range(13)
    ]
    edges.append(_graph_edge("BOARD", "SECOND", source_kind="BOARD_OUTPUT"))
    full = physical_edge_layout(edges)
    shown, hidden = compact_physical_edge_rows(full)
    shown_indexes = {row.index for row in shown}
    assert hidden > 0
    assert 0 in shown_indexes and 13 in shown_indexes  # independent roots
    assert 5 in shown_indexes  # EL_BOX
    assert 7 in shown_indexes  # issue
    assert set(range(8)).issubset(shown_indexes)  # issue ancestry
    assert len(full) == len(shown) + hidden


def test_lines_expansion_compact_and_full_keep_exact_segment_columns(qtbot):
    service = FakeCableService()
    original_topology = service.topology

    def topology(project_id, line_id):
        result = deepcopy(original_topology(project_id, line_id))
        if line_id != "line-1":
            return result
        edges = [
            _graph_edge(
                "BOARD" if index == 0 else f"S{index}",
                f"S{index + 1}",
                source_kind="BOARD_OUTPUT" if index == 0 else "TOPOLOGY_POINT",
                box=index == 5,
                issue=index == 7,
            )
            for index in range(13)
        ]
        edges.append(_graph_edge("BOARD", "SECOND", source_kind="BOARD_OUTPUT"))
        result["edges"] = tuple(edges)
        return result

    service.topology = topology
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    workspace.show()
    base = _row(workspace, "line-1")
    workspace._toggle_line_tree(base, "line-1")

    def child_rows():
        return [
            row
            for row in range(workspace.table.rowCount())
            if workspace._row_kind(row) == "CHILD"
            and workspace.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "line-1"
        ]

    compact_rows = child_rows()
    assert len(compact_rows) < 14
    root_labels = [
        workspace.table.item(row, _column("designation")).text()
        for row in compact_rows
        if workspace.table.item(row, _column("designation")).text().startswith("↳ ")
    ]
    assert root_labels == ["↳ S1", "↳ SECOND"]

    for row in compact_rows:
        designation_item = workspace.table.item(row, _column("designation"))
        segment_id = designation_item.data(Qt.ItemDataRole.UserRole + 4)
        destination = designation_item.text().split(" ")[-1]
        assert segment_id.endswith(f"-{destination}")
        assert workspace.table.item(row, _column("gofra_id")).text() == f"tube-{destination}"
        assert workspace.table.item(row, _column("effective_m")).text() == "1.5"

    more_row = next(
        row
        for row in range(workspace.table.rowCount())
        if workspace._row_kind(row) == "MORE"
        and workspace.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "line-1"
    )
    workspace._table_item_clicked(workspace.table.item(more_row, _column("designation")))
    assert len(child_rows()) == 14
    assert all(workspace._row_kind(row) != "MORE" for row in range(workspace.table.rowCount()))


@pytest.mark.parametrize("network", ["CABLE", "AV", "BUS"])
def test_reordered_graph_preserves_columns_issues_and_double_click(qtbot, monkeypatch, network):
    service = FakeCableService()
    edges = [
        _graph_edge("BOX", "A", issue=True),
        _graph_edge("BOARD", "BOX", source_kind="BOARD_OUTPUT", box=True),
        _graph_edge("BOX", "B"),
        _graph_edge("UNKNOWN", "ORPHAN"),
    ]
    for index, edge in enumerate(edges):
        edge["mount_way"] = f"route-{index}"
        edge["cable_length_m"] = str(index + 1)
        for side in ("source", "target"):
            edge[side]["endpoint_id"] = edge[side]["reference"]
            if network == "BUS":
                edge[side]["kind"] = (
                    "BUS_ROOT" if edge[side]["reference"] == "BOARD" else "BUS_POINT"
                )
    original = service.topology
    service.topology = lambda project_id, line_id: {
        **original(project_id, line_id),
        "edges": deepcopy(edges),
    }
    bus_service = None
    if network == "BUS":

        class FakeBusService:
            def journal_cards(self, project_id):
                card = _card("bus-1", "901", "Шина", room="Холл", board="ЩР-1")
                return [{**card, "network_kind": "BUS", "system_kind": "BUS"}]

            def journal_topology(self, project_id, line_id):
                return {"edges": deepcopy(edges)}

        bus_service = FakeBusService()
    elif network == "AV":
        service.cards[-1]["system_kind"] = "AV"
    workspace = LinesWorkspace(service, FakeConstructor(), "project", bus_service=bus_service)
    qtbot.addWidget(workspace)
    line_id = "bus-1" if network == "BUS" else "line-1"
    workspace._toggle_line_tree(_row(workspace, line_id), line_id)
    rows = [row for row in range(workspace.table.rowCount()) if workspace._row_kind(row) == "CHILD"]
    ordered = [edges[i] for i in (1, 0, 2, 3)]
    captured = []
    workspace.issueRequested.connect(captured.append)
    for row, edge in zip(rows, ordered, strict=True):
        for column in range(len(COLUMNS)):
            assert (
                workspace.table.item(row, column).data(Qt.ItemDataRole.UserRole + 4)
                == edge["segment_id"]
            )
        assert workspace.table.item(row, _column("board")).text() == edge["source"]["label"]
        assert (
            edge["source"]["endpoint_id"] in workspace.table.item(row, _column("board")).toolTip()
        )
        assert workspace.table.item(row, _column("mount_way")).text() == edge["mount_way"]
        assert workspace.table.item(row, _column("gofra_id")).text() == edge["gofra_id"]
        assert workspace.table.item(row, _column("effective_m")).text() == edge["cable_length_m"]
    workspace._table_item_clicked(workspace.table.item(rows[1], _column("effective_m")))
    assert captured[-1]["segment_id"] == edges[0]["segment_id"]
    workspace._table_item_clicked(workspace.table.item(rows[-1], _column("designation")))
    assert captured[-1]["issue_kind"] == "TOPOLOGY"
    assert captured[-1]["segment_id"] == edges[-1]["segment_id"]
    assert captured[-1]["reason"]

    dialogs = []

    def inspect_dialog(dialog):
        table = dialog.findChild(QTableWidget)
        dialogs.append(table.rowCount())
        assert table.horizontalHeaderItem(0).text() == "Источник"
        assert [table.item(row, 0).text() for row in range(4)] == [
            edge["source"]["label"] for edge in ordered
        ]
        assert [table.item(row, 2).text() for row in range(4)] == [
            "↳ BOX",
            "   ├─ A",
            "   └─ B",
            "↳ ORPHAN",
        ]
        assert [table.item(row, 2).data(Qt.ItemDataRole.UserRole + 4) for row in range(4)] == [
            edge["segment_id"] for edge in ordered
        ]
        return 0

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    workspace._table_item_double_clicked(workspace.table.item(rows[0], _column("designation")))
    assert dialogs == [4]


@pytest.mark.parametrize("manual", [None, "0", "28.75"])
def test_length_components_only_in_details_without_changing_total(qtbot, monkeypatch, manual):
    service = FakeCableService()
    original = service.topology
    facts = {
        "board_reserve_m": "4",
        "distribution_box_reserve_m": "1.4",
        "distribution_box_lines": 2,
        "endpoint_reserve_m": "1.2",
        "endpoint_mechanisms": 4,
        "meander_reserve_m": "0.555",
        "obstacle_reserve_m": "0.3",
        "additional_m": "0.25",
        "unrounded_m": "17.7",
        "rounded_m": "18",
        "manual_full_m": manual,
    }
    edges = [
        _graph_edge("board-id", "box-id", source_kind="BOARD_OUTPUT", box=True),
        _graph_edge("box-id", "socket-id"),
    ]
    labels = {"board-id": "ЩР-1", "box-id": "BOX.007", "socket-id": "X07.01"}
    for edge in edges:
        for side in ("source", "target"):
            edge[side]["label"] = labels[edge[side]["reference"]]
    service.topology = lambda project_id, line_id: {
        **original(project_id, line_id),
        **facts,
        "edges": deepcopy(edges),
    }
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    base = _row(workspace, "line-1")
    before = workspace.table.item(base, _column("effective_m")).text()
    workspace._toggle_line_tree(base, "line-1")
    assert all(workspace._row_kind(r) != "ADJUSTMENT" for r in range(workspace.table.rowCount()))
    assert workspace.table.item(base, _column("effective_m")).text() == before
    assert workspace.table.item(base + 1, _column("board")).text() == "ЩР-1"
    assert workspace.table.item(base + 2, _column("board")).text() == "BOX.007"
    assert workspace.table.item(base + 1, _column("designation")).text() == "↳ BOX.007"
    assert workspace.table.item(base + 2, _column("designation")).text() == "   └─ X07.01"

    inspected = []

    def inspect(dialog):
        table = dialog.findChild(QTableWidget, "lineLengthComponentsTable")
        actual = {table.item(r, 0).text(): table.item(r, 1).text() for r in range(table.rowCount())}
        expected = {
            "+ подключение в щите": "4",
            "+ коммутация в распредкоробках (2 линий)": "1.4",
            "+ выводы из подрозетников (4 механизмов)": "1.2",
            "+ нелинейность трассы («змейка»)": "0.555",
            "+ обходы стен и балок": "0.3",
            "+ дополнительная длина": "0.25",
            "= до округления": "17.7",
            "= к выдаче (вверх до шага проекта)": "18",
        }
        if manual is not None:
            expected["= полная ручная длина"] = manual
        assert actual == expected
        segments = dialog.findChild(QTableWidget, "lineDetailsSegments")
        assert segments.rowCount() == 2
        assert segments.item(1, 0).text() == "BOX.007"
        inspected.append(True)
        return 0

    monkeypatch.setattr(QDialog, "exec", inspect)
    workspace._table_item_double_clicked(workspace.table.item(base, _column("designation")))
    assert inspected == [True]
    assert workspace.table.item(base, _column("effective_m")).text() == before
    assert not service.calls and not service.segment_calls


def test_missing_source_label_stays_unknown_and_routes_to_exact_segment(qtbot):
    service = FakeCableService()
    original = service.topology
    edge = _graph_edge("BOARD", "X07.01", source_kind="BOARD_OUTPUT")
    edge["source"].pop("label")
    service.topology = lambda project_id, line_id: {
        **original(project_id, line_id),
        "edges": [deepcopy(edge)],
    }
    workspace = LinesWorkspace(service, FakeConstructor(), "project")
    qtbot.addWidget(workspace)
    base = _row(workspace, "line-1")
    workspace._toggle_line_tree(base, "line-1")
    source = workspace.table.item(base + 1, _column("board"))
    assert source.text() == "Источник не определён"
    assert "отсутствует подпись" in source.toolTip()
    assert "BOARD" in source.toolTip()
    captured = []
    workspace.issueRequested.connect(captured.append)
    workspace._table_item_clicked(source)
    assert captured[-1]["segment_id"] == edge["segment_id"]
    assert captured[-1]["column_key"] == "board"
    assert captured[-1]["issue_kind"] == "TOPOLOGY"
