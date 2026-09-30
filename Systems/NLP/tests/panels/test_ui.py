from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.panels import PanelService
from nl_project_2.persistence.ids import new_id
from nl_project_2.presentation.object_workspace import ObjectWorkspace
from nl_project_2.presentation.panel_workspace import PanelWorkspaceDialog


def test_panel_workspace_shows_shared_instances_placements_materials_and_navigation(
    database, qtbot
):
    project_id = database.test_project_id
    service = PanelService(database.engine)
    board_id = service.create_board(project_id=project_id, designation="PANEL.UI")
    section_id = service.create_section(
        project_id=project_id, board_id=board_id, section_key="MAIN", section_order=1
    )
    rail_id = service.create_rail(
        project_id=project_id,
        section_id=section_id,
        rail_order=1,
        usable_width_mm="108",
    )
    instance = (
        EquipmentService(database.engine)
        .create_instance(
            project_id=project_id,
            designation="QF.UI",
            passport_key="protection.circuit_breaker.1p",
            product_key="product.schneider.a9f84116",
            supply_scope="NEIROLINKS",
            board_id=board_id,
        )
        .instance_id
    )
    service.place_instance(
        project_id=project_id, rail_id=rail_id, instance_id=instance, start_mm="0"
    )
    service.record_material_fact(
        project_id=project_id,
        board_id=board_id,
        material_kind="COMB_BUSBAR",
        quantity="1",
        unit="pcs",
        reason="UI fixture",
    )
    constructor = ConstructorService(database.engine)
    dialog = PanelWorkspaceDialog(service, constructor, project_id)
    qtbot.addWidget(dialog)
    assert dialog.instances_table.rowCount() == 1
    assert dialog.placements_table.rowCount() == 1
    assert dialog.materials_table.item(0, 4).text() == "NO"
    assert "VALID" in dialog.status_label.text()

    runtime = ApplicationRuntime(
        database=database,
        objects=ObjectService(database.engine),
        work_time=WorkTimeService(database.engine, new_id()),
        constructor=constructor,
        panels=service,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.panels_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.panels_button.isEnabled()
    workspace._close_project()
    assert not workspace.panels_button.isEnabled()
