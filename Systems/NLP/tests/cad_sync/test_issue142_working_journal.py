from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTableWidget
from sqlalchemy import select, update
from test_p0003_reconciliation import _apply_new, _batch, _observation

from nl_project_2.cables import CableError, CableService, RouteMethod
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_segment,
    conduit,
    conduit_segment_assignment,
    field_device,
)
from nl_project_2.presentation.lines_workspace import LinesWorkspace


def journal_project(database, *, room_exists=True):
    objects = ObjectService(database.engine)
    pid = objects.create_project(ProjectCard(name="Cable journal", project_code="J142"))
    building = objects.add_building(pid, "B1")
    rid = None
    if room_exists:
        rid = objects.add_room(
            project_id=pid,
            building_id=building,
            name="R1",
            base_mark_mm=-200,
            height_m="3",
            marking_color="#FFFFFF",
        )
    objects.save_settings(pid, ProjectSettings(cable_reserve_at_board_m=Decimal("1.5")))
    observations = [
        _observation(
            "BOARD_OUT",
            handle="B0",
            attributes={
                "BOARD_ID": "B.01",
                "CABLE_ID": "",
                "BOARD": "",
                "CABLE_TYPE": "",
                "MOUNT_WAY": "",
            },
            x=0,
            y=0,
        ),
        _observation(
            "EL_BOX_OUT_100x100",
            handle="E1",
            cable_id="111",
            attributes={
                "BOX_ID": "BOX.021",
                "BUS_POINT_ID": "",
                "BUS_SOURCE": "",
                "MOUNT_WAY": "По полу",
                "GOFRA_TYPE": "ПНД25",
                "GOFRA_ID": "008.PND25",
            },
            x=1000,
            y=0,
        ),
        _observation(
            "EL_BOX_OUT_100x100",
            handle="E2",
            cable_id="111",
            attributes={
                "BOX_ID": "BOX.022",
                "CABLE_SOURCE": "BOX.021",
                "BUS_POINT_ID": "",
                "BUS_SOURCE": "",
                "MOUNT_WAY": "В брусе",
                "GOFRA_TYPE": "ППЛ25",
                "GOFRA_ID": "009.PP25",
            },
            x=2000,
            y=0,
        ),
        _observation(
            "SOCKET_IN",
            handle="S5",
            cable_id="111.05",
            attributes={"CABLE_SOURCE": "BOX.022", "MOUNT_WAY": "В стене"},
            x=3000,
            y=0,
        ),
        _observation(
            "SOCKET_IN",
            handle="S6",
            cable_id="111.06",
            attributes={"CABLE_SOURCE": "BOX.021", "MOUNT_WAY": "В кабель-канале"},
            x=1000,
            y=2000,
        ),
    ]
    batch = _batch(*reversed(observations))
    sync = DwgSyncService(database.engine)
    proposal = sync.preview(project_id=pid, batch=batch)
    assert proposal.summary.invalid == 0
    _apply_new(sync, proposal)
    with database.engine.connect() as c:
        line_id = c.scalar(select(cable_line.c.id).where(cable_line.c.designation == "111"))
    return objects, pid, building, rid, line_id, batch


def snapshot(database):
    with database.engine.connect() as c:
        return {
            t.name: [dict(r) for r in c.execute(select(t)).mappings()]
            for t in (
                cable_line,
                cable_point,
                cable_segment,
                conduit,
                conduit_segment_assignment,
                field_device,
            )
        }


