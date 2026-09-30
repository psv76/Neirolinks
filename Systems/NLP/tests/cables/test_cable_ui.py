from __future__ import annotations

from PySide6.QtCore import Qt

from nl_project_2.cables import CableService, RouteMethod
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_point_field_device,
    field_device,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.presentation.cable_workspace import CableWorkspaceDialog
from nl_project_2.presentation.lines_workspace import LinesWorkspace
from nl_project_2.presentation.object_workspace import ObjectWorkspace


def _add_line_with_rooms(database, project_id, designation, room_ids) -> str:
    line_id = new_id()
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation=designation,
                system_kind="POWER",
                cable_facts_json={
                    "BOARD": "ЩР-1",
                    "CABLE_TYPE": "3x2,5",
                    "LOAD_TYPE": "SOCKET",
                    "MOUNT_WAY": "По полу",
                },
            )
        )
        for ordinal, room_id in enumerate(room_ids):
            device_id = new_id()
            point_id = new_id()
            uow.execute(
                field_device.insert().values(
                    id=device_id,
                    project_id=project_id,
                    block_kind="SOCKET_IN",
                    room_id=room_id,
                    normalized_fields_json={},
                )
            )
            uow.execute(
                cable_point.insert().values(
                    id=point_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    field_device_id=None,
                    point_kind="DEVICE_POINT",
                    ordinal=ordinal,
                    logical_identity=f"{line_id}:{ordinal}",
                    origin_kind="PROJECT",
                    migration_state="CONFIRMED",
                )
            )
            uow.execute(
                cable_point_field_device.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    cable_point_id=point_id,
                    field_device_id=device_id,
                )
            )
        uow.commit()
    return line_id


def test_cable_workspace_filters_av_and_is_reachable_from_open_project(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Cable UI", project_code="CUI-1"))
    cables = CableService(database.engine)
    board_id = cables.create_board_av(project_id=project_id, designation="AV-UI")
    cables.create_av_line(
        project_id=project_id,
        board_id=board_id,
        cable_id="HDMI-01",
        load_type="HDMI",
        cable_type="HDMI 2.1",
    )
    cables.create_empty_conduit(
        project_id=project_id,
        designation="010.PND25",
        conduit_type="ПНД25",
        color="Черный",
    )

    dialog = CableWorkspaceDialog(cables, project_id)
    qtbot.addWidget(dialog)
    assert dialog.lines_table.rowCount() == 1
    assert dialog.lines_table.item(0, 1).text() == "AV"
    dialog.system_filter.setCurrentIndex(dialog.system_filter.findData("AV"))
    assert dialog.lines_table.rowCount() == 1
    assert dialog.catalog_table.columnCount() == 8
    assert dialog.routes_tree.topLevelItemCount() == 1
    assert dialog.routes_tree.topLevelItem(0).text(0) == "010.PND25"
    assert dialog.routes_tree.topLevelItem(0).text(4) == "Не выбран"
    timber_index = dialog.route_combo.findData(RouteMethod.TIMBER)
    assert timber_index >= 0
    assert dialog.route_combo.itemText(timber_index) == "В брусе"

    runtime = ApplicationRuntime(
        database,
        objects,
        WorkTimeService(database.engine, new_id()),
        None,
        cables,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.cables_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.cables_button.isEnabled()
    workspace._close_project()
    assert not workspace.cables_button.isEnabled()


def test_cable_lines_show_unique_room_names_and_keep_line_editor_selection(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Rooms", project_code="ROOMS-1"))
    building_id = objects.add_building(project_id, "Дом")
    hall_id = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Прихожая",
        base_mark_mm=0,
        height_m="2.8",
        marking_color="#FFFFFF",
    )
    living_id = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Гостиная",
        base_mark_mm=0,
        height_m="2.8",
        marking_color="#FFFFFF",
    )
    one_room_line = _add_line_with_rooms(database, project_id, "101", [hall_id])
    several_rooms_line = _add_line_with_rooms(
        database, project_id, "102", [hall_id, living_id, hall_id]
    )

    dialog = CableWorkspaceDialog(CableService(database.engine), project_id)
    qtbot.addWidget(dialog)
    headers = [
        dialog.lines_table.horizontalHeaderItem(column).text()
        for column in range(dialog.lines_table.columnCount())
    ]
    room_column = headers.index("Помещение")
    assert dialog.lines_table.columnCount() == 11
    assert dialog.lines_table.minimumHeight() >= 300

    rows_by_id = {
        dialog.lines_table.item(row, 0).data(Qt.ItemDataRole.UserRole): row
        for row in range(dialog.lines_table.rowCount())
    }
    assert dialog.lines_table.item(rows_by_id[one_room_line], room_column).text() == "Прихожая"
    assert (
        dialog.lines_table.item(rows_by_id[several_rooms_line], room_column).text()
        == "Прихожая, Гостиная"
    )

    dialog.lines_table.selectRow(rows_by_id[several_rooms_line])
    assert dialog._selected_line_id() == several_rooms_line
    assert dialog.board_edit.text() == "ЩР-1"
    assert dialog.cable_type_edit.text() == "3x2,5"


def test_lines_zero_result_search_clears_selection_and_stale_details(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(
        ProjectCard(name="Search details", project_code="SEARCH-DETAILS")
    )
    building_id = objects.add_building(project_id, "Дом")
    room_id = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="1. Прихожая",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    _add_line_with_rooms(database, project_id, "120", [room_id])
    workspace = LinesWorkspace(CableService(database.engine), None, project_id)
    qtbot.addWidget(workspace)
    workspace.table.setCurrentCell(0, 0)
    workspace.table.selectRow(0)
    assert "120" in workspace.card_title.text()

    workspace.search.setText("line-that-does-not-exist")

    assert all(workspace.table.isRowHidden(row) for row in range(workspace.table.rowCount()))
    assert workspace.current_line_id() is None
    assert workspace.selected_line_ids() == ()
    assert workspace.card_title.text() == "Линия не выбрана"
    assert all(label.text() == "—" for label in workspace.card_fields.values())
