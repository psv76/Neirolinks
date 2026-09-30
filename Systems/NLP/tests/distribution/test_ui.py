from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nl_project_2.distribution import DistributionService
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.presentation.distribution_workspace import DistributionWorkspaceDialog
from nl_project_2.presentation.object_workspace import ObjectWorkspace


def test_distribution_workspace_resources_trace_and_availability(database, qtbot):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    service.constructor.create_instance(
        project_id=project_id,
        designation="DIST-UI",
        passport_key="distribution.cross_module.3l_pen",
        product_key="product.iek.ynd10_4_07_100",
        supply_scope="NEIROLINKS",
    )
    service.constructor.create_instance(
        project_id=project_id,
        designation="PSU-UI",
        passport_key="power.acdc.24v.din",
        product_key="product.meanwell.hdr_60_24",
        supply_scope="NEIROLINKS",
    )

    dialog = DistributionWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.instances_table.rowCount() == 2
    assert dialog.resources_table.rowCount() == 30
    psu_row = next(
        row
        for row in range(dialog.instances_table.rowCount())
        if dialog.instances_table.item(row, 0).text() == "PSU-UI"
    )
    dialog.instances_table.selectRow(psu_row)
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "assessDistributionButton"),
        Qt.MouseButton.LeftButton,
    )
    assert "STATUS: VERIFIED" in dialog.assessment_label.text()
    assert "distribution.psu_capacity" in dialog.assessment_label.text()

    runtime = ApplicationRuntime(
        database,
        ObjectService(database.engine),
        WorkTimeService(database.engine, new_id()),
        None,
        None,
        None,
        service,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.distribution_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.distribution_button.isEnabled()
    workspace._close_project()
    assert not workspace.distribution_button.isEnabled()
