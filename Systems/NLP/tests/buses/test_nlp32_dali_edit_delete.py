"""NLP 3.2: editable/deletable DALI bus via guarded service and GUI.

All mutations use disposable test databases. Existing physical device/resource
identities, other buses and assigned cables must survive bus deletion.
"""
from PySide6.QtWidgets import QMessageBox
from nl_project_2.buses import BusError, BusService
from nl_project_2.presentation.bus_workspace import BusWorkspaceDialog
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import bus, bus_endpoint, dali_group, bus_branch
from sqlalchemy import func, select
import pytest

from .test_branched_service import _sources, _points
from .test_service import _rs485_resources


def test_dali_edit_number_and_port_reopen_and_no_cross_kind(database):
    project_id = database.test_project_id
    _a, root, _k, _i = _sources(database)
    service = BusService(database.engine)
    ports = service.list_dali_source_candidates(project_id)
    assert len(ports) == 3
    da2 = next(r["id"] for r in ports if r["label"].endswith("DA2"))
    first = service.create_branched_bus(
        project_id=project_id, bus_kind="DALI", designation="941",
        root_resource_id=root, points=(), branches=(),
    )
    original_id = first.bus_id
    service.update_dali_bus(
        project_id=project_id, bus_id=first.bus_id,
        designation="942", root_resource_id=da2,
    )
    changed = service.get_bus(project_id, first.bus_id)
    assert changed["id"] == original_id
    assert changed["designation"] == "942"
    assert changed["root_resource_id"] == da2
    assert not service.list_dali_source_candidates(project_id) == ports
    service.update_dali_bus(
        project_id=project_id, bus_id=first.bus_id,
        designation="942", root_resource_id=da2,
    )
    with pytest.raises(BusError, match="9YY"):
        service.update_dali_bus(
            project_id=project_id, bus_id=first.bus_id,
            designation="ABCD", root_resource_id=da2,
        )
    second = service.create_branched_bus(
        project_id=project_id, bus_kind="DALI", designation="943",
        root_resource_id=root, points=(), branches=(),
    )
    with pytest.raises(BusError, match="занято"):
        service.update_dali_bus(
            project_id=project_id, bus_id=second.bus_id,
            designation="942", root_resource_id=root,
        )
    with pytest.raises(BusError, match="недоступен|занят"):
        service.update_dali_bus(
            project_id=project_id, bus_id=second.bus_id,
            designation="944", root_resource_id=da2,
        )
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        same = BusService(reopened.engine).get_bus(project_id, original_id)
        assert same["designation"] == "942"
        assert same["root_resource_id"] == da2
    finally:
        reopened.close()


def test_dali_rename_refuses_existing_physical_data_delete_cleans_only_its_graph(database):
    project_id = database.test_project_id
    _a, root, _k, _i = _sources(database)
    endpoints = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = service.create_branched_bus(
        project_id=project_id, bus_kind="DALI", designation="951",
        root_resource_id=root, points=_points(endpoints, "951"),
        branches=((endpoints[0], endpoints[1]), (endpoints[1], endpoints[2], endpoints[3])),
    )
    service.create_dali_group(
        project_id=project_id, bus_id=receipt.bus_id,
        group_key="D.011", member_resource_ids=(endpoints[0], endpoints[1]),
    )
    other_root = next(r["id"] for r in service.list_dali_source_candidates(project_id))
    other = service.create_branched_bus(
        project_id=project_id, bus_kind="DALI", designation="952",
        root_resource_id=other_root, points=(), branches=(),
    )
    with pytest.raises(BusError, match="подключённые"):
        service.update_dali_bus(
            project_id=project_id, bus_id=receipt.bus_id,
            designation="953", root_resource_id=root,
        )
    assert service.get_bus(project_id, receipt.bus_id)["designation"] == "951"
    saved_resource_ids = {r["id"] for r in
        __import__("nl_project_2.constructor", fromlist=["ConstructorService"])
        .ConstructorService(database.engine).list_resources(project_id)}
    service.delete_dali_bus(project_id=project_id, bus_id=receipt.bus_id)
    with pytest.raises(BusError):
        service.get_bus(project_id, receipt.bus_id)
    assert service.get_bus(project_id, other.bus_id)["designation"] == "952"
    assert service.list_dali_groups(project_id, receipt.bus_id) == []
    with database.engine.connect() as connection:
        for table in [bus_endpoint, bus_branch, dali_group]:
            assert connection.scalar(select(func.count()).select_from(table).where(
                table.c.bus_id == receipt.bus_id
            )) == 0
    assert {r["id"] for r in
        __import__("nl_project_2.constructor", fromlist=["ConstructorService"])
        .ConstructorService(database.engine).list_resources(project_id)} == saved_resource_ids
    with pytest.raises(BusError, match="не найдена"):
        service.delete_dali_bus(project_id=project_id, bus_id=receipt.bus_id)
    with pytest.raises(BusError):
        service.delete_rs485_bus(project_id=project_id, bus_id=other.bus_id)


def test_dali_ui_edit_and_delete_with_confirmation(database, qtbot, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit
    pid = database.test_project_id
    _a, root, _k, _i = _sources(database)
    service = BusService(database.engine)
    first = service.create_branched_bus(
        project_id=pid, bus_kind="DALI", designation="941",
        root_resource_id=root, points=(), branches=(),
    )
    widget = BusWorkspaceDialog(service, pid)
    qtbot.addWidget(widget)
    assert widget.edit_dali_button.isEnabled()
    assert widget.delete_bus_button.isEnabled()

    def submit():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        name = dialog.findChild(QLineEdit, "rs485DesignationEdit")
        port = dialog.findChild(QComboBox, "rs485ResourceCombo")
        assert name.text() == "941"
        assert port.currentData() == root
        name.setText("942")
        index = port.findText("DALI-SOURCE / DA2")
        assert index >= 0
        port.setCurrentIndex(index)
        dialog.accept()

    QTimer.singleShot(0, submit)
    widget.edit_dali_button.click()
    assert service.get_bus(pid, first.bus_id)["designation"] == "942"
    assert widget.buses_table.item(0, 0).text() == "942"

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    widget.delete_bus_button.click()
    assert service.get_bus(pid, first.bus_id)["designation"] == "942"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    widget.delete_bus_button.click()
    assert service.list_buses(pid) == []
    assert widget.buses_table.rowCount() == 0
