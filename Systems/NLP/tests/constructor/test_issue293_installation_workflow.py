"""Issue #293 — operator acceptance for 3 controllers / 12 slots / WB-23 MOD3."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog


def _new(service, project_id, designation, passport, product):
    return service.create_instance(
        project_id=project_id, designation=designation, passport_key=passport,
        product_key=product, supply_scope="NEIROLINKS",
    )


def test_three_controllers_wb23_mod3_installs_wbe2_and_reopens(database, qtbot, monkeypatch):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    controllers = {}
    for designation in ("WB-20", "WB-23", "WB-26"):
        controllers[designation] = _new(
            service, project_id, designation,
            "controller.wiren_board_8_5", "product.wirenboard.wb8_4g_64g_ind",
        ).instance_id
    module = _new(
        service, project_id, "M01",
        "module.wirenboard.wbe2_i_rs485_iso",
        "product.wirenboard.wbe2_i_rs485_iso",
    )
    dialog = ConstructorWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.install_host_combo.count() == 3
    assert [dialog.install_host_combo.itemText(i) for i in range(3)] == [
        "WB-20", "WB-23", "WB-26",
    ]
    dialog.install_host_combo.setCurrentIndex(
        dialog.install_host_combo.findText("WB-23")
    )
    assert dialog.install_slot_combo.count() == 4
    assert [dialog.install_slot_table.item(i, 0).text() for i in range(4)] == [
        "MOD1", "MOD2", "MOD3", "MOD4",
    ]
    dialog.install_slot_combo.setCurrentIndex(2)
    assert dialog.install_slot_combo.currentText() == "MOD3 — свободен"
    assert dialog.install_module_combo.count() == 1
    assert dialog.install_module_combo.currentText().startswith("M01 — ")
    assert dialog.install_button.isEnabled()
    slot_id = dialog.install_slot_combo.currentData()
    attachment_id = dialog.install_module_combo.currentData()
    assert next(
        r for r in service.list_resources(project_id) if r["id"] == slot_id
    )["project_instance_id"] == controllers["WB-23"]
    qtbot.mouseClick(dialog.install_button, Qt.MouseButton.LeftButton)
    found = [
        r for r in service.list_relations(project_id)
        if r["relation_kind"] == "MODULE_INSTALLATION"
    ]
    assert len(found) == 1
    assert found[0]["source_resource_id"] == slot_id
    assert found[0]["target_resource_id"] == attachment_id
    assert dialog.install_slot_table.item(2, 1).text() == "Занят"
    assert dialog.install_slot_table.item(2, 2).text() == "M01"
    assert not dialog.install_button.isEnabled()
    assert dialog.uninstall_button.isEnabled()
    for designation in ("WB-20", "WB-26"):
        dialog.install_host_combo.setCurrentIndex(
            dialog.install_host_combo.findText(designation)
        )
        assert all(
            dialog.install_slot_table.item(i, 1).text() == "Свободен"
            for i in range(4)
        )
    path = database.path
    dialog.close()
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        service = ConstructorService(reopened.engine)
        persisted = [
            r for r in service.list_relations(project_id)
            if r["relation_kind"] == "MODULE_INSTALLATION"
        ]
        assert persisted[0]["id"] == found[0]["id"]
        reread = ConstructorWorkspaceDialog(service, project_id)
        qtbot.addWidget(reread)
        reread.install_host_combo.setCurrentIndex(
            reread.install_host_combo.findText("WB-23")
        )
        reread.install_slot_combo.setCurrentIndex(2)
        assert reread.install_slot_table.item(2, 2).text() == "M01"
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        qtbot.mouseClick(reread.uninstall_button, Qt.MouseButton.LeftButton)
        assert not any(
            r["relation_kind"] == "MODULE_INSTALLATION"
            for r in service.list_relations(project_id)
        )
        assert reread.install_slot_table.item(2, 1).text() == "Свободен"
    finally:
        reopened.close()


def test_corrected_wb85_has_four_mod_and_one_separate_modem_slot(database, qtbot):
    from nl_project_2.catalog.installer import CatalogInstaller
    from nl_project_2.catalog.payload import load_payload
    from nl_project_2.persistence.ids import new_id
    from nl_project_2.persistence.schema import project
    from pathlib import Path

    catalog = Path(__file__).resolve().parents[2] / "resources/catalogs"
    release = CatalogInstaller(database.engine).install(load_payload(catalog))
    project_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(project.insert().values(
            id=project_id, project_code="ISSUE293-UI-VARIANT",
            name="Physical MOD/MODEM test", lifecycle="ACTIVE",
            card_fields_json={}, active_catalog_release_id=release.release_id,
        ))
    service = ConstructorService(database.engine)
    _new(service, project_id, "WB-23",
         "controller.wiren_board_8_5_modular_cellular",
         "product.wirenboard.wb8_4g_64g_ind_modular_cellular")
    dialog = ConstructorWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.install_host_combo.count() == 1
    assert dialog.install_slot_combo.count() == 5
    assert [dialog.install_slot_table.item(i, 0).text() for i in range(5)] == [
        "MOD1", "MOD2", "MOD3", "MOD4", "MODEM",
    ]
    assert not dialog.install_button.isEnabled()
    assert "Создайте экземпляр" in dialog.install_status.text()
