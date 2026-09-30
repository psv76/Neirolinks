from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGraphicsTextItem,
    QGraphicsView,
    QLineEdit,
    QMessageBox,
)
from sqlalchemy import func, select

from nl_project_2.buses import BusService
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import functional_relation, instance_resource
from nl_project_2.presentation.bus_workspace import BusWorkspaceDialog
from nl_project_2.presentation.object_workspace import ObjectWorkspace

from .test_branched_service import _points as _branched_points
from .test_branched_service import _sources
from .test_service import (
    _create_rs485_resource,
    _empty_rs485_bus,
    _points,
    _rs485_resources,
)


def _submit_resource_dialog(
    designation: str, resource_label: str, observed: dict | None = None
) -> None:
    def submit() -> None:
        modal = QApplication.activeModalWidget()
        if not isinstance(modal, QDialog):
            raise AssertionError("RS-485 editor did not open")
        designation_edit = modal.findChild(QLineEdit, "rs485DesignationEdit")
        resource_combo = modal.findChild(QComboBox, "rs485ResourceCombo")
        if designation_edit is None or resource_combo is None:
            raise AssertionError("RS-485 editor fields are missing")
        if observed is not None:
            observed["labels"] = [
                resource_combo.itemText(index) for index in range(resource_combo.count())
            ]
            observed["resource_ids"] = [
                resource_combo.itemData(index) for index in range(resource_combo.count())
            ]
        index = resource_combo.findText(resource_label)
        if index < 0:
            raise AssertionError(f"Resource is absent from selector: {resource_label}")
        designation_edit.setText(designation)
        resource_combo.setCurrentIndex(index)
        modal.accept()

    QTimer.singleShot(0, submit)


def _cancel_resource_dialog() -> None:
    def cancel() -> None:
        modal = QApplication.activeModalWidget()
        if not isinstance(modal, QDialog):
            raise AssertionError("RS-485 editor did not open")
        modal.reject()

    QTimer.singleShot(0, cancel)


def _graph_labels(dialog: BusWorkspaceDialog) -> list[str]:
    labels = [
        item for item in dialog.graph_view.scene().items() if isinstance(item, QGraphicsTextItem)
    ]
    return [item.toPlainText() for item in sorted(labels, key=lambda item: item.x())]


