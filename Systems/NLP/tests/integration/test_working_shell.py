from __future__ import annotations

from PySide6.QtWidgets import QMessageBox
from sqlalchemy import select

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.config import PathConfig
from nl_project_2.main_window import MainWindow
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line, project
from nl_project_2.presentation.object_workspace import ObjectWorkspace


def _runtime(tmp_path) -> ApplicationRuntime:
    return ApplicationRuntime.open(
        PathConfig(
            app_root=tmp_path / "app",
            backup_root=tmp_path / "backups",
            release_root=tmp_path / "releases",
            user_projects_root=tmp_path / "projects",
            local_state_root=tmp_path / "state",
        )
    )


def _revision(runtime, project_id: str) -> int:
    with runtime.database.engine.connect() as connection:
        return int(
            connection.scalar(select(project.c.project_revision).where(project.c.id == project_id))
        )


def test_main_shell_lands_on_lines_and_navigation_is_read_only(qtbot, tmp_path):
    runtime = _runtime(tmp_path)
    project_id = runtime.objects.create_project(ProjectCard(name="Shell", project_code="SHELL"))
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    before = _revision(runtime, project_id)

    assert tuple(widget.navigation_buttons) == widget.MAIN_SECTIONS
    assert widget.section_stack.currentWidget() is widget.lines_workspace
    assert widget.navigation_buttons["Линии"].isChecked()
    assert widget.service_button.text() == "Сервис / Инженерные подробности"
    for section in widget.MAIN_SECTIONS:
        widget._switch_section(section)
        assert widget.section_stack.currentWidget() is widget.section_pages[section]
    assert _revision(runtime, project_id) == before

    window = MainWindow(runtime)
    qtbot.addWidget(window)
    assert window.centralWidget() is not None
    window.close()


def test_line_equipment_back_restores_line_filter_and_does_not_write(qtbot, tmp_path):
    runtime = _runtime(tmp_path)
    project_id = runtime.objects.create_project(ProjectCard(name="Navigation", project_code="NAV"))
    instance = EquipmentService(runtime.database.engine).create_instance(
        project_id=project_id,
        designation="A01",
        passport_key="controller.wb_led_v1",
        product_key="product.wirenboard.wb_led_v1",
        supply_scope="NEIROLINKS",
    )
    with runtime.database.engine.begin() as connection:
        line_id = new_id()
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="401",
                system_kind="LIGHTING",
                cable_facts_json={
                    "LOAD_NAME": "Подсветка кухни",
                    "LOAD_TYPE": "LIGHT_LED",
                    "BOARD": "ЩР-1",
                    "CABLE_TYPE": "5x1,5",
                },
                lifecycle="ACTIVE",
            )
        )
    resource = next(
        row
        for row in runtime.constructor.list_resources(project_id)
        if row["project_instance_id"] == instance.instance_id
        and row["resource_key"] == "PWM_OUTPUT"
    )
    runtime.constructor.assign_cable_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=resource["id"],
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    widget.lines_workspace.search.setText("кухни")
    widget.lines_workspace.select_line(line_id)
    before = _revision(runtime, project_id)

    widget._navigate_line_to_resource(resource["id"])
    assert widget.section_stack.currentWidget() is widget.equipment_workspace
    assert widget.equipment_workspace._selected_resource_id() == resource["id"]
    widget._navigate_back()
    assert widget.section_stack.currentWidget() is widget.lines_workspace
    assert widget.lines_workspace.current_line_id() == line_id
    assert widget.lines_workspace.search.text() == "кухни"
    assert _revision(runtime, project_id) == before


def test_close_project_disables_work_sections_without_leaking_previous_selection(
    qtbot, tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)
    first = runtime.objects.create_project(ProjectCard(name="First", project_code="FIRST"))
    second = runtime.objects.create_project(ProjectCard(name="Second", project_code="SECOND"))
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    widget.open_project(first)
    widget.lines_workspace.search.setText("first-filter")
    widget._close_project()
    assert all(
        button.isEnabled() == (section == "Проект")
        for section, button in widget.navigation_buttons.items()
    )
    widget.open_project(second)
    assert widget.lines_workspace.search.text() == ""
    assert widget.section_stack.currentWidget() is widget.lines_workspace