def test_branched_import_chain_lengths_breakdown_and_reopen(database):
    _, pid, _, _, line_id, batch = journal_project(database)
    service = CableService(database.engine)
    topology = service.topology(pid, line_id)
    assert [(e["source"]["label"], e["target"]["label"]) for e in topology["edges"]] == [
        ("Щит B.01", "BOX.021"),
        ("BOX.021", "111.06"),
        ("BOX.021", "BOX.022"),
        ("BOX.022", "111.05"),
    ]
    assert all(e["calculation_status"] == "READY" for e in topology["edges"])
    groups = {g["mount_way"]: g for g in topology["route_breakdown"]}
    assert Decimal(groups["В брусе"]["physical_m"]) == 1
    assert Decimal(groups["В брусе"]["cable_m"]) == Decimal("1.5")
    assert service.effective_length(pid, line_id).automatic_m == Decimal("6.5")
    assert service.effective_length(pid, line_id).effective_m == 8
    service.set_line_length_adjustments(project_id=pid, cable_line_id=line_id, additional_m="2")
    assert service.effective_length(pid, line_id).effective_m == 10
    before = snapshot(database)
    report = service.project_route_breakdown(pid)
    assert len(report["routes"]) == 6
    assert sum(Decimal(g["physical_m"]) for g in report["routes"]) == 6
    assert report["effective_m"] == "10.0"
    assert snapshot(database) == before  # read models are read-only
    with DatabaseManager().open_existing(database.path) as reopened:
        other = CableService(reopened.engine)
        assert other.topology(pid, line_id)["edges"] == topology["edges"]
        assert other.effective_length(pid, line_id).effective_m == 10
        proposal = DwgSyncService(reopened.engine).preview(project_id=pid, batch=batch)
        assert not [
            c for c in proposal.changes if c.change_class == ChangeClass.BOTH_CHANGED_CONFLICT
        ]
        with reopened.engine.connect() as c:
            assert c.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert c.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_exact_segment_edit_assignment_and_three_way_preserve_neighbors(database):
    _, pid, _, _, line_id, batch = journal_project(database)
    service = CableService(database.engine)
    edges = service.topology(pid, line_id)["edges"]
    selected = next(e for e in edges if e["target"]["label"] == "111.05")
    before = snapshot(database)
    service.update_segment_route(
        project_id=pid,
        cable_segment_id=selected["segment_id"],
        route_method=RouteMethod.TIMBER,
        conduit_type="ППЛ25",
        conduit_color="Синий",
        conduit_designation="021.PP25",
    )
    after = snapshot(database)
    for old in before["cable_segment"]:
        if old["id"] != selected["segment_id"]:
            assert next(r for r in after["cable_segment"] if r["id"] == old["id"]) == old
    assert before["cable_line"] == after["cable_line"]
    assert before["cable_point"] == after["cable_point"]
    edge = next(
        e
        for e in service.topology(pid, line_id)["edges"]
        if e["segment_id"] == selected["segment_id"]
    )
    assert (edge["gofra_id"], edge["gofra_type"], edge["gofra_color"]) == (
        "021.PP25",
        "ППЛ25",
        "Синий",
    )
    assert Decimal(edge["cable_length_m"]) == Decimal("1.5")
    assert Decimal(edge["conduit_length_m"]) == 1
    preview = DwgSyncService(database.engine).preview(project_id=pid, batch=batch)
    changes = [
        c
        for c in preview.changes
        if c.handle == "S5" and c.field in {"MOUNT_WAY", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID"}
    ]
    assert changes and all(c.change_class == ChangeClass.PROJECT_CHANGED for c in changes)


def test_shared_conduit_rejects_incompatible_selected_edit_atomically(database):
    _, pid, _, _, line_id, _ = journal_project(database)
    service = CableService(database.engine)
    edges = service.topology(pid, line_id)["edges"]
    source = next(e for e in edges if e["target"]["label"] == "BOX.021")
    leaf = next(e for e in edges if e["target"]["label"] == "111.05")
    service.update_segment_route(
        project_id=pid,
        cable_segment_id=leaf["segment_id"],
        route_method=RouteMethod.WALL,
        conduit_type="ПНД25",
        conduit_designation="008.PND25",
    )
    before = snapshot(database)
    with pytest.raises(CableError, match="новый номер"):
        service.update_segment_route(
            project_id=pid,
            cable_segment_id=source["segment_id"],
            route_method=RouteMethod.FLOOR,
            conduit_type="ПНД25",
            conduit_color="Черный",
            conduit_designation="008.PND25",
        )
    assert snapshot(database) == before
    service.update_segment_route(
        project_id=pid,
        cable_segment_id=source["segment_id"],
        route_method=RouteMethod.FLOOR,
        conduit_type="ПНД25",
        conduit_color="Черный",
        conduit_designation="022.PND25",
    )
    remaining = next(
        e for e in service.topology(pid, line_id)["edges"] if e["segment_id"] == leaf["segment_id"]
    )
    assert remaining["gofra_id"] == "008.PND25"
    assert remaining["gofra_color"] == ""


@pytest.mark.parametrize(
    ("field", "value", "expected", "absent"),
    [
        ("MOUNT_HEIGHT", "", "высоты установки", "координаты X"),
        ("X", None, "координаты X", "координаты Y"),
    ],
)
def test_diagnostic_reports_only_actual_missing_inputs(database, field, value, expected, absent):
    _, pid, _, _, line_id, _ = journal_project(database)
    with database.engine.begin() as c:
        device = (
            c.execute(select(field_device).where(field_device.c.entity_handle == "S5"))
            .mappings()
            .one()
        )
        facts = {**device["normalized_fields_json"], field: value}
        c.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=facts)
        )
        if field == "X":
            c.execute(
                update(cable_point)
                .where(cable_point.c.logical_identity == "111.05")
                .values(location_json={"y": 0})
            )
    service = CableService(database.engine)
    service.recalculate(project_id=pid)
    edge = next(
        e for e in service.topology(pid, line_id)["edges"] if e["target"]["label"] == "111.05"
    )
    assert edge["calculation_status"] == "INCOMPLETE"
    assert expected in edge["calculation_reason"]
    assert absent not in edge["calculation_reason"]


