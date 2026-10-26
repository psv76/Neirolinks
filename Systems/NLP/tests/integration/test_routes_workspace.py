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
    assert _length("1234567890123456789012345678.0005") == "1234567890123456789012345678.0005"


def test_independent_branches_bus_navigation_and_keyboard_multiselect(qtbot):
    from dataclasses import replace

    workspace = RoutesWorkspace(Cables(), Buses(), "p")
    qtbot.addWidget(workspace)
    workspace.resize(1000, 400)
    workspace.show()
    workspace.refresh()
    snapshot = workspace.snapshot
    workspace.snapshot = replace(
        snapshot,
        segments=tuple(
            replace(s, conduit_id="tube-2") if s.id == "seg-5" else s for s in snapshot.segments
        ),
    )
    workspace.toggle_conduit("tube-1")
    assert "CABLE:seg-5" not in {r.identity for r in workspace.model.rows}
    workspace.toggle_conduit("tube-2")
    assert "CABLE:seg-5" in {r.identity for r in workspace.model.rows}
    workspace.select_conduit("tube-1")
    assert workspace._selected == {"tube-1"}  # parents do not select children
    workspace.table.setFocus()
    qtbot.keyClick(workspace.table, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert len(workspace._selected) == 2
    index = next(i for i, row in enumerate(workspace.model.rows) if row.identity == "CABLE:seg-5")
    qtbot.mouseClick(
        workspace.table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        workspace.table.visualRect(workspace.model.index(index, 1)).center(),
    )
    assert len(workspace._selected) == 3
    before = workspace._selected.copy()
    workspace.search.setText("not-present")
    assert workspace._selected == before
    assert "скрыто выбранных: 3" in workspace.selection_info.text()
    workspace.search.clear()
    requested = []
    workspace.lineRequested.connect(requested.append)
    bus_index = next(
        i for i, row in enumerate(workspace.model.rows) if row.identity == "BUS:bus-seg-1"
    )
    workspace._double_clicked(workspace.model.index(bus_index, 1))
    assert requested == ["bus-1"]
    workspace.table.setCurrentIndex(workspace.model.index(0, 0))
    qtbot.keyClick(workspace.table, Qt.Key.Key_Space)
    assert "tube-1" not in workspace._expanded
    qtbot.keyClick(workspace.table, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    assert workspace.table.currentIndex().row() == workspace.model.rowCount() - 1
    before = workspace._selected.copy()
    workspace.refresh()
    assert workspace._selected == before


def test_real_sqlite_services_view_and_refresh_are_read_only(database, qtbot, monkeypatch):
    from pathlib import Path

    from sqlalchemy import event, select

    from nl_project_2.automation import AutomationService
    from nl_project_2.buses import BusService
    from nl_project_2.cables import CableService
    from nl_project_2.persistence.ids import new_id
    from nl_project_2.persistence.schema import (
        bus_segment,
        bus_segment_conduit_assignment,
        conduit,
    )

    # Reuse the existing physical Q07/Q08 fixture, always in pytest's disposable DB.
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "cables"))
    from test_p0004_segment_recalculation import _graph, _project

    _, project_id, room_a, room_b, _ = _project(database)
    line_id, segment_ids, _ = _graph(
        database,
        project_id,
        (room_a, room_b),
        routes=[(0, 1, "По полу", "ПНД25"), (1, 2, "В стене", "")],
        coords=[(0, 0, 300), (1000.5, 2000, 300), (2000, 2000, 600)],
    )
    cables = CableService(database.engine)
    cables.recalculate(project_id=project_id, segment_ids=segment_ids)
    tube_id = cables.list_conduits(project_id)[0]["id"]
    automation = AutomationService(database.engine)
    resources = []
    for number in range(2):
        instance = automation.constructor.create_instance(
            project_id=project_id,
            designation=f"BUS-{number}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        resources.append(
            next(
                r["id"]
                for r in automation.list_resources(project_id)
                if r["project_instance_id"] == instance.instance_id
                and r["resource_kind"] == "RS485_INTERFACE"
            )
        )
    buses = BusService(database.engine)
    receipt = buses.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=resources[0],
        points=({"resource_id": resources[1], "cable_id": "901.001", "x_mm": 1000, "y_mm": 0},),
    )
    with database.engine.begin() as connection:
        bus_segment_id = connection.scalar(
            select(bus_segment.c.id).where(bus_segment.c.bus_id == receipt.bus_id)
        )
        connection.execute(
            bus_segment.update()
            .where(bus_segment.c.id == bus_segment_id)
            .values(length_m_decimal="7.0005")
        )
        connection.execute(
            bus_segment_conduit_assignment.insert().values(
                id=new_id(),
                project_id=project_id,
                bus_segment_id=bus_segment_id,
                conduit_id=tube_id,
            )
        )
        connection.execute(
            conduit.update()
            .where(conduit.c.id == tube_id)
            .values(
                length_m_decimal="12.0005",
                path_json={"length_source": "USER_CONFIRMED"},
            )
        )

    def dump():
        with database.engine.connect() as connection:
            return tuple(connection.connection.driver_connection.iterdump())

    before = dump()
    statements = []

    def reads_only(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
        assert statement.lstrip().upper().startswith(("SELECT", "PRAGMA")), statement

    event.listen(database.engine, "before_cursor_execute", reads_only)
    try:
        widget = RoutesWorkspace(cables, buses, project_id)
        qtbot.addWidget(widget)
        widget.refresh()
        widget.set_expanded(True)
        widget.refresh()
        snapshot = widget.snapshot
        assert snapshot is not None
        assert snapshot.conduits[0].length_m == "12.0005"
        by_id = {s.id: s for s in snapshot.segments}
        assert set(by_id) == {*segment_ids, bus_segment_id}
        assert by_id[segment_ids[0]].geometry_m == "4.1005"
        assert by_id[segment_ids[0]].cable_line_id == line_id
        assert by_id[bus_segment_id].geometry_m == "7.0005"
        assert by_id[bus_segment_id].conduit_id == tube_id
        assert by_id[bus_segment_id].target == "901.001"
        assert by_id[segment_ids[1]].conduit_id is None
        assert widget.select_conduit(tube_id)
        assert statements
    finally:
        event.remove(database.engine, "before_cursor_execute", reads_only)
    assert dump() == before


def test_shell_lazy_refresh_spec_jump_and_exact_line_navigation(qtbot, tmp_path):
    from sqlalchemy import event

    from nl_project_2.objects.models import ProjectCard
    from nl_project_2.persistence.ids import new_id
    from nl_project_2.persistence.schema import cable_line, conduit
    from nl_project_2.presentation.object_workspace import ObjectWorkspace

    from .test_working_shell import _runtime

    runtime = _runtime(tmp_path)
    project_id = runtime.objects.create_project(ProjectCard(name="Routes", project_code="ROUTES"))
    line_id, tube_id = new_id(), new_id()
    with runtime.database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="101",
                system_kind="POWER",
                cable_facts_json={},
                lifecycle="ACTIVE",
            )
        )
        connection.execute(
            conduit.insert().values(
                id=tube_id,
                project_id=project_id,
                designation="001.PND25",
                conduit_type="ПНД25",
            )
        )
    shell = ObjectWorkspace(runtime)
    qtbot.addWidget(shell)
    shell.open_project(project_id)
    routes = shell.routes_workspace
    assert routes.snapshot is None
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(runtime.database.engine, "before_cursor_execute", capture)
    try:
        shell._navigate_specification_source("CONDUIT", tube_id)
        assert shell.section_stack.currentWidget() is routes
        assert routes.snapshot is not None
        assert tube_id in {t.id for t in routes.snapshot.conduits}
        assert routes.model.rowCount() == 1
        assert routes._selected == {tube_id}
        shell._switch_section("Линии")
        shell.lines_workspace.search.setText("hidden by search")
        shell.lines_workspace.projectChanged.emit()
        assert routes.snapshot is None
        shell._switch_section("Трассы")
        assert routes.snapshot is not None
        assert routes._selected == {tube_id}
        shell._navigate_routes_to_line(line_id)
        assert shell.lines_workspace.current_line_id() == line_id
        assert not shell.lines_workspace.table.isRowHidden(shell.lines_workspace.table.currentRow())
        shell._navigate_back()
        assert shell.section_stack.currentWidget() is routes
        assert shell.lines_workspace.search.text() == "hidden by search"
        assert all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements)
    finally:
        event.remove(runtime.database.engine, "before_cursor_execute", capture)
        shell._timer.stop()
        runtime.database.close()
