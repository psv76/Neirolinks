from __future__ import annotations

from pathlib import Path

from nl_project_2.config import PathConfig, ensure_operational_directories


def test_configuration_is_side_effect_free(tmp_path: Path) -> None:
    local_state = tmp_path / "state"
    paths = PathConfig.from_environment(
        {
            "USERPROFILE": str(tmp_path / "user"),
            "LOCALAPPDATA": str(tmp_path / "local"),
            "NLP2_BACKUP_ROOT": str(tmp_path / "backups"),
            "NLP2_RELEASE_ROOT": str(tmp_path / "releases"),
            "NLP2_PROJECTS_ROOT": str(tmp_path / "projects"),
            "NLP2_LOCAL_STATE_ROOT": str(local_state),
        }
    )
    assert not local_state.exists()
    ensure_operational_directories(paths)
    assert paths.log_root.is_dir()
    assert not paths.backup_root.exists()
    assert not paths.release_root.exists()
    assert not paths.user_projects_root.exists()


def test_default_roots_belong_to_product_line_2() -> None:
    paths = PathConfig.from_environment({"USERPROFILE": "C:/Users/example"})
    configured = "\n".join(
        map(str, (paths.app_root, paths.backup_root, paths.release_root, paths.user_projects_root))
    )
    assert "NLP_2" in configured
    assert "NL Project 2.0" in configured
