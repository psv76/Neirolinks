from __future__ import annotations

from pathlib import Path

from nl_project_2.config import (
    DEFAULT_DATABASE_NAME,
    PathConfig,
    ensure_operational_directories,
)


def test_configuration_is_side_effect_free(tmp_path: Path) -> None:
    local_state = tmp_path / "state"
    paths = PathConfig.from_environment(
        {
            "USERPROFILE": str(tmp_path / "user"),
            "LOCALAPPDATA": str(tmp_path / "local"),
            "NLP3_BACKUP_ROOT": str(tmp_path / "backups"),
            "NLP3_RELEASE_ROOT": str(tmp_path / "releases"),
            "NLP3_PROJECTS_ROOT": str(tmp_path / "projects"),
            "NLP3_LOCAL_STATE_ROOT": str(local_state),
        }
    )
    assert not local_state.exists()
    ensure_operational_directories(paths)
    assert paths.log_root.is_dir()
    assert not paths.backup_root.exists()
    assert not paths.release_root.exists()
    assert not paths.user_projects_root.exists()


def test_default_roots_belong_to_product_line_3() -> None:
    paths = PathConfig.from_environment(
        {
            "USERPROFILE": "C:/Users/example",
            "LOCALAPPDATA": "C:/Users/example/AppData/Local",
        }
    )
    assert paths.backup_root == Path("D:/NLP_3_BACKUPS")
    assert paths.release_root == Path("D:/NLP_3_RELEASES")
    assert paths.user_projects_root == Path("D:/NL_Project_3_Data/Projects")
    assert paths.local_state_root == Path("C:/Users/example/AppData/Local/NL Project 3.0")
    assert DEFAULT_DATABASE_NAME == "nl_project_3.sqlite"


def test_legacy_nlp2_environment_does_not_redirect_product_line_3(tmp_path: Path) -> None:
    paths = PathConfig.from_environment(
        {
            "USERPROFILE": str(tmp_path / "user"),
            "LOCALAPPDATA": str(tmp_path / "local"),
            "NLP2_BACKUP_ROOT": str(tmp_path / "legacy-backups"),
            "NLP2_RELEASE_ROOT": str(tmp_path / "legacy-releases"),
            "NLP2_PROJECTS_ROOT": str(tmp_path / "legacy-projects"),
            "NLP2_LOCAL_STATE_ROOT": str(tmp_path / "legacy-state"),
            "NLP3_PROJECTS_ROOT": str(tmp_path / "projects-3"),
        }
    )
    assert paths.user_projects_root == tmp_path / "projects-3"
    assert paths.backup_root == Path("D:/NLP_3_BACKUPS")
    assert paths.release_root == Path("D:/NLP_3_RELEASES")
    assert paths.local_state_root == tmp_path / "local" / "NL Project 3.0"
