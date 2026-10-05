from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nl_project_2.constructor import ConstructorService
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog
from nl_project_2.presentation.object_workspace import ObjectWorkspace


def test_source_target_preview_commit_and_workspace_availability(database, qtbot):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    breaker = service.create_instance(
        project_id=project_id,
        designation="GENERIC-BREAKER",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    power_supply = service.create_instance(
        project_id=project_id,
        designation="GENERIC-PSU",
        passport_key="power.acdc.24v.din",
        product_key="product.meanwell.hdr_60_24",
        supply_scope="NEIROLINKS",
    )
    resources = service.list_resources(project_id)
    source = next(
        row
        for row in resources
        if row["project_instance_id"] == breaker.instance_id
        and row["resource_key"] == "PROTECTED_OUT"
    )
    target = next(
        row
        for row in resources
        if row["project_instance_id"] == power_supply.instance_id
        and row["resource_key"] == "AC_INPUT"
    )

    dialog = ConstructorWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.passport_combo.count() == 19
    assert dialog.instances_table.rowCount() == 2
    assert dialog.resources_table.rowCount() == 4
    dialog.source_combo.setCurrentIndex(dialog.source_combo.findData(source["id"]))
    dialog.relation_kind_combo.setCurrentIndex(dialog.relation_kind_combo.findData("POWER_FLOW"))
    target_row = next(
        row
        for row in range(dialog.targets_table.rowCount())
        if dialog.targets_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == target["id"]
    )
    dialog.targets_table.selectRow(target_row)
    assert dialog.preview_label.text().startswith("Связь допустима: обязательные проверки пройдены")
    assert "constructor.direction" in dialog.preview_label.toolTip()
    assert dialog.targets_table.item(target_row, 2).text() == "Доступно"
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "commitRelationButton"),
        Qt.MouseButton.LeftButton,
    )
    assert dialog.relations_table.rowCount() == 1

    objects = ObjectService(database.engine)
    runtime = ApplicationRuntime(
        database,
        objects,
        WorkTimeService(database.engine, new_id()),
        None,
        None,
        service,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.constructor_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.constructor_button.isEnabled()
    workspace._close_project()
    assert not workspace.constructor_button.isEnabled()


def test_constructor_uses_passport_labels_and_keeps_technical_identity_in_tooltips(database, qtbot):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    service.create_instance(
        project_id=project_id,
        designation="A01",
        passport_key="controller.wb_mr6c_v2",
        product_key="product.wirenboard.wb_mr6c_v2",
        supply_scope="NEIROLINKS",
    )

    dialog = ConstructorWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    labels = {
        dialog.resources_table.item(row, 1).text(): dialog.resources_table.item(row, 1).toolTip()
        for row in range(dialog.resources_table.rowCount())
    }

    assert {"Input0", "COM1", "K1"} <= labels.keys()
    assert "COM[0]" not in labels
    assert labels["COM1"] == "A01 / COM[0]"
    source_labels = {
        dialog.source_combo.itemText(index) for index in range(dialog.source_combo.count())
    }
    assert "A01 / COM1" in source_labels
    assert "A01 / K1" in source_labels