def test_room_canonicalization_recalculates_accepted_geometry_without_importing_pending_dwg(
    database,
):
    objects, pid, bid, _, line_id, batch = journal_project(database, room_exists=False)
    rid = objects.add_room(
        project_id=pid,
        building_id=bid,
        name="R1",
        base_mark_mm=-200,
        height_m="3",
        marking_color="#FFFFFF",
    )
    changed = replace(
        batch,
        observations=tuple(
            replace(o, x=99999) if o.handle == "E1" else o for o in batch.observations
        ),
    )
    sync = DwgSyncService(database.engine)
    preview = sync.preview(project_id=pid, batch=changed)
    paths = {c.field_path for c in preview.changes if c.detail_status == "ROOM_CANONICALIZATION"}
    assert paths
    before = snapshot(database)
    sync.apply_dwg_to_project(preview, selected_paths=paths, confirmed=True)
    after = snapshot(database)
    assert before["cable_point"] == after["cable_point"]
    assert before["conduit_segment_assignment"] == after["conduit_segment_assignment"]
    assert all(r["room_id"] == rid for r in after["field_device"])
    assert [r["normalized_fields_json"] for r in after["field_device"]] == [
        r["normalized_fields_json"] for r in before["field_device"]
    ]
    assert CableService(database.engine).effective_length(pid, line_id).effective_m == 8


def test_real_lines_widget_edits_exact_segment_and_preserves_selection(database, qtbot):
    _, pid, _, _, line_id, _ = journal_project(database)
    service = CableService(database.engine)
    widget = LinesWorkspace(service, None, pid)
    qtbot.addWidget(widget)
    widget.show()
    widget.select_line(line_id)
    assert widget.segment_table.rowCount() == 4
    index = next(
        i for i, edge in enumerate(widget._segment_rows) if edge["target"]["label"] == "111.05"
    )
    segment_id = widget._segment_rows[index]["segment_id"]
    widget.segment_table.selectRow(index)
    widget.segment_route_combo.setCurrentIndex(widget.segment_route_combo.findText("В брусе"))
    widget.segment_gofra_type_edit.setText("ППЛ25")
    widget.segment_gofra_color_edit.setText("Синий")
    widget.segment_conduit_number.setValue(25)
    qtbot.mouseClick(widget.save_segment_button, Qt.MouseButton.LeftButton)
    assert widget._segment_rows[widget.segment_table.currentRow()]["segment_id"] == segment_id
    assert widget.segment_table.item(widget.segment_table.currentRow(), 3).text() == "025.PP25"
    assert "В брусе" in widget.segment_summary.text()


