from __future__ import annotations

from pathlib import Path

import pytest

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_payload
from nl_project_2.persistence.database import DatabaseManager


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def database(tmp_path, project_root):
    handle = DatabaseManager().initialize_new(tmp_path / "objects.sqlite")
    CatalogInstaller(handle.engine).install(load_payload(project_root / "resources" / "catalogs"))
    try:
        yield handle
    finally:
        handle.close()