def test_bus_workspace_graph_is_derived_and_project_scoped(database, qtbot):
    project_id = database.test_project_id
    root, *endpoints = _rs485_resources(database)
    service = BusService(database.engine)
    service.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=root,
        points=_points(endpoints),
    )
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.buses_table.rowCount() == 1
    assert dialog.endpoints_table.rowCount() == 4
    assert len(dialog.findChild(QGraphicsView, "busGraphView").scene().items()) == 9
    assert "STATUS: INCOMPATIBLE" in dialog.status_label.text()
    assert "MISSING_COORDINATE" in dialog.status_label.text()

    runtime = ApplicationRuntime(
        database=database,
        objects=ObjectService(database.engine),
        work_time=WorkTimeService(database.engine, new_id()),
        buses=service,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.buses_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.buses_button.isEnabled()
    workspace._close_project()
    assert not workspace.buses_button.isEnabled()


def test_rs485_create_uses_service_candidates_labels_and_cancel(database, qtbot, monkeypatch):
    project_id = database.test_project_id
    resources = [
        _create_rs485_resource(database, project_id, designation)
        for designation in ("WB.01", "UPS.01", "A01", "A02")
    ]
    service = BusService(database.engine)
    create_calls = []
    original_create = service.create_rs485_bus

    def create_spy(**kwargs):
        create_calls.append(kwargs)
        return original_create(**kwargs)

    monkeypatch.setattr(service, "create_rs485_bus", create_spy)
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    observed = {}
    _submit_resource_dialog("901", "WB.01 / RS485", observed)
    dialog.create_rs485_button.click()

    assert create_calls == [
        {
            "project_id": project_id,
            "designation": "901",
            "root_resource_id": resources[0]["id"],
            "points": (),
        }
    ]
    assert set(observed["resource_ids"]) == {resource["id"] for resource in resources}
    assert set(observed["labels"]) == {
        "WB.01 / RS485",
        "UPS.01 / RS485",
        "A01 / RS485",
        "A02 / RS485",
    }
    assert dialog.buses_table.rowCount() == 1
    assert dialog.buses_table.item(0, 0).text() == "901"
    assert dialog.buses_table.item(0, 3).text() == "WB.01 / RS485"
    assert _graph_labels(dialog) == ["WB.01 / RS485"]

    _cancel_resource_dialog()
    dialog.create_rs485_button.click()
    assert len(create_calls) == 1
    assert len(service.list_buses(project_id)) == 1
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0


def test_rs485_endpoint_add_orders_graph_and_rejection_is_atomic(database, qtbot, monkeypatch):
    project_id = database.test_project_id
    root = _create_rs485_resource(database, project_id, "WB.01")
    for designation in ("UPS.01", "A01", "A02"):
        _create_rs485_resource(database, project_id, designation)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root["id"])
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert len(dialog.graph_view.scene().items()) == 1

    for cable_id, label in (
        ("901.003", "A02 / RS485"),
        ("901.001", "UPS.01 / RS485"),
        ("901.002", "A01 / RS485"),
    ):
        _submit_resource_dialog(cable_id, label)
        dialog.add_endpoint_button.click()

    assert [
        dialog.endpoints_table.item(row, 0).text()
        for row in range(dialog.endpoints_table.rowCount())
    ] == ["901.001", "901.002", "901.003"]
    assert [
        dialog.endpoints_table.item(row, 1).text()
        for row in range(dialog.endpoints_table.rowCount())
    ] == [
        "UPS.01 / RS485",
        "A01 / RS485",
        "A02 / RS485",
    ]
    assert len(dialog.graph_view.scene().items()) == 7
    assert _graph_labels(dialog) == [
        "WB.01 / RS485",
        "UPS.01 / RS485",
        "A01 / RS485",
        "A02 / RS485",
    ]

    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]) or QMessageBox.StandardButton.Ok,
    )
    _submit_resource_dialog("901.004", "WB.01 / RS485")
    dialog.add_endpoint_button.click()
    assert warnings and "distinct resources" in warnings[-1]
    assert dialog.endpoints_table.rowCount() == 3
    assert len(service.get_bus(project_id, receipt.bus_id)["endpoints"]) == 3
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0


def test_rs485_remove_confirm_cancel_and_designation_gap(database, qtbot, monkeypatch):
    project_id = database.test_project_id
    root, endpoint_01, endpoint_02, endpoint_03 = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root)
    for resource_id, cable_id in (
        (endpoint_01, "901.001"),
        (endpoint_02, "901.002"),
        (endpoint_03, "901.003"),
    ):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=receipt.bus_id,
            resource_id=resource_id,
            cable_id=cable_id,
        )
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    dialog.endpoints_table.selectRow(1)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )
    dialog.remove_endpoint_button.click()
    assert [row["address"] for row in service.get_bus(project_id, receipt.bus_id)["endpoints"]] == [
        "901.001",
        "901.002",
        "901.003",
    ]

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    dialog.remove_endpoint_button.click()
    stored = service.get_bus(project_id, receipt.bus_id)
    assert [row["address"] for row in stored["endpoints"]] == ["901.001", "901.003"]
    assert [
        dialog.endpoints_table.item(row, 0).text()
        for row in range(dialog.endpoints_table.rowCount())
    ] == ["901.001", "901.003"]
    topology = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates={},
    )
    assert topology.edges == ((root, endpoint_01), (endpoint_01, endpoint_03))


