from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nl_project_2.buses import BusService
from nl_project_2.constructor import ConstructorService
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog


def test_published_wbe2_constructor_ui_product_slot_and_bus_source(database, qtbot):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    controller = service.create_instance(
        project_id=project_id,
        designation="WB85.UI",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    dialog = ConstructorWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    idx = dialog.passport_combo.findData("module.wirenboard.wbe2_i_rs485_iso")
    assert idx >= 0
    dialog.passport_combo.setCurrentIndex(idx)
    assert dialog.product_combo.findData("product.wirenboard.wbe2_i_rs485_iso") >= 0
    dialog.product_combo.setCurrentIndex(
        dialog.product_combo.findData("product.wirenboard.wbe2_i_rs485_iso")
    )
    dialog.designation_edit.setText("WBE2.UI.MOD1")
    button = dialog.findChild(QPushButton, "createConstructorInstanceButton")
    button.click()
    inst = next(
        row for row in service.list_instances(project_id)
        if row["designation"] == "WBE2.UI.MOD1"
    )
    resources = service.list_resources(project_id)
    mod_slot = next(
        row for row in resources
        if row["project_instance_id"] == controller.instance_id
        and row["resource_kind"] == "INTERNAL_EXPANSION_SLOT"
        and row["ordinal"] == 0
    )
    attachment = next(
        row for row in resources
        if row["project_instance_id"] == inst["id"]
        and row["resource_kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT"
    )
    rs485 = next(
        row for row in resources
        if row["project_instance_id"] == inst["id"]
        and row["resource_kind"] == "RS485_INTERFACE"
    )
    dialog.relation_kind_combo.setCurrentIndex(
        dialog.relation_kind_combo.findData("MODULE_INSTALLATION")
    )
    dialog.source_combo.setCurrentIndex(
        dialog.source_combo.findData(mod_slot["id"])
    )
    dialog.refresh_targets()
    row_index = next(
        i for i in range(dialog.targets_table.rowCount())
        if dialog.targets_table.item(i, 0).data(Qt.ItemDataRole.UserRole) == attachment["id"]
    )
    assert "Доступно" in dialog.targets_table.item(row_index, 2).text()
    dialog.targets_table.selectRow(row_index)
    assert "допустима" in dialog.preview_label.text().lower()
    service.create_relation(
        project_id=project_id, relation_kind="MODULE_INSTALLATION",
        source_resource_id=mod_slot["id"], target_resource_id=attachment["id"]
    )
    candidates = BusService(database.engine).list_rs485_resource_candidates(project_id)
    assert next(r["source_available"] for r in candidates if r["id"] == rs485["id"])