def test_object_breakdown_is_available_from_lines(database, qtbot, monkeypatch):
    _, pid, _, _, line_id, _ = journal_project(database)
    widget = LinesWorkspace(CableService(database.engine), None, pid)
    qtbot.addWidget(widget)
    widget.select_line(line_id)
    inspected = []

    def inspect(dialog):
        table = dialog.findChild(QTableWidget)
        assert table.rowCount() == 6
        assert sum(Decimal(table.item(i, 1).text()) for i in range(6)) == 6
        assert sum(Decimal(table.item(i, 2).text()) for i in range(6)) == Decimal("6.5")
        assert "8.0 м" in " ".join(label.text() for label in dialog.findChildren(QLabel))
        inspected.append(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", inspect)
    widget.findChild(QPushButton, "projectRouteBreakdownButton").click()
    assert inspected


@pytest.mark.parametrize(("handle", "x", "expected"), [("B0", -1000, "9"), ("E1", 1500, "8.5")])
def test_rescan_source_geometry_recalculates_downstream_dependents(database, handle, x, expected):
    _, pid, _, _, line_id, batch = journal_project(database)
    changed = replace(
        batch,
        observations=tuple(
            replace(o, x=x) if o.handle == handle else o for o in batch.observations
        ),
    )
    sync = DwgSyncService(database.engine)
    preview = sync.preview(project_id=pid, batch=changed)
    selected = {c.field_path for c in preview.changes if c.handle == handle and c.field == "X"}
    assert selected
    sync.apply_dwg_to_project(preview, selected_paths=selected, confirmed=True)
    assert CableService(database.engine).effective_length(pid, line_id).effective_m == Decimal(
        expected
    )


def test_manual_length_does_not_change_physical_or_conduit_meters(database):
    _, pid, _, _, line_id, _ = journal_project(database)
    service = CableService(database.engine)
    before = snapshot(database)
    service.set_line_length_adjustments(
        project_id=pid, cable_line_id=line_id, additional_m=4, manual_full_m=30
    )
    report = service.project_route_breakdown(pid)
    assert Decimal(report["effective_m"]) == 30
    assert sum(Decimal(r["physical_m"]) for r in report["routes"]) == 6
    assert sum(Decimal(r["cable_m"]) for r in report["routes"]) == Decimal("6.5")
    assert snapshot(database)["conduit"] == before["conduit"]
    assert snapshot(database)["cable_segment"] == before["cable_segment"]


def test_conduit_tree_exposes_exact_segment_then_line_and_product_columns(database, qtbot):
    from nl_project_2.presentation.cable_workspace import CableWorkspaceDialog

    _, pid, _, _, _, _ = journal_project(database)
    widget = CableWorkspaceDialog(CableService(database.engine), pid)
    qtbot.addWidget(widget)
    parent = next(
        widget.routes_tree.topLevelItem(i)
        for i in range(widget.routes_tree.topLevelItemCount())
        if widget.routes_tree.topLevelItem(i).text(0) == "008.PND25"
    )
    assert parent.text(4) == "Товар трубы не выбран"
    assert parent.text(5) == ""
    segment = parent.child(0)
    assert "Щит B.01 → BOX.021" in segment.text(0)
    assert segment.child(0).text(0) == "Линия 111"
    assert segment.child(0).text(4) == ""
    assert segment.child(0).text(5) == "TEST CABLE"
