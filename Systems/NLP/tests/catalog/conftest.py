from __future__ import annotations

from pathlib import Path

import pytest

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_payload
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def database(tmp_path):
    handle = DatabaseManager().initialize_new(tmp_path / "project.sqlite")
    try:
        yield handle
    finally:
        handle.close()


@pytest.fixture
def catalog_dir(project_root: Path) -> Path:
    return project_root / "resources" / "catalogs"


@pytest.fixture
def installed_catalog(database, catalog_dir):
    receipt = CatalogInstaller(database.engine).install(load_payload(catalog_dir))
    return receipt


@pytest.fixture
def project_id(database, installed_catalog):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=identifier,
                project_code="TEST-008",
                name="TASK 008 test project",
                card_fields_json={},
                active_catalog_release_id=installed_catalog.release_id,
                lifecycle="ACTIVE",
            )
        )
    return identifier
