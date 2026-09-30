from __future__ import annotations

from PySide6.QtCore import Qt
from sqlalchemy import select

from nl_project_2.config import PathConfig
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.persistence.schema import project
from nl_project_2.presentation.constructor_workspace import ConstructorWorkspaceDialog
from nl_project_2.presentation.equipment_workspace import EquipmentWorkspace


def _paths(tmp_path) -> PathConfig:
    return PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )


def _revision(runtime, project_id: str) -> int:
    with runtime.database.engine.connect() as connection:
        return int(
            connection.scalar(select(project.c.project_revision).where(project.c.id == project_id))
        )


def _select(workspace: EquipmentWorkspace, instance_id: str) -> None:
    for row in range(workspace.instances.rowCount()):
        if workspace.instances.item(row, 0).data(Qt.ItemDataRole.UserRole) == instance_id:
            workspace.instances.setCurrentCell(row, 0)
            workspace.instances.selectRow(row)
            return
    raise AssertionError(f"instance {instance_id} is absent")


def _visible_facts(workspace: EquipmentWorkspace) -> tuple[str, ...]:
    row = workspace.instances.currentRow()
    return tuple(
        workspace.instances.item(row, column).text()
        for column in range(workspace.instances.columnCount())
    )


def _resource_owners(workspace: EquipmentWorkspace) -> set[str]:
    return {
        workspace._resources_by_id[workspace.resources.item(row, 0).data(Qt.ItemDataRole.UserRole)][
            "project_instance_id"
        ]
        for row in range(workspace.resources.rowCount())
    }


def test_equipment_selection_is_atomic_owner_correct_and_reopens(qtbot, tmp_path):
    paths = _paths(tmp_path)
    runtime = ApplicationRuntime.open(paths)
    project_id = runtime.objects.create_project(
        ProjectCard(name="Equipment context", project_code="P1007-EQ")
    )
    breaker = runtime.constructor.create_instance(
        project_id=project_id,
        designation="QF.01",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    power_supply = runtime.constructor.create_instance(
        project_id=project_id,
        designation="PSU.01",
        passport_key="power.acdc.24v.din",
        product_key="product.meanwell.hdr_60_24",
        supply_scope="NEIROLINKS",
    )
    before = _revision(runtime, project_id)
    workspace = EquipmentWorkspace(
        runtime.constructor,
        project_id,
        status_service=runtime.integrated_ui,
        ui_state=runtime.ui_state,
    )
    qtbot.addWidget(workspace)
    workspace.resize(1100, 800)
    workspace.show()
    qtbot.wait(10)
    assert workspace.splitter.orientation() == Qt.Orientation.Vertical
    assert workspace.splitter.sizes()[0] > workspace.splitter.sizes()[1] * 2
    assert workspace.instances.horizontalHeader().font().bold()

    _select(workspace, breaker.instance_id)
    breaker_facts = _visible_facts(workspace)
    assert breaker_facts[0] == "QF.01"
    assert "выключатель" in breaker_facts[1].casefold()
    assert "Schneider" in breaker_facts[2]
    assert breaker_facts[3] == "NEIROLINKS"
    assert workspace.status_label.text().endswith(breaker_facts[4])
    assert _resource_owners(workspace) == {breaker.instance_id}
    assert {
        workspace.resources.item(row, 0).text() for row in range(workspace.resources.rowCount())
    } == {
        "QF.01 / LINE_IN",
        "QF.01 / PROTECTED_OUT",
    }

    _select(workspace, power_supply.instance_id)
    psu_facts = _visible_facts(workspace)
    assert psu_facts[0] == "PSU.01"
    assert "DIN-блок питания" in psu_facts[1]
    assert "MEAN WELL" in psu_facts[2]
    assert _resource_owners(workspace) == {power_supply.instance_id}
    assert {
        workspace.resources.item(row, 0).text() for row in range(workspace.resources.rowCount())
    } == {
        "PSU.01 / AC_INPUT",
        "PSU.01 / DC24_OUTPUT",
    }

    _select(workspace, breaker.instance_id)
    assert _visible_facts(workspace) == breaker_facts
    assert _resource_owners(workspace) == {breaker.instance_id}
    assert all(
        "PSU.01" not in workspace.resources.item(row, 0).text()
        for row in range(workspace.resources.rowCount())
    )
    assert _revision(runtime, project_id) == before

    workspace.instances.setColumnWidth(0, 233)
    workspace.splitter.setSizes([560, 220])
    workspace._save_state()
    restored = EquipmentWorkspace(
        runtime.constructor,
        project_id,
        status_service=runtime.integrated_ui,
        ui_state=runtime.ui_state,
    )
    qtbot.addWidget(restored)
    restored.resize(1100, 800)
    restored.show()
    qtbot.wait(10)
    assert restored.instances.columnWidth(0) == 233
    assert restored.splitter.sizes()[0] > restored.splitter.sizes()[1] * 2
    assert restored._selected_instance_id() == breaker.instance_id

    details = ConstructorWorkspaceDialog(
        runtime.constructor, project_id, selected_instance_id=breaker.instance_id
    )
    qtbot.addWidget(details)
    assert "Контекст перехода — QF.01" in details.context_label.text()
    assert "весь проект" in details.context_label.text()
    assert _revision(runtime, project_id) == before

    expected = {
        row["designation"]: (
            row["passport_key"],
            row["passport_version"],
            row["product_key"],
            row["product_version"],
            row["supply_scope"],
        )
        for row in runtime.constructor.list_instances(project_id)
    }
    details.close()
    restored.close()
    workspace.close()
    runtime.close()

    reopened = ApplicationRuntime.open(paths)
    actual = {
        row["designation"]: (
            row["passport_key"],
            row["passport_version"],
            row["product_key"],
            row["product_version"],
            row["supply_scope"],
        )
        for row in reopened.constructor.list_instances(project_id)
    }
    assert actual == expected
    reopened.close()
