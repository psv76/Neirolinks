"""Accepted production Routes B: Project read model and Qt-only behavior."""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt

from nl_project_2.presentation.routes_workspace import (
    RoutesWorkspace,
    build_visible_rows,
    load_routes_snapshot,
)


class Cables:
    def __init__(self):
        self.calls = []

    def list_conduits(self, project_id):
        self.calls.append(("conduits", project_id))
        return [
            {
                "id": "tube-1",
                "designation": "001.PND25",
                "conduit_type": "ПНД25",
                "color": "Синий",
                "length_m_decimal": "12",
                "path_json": {"length_source": "SEGMENT_GEOMETRY"},
                "product_name": "Труба ПНД",
            },
            {
                "id": "tube-2",
                "designation": "002.PND25",
                "conduit_type": "ПНД25",
                "color": "Чёрный",
                "length_m_decimal": None,
                "path_json": {"length_source": "INCOMPLETE_SHARED"},
                "product_name": "",
            },
        ]

    def line_cards(self, project_id):
        self.calls.append(("cards", project_id))
        return [
            {"id": "line-1", "designation": "101", "cable_type": "ВВГнг 3х2,5"},
            {"id": "line-2", "designation": "102", "cable_type": "Cat6"},
        ]

    def topology(self, project_id, line_id):
        self.calls.append(("topology", project_id, line_id))

        def edge(identity, conduit_id, mount, target, geom="10", gofra_type=""):
            return {
                "segment_id": identity,
                "source": {"label": "ЩР-1"},
                "target": {"label": target},
                "conduit_id": conduit_id,
                "physical_length_m": geom,
                "mount_way": mount,
                "gofra_type": gofra_type,
                "connection_kind": "CABLE",
                "calculation_status": "READY" if geom is not None else "INCOMPLETE",
                "calculation_reason": "" if geom is not None else "Нет высот",
            }

        if line_id == "line-1":
            return {
                "edges": [
                    edge("seg-1", "tube-1", "По полу", "BOX.001"),
                    edge("seg-2", None, "По полу", "101.01", None),
                    edge("seg-3", None, "В стене", "101.02"),
                    edge("seg-4", None, "Не задано", "101.03"),
                ]
            }
        return {"edges": [edge("seg-5", "tube-1", "По полу", "102.01")]}


class Buses:
    def journal_cards(self, project_id):
        return [{"id": "bus-1", "designation": "901", "cable_type": "UTP Cat5e"}]

    def journal_topology(self, project_id, bus_id):
        return {
            "edges": [
                {
                    "segment_id": "bus-seg-1",
                    "source": {"label": "901.000"},
                    "target": {"label": "901.01"},
                    "conduit_id": "tube-1",
                    "physical_length_m": "10",
                    "mount_way": "По полу",
                    "connection_kind": "CABLE",
                    "calculation_status": "READY",
                },
                {
                    "segment_id": "bus-track",
                    "source": {"label": "901.01"},
                    "target": {"label": "901.02"},
                    "connection_kind": "TRACK",
                    "calculation_status": "READY",
                },
            ]
        }


def test_read_model_contains_all_cable_and_bus_physical_segments_without_writes():
    cables = Cables()
    snapshot = load_routes_snapshot(cables, Buses(), "p-1")
    assert len(snapshot.conduits) == 2
    assert len(snapshot.segments) == 6  # 5 cables + 1 BUS (not TRACK)
    assert {s.id for s in snapshot.segments} == {
        "seg-1",
        "seg-2",
        "seg-3",
        "seg-4",
        "seg-5",
        "bus-seg-1",
    }
    assert {s.tube_need for s in snapshot.segments if s.conduit_id is None} == {
        "Требуется",
        "Не требуется",
        "Не определено",
    }
    assert not any("write" in name for name, *_ in cables.calls)
    rows, count, tubes = build_visible_rows(snapshot, {"tube-1"})
    assert count == 6 and tubes == 2
    assert [r.kind for r in rows[:4]] == ["CONDUIT", "SEGMENT", "SEGMENT", "SEGMENT"]
    assert rows[0].conduit.id == "tube-1"
    assert rows[0].count == 3  # cable + cable + BUS, shared tube once
    assert rows[0].conduit.length_m == "12"
    assert [r.segment.geometry_m for r in rows[1:4]] == ["10", "10", "10"]


def test_filter_without_conduit_and_required_only_never_hides_valid_open_routes():
    snapshot = load_routes_snapshot(Cables(), Buses(), "p")
    without, count, tubes = build_visible_rows(snapshot, set(), scope="Без трубы")
    assert tubes == 0 and count == 3
    assert all(r.kind == "SEGMENT" and r.segment.conduit_id is None for r in without)
    required, count, tubes = build_visible_rows(snapshot, set(), scope="Требует трубы")
    assert count == 1 and tubes == 0
    assert required[0].segment.id == "seg-2"


def test_routes_b_qt_inline_expand_hidden_selection_and_navigation(qtbot):
    cables = Cables()
    workspace = RoutesWorkspace(cables, Buses(), "p")
    qtbot.addWidget(workspace)
    workspace.resize(1280, 780)
    workspace.show()
    assert workspace.snapshot is None  # lazy load avoids slow open_project
    workspace.refresh()
    assert workspace.table.model() is workspace.model
    assert workspace.model.rowCount() == 5  # 2 tubes, 3 unassigned rows

    assert workspace.select_conduit("tube-1")
    workspace.toggle_conduit("tube-1")
    assert workspace.model.rowCount() == 8
    assert workspace.model.rows[0].kind == "CONDUIT"
    assert [r.kind for r in workspace.model.rows[1:4]] == ["SEGMENT"] * 3

    selected = workspace.model.index(1, 0)
    segment_identity = selected.data(Qt.ItemDataRole.UserRole + 1)
    workspace.table.selectionModel().select(
        selected,
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert segment_identity in workspace._selected
    workspace.toggle_conduit("tube-1")
    assert segment_identity in workspace._selected
    assert "скрыто выбранных: 1" in workspace.selection_info.text()

    workspace.scope.setCurrentText("Без трубы")
    assert workspace.model.rowCount() == 3
    workspace.scope.setCurrentText("Требует трубы")
    assert workspace.model.rowCount() == 1
    workspace.scope.setCurrentText("Все")
    workspace.toggle_conduit("tube-1")
    selected_lines = []
    workspace.lineRequested.connect(selected_lines.append)
    cable_index = workspace.model.index(1, 1)
    workspace._double_clicked(cable_index)
    assert selected_lines == ["line-1"]

    assert workspace.table.editTriggers() == workspace.table.EditTrigger.NoEditTriggers
    actions = {
        w.text(): w
        for w in workspace.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton
        )
    }
    assert not actions["Перенести"].isEnabled()
    assert not actions["Назначить трубу"].isEnabled()


def test_geometry_display_does_not_round_away_stored_precision():
    from nl_project_2.presentation.routes_workspace import _length

    assert _length("1.0005") == "1.0005"
    assert _length("10.000") == "10"
    assert _length(None) == "—"
