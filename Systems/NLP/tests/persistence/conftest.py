from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from nl_project_2.persistence.database import DatabaseHandle, DatabaseManager


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def database(tmp_path) -> Iterator[DatabaseHandle]:
    handle = DatabaseManager().initialize_new(tmp_path / "project.sqlite")
    try:
        yield handle
    finally:
        handle.close()
