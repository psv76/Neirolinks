from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.integration import ValidationItem
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line
from nl_project_2.presentation.cable_workspace import CableWorkspaceDialog
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog
from nl_project_2.presentation.validation_center import ValidationCenterDialog


def test_bidirectional_line_resource_navigation_uses_same_entities(qtbot, database):
    project_id = database.test_project_id
    constructor = ConstructorService(database.engine)
    EquipmentService(database.engine).create_instance(
        project_id=project_id,
        designation="CTRL.UI",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    with database.engine.begin() as connection:
        line_id = new_id()
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="LINE.UI",
                system_kind="CONTROL",
                cable_facts_json={},
                lifecycle="ACTIVE",
            )
        )
    resource = next(
        row
        for row in constructor.list_resources(project_id)
        if row["assignable"] and row["direction"] in {"OUT", "BIDIRECTIONAL"}
    )
    constructor.assign_cable_line(
        project_id=project_id, cable_line_id=line_id, output_resource_id=resource["id"]
    )
    opened_resources = []
    cable_dialog = CableWorkspaceDialog(
        __import__("nl_project_2.cables", fromlist=["CableService"]).CableService(database.engine),
        project_id,
        constructor_service=constructor,
        selected_line_id=line_id,
        open_resource=opened_resources.append,
    )
    qtbot.addWidget(cable_dialog)
    assert cable_dialog._selected_line_id() == line_id
    cable_dialog.assignments_table.selectRow(0)
    cable_dialog._open_selected_resource()
    assert opened_resources == [resource["id"]]

    opened_lines = []
    constructor_dialog = ConstructorWorkspaceDialog(
        constructor,
        project_id,
        selected_resource_id=resource["id"],
        open_cable=opened_lines.append,
    )
    qtbot.addWidget(constructor_dialog)
    assert constructor_dialog.resources_table.currentRow() >= 0
    constructor_dialog.assignments_table.selectRow(0)
    constructor_dialog._open_selected_cable()
    assert opened_lines == [line_id]


def test_validation_center_filters_and_keyboard_navigation(qtbot):
    class FakeService:
        @staticmethod
        def validation_items(_project_id):
            return (
                ValidationItem(
                    "ERROR",
                    "BROKEN_PATH",
                    "Разрыв цепи",
                    "CONSTRUCTOR",
                    "RESOURCE",
                    "resource-1",
                ),
                ValidationItem(
                    "WARNING",
                    "COST_UNKNOWN",
                    "Цена не задана",
                    "SPECIFICATION",
                    "PROJECT_INSTANCE",
                    "instance-1",
                ),
            )

    opened = []
    dialog = ValidationCenterDialog(FakeService(), "project", navigate=opened.append)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 2
    dialog.severity.setCurrentIndex(dialog.severity.findData("ERROR"))
    assert dialog.table.rowCount() == 1
    dialog.text_filter.setText("разрыв")
    dialog.table.selectRow(0)
    button = dialog.findChild(QPushButton, "validationNavigateButton")
    button.setFocus()
    qtbot.keyClick(button, Qt.Key.Key_Return)
    assert opened[0].source_id == "resource-1"
