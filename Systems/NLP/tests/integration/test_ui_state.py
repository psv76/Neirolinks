from __future__ import annotations

import json

from nl_project_2.config import PathConfig
from nl_project_2.local_state import UiStateStore
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.presentation.object_workspace import ObjectWorkspace


def test_versioned_ui_state_is_atomic_and_separate_from_project(tmp_path):
    store = UiStateStore(tmp_path / "state")
    assert store.load() == {"version": 1}
    store.update(last_object_tab=2, cable_filter="AV")
    assert store.load() == {"version": 1, "last_object_tab": 2, "cable_filter": "AV"}
    assert not store.path.with_suffix(".tmp").exists()
    store.path.write_text(json.dumps({"version": 999, "bad": True}), encoding="utf-8")
    assert store.load() == {"version": 1}


def test_integrated_shell_exposes_all_active_sections_and_restores_tab(qtbot, tmp_path):
    paths = PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )
    runtime = ApplicationRuntime.open(paths)
    project_id = runtime.objects.create_project(
        ProjectCard(name="Integrated", project_code="INTEGRATED")
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    workspace.open_project(project_id)
    for name in (
        "cableWorkspaceButton",
        "constructorWorkspaceButton",
        "distributionWorkspaceButton",
        "automationWorkspaceButton",
        "busWorkspaceButton",
        "panelWorkspaceButton",
        "specificationWorkspaceButton",
        "validationCenterButton",
    ):
        button = workspace.findChild(type(workspace.cables_button), name)
        assert button is not None and button.isEnabled()
    workspace.tabs.setCurrentIndex(2)
    assert runtime.ui_state.load()["last_object_tab"] == 2
    workspace.close()
    runtime.close()

    reopened = ApplicationRuntime.open(paths)
    second = ObjectWorkspace(reopened)
    qtbot.addWidget(second)
    assert second.tabs.currentIndex() == 2
    second.close()
    reopened.close()


def test_last_open_project_is_restored_on_restart_and_explicit_close_clears_it(qtbot, tmp_path):
    paths = PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )
    runtime = ApplicationRuntime.open(paths)
    project_id = runtime.objects.create_project(
        ProjectCard(name="Bogdanovich", project_code="NL.05.441.03")
    )
    workspace = ObjectWorkspace(runtime)
    qtbot.addWidget(workspace)
    workspace.open_project(project_id)
    assert runtime.current_project_id == project_id
    assert runtime.ui_state.load()["last_project_id"] == project_id
    workspace.close()
    runtime.close()

    reopened = ApplicationRuntime.open(paths)
    second = ObjectWorkspace(reopened)
    qtbot.addWidget(second)
    assert reopened.current_project_id == project_id

    second._close_project()
    assert reopened.current_project_id is None
    assert reopened.ui_state.load()["last_project_id"] is None
    second.close()
    reopened.close()

    third_runtime = ApplicationRuntime.open(paths)
    third = ObjectWorkspace(third_runtime)
    qtbot.addWidget(third)
    assert third_runtime.current_project_id is None
    third.close()
    third_runtime.close()
