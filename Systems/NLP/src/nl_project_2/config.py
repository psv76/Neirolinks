"""Side-effect-free path configuration for the independent 2.0 application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nl_project_2.runtime_resources import application_root


@dataclass(frozen=True, slots=True)
class PathConfig:
    app_root: Path
    backup_root: Path
    release_root: Path
    user_projects_root: Path
    local_state_root: Path

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> PathConfig:
        env = os.environ if environment is None else environment
        app_root = application_root()
        user_profile = Path(env.get("USERPROFILE", str(Path.home())))
        local_app_data = Path(env.get("LOCALAPPDATA", user_profile / "AppData" / "Local"))
        return cls(
            app_root=app_root,
            backup_root=Path(env.get("NLP2_BACKUP_ROOT", "D:/NLP_2_BACKUPS")),
            release_root=Path(env.get("NLP2_RELEASE_ROOT", "D:/NLP_2_RELEASES")),
            user_projects_root=Path(
                env.get(
                    "NLP2_PROJECTS_ROOT", user_profile / "Documents" / "NL Project 2.0" / "Projects"
                )
            ),
            local_state_root=Path(
                env.get("NLP2_LOCAL_STATE_ROOT", local_app_data / "NL Project 2.0")
            ),
        )

    @property
    def log_root(self) -> Path:
        return self.local_state_root / "logs"


def ensure_operational_directories(paths: PathConfig) -> None:
    """Create only application-owned operational paths, never a project database."""
    paths.log_root.mkdir(parents=True, exist_ok=True)
