from __future__ import annotations

from PySide6.QtCore import Qt
from sqlalchemy import select

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.config import PathConfig
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.persistence.schema import project
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


def test_permanent_specification_unknown_cost_filters_navigation_and_back(qtbot, tmp_path):
    runtime = _runtime(tmp_path)
    project_id = runtime.objects.create_project(
        ProjectCard(name="Specification shell", project_code="SPEC-SHELL")
    )
    instance = EquipmentService(runtime.database.engine).create_instance(
        project_id=project_id,
        designation="QF.1",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    workspace.open_project(project_id)
    documents = workspace.documents_workspace
    specification = documents.specification
    before = _revision(runtime, project_id)

    assert specification is not None
    assert documents.tabs.indexOf(specification) >= 0
    documents.show_specification()
    workspace._switch_section("Документы")
    assert documents.tabs.currentWidget() is specification
    assert any(
        specification.table.item(row, 8).text() == "Стоимость не указана"
        for row in range(specification.table.rowCount())
    )

    supply_index = specification.supply_filter.findData("NEIROLINKS")
    specification.supply_filter.setCurrentIndex(supply_index)
    specification.incomplete_filter.setCurrentIndex(
        specification.incomplete_filter.findData("NEEDS_DATA")
    )
    specification.table.sortItems(0, Qt.SortOrder.DescendingOrder)
    assert _revision(runtime, project_id) == before

    target_row = next(
        table_row
        for table_row in range(specification.table.rowCount())
        if ("PROJECT_INSTANCE", instance.instance_id)
        in specification._rows[
            specification.table.item(table_row, 0).data(Qt.ItemDataRole.UserRole)
        ].source_refs
    )
    specification.table.selectRow(target_row)
    selected_key = specification._selected_key()
    specification._navigate()
    assert workspace.section_stack.currentWidget() is workspace.equipment_workspace
    assert workspace.equipment_workspace._selected_instance_id() == instance.instance_id
    workspace._navigate_back()
    assert workspace.section_stack.currentWidget() is documents
    assert documents.tabs.currentWidget() is specification
    assert specification._selected_key() == selected_key
    assert _revision(runtime, project_id) == before
    runtime.close()
