from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from nl_project_2.automation import AutomationService
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.presentation.automation_workspace import AutomationWorkspaceDialog
from nl_project_2.presentation.object_workspace import ObjectWorkspace

from .test_service import _instance, _line, _profile


def test_automation_workspace_assignments_trace_and_availability(database, qtbot):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    pwm = _instance(
        service,
        project_id,
        "PWM-UI",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    inputs = _instance(
        service,
        project_id,
        "INPUT-UI",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    led_line = _line(database, "LED-UI")
    switch_line = _line(database, "SWITCH-UI", "SWITCHES")
    profile = _profile(service, database, led_line)

    dialog = AutomationWorkspaceDialog(service, project_id)
    qtbot.addWidget(dialog)
    assert dialog.instances_table.rowCount() == 2
    assert dialog.resources_table.rowCount() == 28
    dialog.profile_combo.setCurrentIndex(dialog.profile_combo.findData(profile))
    dialog.module_combo.setCurrentIndex(dialog.module_combo.findData(pwm.instance_id))
    dialog.ordinals_edit.setText("0,1")
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "assignLedChannelsButton"),
        Qt.MouseButton.LeftButton,
    )
    assert dialog.assignments_table.rowCount() == 2
    assert "STATUS: VERIFIED" in dialog.trace_label.text()
    assert "automation.led_total_power_once" in dialog.trace_label.text()

    dialog.line_combo.setCurrentIndex(dialog.line_combo.findData(switch_line))
    input_row = next(
        row
        for row in range(dialog.resources_table.rowCount())
        if dialog.resources_table.item(row, 0).text() == "INPUT-UI"
        and dialog.resources_table.item(row, 1).text() == "INPUT"
        and dialog.resources_table.item(row, 3).text() == "IN"
    )
    dialog.resources_table.selectRow(input_row)
    qtbot.mouseClick(
        dialog.findChild(QPushButton, "assignAutomationInputButton"),
        Qt.MouseButton.LeftButton,
    )
    assert dialog.assignments_table.rowCount() == 2
    assert "per physical key" in dialog.trace_label.text()
    assert not any(
        row["cable_line_id"] == switch_line for row in service.list_assignments(project_id)
    )

    runtime = ApplicationRuntime(
        database,
        ObjectService(database.engine),
        WorkTimeService(database.engine, new_id()),
        None,
        None,
        None,
        None,
        service,
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    assert not workspace.automation_button.isEnabled()
    workspace.open_project(project_id)
    assert workspace.automation_button.isEnabled()
    workspace._close_project()
    assert not workspace.automation_button.isEnabled()
    assert inputs.resource_count == 17