def test_rs485_delete_confirm_cancel_clears_ui_and_preserves_resources(
    database, qtbot, monkeypatch
):
    project_id = database.test_project_id
    root, endpoint = _rs485_resources(database, count=2)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root)
    service.add_rs485_endpoint(
        project_id=project_id,
        bus_id=receipt.bus_id,
        resource_id=endpoint,
        cable_id="901.001",
    )
    with database.engine.connect() as connection:
        resource_count = connection.scalar(select(func.count()).select_from(instance_resource))
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )
    dialog.delete_bus_button.click()
    assert dialog.buses_table.rowCount() == 1
    assert len(dialog.graph_view.scene().items()) == 3

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    dialog.delete_bus_button.click()
    assert service.list_buses(project_id) == []
    assert dialog.buses_table.rowCount() == 0
    assert dialog.endpoints_table.rowCount() == 0
    assert len(dialog.graph_view.scene().items()) == 0
    assert dialog.status_label.text() == "Выберите шину"
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(instance_resource)) == (
            resource_count
        )
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0


def test_dali_and_knx_views_coexist_with_rs485_write_actions(database, qtbot):
    project_id = database.test_project_id
    _automation, dali_root, knx_root, _dali_instance = _sources(database)
    endpoints = _rs485_resources(database, count=8)
    dali_endpoints = endpoints[:4]
    knx_endpoints = endpoints[4:]
    service = BusService(database.engine)
    dali = service.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="903",
        root_resource_id=dali_root,
        points=_branched_points(dali_endpoints),
        branches=(
            (dali_endpoints[0], dali_endpoints[1]),
            (dali_endpoints[1], dali_endpoints[2], dali_endpoints[3]),
        ),
    )
    service.create_dali_group(
        project_id=project_id,
        bus_id=dali.bus_id,
        group_key="D.001",
        member_resource_ids=(dali_endpoints[0], dali_endpoints[2]),
    )
    service.create_branched_bus(
        project_id=project_id,
        bus_kind="KNX",
        designation="904",
        root_resource_id=knx_root,
        points=_branched_points(knx_endpoints, "904"),
        branches=(
            (knx_endpoints[0], knx_endpoints[1]),
            (knx_endpoints[1], knx_endpoints[2], knx_endpoints[3]),
        ),
    )

    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.buses_table.item(0, 1).text() == "DALI"
    assert dialog.groups_table.rowCount() == 1
    assert dialog.states_table.rowCount() == 5
    assert not dialog.add_endpoint_button.isEnabled()
    assert not dialog.delete_bus_button.isEnabled()

    dialog.buses_table.selectRow(1)
    assert dialog.buses_table.item(1, 1).text() == "KNX"
    assert dialog.endpoints_table.rowCount() == 4
    assert dialog.groups_table.rowCount() == 0
    assert dialog.states_table.rowCount() == 5
    assert len(dialog.graph_view.scene().items()) > 0
    assert not dialog.add_endpoint_button.isEnabled()
    assert not dialog.delete_bus_button.isEnabled()


def test_dali_workspace_shows_group_and_independent_states(database, qtbot):
    project_id = database.test_project_id
    _automation, dali_root, _knx_root, _dali_instance = _sources(database)
    endpoints = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = service.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="903",
        root_resource_id=dali_root,
        points=_branched_points(endpoints),
        branches=(
            (endpoints[0], endpoints[1]),
            (endpoints[1], endpoints[2], endpoints[3]),
        ),
    )
    service.create_dali_group(
        project_id=project_id,
        bus_id=receipt.bus_id,
        group_key="D.001",
        member_resource_ids=(endpoints[0], endpoints[2]),
    )
    dialog = BusWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.groups_table.rowCount() == 1
    assert dialog.groups_table.item(0, 0).text() == "D.001"
    assert dialog.states_table.rowCount() == 5
    assert dialog.states_table.item(0, 1).text() == "VERIFIED"
    assert dialog.states_table.item(0, 2).text() == "MISSING"
